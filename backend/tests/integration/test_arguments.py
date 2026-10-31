from __future__ import annotations

import sys

from task_control.worker.loop import register_worker, run_once


def test_arguments_are_appended_to_local_command(logged_in_client, tmp_path):
    script = tmp_path / "args.py"
    script.write_text("import sys\nprint(sys.argv[1:])\n")
    created = logged_in_client.post(
        "/api/v1/task-definitions",
        json={
            "key": "args-demo",
            "name": "Args Demo",
            "version": {
                "executor_type": "local",
                "executor_config": {"argv": [sys.executable, str(script)]},
                "timeout_seconds": 15,
                "retry_policy": {"max_attempts": 1},
                "max_concurrency": 1,
            },
        },
    )
    assert created.status_code == 201, created.text
    submitted = logged_in_client.post(
        "/api/v1/runs",
        json={
            "definition_id": created.json()["id"],
            "arguments": ["alice", "3", "hello world"],
        },
    )
    assert submitted.status_code == 201, submitted.text
    run_id = submitted.json()["id"]
    assert submitted.json()["arguments"] == ["alice", "3", "hello world"]

    worker = register_worker()
    assert run_once(worker) is True
    detail = logged_in_client.get(f"/api/v1/runs/{run_id}").json()
    assert detail["status"] == "succeeded"
    assert "hello world" in detail["attempts"][0]["stdout_excerpt"]
