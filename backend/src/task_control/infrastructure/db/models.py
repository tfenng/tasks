from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint("role IN ('admin','operator','viewer')", name="role"),
        Index("ux_users_username_lower", text("lower(username)"), unique=True),
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    csrf_token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_sessions_user", "user_id", "revoked_at"),)


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (Index("ix_api_tokens_user", "user_id", "revoked_at"),)


class TaskDefinition(Base):
    __tablename__ = "task_definitions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_version_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "task_definition_versions.id",
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_task_definitions_active_version_id",
        ),
        nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    versions: Mapped[list[TaskDefinitionVersion]] = relationship(
        back_populates="definition", foreign_keys="TaskDefinitionVersion.definition_id"
    )

    __table_args__ = (
        CheckConstraint("is_archived = (archived_at IS NOT NULL)", name="archive_state"),
    )


class TaskDefinitionVersion(Base):
    __tablename__ = "task_definition_versions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    definition_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    executor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    parameter_schema: Mapped[dict] = mapped_column(JSONB, nullable=False)
    executor_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_policy: Mapped[dict] = mapped_column(JSONB, nullable=False)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    definition: Mapped[TaskDefinition] = relationship(
        back_populates="versions", foreign_keys=[definition_id]
    )

    __table_args__ = (
        UniqueConstraint("definition_id", "version_no", name="uq_definition_version"),
        CheckConstraint("executor_type IN ('local','ssh','http')", name="executor_type"),
        CheckConstraint("timeout_seconds BETWEEN 1 AND 86400", name="timeout"),
        CheckConstraint("max_concurrency BETWEEN 1 AND 100", name="concurrency"),
    )


class TaskDefinitionRuntime(Base):
    __tablename__ = "task_definition_runtime"

    definition_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_definitions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    running_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint("running_count >= 0", name="running_count"),
        CheckConstraint("max_concurrency BETWEEN 1 AND 100", name="concurrency"),
    )


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint("kind IN ('password','ssh_key','http_bearer','http_basic')", name="kind"),
    )


class ExecutionTarget(Base):
    __tablename__ = "execution_targets"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    credential_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credentials.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (CheckConstraint("type IN ('local','ssh','http')", name="type"),)


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    definition_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    definition_version_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_definition_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)
    fire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cron_expr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    parameters_redacted: Mapped[dict] = mapped_column(JSONB, nullable=False)
    overlap_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="skip")
    misfire_grace_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    next_fire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint("trigger_type IN ('once','cron','interval')", name="trigger_type"),
        CheckConstraint("status IN ('active','paused','completed','cancelled')", name="status"),
        CheckConstraint("overlap_policy IN ('skip','queue')", name="overlap"),
        CheckConstraint(
            "trigger_type = 'once' OR ("
            "trigger_type = 'cron' AND cron_expr IS NOT NULL"
            ") OR ("
            "trigger_type = 'interval' AND interval_seconds IS NOT NULL"
            ")",
            name="trigger_config",
        ),
        CheckConstraint("status <> 'active' OR next_fire_at IS NOT NULL", name="active_next_fire"),
        CheckConstraint("interval_seconds IS NULL OR interval_seconds >= 10", name="interval_min"),
        CheckConstraint("misfire_grace_seconds >= 0", name="grace"),
        Index("ix_schedules_due", "next_fire_at", postgresql_where=text("status = 'active'")),
        Index("ix_schedules_definition", "definition_id", "created_at"),
    )


class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (CheckConstraint("role IN ('worker','scheduler')", name="role"),)


class TaskRun(Base):
    __tablename__ = "runs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    definition_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("task_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    definition_version_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_definition_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    schedule_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False, default="immediate")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    parameters_redacted: Mapped[dict] = mapped_column(JSONB, nullable=False)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    worker_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workers.id", ondelete="SET NULL"), nullable=True
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parent_run_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_requested_by: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'scheduled','queued','running','retry_wait','succeeded',"
            "'failed','cancelled','skipped','missed'"
            ")",
            name="status",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count"),
        CheckConstraint("attempt_count <= max_attempts", name="attempt_limit"),
        Index(
            "uq_runs_idempotency",
            "created_by",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_runs_queue", "queued_at", "id", postgresql_where=text("status = 'queued'")),
        Index(
            "uq_runs_schedule_occurrence",
            "schedule_id",
            "scheduled_for",
            unique=True,
            postgresql_where=text("schedule_id IS NOT NULL"),
        ),
        Index("ix_runs_definition_time", "definition_id", "created_at"),
        Index("ix_runs_schedule_time", "schedule_id", "scheduled_for"),
        Index("ix_runs_status_time", "status", "created_at"),
        Index("ix_runs_lease", "lease_expires_at", postgresql_where=text("status = 'running'")),
        Index("ix_runs_retention", "created_at"),
    )


class TaskAttempt(Base):
    __tablename__ = "attempts"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    executor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    worker_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workers.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        UniqueConstraint("run_id", "attempt_no", name="uq_attempt_no"),
        CheckConstraint(
            "status IN ('running','succeeded','failed','timed_out','cancelled')", name="status"
        ),
        Index("ix_attempt_run", "run_id", "attempt_no"),
        Index("ix_attempt_created", "created_at"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="success")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint("outcome IN ('success','failure','denied')", name="outcome"),
        Index("ix_audit_time", "created_at"),
        Index("ix_audit_actor", "actor_user_id", "created_at"),
        Index("ix_audit_resource", "resource_type", "resource_id", "created_at"),
    )
