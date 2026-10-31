from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from task_control.api.deps import AuthContext, require_roles
from task_control.api.schemas import AttemptStats, RunStats
from task_control.application.stats import service
from task_control.domain.enums import Role
from task_control.infrastructure.db.session import get_db

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/runs", response_model=RunStats)
def get_run_stats(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.OPERATOR, Role.VIEWER))],
    from_time: Annotated[datetime | None, Query(alias="from")] = None,
    to_time: Annotated[datetime | None, Query(alias="to")] = None,
    timezone: str = "UTC",
    definition_id: UUID | None = None,
    definition_version_id: UUID | None = None,
    trigger_type: str | None = None,
    executor_type: str | None = None,
    group_by: str = "none",
) -> RunStats:
    return service.run_stats(
        db,
        from_time=from_time,
        to_time=to_time,
        timezone_name=timezone,
        definition_id=definition_id,
        definition_version_id=definition_version_id,
        trigger_type=trigger_type,
        executor_type=executor_type,
        group_by=group_by,
    )


@router.get("/attempts", response_model=AttemptStats)
def get_attempt_stats(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_roles(Role.ADMIN, Role.OPERATOR, Role.VIEWER))],
    from_time: Annotated[datetime | None, Query(alias="from")] = None,
    to_time: Annotated[datetime | None, Query(alias="to")] = None,
    timezone: str = "UTC",
    group_by: str = "none",
) -> AttemptStats:
    return service.attempt_stats(
        db,
        from_time=from_time,
        to_time=to_time,
        timezone_name=timezone,
        group_by=group_by,
    )
