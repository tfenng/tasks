from __future__ import annotations

import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from task_control.api.deps import AuthContext, require_csrf, require_roles
from task_control.api.errors import correlation_id
from task_control.api.schemas import (
    PasswordResetResponse,
    UserCreate,
    UserList,
    UserOut,
    UserUpdate,
)
from task_control.application.audit.service import record_audit
from task_control.domain.enums import Role
from task_control.domain.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PreconditionRequiredError,
    ValidationError,
)
from task_control.infrastructure.db.models import User
from task_control.infrastructure.db.session import get_db
from task_control.infrastructure.security.passwords import hash_password

router = APIRouter(prefix="/users", tags=["users"])


def _expected_version(value: str | None) -> int:
    if value is None:
        raise PreconditionRequiredError("If-Match header is required")
    try:
        return int(value.strip().strip('"'))
    except ValueError as exc:
        raise ValidationError("If-Match must be a version number") from exc


@router.get("", response_model=UserList)
def list_users(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> UserList:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    users = list(
        db.scalars(
            select(User)
            .order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return UserList(
        items=[UserOut.model_validate(user) for user in users],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
) -> UserOut:
    if ctx.user.role != Role.ADMIN.value:
        raise ForbiddenError("admin role required")
    existing = db.scalar(select(User).where(func.lower(User.username) == payload.username.lower()))
    if existing is not None:
        raise ConflictError("username already exists")
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        must_change_password=True,
    )
    db.add(user)
    record_audit(
        db,
        ctx.user,
        "user.create",
        "user",
        str(user.id),
        correlation_id=correlation_id(request),
        details={"role": user.role},
    )
    db.commit()
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> UserOut:
    if ctx.user.role != Role.ADMIN.value:
        raise ForbiddenError("admin role required")
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    if user.version != _expected_version(if_match):
        raise ConflictError("user version conflict")
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    user.version += 1
    record_audit(
        db,
        ctx.user,
        "user.update",
        "user",
        str(user.id),
        correlation_id=correlation_id(request),
    )
    db.commit()
    return UserOut.model_validate(user)


@router.post("/{user_id}/reset-password", response_model=PasswordResetResponse)
def reset_password(
    user_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
) -> PasswordResetResponse:
    if ctx.user.role != Role.ADMIN.value:
        raise ForbiddenError("admin role required")
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    temporary = secrets.token_urlsafe(12)
    user.password_hash = hash_password(temporary)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    user.version += 1
    record_audit(
        db,
        ctx.user,
        "user.reset_password",
        "user",
        str(user.id),
        correlation_id=correlation_id(request),
    )
    db.commit()
    return PasswordResetResponse(temporary_password=temporary)
