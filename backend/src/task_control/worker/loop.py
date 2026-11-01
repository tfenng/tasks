from __future__ import annotations

import json
import os
import signal
import socket
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from loguru import logger
from sqlalchemy import select

from task_control.application.audit.service import record_audit
from task_control.application.targets.service import credential_values
from task_control.config import get_settings
from task_control.infrastructure.db.models import (
    TaskAttempt,
    TaskDefinitionRuntime,
    TaskDefinitionVersion,
    TaskRun,
    Worker,
)
from task_control.infrastructure.db.session import session_scope
from task_control.infrastructure.executors.base import ExecutionContext
from task_control.infrastructure.executors.registry import registry
from task_control.infrastructure.security.secrets import decrypt_parameters


@dataclass(frozen=True)
class ClaimedRun:
    run_id: UUID
    attempt_id: UUID
    attempt_no: int
    executor_type: str
    parameters: dict
    target: dict
    credential: dict | None
    timeout_seconds: int
    secret_values: tuple[str, ...]


class LeaseHeartbeat:
    """Keep a running run's lease alive while a long task executes."""

    def __init__(self, run_id: UUID, lease_seconds: int) -> None:
        self.run_id = run_id
        self.interval = max(lease_seconds / 3, 1.0)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> LeaseHeartbeat:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                with session_scope() as db:
                    run = db.get(TaskRun, self.run_id)
                    if run is None or run.status != "running":
                        return
                    run.lease_expires_at = datetime.now(UTC) + timedelta(
                        seconds=get_settings().lease_seconds
                    )
            except Exception as exc:  # noqa: BLE001
                logger.bind(run_id=str(self.run_id), component="worker").warning(
                    "lease heartbeat failed: {}", exc
                )


def _secret_values(schema: dict, parameters: dict) -> tuple[str, ...]:
    values: list[str] = []
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for name, definition in properties.items():
            if isinstance(definition, dict) and (
                definition.get("x-secret") or definition.get("writeOnly")
            ):
                value = parameters.get(name)
                if value is not None:
                    values.append(str(value))
    return tuple(values)


def register_worker(role: str = "worker") -> UUID:
    with session_scope() as db:
        worker = Worker(
            id=uuid4(),
            hostname=socket.gethostname(),
            pid=os.getpid(),
            role=role,
        )
        db.add(worker)
        db.flush()
        return worker.id


def claim_run(worker_id: UUID) -> ClaimedRun | None:
    settings = get_settings()
    with session_scope() as db:
        run = db.scalar(
            select(TaskRun)
            .join(
                TaskDefinitionRuntime, TaskDefinitionRuntime.definition_id == TaskRun.definition_id
            )
            .where(
                TaskRun.status == "queued",
                TaskDefinitionRuntime.running_count < TaskDefinitionRuntime.max_concurrency,
            )
            .order_by(TaskRun.queued_at, TaskRun.id)
            .with_for_update(skip_locked=True, of=TaskRun)
            .limit(1)
        )
        if run is None:
            return None
        runtime = db.get(TaskDefinitionRuntime, run.definition_id)
        if runtime is None or runtime.running_count >= runtime.max_concurrency:
            return None
        version = db.get(TaskDefinitionVersion, run.definition_version_id)
        if version is None:
            run.status = "failed"
            run.error_code = "DEFINITION_VERSION_MISSING"
            run.finished_at = datetime.now(UTC)
            return None
        run.status = "running"
        run.started_at = datetime.now(UTC)
        run.worker_id = worker_id
        run.lease_expires_at = datetime.now(UTC) + timedelta(seconds=settings.lease_seconds)
        run.attempt_count += 1
        runtime.running_count += 1
        attempt = TaskAttempt(
            run_id=run.id,
            attempt_no=run.attempt_count,
            status="running",
            executor_type=version.executor_type,
            worker_id=worker_id,
        )
        db.add(attempt)
        db.flush()
        parameters = decrypt_parameters(
            version.parameter_schema, run.parameters, run_id=str(run.id)
        )
        logger.bind(run_id=str(run.id), attempt=attempt.attempt_no, component="worker").info(
            "run claimed"
        )
        credential = None
        credential_id = run.target_snapshot.get("credential_id")
        if credential_id:
            credential = credential_values(db, UUID(str(credential_id)))
        return ClaimedRun(
            run_id=run.id,
            attempt_id=attempt.id,
            attempt_no=attempt.attempt_no,
            executor_type=version.executor_type,
            parameters=parameters,
            target=run.target_snapshot,
            credential=credential,
            timeout_seconds=version.timeout_seconds,
            secret_values=_secret_values(version.parameter_schema, parameters),
        )


def _is_retryable(policy: dict, result) -> bool:
    retryable = set(policy.get("retryable_error_classes") or [])
    if result.error_class in retryable:
        return True
    if result.error_class == "EXIT_CODE":
        return result.exit_code in set(policy.get("retry_on_exit_codes") or [])
    return False


