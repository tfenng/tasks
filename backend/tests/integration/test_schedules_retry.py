from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from task_control.infrastructure.db.models import Schedule, TaskRun
from task_control.infrastructure.db.session import SessionLocal
from task_control.scheduler.loop import run_once as scheduler_once
from task_control.worker.loop import register_worker
from task_control.worker.loop import run_once as worker_once


def _definition(client, script, *, key="scheduled-demo", max_attempts=1, exit_codes=None):
    payload = {
        "key": key,
        "name": "Scheduled Demo",
        "version": {
            "executor_type": "local",
            "parameter_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            "executor_config": {"argv": [sys.executable, str(script)]},
            "timeout_seconds": 15,
            "retry_policy": {
                "max_attempts": max_attempts,
                "initial_backoff_seconds": 1,
                "retry_on_exit_codes": exit_codes or [],
            },
            "max_concurrency": 1,
        },
    }
    response = client.post("/api/v1/task-definitions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_interval_schedule_creates_and_executes_run(logged_in_client, tmp_path):
    script = tmp_path / "ok.py"
    script.write_text("print('scheduled ok')\n")
    definition = _definition(logged_in_client, script)
    version = definition["active_version"]

    response = logged_in_client.post(
        "/api/v1/schedules",
        json={
            "definition_id": definition["id"],
            "definition_version_id": version["id"],
            "name": "every minute",
            "trigger": {"type": "interval", "interval_seconds": 60},
            "timezone": "UTC",
            "parameters": {"name": "bob"},
        },
    )
    assert response.status_code == 201, response.text
    schedule = response.json()
    assert schedule["next_fire_at"] is not None

    with SessionLocal() as db:
        db.execute(
            update(Schedule)
            .where(Schedule.id == schedule["id"])
            .values(next_fire_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.commit()

    created, promoted = scheduler_once()
    assert created == 1
    assert promoted == 0

    with SessionLocal() as db:
        run = db.query(TaskRun).filter(TaskRun.schedule_id == schedule["id"]).one()
        run_id = str(run.id)
        assert run.status == "queued"

    worker = register_worker()
    assert worker_once(worker) is True
    detail = logged_in_client.get(f"/api/v1/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "succeeded"
    assert "scheduled ok" in detail.json()["attempts"][0]["stdout_excerpt"]


def test_retry_wait_then_manual_retry(logged_in_client, tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("import sys\nprint('boom', file=sys.stderr)\nsys.exit(1)\n")
    definition = _definition(
        logged_in_client,
        script,
        key="retry-demo",
        max_attempts=2,
        exit_codes=[1],
    )
    submitted = logged_in_client.post(
        "/api/v1/runs",
        json={"definition_id": definition["id"], "parameters": {"name": "bob"}},
    )
    assert submitted.status_code == 201, submitted.text
    run_id = submitted.json()["id"]

    worker = register_worker()
    assert worker_once(worker) is True
    detail = logged_in_client.get(f"/api/v1/runs/{run_id}").json()
    assert detail["status"] == "retry_wait"
    assert detail["next_retry_at"] is not None

    with SessionLocal() as db:
        db.execute(
            update(TaskRun)
            .where(TaskRun.id == run_id)
            .values(next_retry_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.commit()

    scheduler_once()
    assert worker_once(worker) is True
    failed = logged_in_client.get(f"/api/v1/runs/{run_id}").json()
    assert failed["status"] == "failed"
    assert failed["attempt_count"] == 2

    retried = logged_in_client.post(f"/api/v1/runs/{run_id}/retry")
    assert retried.status_code == 201, retried.text
    new_run = retried.json()
    assert new_run["id"] != run_id
    assert new_run["status"] == "queued"
    assert new_run["parent_run_id"] == run_id


def test_once_schedule_without_fire_at_runs_immediately(logged_in_client, tmp_path):
    script = tmp_path / "once.py"
    script.write_text("print('once ok')\n")
    definition = _definition(logged_in_client, script, key="once-demo")
    response = logged_in_client.post(
        "/api/v1/schedules",
        json={
            "definition_id": definition["id"],
            "definition_version_id": definition["active_version"]["id"],
            "name": "once now",
            "trigger": {"type": "once"},
            "timezone": "UTC",
            "arguments": ["bob"],
        },
    )
    assert response.status_code == 201, response.text
    schedule = response.json()
    assert schedule["next_fire_at"] is not None

    scheduler_once()
    with SessionLocal() as db:
        run = db.query(TaskRun).filter(TaskRun.schedule_id == schedule["id"]).one()
        assert run.status == "queued"
        run_id = str(run.id)

    worker = register_worker()
    assert worker_once(worker) is True
    detail = logged_in_client.get(f"/api/v1/runs/{run_id}").json()
    assert detail["status"] == "succeeded"


def test_delete_schedule_keeps_run_history(logged_in_client, tmp_path):
    script = tmp_path / "delete_me.py"
    script.write_text("print('delete me')\n")
    definition = _definition(logged_in_client, script, key="delete-demo")
    version = definition["active_version"]

    response = logged_in_client.post(
        "/api/v1/schedules",
        json={
            "definition_id": definition["id"],
            "definition_version_id": version["id"],
            "name": "delete one",
            "trigger": {"type": "once"},
            "timezone": "UTC",
            "parameters": {"name": "bob"},
        },
    )
    assert response.status_code == 201, response.text
    schedule = response.json()

    scheduler_once()
    with SessionLocal() as db:
        run = db.query(TaskRun).filter(TaskRun.schedule_id == schedule["id"]).one()
        run_id = str(run.id)

    deleted = logged_in_client.delete(f"/api/v1/schedules/{schedule['id']}")
    assert deleted.status_code == 204, deleted.text

    with SessionLocal() as db:
        run = db.get(TaskRun, run_id)
        assert run is not None
        assert run.schedule_id is None

    detail = logged_in_client.get(f"/api/v1/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["schedule_id"] is None


def test_delete_all_schedules_keeps_runs(logged_in_client, tmp_path):
    script = tmp_path / "delete_all.py"
    script.write_text("print('delete all')\n")
    definition = _definition(logged_in_client, script, key="delete-all-demo")
    version = definition["active_version"]

    schedules = []
    for name in ("first", "second"):
        response = logged_in_client.post(
            "/api/v1/schedules",
            json={
                "definition_id": definition["id"],
                "definition_version_id": version["id"],
                "name": name,
                "trigger": {"type": "interval", "interval_seconds": 60},
                "timezone": "UTC",
                "parameters": {"name": "bob"},
            },
        )
        assert response.status_code == 201, response.text
        schedules.append(response.json())

    with SessionLocal() as db:
        db.execute(
            update(Schedule)
            .where(Schedule.id == schedules[0]["id"])
            .values(next_fire_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        db.commit()
    scheduler_once()
    with SessionLocal() as db:
        run = db.query(TaskRun).filter(TaskRun.schedule_id == schedules[0]["id"]).one()
        run_id = str(run.id)

    deleted = logged_in_client.delete("/api/v1/schedules")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 2

    listing = logged_in_client.get("/api/v1/schedules")
    assert listing.json()["total"] == 0

    with SessionLocal() as db:
        run = db.get(TaskRun, run_id)
        assert run is not None
        assert run.schedule_id is None
