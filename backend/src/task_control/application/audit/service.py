from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from task_control.infrastructure.db.models import AuditEvent, User


def record_audit(
    db: Session,
    actor: User | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    *,
    outcome: str = "success",
    correlation_id: str = "-",
    details: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor.id if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        correlation_id=correlation_id or str(uuid4()),
        details=details or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(event)
    return event
