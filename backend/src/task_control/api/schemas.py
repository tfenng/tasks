from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    field: str | None = None
    code: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    correlation_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(ORMModel):
    id: UUID
    username: str
    display_name: str
    role: str
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    version: int


class LoginResponse(BaseModel):
    user: UserOut
    csrf_token: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    role: Literal["admin", "operator", "viewer"]
    password: str = Field(min_length=12, max_length=256)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    role: Literal["admin", "operator", "viewer"] | None = None
    is_active: bool | None = None


class UserList(BaseModel):
    items: list[UserOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class PasswordResetResponse(BaseModel):
    temporary_password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=256)


class SessionOut(ORMModel):
    id: UUID
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


class SessionList(BaseModel):
    items: list[SessionOut]


class ApiTokenOut(ORMModel):
    id: UUID
    name: str
    token_prefix: str
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    expires_at: datetime | None = None


class ApiTokenCreated(ApiTokenOut):
    token: str


class ApiTokenList(BaseModel):
    items: list[ApiTokenOut]


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=1, ge=1, le=10)
    initial_backoff_seconds: int = Field(default=30, ge=1, le=3600)
    multiplier: float = Field(default=2.0, ge=1, le=10)
    max_backoff_seconds: int = Field(default=600, ge=1, le=86400)
    retry_on_exit_codes: list[int] = Field(default_factory=list)
    retryable_error_classes: list[str] = Field(
        default_factory=lambda: ["TIMEOUT", "CONNECTION", "HTTP_429", "HTTP_5XX", "WORKER_LOST"]
    )


class DefinitionVersionInput(BaseModel):
    executor_type: Literal["local", "ssh"] = "local"
    parameter_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}, "additionalProperties": True}
    )
    executor_config: dict[str, Any]
    timeout_seconds: int = Field(default=60, ge=1, le=86400)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    max_concurrency: int = Field(default=1, ge=1, le=100)


class DefinitionCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,99}$")
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    version: DefinitionVersionInput


class DefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    version: DefinitionVersionInput | None = None


class VersionOut(ORMModel):
    id: UUID
    definition_id: UUID
    version_no: int
    executor_type: str
    parameter_schema: dict[str, Any]
    executor_config: dict[str, Any]
    timeout_seconds: int
    retry_policy: dict[str, Any]
    max_concurrency: int
    checksum: str
    created_at: datetime


class DefinitionOut(BaseModel):
    id: UUID
    key: str
    name: str
    description: str | None
    is_archived: bool
    active_version: VersionOut | None
    created_at: datetime
    updated_at: datetime
    version: int


