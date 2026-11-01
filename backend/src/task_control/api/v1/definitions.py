from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from task_control.api.deps import AuthContext, require_csrf, require_roles
from task_control.api.errors import correlation_id
from task_control.api.schemas import (
    DefinitionCreate,
    DefinitionDeleteResult,
    DefinitionList,
    DefinitionOut,
    DefinitionUpdate,
    VersionOut,
)
from task_control.application.definitions import service
from task_control.domain.enums import Role
from task_control.domain.errors import PreconditionRequiredError, ValidationError
from task_control.infrastructure.db.models import TaskDefinition, TaskDefinitionVersion
from task_control.infrastructure.db.session import get_db

router = APIRouter(prefix="/task-definitions", tags=["definitions"])


def _expected_version(value: str | None) -> int:
    if value is None:
        raise PreconditionRequiredError("If-Match header is required")
    cleaned = value.strip().strip('"')
    try:
        version = int(cleaned)
    except ValueError as exc:
        raise ValidationError("If-Match must be a version number") from exc
    if version < 1:
        raise ValidationError("If-Match must be positive")
    return version


def _serialize(db: Session, definition: TaskDefinition) -> DefinitionOut:
    version = (
        db.get(TaskDefinitionVersion, definition.active_version_id)
        if definition.active_version_id
        else None
    )
    return DefinitionOut(
        id=definition.id,
        key=definition.key,
        name=definition.name,
        description=definition.description,
        is_archived=definition.is_archived,
        active_version=VersionOut.model_validate(version) if version else None,
        created_at=definition.created_at,
        updated_at=definition.updated_at,
        version=definition.version,
    )


@router.get("", response_model=DefinitionList)
def list_definitions(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.OPERATOR, Role.VIEWER))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = None,
    archived: bool | None = None,
) -> DefinitionList:
    items, total = service.list_definitions(
        db, page=page, page_size=page_size, q=q, archived=archived
    )
    total_pages = (total + page_size - 1) // page_size
    return DefinitionList(
        items=[_serialize(db, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@router.post("", response_model=DefinitionOut, status_code=201)
def create_definition(
    payload: DefinitionCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
) -> DefinitionOut:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        from task_control.domain.errors import ForbiddenError

        raise ForbiddenError("insufficient role")
    definition = service.create_definition(
        db, ctx.user, payload, correlation_id=correlation_id(request)
    )
    db.commit()
    return _serialize(db, definition)


@router.get("/{definition_id}", response_model=DefinitionOut)
def get_definition(
    definition_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.OPERATOR, Role.VIEWER))],
) -> DefinitionOut:
    return _serialize(db, service.get_definition(db, definition_id))


@router.patch("/{definition_id}", response_model=DefinitionOut)
def update_definition(
    definition_id: UUID,
    payload: DefinitionUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> DefinitionOut:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        from task_control.domain.errors import ForbiddenError

        raise ForbiddenError("insufficient role")
    definition = service.update_definition(
        db,
        ctx.user,
        definition_id,
        payload,
        _expected_version(if_match),
        correlation_id=correlation_id(request),
    )
    db.commit()
    return _serialize(db, definition)


@router.post("/{definition_id}/enable", response_model=DefinitionOut)
def enable_definition(
    definition_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> DefinitionOut:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        from task_control.domain.errors import ForbiddenError

        raise ForbiddenError("insufficient role")
    definition = service.get_definition(db, definition_id)
    if definition.version != _expected_version(if_match):
        from task_control.domain.errors import ConflictError

        raise ConflictError("definition version conflict")
    service.set_enabled(
        db, ctx.user, definition, enabled=True, correlation_id=correlation_id(request)
    )
    db.commit()
    return _serialize(db, definition)


@router.post("/{definition_id}/disable", response_model=DefinitionOut)
def disable_definition(
    definition_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> DefinitionOut:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        from task_control.domain.errors import ForbiddenError

        raise ForbiddenError("insufficient role")
    definition = service.get_definition(db, definition_id)
    if definition.version != _expected_version(if_match):
        from task_control.domain.errors import ConflictError

        raise ConflictError("definition version conflict")
    service.set_enabled(
        db, ctx.user, definition, enabled=False, correlation_id=correlation_id(request)
    )
    db.commit()
    return _serialize(db, definition)


@router.post("/{definition_id}/archive", response_model=DefinitionOut)
def archive_definition(
    definition_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> DefinitionOut:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        from task_control.domain.errors import ForbiddenError

        raise ForbiddenError("insufficient role")
    definition = service.get_definition(db, definition_id)
    if definition.version != _expected_version(if_match):
        from task_control.domain.errors import ConflictError

        raise ConflictError("definition version conflict")
    service.archive_definition(db, ctx.user, definition, correlation_id=correlation_id(request))
    db.commit()
    return _serialize(db, definition)


@router.delete("/{definition_id}", response_model=DefinitionDeleteResult)
def delete_definition(
    definition_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    delete_runs: bool = Query(default=False),
) -> DefinitionDeleteResult:
    if ctx.user.role not in {Role.ADMIN.value, Role.OPERATOR.value}:
        from task_control.domain.errors import ForbiddenError

        raise ForbiddenError("insufficient role")
    definition = service.get_definition(db, definition_id)
    deleted_runs = service.delete_definition(
        db,
        ctx.user,
        definition,
        delete_runs=delete_runs,
        correlation_id=correlation_id(request),
    )
    db.commit()
    return DefinitionDeleteResult(archived=True, deleted_runs=deleted_runs)
