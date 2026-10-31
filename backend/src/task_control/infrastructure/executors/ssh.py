from __future__ import annotations

import io
import shlex
import time

import paramiko

from task_control.infrastructure.executors.base import ExecutionContext, ExecutionResult


def _truncate(data: bytes, limit: int) -> tuple[str, bool]:
    return data[:limit].decode("utf-8", errors="replace"), len(data) > limit


class SshExecutor:
    executor_type = "ssh"

    def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        target = ctx.target
        config = target.get("config", {}) if isinstance(target, dict) else {}
        executor = target.get("executor", {}) if isinstance(target, dict) else {}
        host = str(config.get("host", ""))
        port = int(config.get("port", 22))
        username = str(config.get("user", ""))
        command = str(executor.get("command", ""))
        extra = [str(item) for item in ctx.parameters.get("__arguments__", [])]
        if extra:
            command = f"{command} {shlex.join(extra)}"
        credential = ctx.credential or {}
        started = time.perf_counter()
        client = paramiko.SSHClient()
        try:
            known_hosts = config.get("known_hosts")
            if known_hosts:
                client.load_host_keys(str(known_hosts))
            else:
                client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            connect_kwargs: dict = {
                "hostname": host,
                "port": port,
                "username": username,
                "timeout": ctx.timeout_seconds,
                "banner_timeout": ctx.timeout_seconds,
                "auth_timeout": ctx.timeout_seconds,
            }
            if credential.get("private_key"):
                key_stream = io.StringIO(str(credential["private_key"]))
                passphrase = credential.get("passphrase") or None
                key_classes = [
                    paramiko.Ed25519Key,
                    paramiko.ECDSAKey,
                    paramiko.RSAKey,
                    paramiko.DSSKey,
                ]
                last_error: Exception | None = None
                for key_class in key_classes:
                    key_stream.seek(0)
                    try:
                        connect_kwargs["pkey"] = key_class.from_private_key(
                            key_stream, password=passphrase
                        )
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                if "pkey" not in connect_kwargs:
                    raise paramiko.AuthenticationException(str(last_error))
            elif credential.get("password"):
                connect_kwargs["password"] = str(credential["password"])
            client.connect(**connect_kwargs)
            stdin, stdout, stderr = client.exec_command(command, timeout=ctx.timeout_seconds)
            stdout_bytes = stdout.read()
            stderr_bytes = stderr.read()
            exit_code = stdout.channel.recv_exit_status()
            out_text, out_truncated = _truncate(stdout_bytes, ctx.output_limit_bytes)
            err_text, err_truncated = _truncate(stderr_bytes, ctx.output_limit_bytes)
            return ExecutionResult(
                status="succeeded" if exit_code == 0 else "failed",
                error_class=None if exit_code == 0 else "EXIT_CODE",
                error_message=None if exit_code == 0 else f"ssh command exited with {exit_code}",
                exit_code=exit_code,
                stdout=out_text,
                stderr=err_text,
                duration_ms=int((time.perf_counter() - started) * 1000),
                truncated=out_truncated or err_truncated,
            )
        except paramiko.BadHostKeyException as exc:
            return ExecutionResult(
                status="failed",
                error_class="SSH_HOST_KEY",
                error_message=str(exc)[:1000],
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except paramiko.AuthenticationException as exc:
            return ExecutionResult(
                status="failed",
                error_class="SSH_AUTH",
                error_message=str(exc)[:1000],
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except TimeoutError:
            return ExecutionResult(
                status="timed_out",
                error_class="TIMEOUT",
                error_message="ssh command timed out",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                status="failed",
                error_class="CONNECTION",
                error_message=str(exc)[:1000],
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        finally:
            client.close()
