from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from task_control.api.schemas import HealthResponse
from task_control.infrastructure.db.models import Worker
from task_control.infrastructure.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def ready(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    checks: dict[str, dict[str, str]] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception:  # noqa: BLE001
        checks["database"] = {"status": "unavailable"}
    cutoff = datetime.now(UTC) - timedelta(seconds=90)
    worker = db.scalar(
        select(Worker)
        .where(Worker.stopped_at.is_(None), Worker.last_heartbeat_at >= cutoff)
        .limit(1)
    )
    checks["worker"] = {"status": "ok" if worker else "degraded"}
    status = "ok" if checks["database"]["status"] == "ok" else "unavailable"
    return HealthResponse(status=status, checks=checks)
