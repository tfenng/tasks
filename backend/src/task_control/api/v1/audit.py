from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from task_control.api.deps import AuthContext, require_roles
from task_control.api.schemas import AuditEventList, AuditEventOut
from task_control.domain.enums import Role
from task_control.infrastructure.db.models import AuditEvent, User
from task_control.infrastructure.db.session import get_db

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=AuditEventList)
def list_audit_events(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = None,
    resource_type: str | None = None,
    from_time: Annotated[datetime | None, Query(alias="from")] = None,
    to_time: Annotated[datetime | None, Query(alias="to")] = None,
) -> AuditEventList:
    stmt = select(AuditEvent)
    count_stmt = select(func.count()).select_from(AuditEvent)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
        count_stmt = count_stmt.where(AuditEvent.action == action)
    if resource_type:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
        count_stmt = count_stmt.where(AuditEvent.resource_type == resource_type)
    if from_time:
        stmt = stmt.where(AuditEvent.created_at >= from_time)
        count_stmt = count_stmt.where(AuditEvent.created_at >= from_time)
    if to_time:
        stmt = stmt.where(AuditEvent.created_at <= to_time)
        count_stmt = count_stmt.where(AuditEvent.created_at <= to_time)
    total = db.scalar(count_stmt) or 0
    items = list(
        db.scalars(
            stmt.order_by(AuditEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    actor_ids = {item.actor_user_id for item in items if item.actor_user_id is not None}
    usernames = (
        {user.id: user.username for user in db.scalars(select(User).where(User.id.in_(actor_ids)))}
        if actor_ids
        else {}
    )
    return AuditEventList(
        items=[
            AuditEventOut.model_validate(item).model_copy(
                update={"actor_username": usernames.get(item.actor_user_id)}
            )
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
    )
