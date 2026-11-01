from __future__ import annotations

import sys
from pathlib import Path

from task_control.infrastructure.db.models import TaskAttempt, TaskRun
from task_control.infrastructure.db.session import SessionLocal
from task_control.infrastructure.executors.output import attempt_dir
from task_control.worker.loop import claim_run, register_worker, run_once


def _definition(client, script: Path, key: str) -> dict:
    response = client.post(
        "/api/v1/task-definitions",
        json={
            "key": key,
            "name": key,
            "version": {
                "executor_type": "local",
                "parameter_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "executor_config": {"argv": [sys.executable, str(script)]},
                "timeout_seconds": 15,
                "retry_policy": {"max_attempts": 1},
                "max_concurrency": 1,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _submit(client, definition: dict) -> dict:
    response = client.post(
        "/api/v1/runs",
        json={
            "definition_id": definition["id"],
            "definition_version_id": definition["active_version"]["id"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_delete_definition_keeps_finished_runs(logged_in_client, tmp_path):
    script = tmp_path / "keep.py"
    script.write_text("print('keep me')\n")
    definition = _definition(logged_in_client, script, "delete-keep")
    run = _submit(logged_in_client, definition)
    worker = register_worker()
    assert run_once(worker) is True

    deleted = logged_in_client.delete(f"/api/v1/task-definitions/{definition['id']}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"archived": True, "deleted_runs": 0}

    archived = logged_in_client.get(f"/api/v1/task-definitions/{definition['id']}")
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True

    detail = logged_in_client.get(f"/api/v1/runs/{run['id']}")
    assert detail.status_code == 200
    assert detail.json()["definition_name"] == "delete-keep"

    listing = logged_in_client.get("/api/v1/task-definitions?archived=false")
    assert listing.json()["total"] == 0


def test_delete_definition_with_runs(logged_in_client, tmp_path):
    script = tmp_path / "purge.py"
    script.write_text("print('purge me')\n")
    definition = _definition(logged_in_client, script, "delete-purge")
    run = _submit(logged_in_client, definition)
    worker = register_worker()
    assert run_once(worker) is True

    with SessionLocal() as db:
        assert db.query(TaskAttempt).filter(TaskAttempt.run_id == run["id"]).count() == 1

    deleted = logged_in_client.delete(
        f"/api/v1/task-definitions/{definition['id']}?delete_runs=true"
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_runs"] == 1

    assert logged_in_client.get(f"/api/v1/runs/{run['id']}").status_code == 404
    with SessionLocal() as db:
        assert db.get(TaskRun, run["id"]) is None
        assert db.query(TaskAttempt).filter(TaskAttempt.run_id == run["id"]).count() == 0
    assert not attempt_dir(run["id"], 1).exists()


def test_delete_definition_blocks_running_runs(logged_in_client, tmp_path):
    script = tmp_path / "running.py"
    script.write_text("print('running')\n")
    definition = _definition(logged_in_client, script, "delete-running")
    run = _submit(logged_in_client, definition)
    worker = register_worker()
    claimed = claim_run(worker)
    assert claimed is not None and str(claimed.run_id) == run["id"]

    deleted = logged_in_client.delete(f"/api/v1/task-definitions/{definition['id']}")
    assert deleted.status_code == 409, deleted.text
    assert deleted.json()["error"]["code"] == "CONFLICT_VERSION"
