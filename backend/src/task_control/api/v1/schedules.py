from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from task_control.api.deps import AuthContext, require_csrf, require_roles
from task_control.api.errors import correlation_id
from task_control.api.schemas import ScheduleCreate, ScheduleList, ScheduleOut, ScheduleUpdate
from task_control.application.schedules import service
from task_control.domain.enums import Role
from task_control.domain.errors import (
    ConflictError,
    ForbiddenError,
    PreconditionRequiredError,
    ValidationError,
)
from task_control.infrastructure.db.models import Schedule
from task_control.infrastructure.db.session import get_db

router = APIRouter(prefix="/schedules", tags=["schedules"])


def _expected_version(value: str | None) -> int:
    if value is None:
        raise PreconditionRequiredError("If-Match header is required")
    try:
        return int(value.strip().strip('"'))
    except ValueError as exc:
        raise ValidationError("If-Match must be a version number") from exc


def _out(schedule: Schedule) -> ScheduleOut:
    return ScheduleOut(
        id=schedule.id,
        definition_id=schedule.definition_id,
        definition_version_id=schedule.definition_version_id,
        name=schedule.name,
        trigger_type=schedule.trigger_type,
        fire_at=schedule.fire_at,
        cron_expr=schedule.cron_expr,
        interval_seconds=schedule.interval_seconds,
        timezone=schedule.timezone,
        arguments=list((schedule.parameters_redacted or {}).get("__arguments__", [])),
        parameters=schedule.parameters_redacted,
        overlap_policy=schedule.overlap_policy,
        misfire_grace_seconds=schedule.misfire_grace_seconds,
        status=schedule.status,
        next_fire_at=schedule.next_fire_at,
        last_fire_at=schedule.last_fire_at,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
        version=schedule.version,
    )


@router.get("", response_model=ScheduleList)
def list_schedules(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.OPERATOR, Role.VIEWER))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    definition_id: UUID | None = None,
    status: str | None = None,
) -> ScheduleList:
    items, total = service.list_schedules(
        db, page=page, page_size=page_size, definition_id=definition_id, status=status
    )
    total_pages = (total + page_size - 1) // page_size
    return ScheduleList(
        items=[_out(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("", response_model=ScheduleOut, status_code=201)
def create_schedule(
    payload: ScheduleCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
) -> ScheduleOut:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        raise ForbiddenError("insufficient role")
    schedule = service.create_schedule(
        db, ctx.user, payload, correlation_id=correlation_id(request)
    )
    db.commit()
    return _out(schedule)


@router.get("/{schedule_id}", response_model=ScheduleOut)
def get_schedule(
    schedule_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.OPERATOR, Role.VIEWER))],
) -> ScheduleOut:
    return _out(service.get_schedule(db, schedule_id))


@router.patch("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: UUID,
    payload: ScheduleUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ScheduleOut:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        raise ForbiddenError("insufficient role")
    schedule = service.get_schedule(db, schedule_id)
    if schedule.version != _expected_version(if_match):
        raise ConflictError("schedule version conflict")
    service.update_schedule(
        db,
        ctx.user,
        schedule,
        payload,
        schedule.version,
        correlation_id=correlation_id(request),
    )
    db.commit()
    return _out(schedule)


def _action(
    db: Session,
    ctx: AuthContext,
    schedule_id: UUID,
    action: str,
    if_match: str | None,
    correlation_id_value: str,
) -> ScheduleOut:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        raise ForbiddenError("insufficient role")
    schedule = service.get_schedule(db, schedule_id)
    if schedule.version != _expected_version(if_match):
        raise ConflictError("schedule version conflict")
    getattr(service, action)(db, ctx.user, schedule, correlation_id=correlation_id_value)
    db.commit()
    return _out(schedule)


@router.post("/{schedule_id}/pause", response_model=ScheduleOut)
def pause_schedule(
    schedule_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ScheduleOut:
    return _action(db, ctx, schedule_id, "pause_schedule", if_match, correlation_id(request))


@router.post("/{schedule_id}/resume", response_model=ScheduleOut)
def resume_schedule(
    schedule_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ScheduleOut:
    return _action(db, ctx, schedule_id, "resume_schedule", if_match, correlation_id(request))


@router.post("/{schedule_id}/cancel", response_model=ScheduleOut)
def cancel_schedule(
    schedule_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> ScheduleOut:
    return _action(db, ctx, schedule_id, "cancel_schedule", if_match, correlation_id(request))
