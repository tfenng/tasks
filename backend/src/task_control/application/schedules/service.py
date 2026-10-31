from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from croniter import croniter
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from task_control.api.schemas import ScheduleCreate, ScheduleUpdate
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
from task_control.infrastructure.db.models import Schedule, TaskDefinitionVersion, TaskRun, User
from task_control.infrastructure.security.secrets import encrypt_parameters


def compute_next_fire(
    trigger_type: str,
    *,
    fire_at: datetime | None,
    cron_expr: str | None,
    interval_seconds: int | None,
    tz_name: str,
    after: datetime,
) -> datetime | None:
    try:
        zone = ZoneInfo(tz_name)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"invalid timezone: {tz_name}") from exc
    after = after.astimezone(UTC)
    if trigger_type == "once":
        return fire_at if fire_at and fire_at > after else None
    if trigger_type == "interval":
        if interval_seconds is None or interval_seconds < 10:
            raise ValidationError("interval must be at least 10 seconds")
        return after + timedelta(seconds=interval_seconds)
    if trigger_type == "cron":
        if not cron_expr:
            raise ValidationError("cron expression is required")
        try:
            base = after.astimezone(zone)
            next_value = croniter(cron_expr, base).get_next(datetime)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError("invalid cron expression") from exc
        return next_value.astimezone(UTC)
    raise ValidationError("unsupported trigger type")


def _validate_and_encrypt(
    db: Session,
    payload: ScheduleCreate,
    version: TaskDefinitionVersion,
    schedule_id: UUID,
) -> tuple[dict, dict]:
    parameters = payload.parameters
    try:
        validate_parameters(version.parameter_schema, parameters)
    except ParameterValidationError as exc:
        raise ValidationError("invalid parameters", details=exc.errors) from exc
    encrypted = encrypt_parameters(
        version.parameter_schema, parameters, run_id=f"schedule:{schedule_id}"
    )
    redacted = redact_parameters(version.parameter_schema, parameters)
    return encrypted, redacted


def create_schedule(
    db: Session, actor: User, payload: ScheduleCreate, *, correlation_id: str = "-"
) -> Schedule:
    definition = get_definition(db, payload.definition_id)
    if definition.is_archived:
        raise DefinitionDisabledError("definition is archived")
    version = active_version(db, definition, payload.definition_version_id)
    schedule_id = uuid4()
    if payload.arguments:
        encrypted = {"__arguments__": list(payload.arguments)}
        redacted = encrypted
    else:
        encrypted, redacted = _validate_and_encrypt(db, payload, version, schedule_id)
    now = datetime.now(UTC)
    if payload.trigger.type == "once":
        # 一次性调度不选时间，或选了已经过去的时间，都在创建后立即触发。
        fire_at = payload.trigger.fire_at
        next_fire = fire_at if fire_at is not None and fire_at > now else now
    else:
        next_fire = compute_next_fire(
            payload.trigger.type,
            fire_at=payload.trigger.fire_at,
            cron_expr=payload.trigger.cron_expr,
            interval_seconds=payload.trigger.interval_seconds,
            tz_name=payload.timezone,
            after=now,
        )
    schedule = Schedule(
        id=schedule_id,
        definition_id=definition.id,
        definition_version_id=version.id,
        name=payload.name,
        trigger_type=payload.trigger.type,
        fire_at=payload.trigger.fire_at,
        cron_expr=payload.trigger.cron_expr,
        interval_seconds=payload.trigger.interval_seconds,
        timezone=payload.timezone,
        parameters=encrypted,
        parameters_redacted=redacted,
        overlap_policy=payload.overlap_policy,
        misfire_grace_seconds=payload.misfire_grace_seconds,
        status="active",
        next_fire_at=next_fire,
        created_by=actor.id,
    )
    db.add(schedule)
    record_audit(
        db,
        actor,
        "schedule.create",
        "schedule",
        str(schedule.id),
        correlation_id=correlation_id,
        details={"definition_id": str(definition.id)},
    )
    db.flush()
    return schedule


def get_schedule(db: Session, schedule_id: UUID) -> Schedule:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise NotFoundError("schedule not found")
    return schedule


