from __future__ import annotations

import contextlib
import os
import re
import shlex
import signal
import subprocess
import time

from task_control.config import get_settings
from task_control.infrastructure.executors.base import ExecutionContext, ExecutionResult
from task_control.infrastructure.executors.output import (
    STDERR_NAME,
    STDOUT_NAME,
    RedactingCapture,
    attempt_dir,
    ensure_attempt_dir,
    read_tail,
)

_PLACEHOLDER = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _render(value: str, parameters: dict) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in parameters:
            raise ValueError(f"unknown parameter in argv: {name}")
        return str(parameters[name])

    return _PLACEHOLDER.sub(replace, value)


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def _apply_shebang(argv: list[str], default_shell: str) -> list[str]:
    if len(argv) != 1 or not os.path.isfile(argv[0]):
        return argv
    try:
        with open(argv[0], "rb") as script:
            first_line = script.readline(512)
    except OSError:
        return argv
    if first_line.startswith(b"#!"):
        try:
            shebang = shlex.split(first_line[2:].decode("utf-8", errors="replace").strip())
        except ValueError:
            shebang = []
        if shebang:
            return [*shebang, argv[0]]
    suffix = os.path.splitext(argv[0])[1].lower()
    if suffix == ".py":
        return ["python3", argv[0]]
    return [default_shell or "/bin/bash", argv[0]]


class LocalScriptExecutor:
    executor_type = "local"

    def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        config = ctx.target.get("executor", ctx.target)
        argv = [_render(str(item), ctx.parameters) for item in config.get("argv", [])]
        extra_arguments = [str(item) for item in ctx.parameters.get("__arguments__", [])]
        interpreter = config.get("interpreter")
        argv = (
            [str(interpreter), *argv]
            if interpreter
            else _apply_shebang(argv, get_settings().default_shell)
        )
        argv.extend(extra_arguments)
        cwd = config.get("cwd") or None
        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in (config.get("env") or {}).items()})
        for name, value in ctx.parameters.items():
            env[f"TASK_PARAM_{str(name).upper()}"] = str(value)
        started = time.perf_counter()
        process = None
        captures: list[RedactingCapture] = []
        threads: list = []

        def read_outputs() -> tuple[str, str, bool]:
            directory = attempt_dir(ctx.run_id, ctx.attempt_no)
            out_text, out_total, out_cut = read_tail(
                directory / STDOUT_NAME, ctx.output_limit_bytes
            )
            err_text, err_total, err_cut = read_tail(
                directory / STDERR_NAME, ctx.output_limit_bytes
            )
            truncated = (
                out_cut
                or err_cut
                or any(capture.truncated for capture in captures)
                or out_total > ctx.output_limit_bytes
                or err_total > ctx.output_limit_bytes
            )
            return (
                _redact(out_text, ctx.secret_values),
                _redact(err_text, ctx.secret_values),
                truncated,
            )

        try:
            settings = get_settings()
            directory = ensure_attempt_dir(ctx.run_id, ctx.attempt_no)
            stdout_capture = RedactingCapture(
                directory / STDOUT_NAME,
                settings.output_capture_limit_bytes,
                ctx.secret_values,
            )
            stderr_capture = RedactingCapture(
                directory / STDERR_NAME,
                settings.output_capture_limit_bytes,
                ctx.secret_values,
            )
            captures = [stdout_capture, stderr_capture]
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
            )
            threads = [
                stdout_capture.start(process.stdout),
                stderr_capture.start(process.stderr),
            ]
            timed_out = False
            try:
                process.wait(timeout=ctx.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=10)
            for thread in threads:
                thread.join(timeout=10)

            duration_ms = int((time.perf_counter() - started) * 1000)
            out_text, err_text, truncated = read_outputs()
            if timed_out:
                return ExecutionResult(
                    status="timed_out",
                    error_class="TIMEOUT",
                    error_message=f"execution timed out after {ctx.timeout_seconds}s",
                    stdout=out_text,
                    stderr=err_text,
                    duration_ms=duration_ms,
                    truncated=truncated,
                )
            return_code = process.returncode
            status = "succeeded" if return_code == 0 else "failed"
            return ExecutionResult(
                status=status,
                error_class=None if status == "succeeded" else "EXIT_CODE",
                error_message=None
                if status == "succeeded"
                else f"process exited with code {return_code}",
                exit_code=return_code,
                stdout=out_text,
                stderr=err_text,
                duration_ms=duration_ms,
                truncated=truncated,
            )
        except Exception as exc:  # noqa: BLE001
            if process is not None and process.poll() is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                with contextlib.suppress(Exception):
                    process.wait(timeout=10)
            for capture in captures:
                capture.close()
            return ExecutionResult(
                status="failed",
                error_class="UNKNOWN",
                error_message=str(exc)[:1000],
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
