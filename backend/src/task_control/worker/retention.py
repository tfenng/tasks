from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from task_control.config import get_settings
from task_control.infrastructure.db.models import (
    ApiToken,
    AuditEvent,
    Session,
    TaskAttempt,
    TaskRun,
)
from task_control.infrastructure.db.session import session_scope


def run_retention() -> dict[str, int]:
    settings = get_settings()
    now = datetime.now(UTC)
    run_cutoff = now - timedelta(days=settings.retention_days)
    attempt_cutoff = now - timedelta(days=settings.attempt_retention_days)
    with session_scope() as db:
        attempts = (
            db.execute(
                delete(TaskAttempt).where(
                    TaskAttempt.created_at < attempt_cutoff, TaskAttempt.status != "running"
                )
            ).rowcount
            or 0
        )
        runs = (
            db.execute(
                delete(TaskRun).where(
                    TaskRun.created_at < run_cutoff,
                    TaskRun.status.in_(["succeeded", "failed", "cancelled", "skipped", "missed"]),
                )
            ).rowcount
            or 0
        )
        audit = (
            db.execute(delete(AuditEvent).where(AuditEvent.created_at < run_cutoff)).rowcount or 0
        )
        sessions = (
            db.execute(
                delete(Session).where(Session.expires_at < now - timedelta(days=30))
            ).rowcount
            or 0
        )
        tokens = (
            db.execute(
                delete(ApiToken).where(
                    ApiToken.revoked_at.is_not(None),
                    ApiToken.revoked_at < now - timedelta(days=90),
                )
            ).rowcount
            or 0
        )
    return {
        "attempts": attempts,
        "runs": runs,
        "audit": audit,
        "sessions": sessions,
        "api_tokens": tokens,
    }


if __name__ == "__main__":
    print(run_retention())
