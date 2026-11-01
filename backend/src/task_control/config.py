from __future__ import annotations

import base64
import json
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TASK_CONTROL_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://localhost:5432/task_control"
    database_echo: bool = False

    secret_keys: str = '{"1":"ZGV2LW9ubHktMzItYnl0ZS1rZXktZm9yLXRlc3RzISE="}'
    secret_active_version: int = 1

    cookie_secure: bool = False
    session_cookie_name: str = "tc_session"
    csrf_cookie_name: str = "tc_csrf"
    session_idle_minutes: int = 30
    session_absolute_hours: int = 8
    session_remember_days: int = 7

    script_root: str = "/tmp/task-control-scripts"
    default_shell: str = "/bin/bash"
    known_hosts_path: str = ""
    output_limit_bytes: int = 1024 * 1024
    output_root: str = "/tmp/task-control-output"
    output_capture_limit_bytes: int = 64 * 1024 * 1024
    live_output_max_bytes: int = 256 * 1024
    retention_days: int = 395
    attempt_retention_days: int = 90
    worker_poll_seconds: float = 1.0
    worker_concurrency: int = 4
    lease_seconds: int = 60

    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"

    @field_validator("secret_keys")
    @classmethod
    def _valid_secret_keys(cls, value: str) -> str:
        parsed = json.loads(value)
        if not isinstance(parsed, dict) or not parsed:
            raise ValueError("secret_keys must be a non-empty JSON object")
        for version, encoded in parsed.items():
            try:
                raw = base64.b64decode(encoded, validate=True)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"secret version {version} is not valid base64") from exc
            if len(raw) != 32:
                raise ValueError(f"secret version {version} must decode to 32 bytes")
        return value

    @property
    def secret_key_ring(self) -> dict[int, bytes]:
        return {
            int(version): base64.b64decode(encoded)
            for version, encoded in json.loads(self.secret_keys).items()
        }

    @property
    def allowed_host_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
