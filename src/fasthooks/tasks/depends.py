"""
Dependency injection classes for background tasks.

These classes are injected into handlers via type hints, similar to
Transcript and State in fasthooks.depends.
"""

from collections.abc import Callable
from typing import Any

from .backend import BaseBackend
from .base import Task, TaskResult


class BackgroundTasks:
    """
    FastAPI-style task enqueueing dependency.

    Injected into handlers to allow adding background tasks.

    Usage:
        @app.pre_tool("Write")
        def on_write(event, tasks: BackgroundTasks):
            tasks.add(review_code, event.content, key="review")
            return allow()
    """

    def __init__(self, backend: BaseBackend, session_id: str):
        self._backend = backend
        self._session_id = session_id

    def add(
        self,
        func: Callable[..., Any] | Task,
        *args: Any,
        key: str,
        ttl: int = 300,
        **kwargs: Any,
    ) -> TaskResult:
        """
        Add a task to be executed in the background.

        Args:
            func: The function or Task to execute
            *args: Positional arguments for the function
            key: Unique key for this task (used to retrieve results)
            ttl: Time-to-live in seconds for the result (default 300)
            **kwargs: Keyword arguments for the function

        Returns:
            TaskResult with status 'pending'
        """
        if isinstance(func, Task):
            task = func
        else:
            task = Task(func=func, ttl=ttl)

        return self._backend.enqueue(
            task,
            args,
            kwargs,
            session_id=self._session_id,
            key=key,
        )

    def cancel(self, key: str) -> bool:
        """Cancel a pending/running task by key."""
        return self._backend.cancel(self._session_id, key)

    def cancel_all(self) -> int:
        """Cancel all tasks for this session. Returns count cancelled."""
        return self._backend.cancel_all(self._session_id)


class PendingResults:
    """
    Access to completed background task results.

    Injected into handlers to retrieve results from previous tasks.

    Usage:
        @app.on_prompt()
        def check_memory(event, pending: PendingResults):
            if result := pending.pop("memory"):
                return allow(message=f"Found: {result}")
            return allow()
    """

    def __init__(self, backend: BaseBackend, session_id: str):
        self._backend = backend
        self._session_id = session_id

    def get(self, key: str) -> TaskResult | None:
        """Get a task result without removing it."""
        return self._backend.get(self._session_id, key)

    def pop(self, key: str) -> Any | None:
        """
        Pop a completed result value, removing it from storage.

        Returns None if task not found or not yet completed.
        """
        return self._backend.pop(self._session_id, key)

    def pop_all(self) -> list[Any]:
        """Pop all completed results for this session."""
        return self._backend.pop_all(self._session_id)

    def pop_errors(self) -> list[tuple[str, Exception]]:
        """Pop all failed results, returning (key, error) pairs."""
        return self._backend.pop_errors(self._session_id)

    def has(self, key: str | None = None) -> bool:
        """
        Check if there are completed results.

        Args:
            key: Specific task key to check, or None to check any
        """
        return self._backend.has(self._session_id, key)

    async def wait(self, key: str, timeout: float = 30.0) -> Any | None:
        """
        Wait for a specific task to complete.

        Args:
            key: Task key to wait for
            timeout: Maximum seconds to wait

        Returns:
            Task result value, or None if timeout/failed/cancelled
        """
        return await self._backend.wait(self._session_id, key, timeout)

    async def wait_all(
        self,
        keys: list[str],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Wait for multiple tasks to complete.

        Args:
            keys: List of task keys to wait for
            timeout: Maximum seconds to wait

        Returns:
            Dict of key -> value for completed tasks
        """
        return await self._backend.wait_all(self._session_id, keys, timeout)

    async def wait_any(
        self,
        keys: list[str],
        timeout: float = 30.0,
    ) -> tuple[str, Any] | None:
        """
        Wait for any task to complete.

        Args:
            keys: List of task keys to wait for
            timeout: Maximum seconds to wait

        Returns:
            (key, value) tuple for first completed task, or None
        """
        return await self._backend.wait_any(self._session_id, keys, timeout)
