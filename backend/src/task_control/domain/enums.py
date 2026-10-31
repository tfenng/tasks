from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class ExecutorType(StrEnum):
    LOCAL = "local"
    SSH = "ssh"
    HTTP = "http"


class RunStatus(StrEnum):
    SCHEDULED = "scheduled"
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    MISSED = "missed"


class AttemptStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class TriggerType(StrEnum):
    IMMEDIATE = "immediate"
    ONCE = "once"
    CRON = "cron"
    INTERVAL = "interval"


TERMINAL_RUN_STATUSES = {
    RunStatus.SUCCEEDED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.SKIPPED,
    RunStatus.MISSED,
}
