from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from task_control.api.schemas import RunCreate
from task_control.application.audit.service import record_audit
from task_control.application.definitions.service import active_version, get_definition
from task_control.application.targets.service import build_target_snapshot
from task_control.domain.errors import (
    ConflictError,
    DefinitionDisabledError,
    InvalidStateError,
    NotFoundError,
    ValidationError,
)
from task_control.domain.parameters import (
    ParameterValidationError,
    redact_parameters,
    validate_parameters,
)
from task_control.infrastructure.db.models import (
    TaskAttempt,
    TaskDefinitionVersion,
    TaskRun,
    User,
)
from task_control.infrastructure.security.secrets import (
    decrypt_parameters,
    encrypt_parameters,
)


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _apply_defaults(schema: dict, value: dict) -> dict:
    result = json.loads(json.dumps(value))
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return result
    for name, definition in properties.items():
        if name not in result and isinstance(definition, dict) and "default" in definition:
            result[name] = definition["default"]
    return result


def create_run(
    db: Session,
    actor: User,
    payload: RunCreate,
    *,
    idempotency_key: str | None = None,
    correlation_id: str = "-",
) -> TaskRun:
    definition = get_definition(db, payload.definition_id)
    if definition.is_archived:
        raise DefinitionDisabledError("definition is archived")
    version = active_version(db, definition, payload.definition_version_id)
    if payload.arguments:
        parameters = {"__arguments__": list(payload.arguments)}
        redacted = parameters
    else:
        parameters = _apply_defaults(version.parameter_schema, payload.parameters)
        try:
            validate_parameters(version.parameter_schema, parameters)
        except ParameterValidationError as exc:
            raise ValidationError("invalid parameters", details=exc.errors) from exc
        redacted = redact_parameters(version.parameter_schema, parameters)

    request_hash = _hash_payload(
        {
            "definition_id": str(payload.definition_id),
            "arguments": payload.arguments,
            "parameters": parameters,
        }
    )
    if idempotency_key:
        existing = db.scalar(
            select(TaskRun).where(
                TaskRun.created_by == actor.id, TaskRun.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            if existing.request_hash == request_hash:
                return existing
            raise ConflictError("idempotency key reused with a different payload")

    run_id = uuid4()
    if payload.arguments:
        encrypted = parameters
        redacted = parameters
    else:
        encrypted = encrypt_parameters(version.parameter_schema, parameters, run_id=str(run_id))
        redacted = redact_parameters(version.parameter_schema, parameters)
    retry_policy = version.retry_policy or {}
    run = TaskRun(
        id=run_id,
        definition_id=definition.id,
        definition_version_id=version.id,
        target_snapshot=build_target_snapshot(db, version.executor_config),
        trigger_type="immediate",
        status="queued",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        parameters=encrypted,
        parameters_redacted=redacted,
        queued_at=datetime.now(UTC),
        attempt_count=0,
        max_attempts=int(retry_policy.get("max_attempts", 1)),
        created_by=actor.id,
    )
    db.add(run)
    record_audit(
        db,
        actor,
        "run.create",
        "task_run",
        str(run.id),
        correlation_id=correlation_id,
        details={"definition_id": str(definition.id), "version": version.version_no},
    )
    db.flush()
    return run


def list_runs(
    db: Session,
    *,
    page: int,
    page_size: int,
    definition_id: UUID | None = None,
    status: str | None = None,
) -> tuple[list[TaskRun], int]:
    stmt = select(TaskRun)
    count_stmt = select(func.count()).select_from(TaskRun)
    if definition_id:
        stmt = stmt.where(TaskRun.definition_id == definition_id)
        count_stmt = count_stmt.where(TaskRun.definition_id == definition_id)
    if status:
        stmt = stmt.where(TaskRun.status == status)
        count_stmt = count_stmt.where(TaskRun.status == status)
    total = db.scalar(count_stmt) or 0
    items = list(
        db.scalars(
            stmt.order_by(TaskRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    return items, total


def get_run(db: Session, run_id: UUID) -> TaskRun:
    run = db.get(TaskRun, run_id)
    if run is None:
        raise NotFoundError("run not found")
    return run


def attempts_for(db: Session, run_id: UUID) -> list[TaskAttempt]:
    return list(
        db.scalars(
            select(TaskAttempt).where(TaskAttempt.run_id == run_id).order_by(TaskAttempt.attempt_no)
        )
    )


def retry_run(
    db: Session,
    actor: User,
    run: TaskRun,
    *,
    idempotency_key: str | None = None,
    correlation_id: str = "-",
) -> TaskRun:
    if run.status not in {"succeeded", "failed", "cancelled"}:
        raise InvalidStateError("run is not terminal")
    if idempotency_key:
        existing = db.scalar(
            select(TaskRun).where(
                TaskRun.created_by == actor.id, TaskRun.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return existing
    version = db.get(TaskDefinitionVersion, run.definition_version_id)
    if version is None:
        raise NotFoundError("definition version not found")
    plain = decrypt_parameters(version.parameter_schema, run.parameters, run_id=str(run.id))
    new_id = uuid4()
    encrypted = encrypt_parameters(version.parameter_schema, plain, run_id=str(new_id))
    retry_policy = version.retry_policy or {}
    new_run = TaskRun(
        id=new_id,
        definition_id=run.definition_id,
        definition_version_id=run.definition_version_id,
        target_snapshot=run.target_snapshot,
        trigger_type="immediate",
        status="queued",
        idempotency_key=idempotency_key,
        parameters=encrypted,
        parameters_redacted=run.parameters_redacted,
        queued_at=datetime.now(UTC),
        attempt_count=0,
        max_attempts=int(retry_policy.get("max_attempts", 1)),
        parent_run_id=run.id,
        created_by=actor.id,
    )
    db.add(new_run)
    record_audit(
        db,
        actor,
        "run.retry",
        "task_run",
        str(new_run.id),
        correlation_id=correlation_id,
        details={"parent_run_id": str(run.id)},
    )
    db.flush()
    return new_run


def cancel_run(db: Session, actor: User, run: TaskRun, *, correlation_id: str = "-") -> TaskRun:
    if run.status in {"succeeded", "failed", "cancelled", "skipped", "missed"}:
        raise InvalidStateError("run is already terminal")
    now = datetime.now(UTC)
    if run.status in {"scheduled", "queued", "retry_wait"}:
        run.status = "cancelled"
        run.finished_at = now
    else:
        run.cancel_requested_at = now
        run.cancel_requested_by = actor.id
    run.version += 1
    record_audit(
        db,
        actor,
        "run.cancel",
        "task_run",
        str(run.id),
        correlation_id=correlation_id,
    )
    return run
