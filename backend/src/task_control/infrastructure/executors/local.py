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

_PLACEHOLDER = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _render(value: str, parameters: dict) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in parameters:
            raise ValueError(f"unknown parameter in argv: {name}")
        return str(parameters[name])

    return _PLACEHOLDER.sub(replace, value)


def _truncate(data: bytes, limit: int) -> tuple[str, bool]:
    truncated = len(data) > limit
    return data[:limit].decode("utf-8", errors="replace"), truncated


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
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
            )
            stdout, stderr = process.communicate(timeout=ctx.timeout_seconds)
            duration_ms = int((time.perf_counter() - started) * 1000)
            out_text, out_truncated = _truncate(stdout, ctx.output_limit_bytes)
            err_text, err_truncated = _truncate(stderr, ctx.output_limit_bytes)
            out_text = _redact(out_text, ctx.secret_values)
            err_text = _redact(err_text, ctx.secret_values)
            status = "succeeded" if process.returncode == 0 else "failed"
            return ExecutionResult(
                status=status,
                error_class=None if status == "succeeded" else "EXIT_CODE",
                error_message=None
                if status == "succeeded"
                else f"process exited with code {process.returncode}",
                exit_code=process.returncode,
                stdout=out_text,
                stderr=err_text,
                duration_ms=duration_ms,
                truncated=out_truncated or err_truncated,
            )
        except subprocess.TimeoutExpired:
            if process is not None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            return ExecutionResult(
                status="timed_out",
                error_class="TIMEOUT",
                error_message="execution timed out",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                status="failed",
                error_class="UNKNOWN",
                error_message=str(exc)[:1000],
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
