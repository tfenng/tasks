from __future__ import annotations

import sys
from pathlib import Path

from task_control.infrastructure.executors.base import ExecutionContext
from task_control.infrastructure.executors.local import LocalScriptExecutor


def test_local_executor_success(tmp_path: Path):
    script = tmp_path / "hello.py"
    script.write_text(
        "import os, sys\nprint('hello', os.environ['TASK_PARAM_NAME'])\nprint(sys.argv[1])\n"
    )
    result = LocalScriptExecutor().execute(
        ExecutionContext(
            run_id="r1",
            attempt_no=1,
            parameters={"name": "alice", "count": 2},
            target={
                "argv": [sys.executable, str(script), "${count}"],
            },
            timeout_seconds=10,
            output_limit_bytes=1024,
        )
    )
    assert result.status == "succeeded"
    assert "hello alice" in (result.stdout or "")
    assert "2" in (result.stdout or "")


def test_local_executor_nonzero_exit(tmp_path: Path):
    script = tmp_path / "fail.py"
    script.write_text("import sys\nprint('bad', file=sys.stderr)\nsys.exit(3)\n")
    result = LocalScriptExecutor().execute(
        ExecutionContext(
            run_id="r2",
            attempt_no=1,
            parameters={},
            target={"argv": [sys.executable, str(script)]},
            timeout_seconds=10,
            output_limit_bytes=1024,
        )
    )
    assert result.status == "failed"
    assert result.exit_code == 3
    assert result.error_class == "EXIT_CODE"


def test_local_executor_redacts_secret(tmp_path: Path):
    script = tmp_path / "secret.py"
    script.write_text("print('secret-value')\n")
    result = LocalScriptExecutor().execute(
        ExecutionContext(
            run_id="r3",
            attempt_no=1,
            parameters={"token": "secret-value"},
            target={"argv": [sys.executable, str(script)]},
            timeout_seconds=10,
            output_limit_bytes=1024,
            secret_values=("secret-value",),
        )
    )
    assert "secret-value" not in (result.stdout or "")
    assert "***" in (result.stdout or "")


def test_local_executor_uses_shebang_when_interpreter_auto(tmp_path: Path):
    script = tmp_path / "shebang.py"
    script.write_text("#!/usr/bin/env python3\nprint('shebang ok')\n")
    result = LocalScriptExecutor().execute(
        ExecutionContext(
            run_id="r4",
            attempt_no=1,
            parameters={},
            target={"argv": [str(script)]},
            timeout_seconds=10,
            output_limit_bytes=1024,
        )
    )
    assert result.status == "succeeded"
    assert "shebang ok" in (result.stdout or "")


def test_local_executor_falls_back_to_bash_without_shebang(tmp_path: Path):
    script = tmp_path / "plain.sh"
    script.write_text("echo shell ok\n")
    result = LocalScriptExecutor().execute(
        ExecutionContext(
            run_id="r5",
            attempt_no=1,
            parameters={},
            target={"argv": [str(script)]},
            timeout_seconds=10,
            output_limit_bytes=1024,
        )
    )
    assert result.status == "succeeded"
    assert "shell ok" in (result.stdout or "")


def test_local_executor_infers_python_for_py_without_shebang(tmp_path: Path):
    script = tmp_path / "plain.py"
    script.write_text("print('python fallback ok')\n")
    result = LocalScriptExecutor().execute(
        ExecutionContext(
            run_id="r6",
            attempt_no=1,
            parameters={},
            target={"argv": [str(script)]},
            timeout_seconds=10,
            output_limit_bytes=1024,
        )
    )
    assert result.status == "succeeded"
    assert "python fallback ok" in (result.stdout or "")
