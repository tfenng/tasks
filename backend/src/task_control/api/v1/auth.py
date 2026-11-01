from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from task_control.api.deps import AuthContext, client_meta, get_auth_context, require_csrf
from task_control.api.errors import correlation_id
from task_control.api.rate_limit import limiter
from task_control.api.schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenList,
    ApiTokenOut,
    LoginRequest,
    LoginResponse,
    PasswordChange,
    SessionList,
    SessionOut,
    UserOut,
)
from task_control.application.audit.service import record_audit
from task_control.config import get_settings
from task_control.domain.errors import (
    AccountLockedError,
    InvalidCredentialsError,
    NotFoundError,
    RateLimitedError,
)
from task_control.infrastructure.db.models import ApiToken, User
from task_control.infrastructure.db.models import Session as SessionModel
from task_control.infrastructure.db.session import get_db
from task_control.infrastructure.security.passwords import hash_password, verify_password
from task_control.infrastructure.security.sessions import (
    create_session,
    revoke_session,
    session_ttl_seconds,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_hash(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("utf-8")).digest()


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> LoginResponse:
    settings = get_settings()
    ip_address = client_meta(request)[0] or "unknown"
    if not limiter.allow(f"login:{ip_address}:{payload.username.lower()}", 10, 60):
        raise RateLimitedError("too many login attempts", retry_after=60)
    user = db.scalar(select(User).where(func.lower(User.username) == payload.username.lower()))
    now = datetime.now(UTC)
    if user is not None and user.locked_until is not None and user.locked_until > now:
        raise AccountLockedError("account is locked")
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until = now + timedelta(minutes=15)
            record_audit(
                db,
                user,
                "auth.login",
                "user",
                str(user.id),
                outcome="failure",
                correlation_id=correlation_id(request),
                ip_address=client_meta(request)[0],
                user_agent=client_meta(request)[1],
            )
            db.commit()
        raise InvalidCredentialsError("invalid username or password")
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    tokens = create_session(
        db,
        user,
        ip_address=client_meta(request)[0],
        user_agent=client_meta(request)[1],
        remember=payload.remember,
    )
    record_audit(
        db,
        user,
        "auth.login",
        "user",
        str(user.id),
        correlation_id=correlation_id(request),
        ip_address=client_meta(request)[0],
        user_agent=client_meta(request)[1],
    )
    db.commit()
    cookie_max_age = session_ttl_seconds(payload.remember)
    response.set_cookie(
        settings.session_cookie_name,
        tokens.session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=cookie_max_age,
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        tokens.csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=cookie_max_age,
        path="/",
    )
    return LoginResponse(user=UserOut.model_validate(user), csrf_token=tokens.csrf_token)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    if ctx.session is not None:
        revoke_session(db, ctx.session)
    record_audit(
        db,
        ctx.user,
        "auth.logout",
        "session",
        str(ctx.session.id) if ctx.session else None,
        correlation_id=correlation_id(request),
    )
    db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    response.delete_cookie(get_settings().csrf_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(ctx: Annotated[AuthContext, Depends(get_auth_context)]) -> UserOut:
    return UserOut.model_validate(ctx.user)


@router.post("/password", status_code=204)
def change_password(
    payload: PasswordChange,
    request: Request,
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    if not verify_password(payload.current_password, ctx.user.password_hash):
        raise InvalidCredentialsError("current password is incorrect")
    ctx.user.password_hash = hash_password(payload.new_password)
    ctx.user.must_change_password = False
    ctx.user.version += 1
    sessions = list(
        db.scalars(
            select(SessionModel).where(
                SessionModel.user_id == ctx.user.id, SessionModel.revoked_at.is_(None)
            )
        )
    )
    for session in sessions:
        if ctx.session is None or session.id != ctx.session.id:
            session.revoked_at = datetime.now(UTC)
    record_audit(
        db,
        ctx.user,
        "auth.password_change",
        "user",
        str(ctx.user.id),
        correlation_id=correlation_id(request),
    )
    db.commit()
    return Response(status_code=204)


@router.get("/sessions", response_model=SessionList)
def list_sessions(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[Session, Depends(get_db)],
) -> SessionList:
    sessions = list(
        db.scalars(
            select(SessionModel)
            .where(SessionModel.user_id == ctx.user.id, SessionModel.revoked_at.is_(None))
            .order_by(SessionModel.created_at.desc())
        )
    )
    return SessionList(items=[SessionOut.model_validate(item) for item in sessions])


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_one_session(
    session_id: UUID,
    request: Request,
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    session = db.get(SessionModel, session_id)
    if session is None or session.user_id != ctx.user.id:
        raise NotFoundError("session not found")
    revoke_session(db, session)
    record_audit(
        db,
        ctx.user,
        "auth.session_revoke",
        "session",
        str(session.id),
        correlation_id=correlation_id(request),
    )
    db.commit()
    return Response(status_code=204)


@router.get("/tokens", response_model=ApiTokenList)
def list_tokens(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiTokenList:
    tokens = list(
        db.scalars(
            select(ApiToken)
            .where(ApiToken.user_id == ctx.user.id)
            .order_by(ApiToken.created_at.desc())
        )
    )
    return ApiTokenList(items=[ApiTokenOut.model_validate(item) for item in tokens])


@router.post("/tokens", response_model=ApiTokenCreated, status_code=201)
def create_token(
    payload: ApiTokenCreate,
    request: Request,
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiTokenCreated:
    raw = f"tc_{secrets.token_urlsafe(32)}"
    token = ApiToken(
        user_id=ctx.user.id,
        name=payload.name,
        token_prefix=raw[:12],
        token_hash=_token_hash(raw),
        expires_at=payload.expires_at,
    )
    db.add(token)
    record_audit(
        db,
        ctx.user,
        "auth.token_create",
        "api_token",
        str(token.id),
        correlation_id=correlation_id(request),
        details={"name": payload.name},
    )
    db.commit()
    return ApiTokenCreated(**ApiTokenOut.model_validate(token).model_dump(), token=raw)


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(
    token_id: UUID,
    request: Request,
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    token = db.get(ApiToken, token_id)
    if token is None or token.user_id != ctx.user.id:
        raise NotFoundError("token not found")
    token.revoked_at = datetime.now(UTC)
    record_audit(
        db,
        ctx.user,
        "auth.token_revoke",
        "api_token",
        str(token.id),
        correlation_id=correlation_id(request),
    )
    db.commit()
    return Response(status_code=204)
