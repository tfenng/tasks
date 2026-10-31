from __future__ import annotations

import sys
from pathlib import Path

from task_control.worker.loop import register_worker, run_once


def _definition_payload(script: Path) -> dict:
    return {
        "key": "demo-hello",
        "name": "Demo Hello",
        "description": "local demo",
        "version": {
            "executor_type": "local",
            "parameter_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "integer", "minimum": 1, "default": 1},
                    "token": {"type": "string", "x-secret": True, "writeOnly": True},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            "executor_config": {
                "argv": [sys.executable, str(script), "${count}"],
            },
            "timeout_seconds": 15,
            "retry_policy": {"max_attempts": 1},
            "max_concurrency": 1,
        },
    }


def test_auth_and_csrf(logged_in_client):
    assert logged_in_client.get("/api/v1/auth/me").json()["username"] == "admin"
    response = logged_in_client.post(
        "/api/v1/task-definitions",
        json={},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert response.status_code == 403


def test_create_definition_and_run(logged_in_client, tmp_path):
    script = tmp_path / "hello.py"
    script.write_text(
        "import os, sys\nprint('hello', os.environ['TASK_PARAM_NAME'])\nprint(sys.argv[1])\n"
    )
    created = logged_in_client.post("/api/v1/task-definitions", json=_definition_payload(script))
    assert created.status_code == 201, created.text
    definition = created.json()
    assert definition["active_version"]["version_no"] == 1

    invalid = logged_in_client.post(
        "/api/v1/runs",
        json={"definition_id": definition["id"], "parameters": {"count": 1}},
    )
    assert invalid.status_code == 422

    submitted = logged_in_client.post(
        "/api/v1/runs",
        json={
            "definition_id": definition["id"],
            "parameters": {"name": "alice", "count": 2, "token": "secret-value"},
        },
        headers={"Idempotency-Key": "demo-key-1"},
    )
    assert submitted.status_code == 201, submitted.text
    run = submitted.json()
    assert run["status"] == "queued"
    assert run["parameters"]["token"] == "***"

    duplicate = logged_in_client.post(
        "/api/v1/runs",
        json={
            "definition_id": definition["id"],
            "parameters": {"name": "alice", "count": 2, "token": "secret-value"},
        },
        headers={"Idempotency-Key": "demo-key-1"},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == run["id"]

    worker_id = register_worker()
    assert run_once(worker_id) is True

    detail = logged_in_client.get(f"/api/v1/runs/{run['id']}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "succeeded"
    assert body["definition_name"] == "Demo Hello"
    assert body["definition_version_no"] == 1
    assert body["executor_type"] == "local"
    assert "hello.py" in " ".join(body["executor_config"]["argv"])
    assert body["attempts"][0]["exit_code"] == 0
    assert "hello alice" in body["attempts"][0]["stdout_excerpt"]
    assert "secret-value" not in body["attempts"][0]["stdout_excerpt"]
