from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from task_control.config import get_settings
from task_control.infrastructure.db.models import Session as SessionModel
from task_control.infrastructure.db.models import User


def _hash(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


@dataclass(frozen=True)
class SessionTokens:
    session_token: str
    csrf_token: str
    session: SessionModel


def create_session(
    db: Session, user: User, *, ip_address: str | None = None, user_agent: str | None = None
) -> SessionTokens:
    settings = get_settings()
    now = datetime.now(UTC)
    session_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    session = SessionModel(
        user_id=user.id,
        token_hash=_hash(session_token),
        csrf_token_hash=_hash(csrf_token),
        ip_address=ip_address,
        user_agent=(user_agent or "")[:512] or None,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=settings.session_idle_minutes),
    )
    db.add(session)
    db.flush()
    return SessionTokens(session_token, csrf_token, session)


def get_session(db: Session, token: str | None) -> SessionModel | None:
    if not token:
        return None
    session = db.scalar(select(SessionModel).where(SessionModel.token_hash == _hash(token)))
    if session is None or session.revoked_at is not None:
        return None
    now = datetime.now(UTC)
    if session.expires_at <= now:
        session.revoked_at = now
        return None
    session.last_seen_at = now
    return session


def verify_csrf(session: SessionModel, token: str | None) -> bool:
    return bool(token) and secret_compare(_hash(token), session.csrf_token_hash)


def secret_compare(left: bytes, right: bytes) -> bool:
    return secrets.compare_digest(left, right)


def revoke_session(db: Session, session: SessionModel) -> None:
    session.revoked_at = datetime.now(UTC)
