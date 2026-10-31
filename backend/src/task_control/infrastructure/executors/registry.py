from __future__ import annotations

from task_control.infrastructure.executors.base import TaskExecutor
from task_control.infrastructure.executors.http import HttpExecutor
from task_control.infrastructure.executors.local import LocalScriptExecutor
from task_control.infrastructure.executors.ssh import SshExecutor


class ExecutorRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, type[TaskExecutor]] = {}
        self.register("local", LocalScriptExecutor)
        self.register("http", HttpExecutor)
        self.register("ssh", SshExecutor)

    def register(self, executor_type: str, factory: type[TaskExecutor]) -> None:
        self._factories[executor_type] = factory

    def create(self, executor_type: str) -> TaskExecutor:
        factory = self._factories.get(executor_type)
        if factory is None:
            raise ValueError(f"unsupported executor type: {executor_type}")
        return factory()


registry = ExecutorRegistry()
