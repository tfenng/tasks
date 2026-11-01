from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from task_control.api.schemas import DefinitionCreate, DefinitionUpdate
from task_control.application.audit.service import record_audit
from task_control.domain.errors import (
    ConflictError,
    DefinitionDisabledError,
    NotFoundError,
    ValidationError,
)
from task_control.domain.parameters import ParameterValidationError, validate_schema
from task_control.infrastructure.db.models import (
    Schedule,
    TaskDefinition,
    TaskDefinitionRuntime,
    TaskDefinitionVersion,
    TaskRun,
    User,
)
from task_control.infrastructure.executors.output import cleanup_run_output


def _checksum(payload: dict) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_executor_config(executor_type: str, config: dict) -> None:
    if not isinstance(config, dict):
        raise ValidationError("executor_config must be an object")
    if executor_type == "local":
        argv = config.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(item, str) for item in argv)
        ):
            raise ValidationError("local executor requires a non-empty argv string array")
        if "env" in config and not isinstance(config["env"], dict):
            raise ValidationError("executor_config.env must be an object")
        if "cwd" in config and not isinstance(config["cwd"], str):
            raise ValidationError("executor_config.cwd must be a string")
        return
    if not config.get("target_id"):
        raise ValidationError(f"{executor_type} executor requires target_id")
    if executor_type == "ssh" and not config.get("command"):
        raise ValidationError("ssh executor requires command")
    if executor_type == "http":
        if not (config.get("path") or config.get("url")):
            raise ValidationError("http executor requires path or url")
        method = config.get("method", "GET")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
            raise ValidationError("unsupported http method")


def _version_payload(payload: DefinitionCreate) -> dict:
    version = payload.version
    try:
        validate_schema(version.parameter_schema)
    except (ParameterValidationError, Exception) as exc:  # noqa: BLE001
        if isinstance(exc, ParameterValidationError):
            raise ValidationError("invalid parameter schema", details=exc.errors) from exc
        raise ValidationError(f"invalid parameter schema: {exc}") from exc
    _validate_executor_config(version.executor_type, version.executor_config)
    return {
        "executor_type": version.executor_type,
        "parameter_schema": version.parameter_schema,
        "executor_config": version.executor_config,
        "timeout_seconds": version.timeout_seconds,
        "retry_policy": version.retry_policy.model_dump(),
        "max_concurrency": version.max_concurrency,
    }


def create_definition(
    db: Session, actor: User, payload: DefinitionCreate, *, correlation_id: str = "-"
) -> TaskDefinition:
    existing = db.scalar(select(TaskDefinition).where(TaskDefinition.key == payload.key))
    if existing is not None:
        raise ConflictError("definition key already exists")
    version_payload = _version_payload(payload)
    definition = TaskDefinition(
        key=payload.key,
        name=payload.name,
        description=payload.description,
        created_by=actor.id,
    )
    db.add(definition)
    db.flush()
    version = TaskDefinitionVersion(
        definition_id=definition.id,
        version_no=1,
        checksum=_checksum(version_payload),
        created_by=actor.id,
        **version_payload,
    )
    db.add(version)
    db.flush()
    definition.active_version_id = version.id
    runtime = TaskDefinitionRuntime(
        definition_id=definition.id,
        running_count=0,
        max_concurrency=version.max_concurrency,
    )
    db.add(runtime)
    record_audit(
        db,
        actor,
        "definition.create",
        "task_definition",
        str(definition.id),
        correlation_id=correlation_id,
        details={"key": definition.key, "version": 1},
    )
    db.flush()
    return definition


def update_definition(
    db: Session,
    actor: User,
    definition_id: UUID,
    payload: DefinitionUpdate,
    expected_version: int,
    *,
    correlation_id: str = "-",
) -> TaskDefinition:
    definition = get_definition(db, definition_id)
    if definition.version != expected_version:
        raise ConflictError("definition version conflict")
    if payload.name is not None:
        definition.name = payload.name
    if payload.description is not None:
        definition.description = payload.description
    if payload.version is not None:
        last = (
            db.scalar(
                select(func.max(TaskDefinitionVersion.version_no)).where(
                    TaskDefinitionVersion.definition_id == definition.id
                )
            )
            or 0
        )
        version_payload = _version_payload(
            DefinitionCreate(key=definition.key, name=definition.name, version=payload.version)
        )
        version = TaskDefinitionVersion(
            definition_id=definition.id,
            version_no=last + 1,
            checksum=_checksum(version_payload),
            created_by=actor.id,
            **version_payload,
        )
        db.add(version)
        db.flush()
        definition.active_version_id = version.id
        runtime = db.get(TaskDefinitionRuntime, definition.id)
        if runtime is not None:
            if version.max_concurrency < runtime.running_count:
                raise ConflictError("max_concurrency cannot be lower than running_count")
            runtime.max_concurrency = version.max_concurrency
    definition.version += 1
    definition.updated_at = datetime.now(UTC)
    record_audit(
        db,
        actor,
        "definition.update",
        "task_definition",
        str(definition.id),
        correlation_id=correlation_id,
    )
    db.flush()
    return definition


def get_definition(db: Session, definition_id: UUID) -> TaskDefinition:
    definition = db.get(TaskDefinition, definition_id)
    if definition is None:
        raise NotFoundError("definition not found")
    return definition


