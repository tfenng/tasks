from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ExecutionContext:
    run_id: str
    attempt_no: int
    parameters: dict[str, Any]
    target: dict[str, Any]
    timeout_seconds: int
    output_limit_bytes: int
    credential: dict[str, Any] | None = None
    secret_values: tuple[str, ...] = field(default_factory=tuple)
    cancelled: bool = False


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    error_class: str | None = None
    error_message: str | None = None
    exit_code: int | None = None
    http_status: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    response: str | None = None
    duration_ms: int = 0
    truncated: bool = False


class TaskExecutor(Protocol):
    executor_type: str

    def execute(self, ctx: ExecutionContext) -> ExecutionResult: ...