class DefinitionList(BaseModel):
    items: list[DefinitionOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class TriggerInput(BaseModel):
    type: Literal["immediate"] = "immediate"


class RunCreate(BaseModel):
    definition_id: UUID
    definition_version_id: UUID | None = None
    arguments: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    trigger: TriggerInput = Field(default_factory=TriggerInput)

    @field_validator("parameters")
    @classmethod
    def _parameters_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json

        if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 256 * 1024:
            raise ValueError("parameters too large")
        return value


class ScheduledTrigger(BaseModel):
    type: Literal["once", "cron", "interval"]
    fire_at: datetime | None = None
    cron_expr: str | None = None
    interval_seconds: int | None = Field(default=None, ge=10)


class ScheduleCreate(BaseModel):
    definition_id: UUID
    definition_version_id: UUID
    name: str = Field(min_length=1, max_length=120)
    trigger: ScheduledTrigger
    timezone: str = "UTC"
    arguments: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    overlap_policy: Literal["skip", "queue"] = "skip"
    misfire_grace_seconds: int = Field(default=3600, ge=0)


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    parameters: dict[str, Any] | None = None
    overlap_policy: Literal["skip", "queue"] | None = None
    misfire_grace_seconds: int | None = Field(default=None, ge=0)


class ScheduleOut(ORMModel):
    id: UUID
    definition_id: UUID
    definition_version_id: UUID
    name: str
    trigger_type: str
    fire_at: datetime | None
    cron_expr: str | None
    interval_seconds: int | None
    timezone: str
    arguments: list[str] = Field(default_factory=list)
    parameters: dict[str, Any]
    overlap_policy: str
    misfire_grace_seconds: int
    status: str
    next_fire_at: datetime | None
    last_fire_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class ScheduleList(BaseModel):
    items: list[ScheduleOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class RunOut(ORMModel):
    id: UUID
    definition_id: UUID
    definition_version_id: UUID
    schedule_id: UUID | None = None
    scheduled_for: datetime | None = None
    trigger_type: str
    status: str
    arguments: list[str] = Field(default_factory=list)
    parameters: dict[str, Any]
    attempt_count: int
    max_attempts: int
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    next_retry_at: datetime | None
    parent_run_id: UUID | None
    error_code: str | None
    error_message: str | None
    result_summary: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    version: int


class AttemptOut(ORMModel):
    id: UUID
    run_id: UUID
    attempt_no: int
    status: str
    executor_type: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    exit_code: int | None
    http_status: int | None
    error_class: str | None
    error_message: str | None
    stdout_excerpt: str | None
    stderr_excerpt: str | None
    response_excerpt: str | None = None
    truncated: bool


class RunDetail(RunOut):
    definition_key: str | None = None
    definition_name: str | None = None
    definition_version_no: int | None = None
    executor_type: str | None = None
    executor_config: dict[str, Any] | None = None
    parameter_schema: dict[str, Any] | None = None
    attempts: list[AttemptOut]


class RunList(BaseModel):
    items: list[RunOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class CredentialOut(BaseModel):
    id: UUID
    name: str
    kind: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    created_at: datetime
    updated_at: datetime
    version: int


class CredentialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["password", "ssh_key", "http_bearer", "http_basic"]
    secret: str = Field(min_length=1, max_length=10000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CredentialUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    secret: str | None = Field(default=None, max_length=10000)
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None


class TargetOut(ORMModel):
    id: UUID
    name: str
    type: str
    config: dict[str, Any]
    credential_id: UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    version: int


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: Literal["local", "ssh", "http"]
    config: dict[str, Any]
    credential_id: UUID | None = None


class TargetUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    config: dict[str, Any] | None = None
    credential_id: UUID | None = None
    is_active: bool | None = None


class TargetList(BaseModel):
    items: list[TargetOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class CredentialList(BaseModel):
    items: list[CredentialOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class StatsBucket(BaseModel):
    key: str
    total: int
    succeeded: int
    failed: int
    cancelled: int
    skipped: int
    missed: int
    success_rate: float
    avg_duration_ms: float | None = None
    p95_duration_ms: float | None = None


class RunStats(BaseModel):
    total: int
    succeeded: int
    failed: int
    cancelled: int
    skipped: int
    missed: int
    retrying: int
    success_rate: float
    avg_duration_ms: float | None = None
    p95_duration_ms: float | None = None
    buckets: list[StatsBucket] = Field(default_factory=list)


class AttemptStats(BaseModel):
    total: int
    succeeded: int
    failed: int
    timed_out: int
    cancelled: int
    success_rate: float
    avg_duration_ms: float | None = None
    buckets: list[StatsBucket] = Field(default_factory=list)


class AuditEventOut(ORMModel):
    id: int
    actor_user_id: UUID | None
    actor_username: str | None = None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    ip_address: str | None
    user_agent: str | None
    correlation_id: str
    details: dict[str, Any]
    created_at: datetime


class AuditEventList(BaseModel):
    items: list[AuditEventOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class ScriptEntry(BaseModel):
    name: str
    path: str
    type: Literal["file", "dir"]
    size: int | None = None


class ScriptList(BaseModel):
    root: str
    path: str
    parent: str | None
    items: list[ScriptEntry]


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, dict[str, str]] = Field(default_factory=dict)