def list_definitions(
    db: Session, *, page: int, page_size: int, q: str | None = None, archived: bool | None = None
) -> tuple[list[TaskDefinition], int]:
    stmt = select(TaskDefinition)
    count_stmt = select(func.count()).select_from(TaskDefinition)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(TaskDefinition.name.ilike(pattern) | TaskDefinition.key.ilike(pattern))
        count_stmt = count_stmt.where(
            TaskDefinition.name.ilike(pattern) | TaskDefinition.key.ilike(pattern)
        )
    if archived is not None:
        stmt = stmt.where(TaskDefinition.is_archived == archived)
        count_stmt = count_stmt.where(TaskDefinition.is_archived == archived)
    total = db.scalar(count_stmt) or 0
    items = list(
        db.scalars(
            stmt.order_by(TaskDefinition.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


def set_enabled(
    db: Session,
    actor: User,
    definition: TaskDefinition,
    *,
    enabled: bool,
    correlation_id: str = "-",
) -> TaskDefinition:
    if definition.is_archived:
        raise DefinitionDisabledError("definition is archived")
    if enabled:
        definition.version += 1
        definition.updated_at = datetime.now(UTC)
        record_audit(
            db,
            actor,
            "definition.enable",
            "task_definition",
            str(definition.id),
            correlation_id=correlation_id,
        )
        return definition
    now = datetime.now(UTC)
    scheduled = list(
        db.scalars(
            select(TaskRun).where(
                TaskRun.definition_id == definition.id, TaskRun.status == "scheduled"
            )
        )
    )
    for run in scheduled:
        run.status = "cancelled"
        run.error_code = "DEFINITION_DISABLED"
        run.error_message = "definition disabled"
        run.finished_at = now
        run.version += 1
    paused = list(
        db.scalars(
            select(Schedule).where(
                Schedule.definition_id == definition.id, Schedule.status == "active"
            )
        )
    )
    for schedule in paused:
        schedule.status = "paused"
        schedule.next_fire_at = None
        schedule.version += 1
    definition.version += 1
    definition.updated_at = now
    record_audit(
        db,
        actor,
        "definition.disable",
        "task_definition",
        str(definition.id),
        correlation_id=correlation_id,
        details={"cancelled_scheduled_runs": len(scheduled), "paused_schedules": len(paused)},
    )
    return definition


def archive_definition(
    db: Session, actor: User, definition: TaskDefinition, *, correlation_id: str = "-"
) -> TaskDefinition:
    if definition.is_archived:
        return definition
    now = datetime.now(UTC)
    runs = list(
        db.scalars(
            select(TaskRun).where(
                TaskRun.definition_id == definition.id,
                TaskRun.status.in_(["scheduled", "queued", "retry_wait"]),
            )
        )
    )
    for run in runs:
        run.status = "cancelled"
        run.error_code = "DEFINITION_ARCHIVED"
        run.error_message = "definition archived"
        run.finished_at = now
        run.version += 1
    schedules = list(db.scalars(select(Schedule).where(Schedule.definition_id == definition.id)))
    for schedule in schedules:
        schedule.status = "cancelled"
        schedule.next_fire_at = None
        schedule.version += 1
    definition.is_archived = True
    definition.archived_at = now
    definition.version += 1
    record_audit(
        db,
        actor,
        "definition.archive",
        "task_definition",
        str(definition.id),
        correlation_id=correlation_id,
        details={"cancelled_runs": len(runs)},
    )
    return definition


def delete_definition(
    db: Session,
    actor: User,
    definition: TaskDefinition,
    *,
    delete_runs: bool = False,
    correlation_id: str = "-",
) -> int:
    running = (
        db.scalar(
            select(func.count())
            .select_from(TaskRun)
            .where(
                TaskRun.definition_id == definition.id,
                TaskRun.status == "running",
            )
        )
        or 0
    )
    if running:
        raise ConflictError("definition has running tasks; cancel them first")
    archive_definition(db, actor, definition, correlation_id=correlation_id)
    deleted_runs = 0
    if delete_runs:
        run_ids = list(db.scalars(select(TaskRun.id).where(TaskRun.definition_id == definition.id)))
        if run_ids:
            db.execute(delete(TaskRun).where(TaskRun.definition_id == definition.id))
            deleted_runs = len(run_ids)
            for run_id in run_ids:
                cleanup_run_output(str(run_id))
    record_audit(
        db,
        actor,
        "definition.delete",
        "task_definition",
        str(definition.id),
        correlation_id=correlation_id,
        details={"archived": True, "deleted_runs": deleted_runs},
    )
    return deleted_runs


def active_version(
    db: Session, definition: TaskDefinition, version_id: UUID | None = None
) -> TaskDefinitionVersion:
    if version_id is not None:
        version = db.get(TaskDefinitionVersion, version_id)
        if version is None or version.definition_id != definition.id:
            raise NotFoundError("definition version not found")
        return version
    if definition.active_version_id is None:
        raise NotFoundError("definition has no active version")
    version = db.get(TaskDefinitionVersion, definition.active_version_id)
    if version is None:
        raise NotFoundError("definition version not found")
    return version