def _retry_delay(policy: dict, attempt_count: int) -> int:
    initial = int(policy.get("initial_backoff_seconds", 30))
    multiplier = float(policy.get("multiplier", 2))
    maximum = int(policy.get("max_backoff_seconds", 600))
    return min(int(initial * (multiplier ** max(attempt_count - 1, 0))), maximum)


def finish_run(claimed: ClaimedRun, result) -> None:
    with session_scope() as db:
        run = db.get(TaskRun, claimed.run_id)
        attempt = db.get(TaskAttempt, claimed.attempt_id)
        if run is None or attempt is None:
            return
        version = db.get(TaskDefinitionVersion, run.definition_version_id)
        now = datetime.now(UTC)
        attempt.status = result.status
        attempt.finished_at = now
        attempt.duration_ms = result.duration_ms
        attempt.exit_code = result.exit_code
        attempt.http_status = result.http_status
        attempt.error_class = result.error_class
        attempt.error_message = (result.error_message or "")[:2000] or None
        attempt.stdout_excerpt = result.stdout
        attempt.stderr_excerpt = result.stderr
        attempt.response_excerpt = result.response
        attempt.truncated = result.truncated
        run.error_code = result.error_class
        run.error_message = (result.error_message or "")[:2000] or None
        run.result_summary = {
            "exit_code": result.exit_code,
            "http_status": result.http_status,
            "duration_ms": result.duration_ms,
            "truncated": result.truncated,
        }
        if result.status == "succeeded":
            run.status = "succeeded"
            run.finished_at = now
        elif run.cancel_requested_at is not None:
            run.status = "cancelled"
            run.finished_at = now
        else:
            policy = version.retry_policy if version is not None else {}
            if _is_retryable(policy, result) and run.attempt_count < run.max_attempts:
                run.status = "retry_wait"
                run.next_retry_at = now + timedelta(seconds=_retry_delay(policy, run.attempt_count))
                run.finished_at = None
            else:
                run.status = "failed"
                run.finished_at = now
        run.lease_expires_at = None
        run.version += 1
        runtime = db.get(TaskDefinitionRuntime, run.definition_id)
        if runtime is not None and runtime.running_count > 0:
            runtime.running_count -= 1
        record_audit(
            db,
            None,
            f"run.{run.status}",
            "task_run",
            str(run.id),
            details={"attempt": attempt.attempt_no, "error_class": result.error_class},
        )
        logger.bind(
            run_id=str(run.id),
            attempt=attempt.attempt_no,
            status=run.status,
            component="worker",
        ).info("run finished")


def execute_claimed(worker_id: UUID, claimed: ClaimedRun) -> None:
    executor = registry.create(claimed.executor_type)
    with LeaseHeartbeat(claimed.run_id, get_settings().lease_seconds):
        result = executor.execute(
            ExecutionContext(
                run_id=str(claimed.run_id),
                attempt_no=claimed.attempt_no,
                parameters=claimed.parameters,
                target=claimed.target,
                credential=claimed.credential,
                timeout_seconds=claimed.timeout_seconds,
                output_limit_bytes=get_settings().output_limit_bytes,
                secret_values=claimed.secret_values,
            )
        )
    finish_run(claimed, result)


def run_once(worker_id: UUID) -> bool:
    claimed = claim_run(worker_id)
    if claimed is None:
        return False
    execute_claimed(worker_id, claimed)
    return True


def reap_once() -> int:
    now = datetime.now(UTC)
    with session_scope() as db:
        runs = list(
            db.scalars(
                select(TaskRun).where(
                    TaskRun.status == "running",
                    TaskRun.lease_expires_at.is_not(None),
                    TaskRun.lease_expires_at < now,
                )
            )
        )
        for run in runs:
            attempts = list(db.scalars(select(TaskAttempt).where(TaskAttempt.run_id == run.id)))
            for attempt in attempts:
                if attempt.status == "running":
                    attempt.status = "failed"
                    attempt.finished_at = now
                    attempt.error_class = "WORKER_LOST"
                    attempt.error_message = "worker lease expired"
            run.status = "failed"
            run.error_code = "WORKER_LOST"
            run.error_message = "worker lease expired"
            run.finished_at = now
            run.lease_expires_at = None
            run.version += 1
            runtime = db.get(TaskDefinitionRuntime, run.definition_id)
            if runtime is not None and runtime.running_count > 0:
                runtime.running_count -= 1
            record_audit(db, None, "run.failed", "task_run", str(run.id), details={"reaper": True})
        return len(runs)


def run_forever() -> None:
    settings = get_settings()
    worker_id = register_worker()
    running = True

    def stop(*_: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        try:
            did_work = run_once(worker_id)
            reap_once()
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"level": "error", "message": str(exc)}), flush=True)
            did_work = False
        if not did_work:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    run_forever()
