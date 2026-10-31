from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from task_control.api.schemas import CredentialCreate, CredentialUpdate, TargetCreate, TargetUpdate
from task_control.application.audit.service import record_audit
from task_control.domain.errors import (
    ConflictError,
    NotFoundError,
    TargetDisabledError,
    ValidationError,
)
from task_control.infrastructure.db.models import (
    Credential,
    ExecutionTarget,
    TaskDefinitionRuntime,
    TaskDefinitionVersion,
    TaskRun,
    User,
)
from task_control.infrastructure.security.secrets import get_secret_box

_CREDENTIAL_KIND_BY_TARGET = {
    "ssh": {"password", "ssh_key"},
    "http": {"http_bearer", "http_basic"},
}


def _target_validation(
    db: Session, target_type: str, config: dict, credential_id: UUID | None
) -> None:
    if not isinstance(config, dict):
        raise ValidationError("target config must be an object")
    if target_type == "local":
        if credential_id is not None:
            raise ValidationError("local target cannot have a credential")
        if not isinstance(config.get("script_root", ""), str):
            raise ValidationError("local target script_root must be a string")
        return
    if candidate := _CREDENTIAL_KIND_BY_TARGET.get(target_type):
        if credential_id is None:
            raise ValidationError(f"{target_type} target requires a credential")
        credential = db.get(Credential, credential_id)
        if credential is None or not credential.is_active:
            raise ValidationError("credential not found or inactive")
        if credential.kind not in candidate:
            raise ValidationError(f"credential kind {credential.kind} is invalid for {target_type}")
    if target_type == "ssh" and (not config.get("host") or not config.get("user")):
        raise ValidationError("ssh target requires host and user")
    if target_type == "http":
        if not config.get("base_url"):
            raise ValidationError("http target requires base_url")
        if not str(config["base_url"]).startswith(("http://", "https://")):
            raise ValidationError("http base_url must use http or https")


def create_target(
    db: Session, actor: User, payload: TargetCreate, *, correlation_id: str = "-"
) -> ExecutionTarget:
    _target_validation(db, payload.type, payload.config, payload.credential_id)
    target = ExecutionTarget(
        id=uuid4(),
        name=payload.name,
        type=payload.type,
        config=payload.config,
        credential_id=payload.credential_id,
        created_by=actor.id,
    )
    db.add(target)
    record_audit(
        db,
        actor,
        "target.create",
        "execution_target",
        str(target.id),
        correlation_id=correlation_id,
        details={"type": target.type},
    )
    db.flush()
    return target


def get_target(db: Session, target_id: UUID) -> ExecutionTarget:
    target = db.get(ExecutionTarget, target_id)
    if target is None:
        raise NotFoundError("target not found")
    return target


