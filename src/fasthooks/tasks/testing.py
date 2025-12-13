"""
Testing utilities for background tasks.

Provides MockBackend and ImmediateBackend for testing hooks that use tasks.
"""

from inspect import iscoroutinefunction
from time import time
from typing import Any

import anyio

from .backend import BaseBackend
from .base import Task, TaskResult, TaskStatus


class ImmediateBackend(BaseBackend):
    """
    Backend that executes tasks immediately (synchronously).

    Useful for testing when you want tasks to complete before assertions.
    Tracks full lifecycle (status transitions, timestamps).

    Example:
        backend = ImmediateBackend()
        app = HookApp(task_backend=backend)

        # Tasks complete immediately
        client = TestClient(app)
        response = client.send(MockEvent.bash(command="ls"))

        # Results are immediately available
        assert backend.get("session", "key").status == TaskStatus.COMPLETED
    """

    def __init__(self) -> None:
        self.results: dict[str, TaskResult] = {}

    def _result_key(self, session_id: str, key: str) -> str:
        return f"{session_id}:{key}"

    def _cleanup_expired(self) -> None:
        """Remove expired results."""
        now = time()
        expired = [k for k, v in self.results.items() if now - v.created_at > v.ttl]
        for k in expired:
            del self.results[k]

    def enqueue(
        self,
        task: Task,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        session_id: str,
        key: str,
    ) -> TaskResult:
        """Execute task immediately (synchronous)."""
        self._cleanup_expired()

        result_key = self._result_key(session_id, key)
        task_result = task._create_result(session_id, key)
        task_result.set_running()

        try:
            if iscoroutinefunction(task.func):
                # Run async function synchronously with new event loop
                result = anyio.run(lambda: task.func(*args, **kwargs))
            else:
                result = task.func(*args, **kwargs)

            if task.transform:
                result = task.transform(result)

            task_result.set_completed(result)

        except Exception as e:
            task_result.set_failed(e)

        self.results[result_key] = task_result
        return task_result

    def get(self, session_id: str, key: str) -> TaskResult | None:
        self._cleanup_expired()
        return self.results.get(self._result_key(session_id, key))

    def pop(self, session_id: str, key: str) -> Any | None:
        self._cleanup_expired()
        result_key = self._result_key(session_id, key)
        task_result = self.results.get(result_key)

        if task_result and task_result.status == TaskStatus.COMPLETED:
            del self.results[result_key]
            return task_result.value
        return None

    def pop_all(self, session_id: str) -> list[Any]:
        self._cleanup_expired()
        values = []
        keys_to_remove = []

        for result_key, task_result in self.results.items():
            if (
                task_result.session_id == session_id
                and task_result.status == TaskStatus.COMPLETED
            ):
                values.append(task_result.value)
                keys_to_remove.append(result_key)

        for k in keys_to_remove:
            del self.results[k]

        return values

    def pop_errors(self, session_id: str) -> list[tuple[str, Exception]]:
        self._cleanup_expired()
        errors = []
        keys_to_remove = []

        for result_key, task_result in self.results.items():
            if (
                task_result.session_id == session_id
                and task_result.status == TaskStatus.FAILED
                and task_result.error is not None
            ):
                errors.append((task_result.key, task_result.error))
                keys_to_remove.append(result_key)

        for k in keys_to_remove:
            del self.results[k]

        return errors

    def has(self, session_id: str, key: str | None = None) -> bool:
        self._cleanup_expired()

        if key is not None:
            result_key = self._result_key(session_id, key)
            task_result = self.results.get(result_key)
            return (
                task_result is not None
                and task_result.status == TaskStatus.COMPLETED
            )

        return any(
            r.session_id == session_id and r.status == TaskStatus.COMPLETED
            for r in self.results.values()
        )

    def cancel(self, session_id: str, key: str) -> bool:
        result_key = self._result_key(session_id, key)
        task_result = self.results.get(result_key)

        if task_result and not task_result.is_finished:
            task_result.set_cancelled()
            return True
        return False

    def cancel_all(self, session_id: str) -> int:
        cancelled = 0
        for task_result in self.results.values():
            if task_result.session_id == session_id and not task_result.is_finished:
                task_result.set_cancelled()
                cancelled += 1
        return cancelled

    async def wait(
        self, session_id: str, key: str, timeout: float = 30.0
    ) -> Any | None:
        # Immediate backend - result is already available
        task_result = self.get(session_id, key)
        if task_result and task_result.status == TaskStatus.COMPLETED:
            return task_result.value
        return None

    async def wait_all(
        self, session_id: str, keys: list[str], timeout: float = 30.0
    ) -> dict[str, Any]:
        results = {}
        for key in keys:
            task_result = self.get(session_id, key)
            if task_result and task_result.status == TaskStatus.COMPLETED:
                results[key] = task_result.value
        return results

    async def wait_any(
        self, session_id: str, keys: list[str], timeout: float = 30.0
    ) -> tuple[str, Any] | None:
        for key in keys:
            task_result = self.get(session_id, key)
            if task_result and task_result.status == TaskStatus.COMPLETED:
                return (key, task_result.value)
        return None


# Alias for convenience
MockBackend = ImmediateBackend
