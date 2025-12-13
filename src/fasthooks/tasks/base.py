"""
Task and TaskResult dataclasses for background task execution.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Any
from uuid import uuid4


class TaskStatus(str, Enum):
    """Status of a background task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    """Result of a background task execution."""

    id: str
    session_id: str
    key: str
    status: TaskStatus = TaskStatus.PENDING
    value: Any = None
    error: Exception | None = None
    created_at: float = field(default_factory=time)
    started_at: float | None = None
    finished_at: float | None = None
    ttl: int = 300

    @property
    def is_finished(self) -> bool:
        """Check if task has completed (success or failure)."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

    @property
    def is_expired(self) -> bool:
        """Check if task result has expired based on TTL."""
        return time() - self.created_at > self.ttl

    def set_running(self) -> None:
        """Mark task as running."""
        self.status = TaskStatus.RUNNING
        self.started_at = time()

    def set_completed(self, value: Any) -> None:
        """Mark task as completed with result."""
        self.status = TaskStatus.COMPLETED
        self.value = value
        self.finished_at = time()

    def set_failed(self, error: Exception) -> None:
        """Mark task as failed with error."""
        self.status = TaskStatus.FAILED
        self.error = error
        self.finished_at = time()

    def set_cancelled(self) -> None:
        """Mark task as cancelled."""
        self.status = TaskStatus.CANCELLED
        self.finished_at = time()


@dataclass(frozen=True)
class Task:
    """
    A background task definition.

    Usage:
        @task
        def my_task(x: int) -> int:
            return x * 2

        # Or with options
        @task(priority=2, ttl=600)
        def slow_task(query: str) -> str:
            return search_db(query)
    """

    func: Callable[..., Any]
    priority: int = 0
    ttl: int = 300
    transform: Callable[[Any], Any] | None = None

    @property
    def name(self) -> str:
        """Get task function name."""
        return self.func.__name__

    def _create_result(self, session_id: str, key: str) -> TaskResult:
        """Create a TaskResult for this task."""
        return TaskResult(
            id=str(uuid4()),
            session_id=session_id,
            key=key,
            ttl=self.ttl,
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the underlying function directly (for testing)."""
        result = self.func(*args, **kwargs)
        if self.transform:
            result = self.transform(result)
        return result


def task(
    func: Callable[..., Any] | None = None,
    *,
    priority: int = 0,
    ttl: int = 300,
    transform: Callable[[Any], Any] | None = None,
) -> Task | Callable[[Callable[..., Any]], Task]:
    """
    Decorator to define a background task.

    Usage:
        @task
        def simple_task(x: int) -> int:
            return x * 2

        @task(priority=2, ttl=600)
        def slow_task(query: str) -> str:
            return search_db(query)

        @task(transform=lambda r: f"Result: {r}")
        def formatted_task(x: int) -> str:
            return x * 2
    """

    def wrapper(f: Callable[..., Any]) -> Task:
        return Task(func=f, priority=priority, ttl=ttl, transform=transform)

    if func is not None:
        return wrapper(func)
    return wrapper
