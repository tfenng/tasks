from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from task_control.api.deps import AuthContext, require_csrf, require_roles
from task_control.api.errors import correlation_id
from task_control.api.schemas import (
    CredentialCreate,
    CredentialList,
    CredentialOut,
    CredentialUpdate,
    TargetCreate,
    TargetList,
    TargetOut,
    TargetUpdate,
)
from task_control.application.targets import service
from task_control.domain.enums import Role
from task_control.domain.errors import (
    ConflictError,
    ForbiddenError,
    PreconditionRequiredError,
    ValidationError,
)
from task_control.infrastructure.db.models import Credential
from task_control.infrastructure.db.session import get_db

router = APIRouter(tags=["targets"])


def _expected_version(value: str | None) -> int:
    if value is None:
        raise PreconditionRequiredError("If-Match header is required")
    try:
        return int(value.strip().strip('"'))
    except ValueError as exc:
        raise ValidationError("If-Match must be a version number") from exc


def _credential_out(credential: Credential) -> CredentialOut:
    return CredentialOut(
        id=credential.id,
        name=credential.name,
        kind=credential.kind,
        metadata=credential.metadata_json,
        is_active=credential.is_active,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
        version=credential.version,
    )


@router.get("/execution-targets", response_model=TargetList)
def list_targets(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    type_filter: str | None = Query(default=None, alias="type"),
) -> TargetList:
    items, total = service.list_targets(db, page=page, page_size=page_size, type_filter=type_filter)
    return TargetList(
        items=[TargetOut.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/execution-targets", response_model=TargetOut, status_code=201)
def create_target(
    payload: TargetCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
) -> TargetOut:
    if ctx.user.role != Role.ADMIN.value:
        raise ForbiddenError("admin role required")
    target = service.create_target(db, ctx.user, payload, correlation_id=correlation_id(request))
    db.commit()
    return TargetOut.model_validate(target)


@router.patch("/execution-targets/{target_id}", response_model=TargetOut)
def update_target(
    target_id: UUID,
    payload: TargetUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> TargetOut:
    if ctx.user.role != Role.ADMIN.value:
        raise ForbiddenError("admin role required")
    target = service.get_target(db, target_id)
    if target.version != _expected_version(if_match):
        raise ConflictError("target version conflict")
    service.update_target(
        db, ctx.user, target, payload, target.version, correlation_id=correlation_id(request)
    )
    db.commit()
    return TargetOut.model_validate(target)


@router.delete("/execution-targets/{target_id}", status_code=204)
def delete_target(
    target_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> Response:
    if ctx.user.role != Role.ADMIN.value:
        raise ForbiddenError("admin role required")
    target = service.get_target(db, target_id)
    service.delete_target(
        db, ctx.user, target, _expected_version(if_match), correlation_id=correlation_id(request)
    )
    db.commit()
    return Response(status_code=204)


@router.get("/credentials", response_model=CredentialList)
def list_credentials(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> CredentialList:
    items, total = service.list_credentials(db, page=page, page_size=page_size)
    return CredentialList(
        items=[_credential_out(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/credentials", response_model=CredentialOut, status_code=201)
def create_credential(
    payload: CredentialCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
) -> CredentialOut:
    if ctx.user.role != Role.ADMIN.value:
        raise ForbiddenError("admin role required")
    credential = service.create_credential(
        db, ctx.user, payload, correlation_id=correlation_id(request)
    )
    db.commit()
    return _credential_out(credential)


@router.delete("/credentials/{credential_id}", status_code=204)
def delete_credential(
    credential_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> Response:
    if ctx.user.role != Role.ADMIN.value:
        raise ForbiddenError("admin role required")
    credential = service.get_credential(db, credential_id)
    service.delete_credential(
        db,
        ctx.user,
        credential,
        _expected_version(if_match),
        correlation_id=correlation_id(request),
    )
    db.commit()
    return Response(status_code=204)


@router.patch("/credentials/{credential_id}", response_model=CredentialOut)
def update_credential(
    credential_id: UUID,
    payload: CredentialUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> CredentialOut:
    if ctx.user.role != Role.ADMIN.value:
        raise ForbiddenError("admin role required")
    credential = service.get_credential(db, credential_id)
    if credential.version != _expected_version(if_match):
        raise ConflictError("credential version conflict")
    service.update_credential(
        db,
        ctx.user,
        credential,
        payload,
        credential.version,
        correlation_id=correlation_id(request),
    )
    db.commit()
    return _credential_out(credential)