def list_targets(
    db: Session, *, page: int, page_size: int, type_filter: str | None = None
) -> tuple[list[ExecutionTarget], int]:
    stmt = select(ExecutionTarget)
    count_stmt = select(func.count()).select_from(ExecutionTarget)
    if type_filter:
        stmt = stmt.where(ExecutionTarget.type == type_filter)
        count_stmt = count_stmt.where(ExecutionTarget.type == type_filter)
    total = db.scalar(count_stmt) or 0
    items = list(
        db.scalars(
            stmt.order_by(ExecutionTarget.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


def update_target(
    db: Session,
    actor: User,
    target: ExecutionTarget,
    payload: TargetUpdate,
    expected_version: int,
    *,
    correlation_id: str = "-",
) -> ExecutionTarget:
    if target.version != expected_version:
        raise ConflictError("target version conflict")
    new_config = payload.config if payload.config is not None else target.config
    new_credential = (
        payload.credential_id
        if "credential_id" in payload.model_fields_set
        else target.credential_id
    )
    _target_validation(db, target.type, new_config, new_credential)
    target.name = payload.name or target.name
    target.config = new_config
    target.credential_id = new_credential
    if payload.is_active is not None:
        target.is_active = payload.is_active
        if not target.is_active:
            _fail_affected_runs(db, target_id=target.id)
    target.version += 1
    target.updated_at = datetime.now(UTC)
    record_audit(
        db,
        actor,
        "target.update",
        "execution_target",
        str(target.id),
        correlation_id=correlation_id,
    )
    return target


def _fail_affected_runs(
    db: Session, *, target_id: UUID | None = None, credential_id: UUID | None = None
) -> int:
    stmt = select(TaskRun).where(TaskRun.status.in_(["queued", "retry_wait"]))
    if target_id is not None:
        stmt = stmt.where(TaskRun.target_snapshot["target_id"].astext == str(target_id))
    if credential_id is not None:
        stmt = stmt.where(TaskRun.target_snapshot["credential_id"].astext == str(credential_id))
    runs = list(db.scalars(stmt))
    now = datetime.now(UTC)
    for run in runs:
        run.status = "failed"
        run.error_code = "TARGET_DISABLED"
        run.error_message = "execution target or credential disabled"
        run.finished_at = now
        run.version += 1
        runtime = db.get(TaskDefinitionRuntime, run.definition_id)
        if runtime is not None and runtime.running_count > 0 and run.status == "running":
            runtime.running_count -= 1
    return len(runs)


def create_credential(
    db: Session, actor: User, payload: CredentialCreate, *, correlation_id: str = "-"
) -> Credential:
    credential_id = uuid4()
    box = get_secret_box()
    encrypted = box.encrypt(payload.secret, aad=f"credential:{credential_id}:{payload.kind}")
    credential = Credential(
        id=credential_id,
        name=payload.name,
        kind=payload.kind,
        ciphertext=json.dumps(encrypted).encode("utf-8"),
        key_version=int(encrypted["key_version"]),
        metadata_json=payload.metadata,
        created_by=actor.id,
    )
    db.add(credential)
    record_audit(
        db,
        actor,
        "credential.create",
        "credential",
        str(credential.id),
        correlation_id=correlation_id,
        details={"kind": credential.kind},
    )
    db.flush()
    return credential


def get_credential(db: Session, credential_id: UUID) -> Credential:
    credential = db.get(Credential, credential_id)
    if credential is None:
        raise NotFoundError("credential not found")
    return credential


def list_credentials(db: Session, *, page: int, page_size: int) -> tuple[list[Credential], int]:
    total = db.scalar(select(func.count()).select_from(Credential)) or 0
    items = list(
        db.scalars(
            select(Credential)
            .order_by(Credential.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


def update_credential(
    db: Session,
    actor: User,
    credential: Credential,
    payload: CredentialUpdate,
    expected_version: int,
    *,
    correlation_id: str = "-",
) -> Credential:
    if credential.version != expected_version:
        raise ConflictError("credential version conflict")
    if payload.name is not None:
        credential.name = payload.name
    if payload.metadata is not None:
        credential.metadata_json = payload.metadata
    if payload.secret is not None:
        box = get_secret_box()
        encrypted = box.encrypt(payload.secret, aad=f"credential:{credential.id}:{credential.kind}")
        credential.ciphertext = json.dumps(encrypted).encode("utf-8")
        credential.key_version = int(encrypted["key_version"])
    if payload.is_active is not None:
        credential.is_active = payload.is_active
        if not credential.is_active:
            _fail_affected_runs(db, credential_id=credential.id)
    credential.version += 1
    credential.updated_at = datetime.now(UTC)
    record_audit(
        db,
        actor,
        "credential.update",
        "credential",
        str(credential.id),
        correlation_id=correlation_id,
    )
    return credential


def credential_values(db: Session, credential_id: UUID) -> dict:
    credential = get_credential(db, credential_id)
    if not credential.is_active:
        raise TargetDisabledError("credential is disabled")
    box = get_secret_box()
    payload = json.loads(credential.ciphertext.decode("utf-8"))
    secret = box.decrypt(payload, aad=f"credential:{credential.id}:{credential.kind}")
    if credential.kind == "password":
        return {"password": secret}
    if credential.kind == "ssh_key":
        return {"private_key": secret, "passphrase": credential.metadata_json.get("passphrase")}
    if credential.kind == "http_bearer":
        return {"token": secret}
    if credential.kind == "http_basic":
        return {"username": credential.metadata_json.get("username"), "password": secret}
    raise ValidationError("unsupported credential kind")


def delete_target(
    db: Session,
    actor: User,
    target: ExecutionTarget,
    expected_version: int,
    *,
    correlation_id: str = "-",
) -> None:
    if target.version != expected_version:
        raise ConflictError("target version conflict")
    active_run = db.scalar(
        select(TaskRun.id)
        .where(
            TaskRun.status.in_(["queued", "running", "retry_wait"]),
            TaskRun.target_snapshot["target_id"].astext == str(target.id),
        )
        .limit(1)
    )
    if active_run is not None:
        raise ValidationError("target has active runs; cancel them first")
    referenced = db.scalar(
        select(TaskDefinitionVersion.id)
        .where(TaskDefinitionVersion.executor_config["target_id"].astext == str(target.id))
        .limit(1)
    )
    if referenced is not None:
        raise ValidationError("target is referenced by a task definition version")
    record_audit(
        db,
        actor,
        "target.delete",
        "execution_target",
        str(target.id),
        correlation_id=correlation_id,
        details={"name": target.name, "type": target.type},
    )
    db.delete(target)


def delete_credential(
    db: Session,
    actor: User,
    credential: Credential,
    expected_version: int,
    *,
    correlation_id: str = "-",
) -> None:
    if credential.version != expected_version:
        raise ConflictError("credential version conflict")
    target = db.scalar(
        select(ExecutionTarget.id).where(ExecutionTarget.credential_id == credential.id).limit(1)
    )
    if target is not None:
        raise ValidationError("credential is referenced by an execution target")
    active_run = db.scalar(
        select(TaskRun.id)
        .where(
            TaskRun.status.in_(["queued", "running", "retry_wait"]),
            TaskRun.target_snapshot["credential_id"].astext == str(credential.id),
        )
        .limit(1)
    )
    if active_run is not None:
        raise ValidationError("credential has active runs; cancel them first")
    record_audit(
        db,
        actor,
        "credential.delete",
        "credential",
        str(credential.id),
        correlation_id=correlation_id,
        details={"name": credential.name, "kind": credential.kind},
    )
    db.delete(credential)


def build_target_snapshot(db: Session, executor_config: dict) -> dict:
    target_id = executor_config.get("target_id")
    if not target_id:
        return executor_config
    target = get_target(db, UUID(str(target_id)))
    if not target.is_active:
        raise TargetDisabledError("target is disabled")
    snapshot = {
        "type": target.type,
        "target_id": str(target.id),
        "name": target.name,
        "config": target.config,
        "executor": {k: v for k, v in executor_config.items() if k != "target_id"},
    }
    if target.credential_id is not None:
        snapshot["credential_id"] = str(target.credential_id)
    return snapshot
