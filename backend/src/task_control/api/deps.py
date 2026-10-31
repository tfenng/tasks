from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from task_control.api.rate_limit import limiter
from task_control.config import get_settings
from task_control.domain.enums import Role
from task_control.domain.errors import AuthError, ForbiddenError, RateLimitedError
from task_control.infrastructure.db.models import ApiToken, User
from task_control.infrastructure.db.models import Session as SessionModel
from task_control.infrastructure.db.session import get_db
from task_control.infrastructure.security.sessions import get_session, verify_csrf


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: SessionModel | None


def _bearer_user(db: Session, authorization: str | None) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    raw = authorization.split(" ", 1)[1].strip()
    token_hash = hashlib.sha256(raw.encode("utf-8")).digest()
    token = db.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash))
    now = datetime.now(UTC)
    if token is None or token.revoked_at is not None:
        return None
    if token.expires_at is not None and token.expires_at <= now:
        return None
    token.last_used_at = now
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_auth_context(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    tc_session: Annotated[str | None, Cookie()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    bearer_user = _bearer_user(db, authorization)
    if bearer_user is not None:
        return AuthContext(user=bearer_user, session=None)
    session = get_session(db, tc_session)
    if session is None:
        raise AuthError("authentication required")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthError("authentication required")
    return AuthContext(user=user, session=session)


def require_roles(*roles: Role):
    allowed = {role.value for role in roles}

    def dependency(ctx: Annotated[AuthContext, Depends(get_auth_context)]) -> AuthContext:
        if ctx.user.role not in allowed:
            raise ForbiddenError("insufficient role")
        return ctx

    return dependency


def require_csrf(
    ctx: Annotated[AuthContext, Depends(get_auth_context)],
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthContext:
    if not limiter.allow(f"write:{ctx.user.id}", 120, 60):
        raise RateLimitedError("too many write requests", retry_after=60)
    if ctx.session is None:
        return ctx
    if not verify_csrf(ctx.session, x_csrf_token):
        raise ForbiddenError("invalid csrf token")
    return ctx


def client_meta(request: Request) -> tuple[str | None, str | None]:
    return request.client.host if request.client else None, request.headers.get("user-agent")


def settings_dep():
    return get_settings()
