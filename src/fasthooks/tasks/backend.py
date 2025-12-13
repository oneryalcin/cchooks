"""
Task backends for executing background tasks.
"""

from abc import ABC, abstractmethod
from concurrent.futures import Future, ThreadPoolExecutor
from inspect import iscoroutinefunction
from threading import Lock
from time import time
from typing import Any

import anyio

from .base import Task, TaskResult, TaskStatus


class BaseBackend(ABC):
    """Abstract base class for task backends."""

    @abstractmethod
    def enqueue(
        self,
        task: Task,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        session_id: str,
        key: str,
    ) -> TaskResult:
        """Enqueue a task for execution."""

    @abstractmethod
    def get(self, session_id: str, key: str) -> TaskResult | None:
        """Get a task result by session and key."""

    @abstractmethod
    def pop(self, session_id: str, key: str) -> Any | None:
        """Pop a completed result value, removing it from storage."""

    @abstractmethod
    def pop_all(self, session_id: str) -> list[Any]:
        """Pop all completed results for a session."""

    @abstractmethod
    def cancel(self, session_id: str, key: str) -> bool:
        """Cancel a pending/running task."""

    @abstractmethod
    def cancel_all(self, session_id: str) -> int:
        """Cancel all tasks for a session. Returns count cancelled."""

    @abstractmethod
    def pop_errors(self, session_id: str) -> list[tuple[str, Exception]]:
        """Pop all failed results for a session, returning (key, error) pairs."""

    @abstractmethod
    def has(self, session_id: str, key: str | None = None) -> bool:
        """Check if there are any completed results."""

    @abstractmethod
    async def wait(
        self,
        session_id: str,
        key: str,
        timeout: float = 30.0,
    ) -> Any | None:
        """Wait for a specific task to complete."""

    @abstractmethod
    async def wait_all(
        self,
        session_id: str,
        keys: list[str],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Wait for multiple tasks to complete. Returns dict of key -> value."""

    @abstractmethod
    async def wait_any(
        self,
        session_id: str,
        keys: list[str],
        timeout: float = 30.0,
    ) -> tuple[str, Any] | None:
        """Wait for any task to complete. Returns (key, value) or None."""


class InMemoryBackend(BaseBackend):
    """
    In-memory task backend using ThreadPoolExecutor.

    Tasks are executed in a thread pool and results are stored in memory.
    Results are automatically cleaned up when expired (lazy cleanup on access).
    """

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.results: dict[str, TaskResult] = {}
        self.futures: dict[str, Future[Any]] = {}
        self._lock = Lock()

    def _result_key(self, session_id: str, key: str) -> str:
        """Create a unique key for storing results."""
        return f"{session_id}:{key}"

    def _cleanup_expired(self) -> None:
        """Remove expired results (called lazily on access)."""
        now = time()
        with self._lock:
            expired = [
                k for k, v in self.results.items() if now - v.created_at > v.ttl
            ]
            for k in expired:
                del self.results[k]
                self.futures.pop(k, None)

    def _run_task(
        self,
        result_key: str,
        task: Task,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Execute task and update result (runs in thread pool)."""
        task_result = self.results.get(result_key)
        if task_result is None or task_result.status == TaskStatus.CANCELLED:
            return None

        task_result.set_running()

        try:
            # Handle async functions - use anyio.run() to create event loop in thread
            if iscoroutinefunction(task.func):
                result = anyio.run(lambda: task.func(*args, **kwargs))
            else:
                result = task.func(*args, **kwargs)

            # Apply transform if specified
            if task.transform:
                result = task.transform(result)

            task_result.set_completed(result)
            return result

        except Exception as e:
            task_result.set_failed(e)
            raise

    def enqueue(
        self,
        task: Task,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        session_id: str,
        key: str,
    ) -> TaskResult:
        """Enqueue a task for background execution."""
        self._cleanup_expired()

        result_key = self._result_key(session_id, key)
        task_result = task._create_result(session_id, key)

        with self._lock:
            self.results[result_key] = task_result

        # Submit to thread pool
        future = self.executor.submit(
            self._run_task, result_key, task, args, kwargs
        )
        with self._lock:
            self.futures[result_key] = future

        return task_result

    def get(self, session_id: str, key: str) -> TaskResult | None:
        """Get a task result by session and key."""
        self._cleanup_expired()
        result_key = self._result_key(session_id, key)
        return self.results.get(result_key)

    def pop(self, session_id: str, key: str) -> Any | None:
        """Pop a completed result value, removing it from storage."""
        self._cleanup_expired()
        result_key = self._result_key(session_id, key)

        with self._lock:
            task_result = self.results.get(result_key)
            if task_result is None:
                return None

            if task_result.status == TaskStatus.COMPLETED:
                del self.results[result_key]
                self.futures.pop(result_key, None)
                return task_result.value

        return None

    def pop_all(self, session_id: str) -> list[Any]:
        """Pop all completed results for a session."""
        self._cleanup_expired()
        values = []

        with self._lock:
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
                self.futures.pop(k, None)

        return values

    def pop_errors(self, session_id: str) -> list[tuple[str, Exception]]:
        """Pop all failed results for a session, returning (key, error) pairs."""
        self._cleanup_expired()
        errors = []

        with self._lock:
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
                self.futures.pop(k, None)

        return errors

    def has(self, session_id: str, key: str | None = None) -> bool:
        """Check if there are any completed results."""
        self._cleanup_expired()

        with self._lock:
            if key is not None:
                result_key = self._result_key(session_id, key)
                task_result = self.results.get(result_key)
                return (
                    task_result is not None
                    and task_result.status == TaskStatus.COMPLETED
                )

            # Check if any completed for session
            return any(
                r.session_id == session_id and r.status == TaskStatus.COMPLETED
                for r in self.results.values()
            )

    def cancel(self, session_id: str, key: str) -> bool:
        """Cancel a pending/running task."""
        result_key = self._result_key(session_id, key)

        with self._lock:
            task_result = self.results.get(result_key)
            if task_result is None:
                return False

            if task_result.is_finished:
                return False

            # Cancel the future if possible
            future = self.futures.get(result_key)
            if future is not None:
                future.cancel()

            task_result.set_cancelled()
            return True

    def cancel_all(self, session_id: str) -> int:
        """Cancel all tasks for a session. Returns count cancelled."""
        cancelled = 0

        with self._lock:
            for result_key, task_result in self.results.items():
                if task_result.session_id == session_id and not task_result.is_finished:
                    future = self.futures.get(result_key)
                    if future is not None:
                        future.cancel()
                    task_result.set_cancelled()
                    cancelled += 1

        return cancelled

    async def wait(
        self,
        session_id: str,
        key: str,
        timeout: float = 30.0,
    ) -> Any | None:
        """Wait for a specific task to complete."""
        result_key = self._result_key(session_id, key)
        deadline = time() + timeout

        while time() < deadline:
            task_result = self.results.get(result_key)
            if task_result is None:
                return None

            if task_result.status == TaskStatus.COMPLETED:
                return task_result.value
            elif task_result.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                return None

            await anyio.sleep(0.1)

        return None

    async def wait_all(
        self,
        session_id: str,
        keys: list[str],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Wait for multiple tasks to complete. Returns dict of key -> value."""
        results: dict[str, Any] = {}
        deadline = time() + timeout

        remaining = set(keys)

        while remaining and time() < deadline:
            for key in list(remaining):
                result_key = self._result_key(session_id, key)
                task_result = self.results.get(result_key)

                if task_result is None:
                    remaining.discard(key)
                elif task_result.status == TaskStatus.COMPLETED:
                    results[key] = task_result.value
                    remaining.discard(key)
                elif task_result.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                    remaining.discard(key)

            if remaining:
                await anyio.sleep(0.1)

        return results

    async def wait_any(
        self,
        session_id: str,
        keys: list[str],
        timeout: float = 30.0,
    ) -> tuple[str, Any] | None:
        """Wait for any task to complete. Returns (key, value) or None."""
        deadline = time() + timeout

        while time() < deadline:
            for key in keys:
                result_key = self._result_key(session_id, key)
                task_result = self.results.get(result_key)

                if task_result is not None and task_result.status == TaskStatus.COMPLETED:
                    return (key, task_result.value)

            await anyio.sleep(0.1)

        return None

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the thread pool."""
        self.executor.shutdown(wait=wait)
