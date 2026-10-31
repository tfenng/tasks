from __future__ import annotations

import time
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from task_control.application.schedules.service import (
    compute_next_fire,
    create_run_from_schedule,
)
from task_control.infrastructure.db.models import Schedule, TaskRun
from task_control.infrastructure.db.session import session_scope


def _has_active_run(db: Session, schedule_id) -> bool:
    return (
        db.scalar(
            select(TaskRun.id)
            .where(
                TaskRun.schedule_id == schedule_id,
                TaskRun.status.in_(["queued", "running", "retry_wait"]),
            )
            .limit(1)
        )
        is not None
    )


def _occurrence_exists(db: Session, schedule_id, scheduled_for: datetime) -> bool:
    return (
        db.scalar(
            select(TaskRun.id)
            .where(
                TaskRun.schedule_id == schedule_id,
                TaskRun.scheduled_for == scheduled_for,
            )
            .limit(1)
        )
        is not None
    )


def promote_retry_wait(db: Session, now: datetime) -> int:
    runs = list(
        db.scalars(
            select(TaskRun).where(
                TaskRun.status == "retry_wait",
                TaskRun.next_retry_at.is_not(None),
                TaskRun.next_retry_at <= now,
            )
        )
    )
    for run in runs:
        run.status = "queued"
        run.queued_at = now
        run.next_retry_at = None
        run.version += 1
    return len(runs)


def run_once() -> tuple[int, int]:
    now = datetime.now(UTC)
    with session_scope() as db:
        locked = db.scalar(text("SELECT pg_try_advisory_lock(hashtext('task_control_scheduler'))"))
        if not locked:
            return (0, 0)
        try:
            schedules = list(
                db.scalars(
                    select(Schedule)
                    .where(Schedule.status == "active", Schedule.next_fire_at <= now)
                    .order_by(Schedule.next_fire_at)
                    .with_for_update(skip_locked=True)
                )
            )
            created = 0
            for schedule in schedules:
                scheduled_for = schedule.next_fire_at
                if scheduled_for is None:
                    continue
                if not _occurrence_exists(db, schedule.id, scheduled_for):
                    age = (now - scheduled_for).total_seconds()
                    if age > schedule.misfire_grace_seconds:
                        create_run_from_schedule(
                            db,
                            schedule,
                            scheduled_for=scheduled_for,
                            status="missed",
                            reason="outside misfire grace window",
                        )
                        created += 1
                    elif _has_active_run(db, schedule.id):
                        if schedule.overlap_policy == "skip":
                            create_run_from_schedule(
                                db,
                                schedule,
                                scheduled_for=scheduled_for,
                                status="skipped",
                                reason="previous run still active",
                            )
                            created += 1
                        else:
                            create_run_from_schedule(
                                db, schedule, scheduled_for=scheduled_for, status="queued"
                            )
                            created += 1
                    else:
                        create_run_from_schedule(
                            db, schedule, scheduled_for=scheduled_for, status="queued"
                        )
                        created += 1
                schedule.last_fire_at = scheduled_for
                if schedule.trigger_type == "once":
                    schedule.status = "completed"
                    schedule.next_fire_at = None
                else:
                    schedule.next_fire_at = compute_next_fire(
                        schedule.trigger_type,
                        fire_at=schedule.fire_at,
                        cron_expr=schedule.cron_expr,
                        interval_seconds=schedule.interval_seconds,
                        tz_name=schedule.timezone,
                        after=scheduled_for,
                    )
                    if schedule.next_fire_at is None:
                        schedule.status = "completed"
                schedule.version += 1
            promoted = promote_retry_wait(db, now)
            return created, promoted
        finally:
            db.execute(text("SELECT pg_advisory_unlock(hashtext('task_control_scheduler'))"))


def run_forever() -> None:
    while True:
        try:
            run_once()
        except Exception as exc:  # noqa: BLE001
            print(f"scheduler error: {exc}", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    run_forever()
