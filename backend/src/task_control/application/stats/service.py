from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from task_control.api.schemas import AttemptStats, RunStats, StatsBucket
from task_control.domain.errors import ValidationError
from task_control.infrastructure.db.models import TaskAttempt, TaskDefinitionVersion, TaskRun


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[index]


def _duration_ms(run: TaskRun) -> float | None:
    if run.started_at is None or run.finished_at is None:
        return None
    return max(0.0, (run.finished_at - run.started_at).total_seconds() * 1000)


def _bucket_key(
    run: TaskRun, group_by: str, timezone_name: str, version: TaskDefinitionVersion | None
) -> str:
    if group_by == "none":
        return "all"
    if group_by == "day":
        zone = ZoneInfo(timezone_name)
        return run.created_at.astimezone(zone).strftime("%Y-%m-%d")
    if group_by == "definition":
        return str(run.definition_id)
    if group_by == "trigger":
        return run.trigger_type
    if group_by == "executor":
        return version.executor_type if version else "unknown"
    raise ValidationError("invalid group_by")


def _bucket(total: list[TaskRun], key: str) -> StatsBucket:
    succeeded = sum(1 for run in total if run.status == "succeeded")
    failed = sum(1 for run in total if run.status == "failed")
    durations = [value for run in total if (value := _duration_ms(run)) is not None]
    denominator = succeeded + failed
    return StatsBucket(
        key=key,
        total=len(total),
        succeeded=succeeded,
        failed=failed,
        cancelled=sum(1 for run in total if run.status == "cancelled"),
        skipped=sum(1 for run in total if run.status == "skipped"),
        missed=sum(1 for run in total if run.status == "missed"),
        success_rate=(succeeded / denominator * 100) if denominator else 0.0,
        avg_duration_ms=(sum(durations) / len(durations)) if durations else None,
        p95_duration_ms=_percentile(durations, 95),
    )


def run_stats(
    db: Session,
    *,
    from_time: datetime | None,
    to_time: datetime | None,
    timezone_name: str = "UTC",
    definition_id=None,
    definition_version_id=None,
    trigger_type: str | None = None,
    executor_type: str | None = None,
    group_by: str = "none",
) -> RunStats:
    if from_time is None:
        from_time = datetime.now(UTC) - timedelta(days=7)
    if to_time is None:
        to_time = datetime.now(UTC)
    stmt = select(TaskRun).where(TaskRun.created_at >= from_time, TaskRun.created_at <= to_time)
    if definition_id:
        stmt = stmt.where(TaskRun.definition_id == definition_id)
    if definition_version_id:
        stmt = stmt.where(TaskRun.definition_version_id == definition_version_id)
    if trigger_type:
        stmt = stmt.where(TaskRun.trigger_type == trigger_type)
    runs = list(db.scalars(stmt))
    versions = (
        {
            version.id: version
            for version in db.scalars(
                select(TaskDefinitionVersion).where(
                    TaskDefinitionVersion.id.in_([run.definition_version_id for run in runs])
                )
            )
        }
        if runs
        else {}
    )
    if executor_type:
        runs = [
            run
            for run in runs
            if versions.get(run.definition_version_id)
            and versions[run.definition_version_id].executor_type == executor_type
        ]
    grouped: dict[str, list[TaskRun]] = defaultdict(list)
    for run in runs:
        grouped[
            _bucket_key(run, group_by, timezone_name, versions.get(run.definition_version_id))
        ].append(run)
    buckets = [_bucket(items, key) for key, items in sorted(grouped.items())]
    succeeded = sum(1 for run in runs if run.status == "succeeded")
    failed = sum(1 for run in runs if run.status == "failed")
    durations = [value for run in runs if (value := _duration_ms(run)) is not None]
    denominator = succeeded + failed
    return RunStats(
        total=len(runs),
        succeeded=succeeded,
        failed=failed,
        cancelled=sum(1 for run in runs if run.status == "cancelled"),
        skipped=sum(1 for run in runs if run.status == "skipped"),
        missed=sum(1 for run in runs if run.status == "missed"),
        retrying=sum(1 for run in runs if run.status == "retry_wait"),
        success_rate=(succeeded / denominator * 100) if denominator else 0.0,
        avg_duration_ms=(sum(durations) / len(durations)) if durations else None,
        p95_duration_ms=_percentile(durations, 95),
        buckets=buckets,
    )


def attempt_stats(
    db: Session,
    *,
    from_time: datetime | None,
    to_time: datetime | None,
    timezone_name: str = "UTC",
    group_by: str = "none",
) -> AttemptStats:
    if from_time is None:
        from_time = datetime.now(UTC) - timedelta(days=7)
    if to_time is None:
        to_time = datetime.now(UTC)
    attempts = list(
        db.scalars(
            select(TaskAttempt).where(
                TaskAttempt.created_at >= from_time, TaskAttempt.created_at <= to_time
            )
        )
    )
    durations = [attempt.duration_ms for attempt in attempts if attempt.duration_ms is not None]
    return AttemptStats(
        total=len(attempts),
        succeeded=sum(1 for item in attempts if item.status == "succeeded"),
        failed=sum(1 for item in attempts if item.status == "failed"),
        timed_out=sum(1 for item in attempts if item.status == "timed_out"),
        cancelled=sum(1 for item in attempts if item.status == "cancelled"),
        success_rate=(
            sum(1 for item in attempts if item.status == "succeeded") / len(attempts) * 100
            if attempts
            else 0.0
        ),
        avg_duration_ms=(sum(durations) / len(durations)) if durations else None,
    )
