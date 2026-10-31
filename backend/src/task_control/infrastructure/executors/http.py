from __future__ import annotations

import re
import time

import httpx

from task_control.infrastructure.executors.base import ExecutionContext, ExecutionResult


def _truncate(value: bytes, limit: int) -> tuple[str, bool]:
    return value[:limit].decode("utf-8", errors="replace"), len(value) > limit


class HttpExecutor:
    executor_type = "http"

    def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        target = ctx.target
        config = target.get("config", {}) if isinstance(target, dict) else {}
        executor = target.get("executor", {}) if isinstance(target, dict) else {}
        base_url = str(config.get("base_url", "")).rstrip("/")
        url = executor.get("url") or f"{base_url}{executor.get('path', '')}"
        method = str(executor.get("method", "GET")).upper()
        headers = {str(k): str(v) for k, v in (executor.get("headers") or {}).items()}
        credential = ctx.credential or {}
        auth = None
        if credential.get("token"):
            headers["Authorization"] = f"Bearer {credential['token']}"
        elif credential.get("username") is not None:
            auth = httpx.BasicAuth(str(credential["username"]), str(credential.get("password", "")))
        body = executor.get("body")
        started = time.perf_counter()
        try:
            with httpx.Client(
                timeout=ctx.timeout_seconds,
                verify=True,
                follow_redirects=bool(executor.get("follow_redirects", False)),
            ) as client:
                response = client.request(method, url, headers=headers, json=body, auth=auth)
            duration_ms = int((time.perf_counter() - started) * 1000)
            excerpt, truncated = _truncate(response.content, ctx.output_limit_bytes)
            success_codes = executor.get("success_status_codes") or list(range(200, 300))
            success = response.status_code in set(int(code) for code in success_codes)
            if success and executor.get("response_body_regex"):
                success = bool(re.search(str(executor["response_body_regex"]), excerpt))
            if success and isinstance(executor.get("response_header_regex"), dict):
                for name, pattern in executor["response_header_regex"].items():
                    if not re.search(str(pattern), response.headers.get(str(name), "")):
                        success = False
                        break
            if success:
                return ExecutionResult(
                    status="succeeded",
                    http_status=response.status_code,
                    response=excerpt,
                    duration_ms=duration_ms,
                    truncated=truncated,
                )
            error_class = "HTTP_4XX" if 400 <= response.status_code < 500 else "HTTP_5XX"
            if response.status_code < 400 or not success:
                error_class = "RESPONSE_MISMATCH"
            return ExecutionResult(
                status="failed",
                error_class=error_class,
                error_message=f"unexpected HTTP status {response.status_code}",
                http_status=response.status_code,
                response=excerpt,
                duration_ms=duration_ms,
                truncated=truncated,
            )
        except httpx.TimeoutException:
            return ExecutionResult(
                status="timed_out",
                error_class="TIMEOUT",
                error_message="http request timed out",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except httpx.ConnectError as exc:
            return ExecutionResult(
                status="failed",
                error_class="CONNECTION",
                error_message=str(exc)[:1000],
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                status="failed",
                error_class="UNKNOWN",
                error_message=str(exc)[:1000],
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
