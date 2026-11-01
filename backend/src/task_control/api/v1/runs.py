from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from task_control.api.deps import AuthContext, require_csrf, require_roles
from task_control.api.errors import correlation_id
from task_control.api.schemas import (
    AttemptOut,
    RunCreate,
    RunDetail,
    RunList,
    RunLiveOutput,
    RunOut,
)
from task_control.application.runs import service
from task_control.domain.enums import Role
from task_control.domain.errors import ForbiddenError, NotFoundError
from task_control.infrastructure.db.models import (
    TaskAttempt,
    TaskDefinition,
    TaskDefinitionVersion,
    TaskRun,
)
from task_control.infrastructure.db.session import get_db
from task_control.infrastructure.executors.output import (
    STDERR_NAME,
    STDOUT_NAME,
    attempt_dir,
    read_tail,
    tail_text,
)

router = APIRouter(prefix="/runs", tags=["runs"])


def _run_out(run: TaskRun) -> RunOut:
    return RunOut(
        id=run.id,
        definition_id=run.definition_id,
        definition_version_id=run.definition_version_id,
        schedule_id=run.schedule_id,
        scheduled_for=run.scheduled_for,
        trigger_type=run.trigger_type,
        status=run.status,
        arguments=list((run.parameters_redacted or {}).get("__arguments__", [])),
        parameters=run.parameters_redacted,
        attempt_count=run.attempt_count,
        max_attempts=run.max_attempts,
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        next_retry_at=run.next_retry_at,
        parent_run_id=run.parent_run_id,
        error_code=run.error_code,
        error_message=run.error_message,
        result_summary=run.result_summary,
        created_at=run.created_at,
        updated_at=run.updated_at,
        version=run.version,
    )


def _attempt_out(attempt: TaskAttempt) -> AttemptOut:
    return AttemptOut.model_validate(attempt)


@router.get("", response_model=RunList)
def list_runs(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.OPERATOR, Role.VIEWER))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    definition_id: UUID | None = None,
    status: str | None = None,
) -> RunList:
    items, total = service.list_runs(
        db, page=page, page_size=page_size, definition_id=definition_id, status=status
    )
    total_pages = (total + page_size - 1) // page_size
    return RunList(
        items=[_run_out(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("", response_model=RunOut, status_code=201)
def create_run(
    payload: RunCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> RunOut:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        raise ForbiddenError("insufficient role")
    run = service.create_run(
        db,
        ctx.user,
        payload,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id(request),
    )
    db.commit()
    return _run_out(run)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.OPERATOR, Role.VIEWER))],
) -> RunDetail:
    run = service.get_run(db, run_id)
    base = _run_out(run)
    definition = db.get(TaskDefinition, run.definition_id)
    version = db.get(TaskDefinitionVersion, run.definition_version_id)
    return RunDetail(
        **base.model_dump(),
        definition_key=definition.key if definition else None,
        definition_name=definition.name if definition else None,
        definition_version_no=version.version_no if version else None,
        executor_type=version.executor_type if version else None,
        executor_config=version.executor_config if version else None,
        parameter_schema=version.parameter_schema if version else None,
        timeout_seconds=version.timeout_seconds if version else None,
        attempts=[_attempt_out(item) for item in service.attempts_for(db, run_id)],
    )


@router.get("/{run_id}/live-output", response_model=RunLiveOutput)
def get_live_output(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.OPERATOR, Role.VIEWER))],
    attempt_no: int | None = Query(default=None, ge=1),
    max_bytes: int = Query(default=256 * 1024, ge=1024, le=4 * 1024 * 1024),
) -> RunLiveOutput:
    run = service.get_run(db, run_id)
    attempts = service.attempts_for(db, run_id)
    if not attempts:
        raise NotFoundError("run has no attempts yet")
    attempt = None
    if attempt_no is None:
        attempt = attempts[-1]
    else:
        attempt = next((item for item in attempts if item.attempt_no == attempt_no), None)
    if attempt is None:
        raise NotFoundError("attempt not found")

    directory = attempt_dir(str(run.id), attempt.attempt_no)
    stdout, stdout_bytes, stdout_truncated = read_tail(directory / STDOUT_NAME, max_bytes)
    stderr, stderr_bytes, stderr_truncated = read_tail(directory / STDERR_NAME, max_bytes)
    if not stdout and attempt.stdout_excerpt:
        stdout, stdout_bytes, stdout_truncated = tail_text(attempt.stdout_excerpt, max_bytes)
    if not stderr and attempt.stderr_excerpt:
        stderr, stderr_bytes, stderr_truncated = tail_text(attempt.stderr_excerpt, max_bytes)

    return RunLiveOutput(
        run_id=run.id,
        attempt_no=attempt.attempt_no,
        status=attempt.status,
        running=attempt.status == "running",
        stdout=stdout,
        stderr=stderr,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


@router.post("/{run_id}/retry", response_model=RunOut, status_code=201)
def retry_run(
    run_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> RunOut:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        raise ForbiddenError("insufficient role")
    run = service.get_run(db, run_id)
    new_run = service.retry_run(
        db,
        ctx.user,
        run,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id(request),
    )
    db.commit()
    return _run_out(new_run)


@router.post("/{run_id}/cancel", response_model=RunOut)
def cancel_run(
    run_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
) -> RunOut:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        raise ForbiddenError("insufficient role")
    run = service.get_run(db, run_id)
    service.cancel_run(db, ctx.user, run, correlation_id=correlation_id(request))
    db.commit()
    return _run_out(run)