def list_schedules(
    db: Session,
    *,
    page: int,
    page_size: int,
    definition_id: UUID | None = None,
    status: str | None = None,
) -> tuple[list[Schedule], int]:
    stmt = select(Schedule)
    count_stmt = select(func.count()).select_from(Schedule)
    if definition_id:
        stmt = stmt.where(Schedule.definition_id == definition_id)
        count_stmt = count_stmt.where(Schedule.definition_id == definition_id)
    if status:
        stmt = stmt.where(Schedule.status == status)
        count_stmt = count_stmt.where(Schedule.status == status)
    total = db.scalar(count_stmt) or 0
    items = list(
        db.scalars(
            stmt.order_by(Schedule.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


def update_schedule(
    db: Session,
    actor: User,
    schedule: Schedule,
    payload: ScheduleUpdate,
    expected_version: int,
    *,
    correlation_id: str = "-",
) -> Schedule:
    if schedule.version != expected_version:
        raise ConflictError("schedule version conflict")
    if payload.name is not None:
        schedule.name = payload.name
    if payload.overlap_policy is not None:
        schedule.overlap_policy = payload.overlap_policy
    if payload.misfire_grace_seconds is not None:
        schedule.misfire_grace_seconds = payload.misfire_grace_seconds
    if payload.parameters is not None:
        version = db.get(TaskDefinitionVersion, schedule.definition_version_id)
        if version is None:
            raise NotFoundError("definition version not found")
        schedule_id = schedule.id
        encrypted, redacted = _validate_and_encrypt(
            db,
            ScheduleCreate(
                definition_id=schedule.definition_id,
                definition_version_id=schedule.definition_version_id,
                name=schedule.name,
                trigger={
                    "type": schedule.trigger_type,
                    "fire_at": schedule.fire_at,
                    "cron_expr": schedule.cron_expr,
                    "interval_seconds": schedule.interval_seconds,
                },
                timezone=schedule.timezone,
                parameters=payload.parameters,
            ),
            version,
            schedule_id,
        )
        schedule.parameters = encrypted
        schedule.parameters_redacted = redacted
    schedule.version += 1
    schedule.updated_at = datetime.now(UTC)
    record_audit(
        db,
        actor,
        "schedule.update",
        "schedule",
        str(schedule.id),
        correlation_id=correlation_id,
    )
    return schedule


def pause_schedule(
    db: Session, actor: User, schedule: Schedule, *, correlation_id: str = "-"
) -> Schedule:
    if schedule.status != "active":
        raise InvalidStateError("schedule is not active")
    schedule.status = "paused"
    schedule.next_fire_at = None
    schedule.version += 1
    record_audit(
        db, actor, "schedule.pause", "schedule", str(schedule.id), correlation_id=correlation_id
    )
    return schedule


def resume_schedule(
    db: Session, actor: User, schedule: Schedule, *, correlation_id: str = "-"
) -> Schedule:
    if schedule.status != "paused":
        raise InvalidStateError("schedule is not paused")
    next_fire = compute_next_fire(
        schedule.trigger_type,
        fire_at=schedule.fire_at,
        cron_expr=schedule.cron_expr,
        interval_seconds=schedule.interval_seconds,
        tz_name=schedule.timezone,
        after=datetime.now(UTC),
    )
    schedule.status = "active"
    schedule.next_fire_at = next_fire
    schedule.version += 1
    record_audit(
        db, actor, "schedule.resume", "schedule", str(schedule.id), correlation_id=correlation_id
    )
    return schedule


def cancel_schedule(
    db: Session, actor: User, schedule: Schedule, *, correlation_id: str = "-"
) -> Schedule:
    if schedule.status in {"completed", "cancelled"}:
        raise InvalidStateError("schedule is already terminal")
    schedule.status = "cancelled"
    schedule.next_fire_at = None
    schedule.version += 1
    record_audit(
        db, actor, "schedule.cancel", "schedule", str(schedule.id), correlation_id=correlation_id
    )
    return schedule


def create_run_from_schedule(
    db: Session,
    schedule: Schedule,
    *,
    scheduled_for: datetime,
    status: str,
    reason: str | None = None,
) -> TaskRun:
    version = db.get(TaskDefinitionVersion, schedule.definition_version_id)
    if version is None:
        raise NotFoundError("definition version not found")
    run_id = uuid4()
    # Schedule parameters are encrypted with AAD schedule:<id>; decrypt then
    # re-encrypt with the new run id so retries use an immutable run snapshot.
    from task_control.infrastructure.security.secrets import decrypt_parameters, encrypt_parameters

    plain = decrypt_parameters(
        version.parameter_schema, schedule.parameters, run_id=f"schedule:{schedule.id}"
    )
    encrypted = encrypt_parameters(version.parameter_schema, plain, run_id=str(run_id))
    retry_policy = version.retry_policy or {}
    run = TaskRun(
        id=run_id,
        definition_id=schedule.definition_id,
        definition_version_id=schedule.definition_version_id,
        target_snapshot=build_target_snapshot(db, version.executor_config),
        schedule_id=schedule.id,
        scheduled_for=scheduled_for,
        trigger_type=schedule.trigger_type,
        status=status,
        parameters=encrypted,
        parameters_redacted=schedule.parameters_redacted,
        queued_at=datetime.now(UTC) if status == "queued" else None,
        finished_at=datetime.now(UTC) if status in {"skipped", "missed", "failed"} else None,
        attempt_count=0,
        max_attempts=int(retry_policy.get("max_attempts", 1)),
        error_code="SCHEDULE_OVERLAP" if status == "skipped" else None,
        error_message=reason,
        created_by=schedule.created_by,
    )
    db.add(run)
    record_audit(
        db,
        None,
        "run.create",
        "task_run",
        str(run.id),
        details={
            "schedule_id": str(schedule.id),
            "status": status,
            "scheduled_for": scheduled_for.isoformat(),
        },
    )
    logger.bind(run_id=str(run.id), schedule_id=str(schedule.id), component="scheduler").info(
        "scheduled run created"
    )
    return run
