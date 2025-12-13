"""
Background tasks for fasthooks.

Enables hooks to spawn async work that feeds back results in subsequent hook calls.

Usage:
    from fasthooks.tasks import task, BackgroundTasks, PendingResults

    @task
    def memory_lookup(query: str) -> str:
        return search_db(query)

    @app.on_prompt()
    def check_memory(event, tasks: BackgroundTasks, pending: PendingResults):
        if result := pending.pop("memory"):
            return allow(message=f"Found: {result}")

        tasks.add(memory_lookup, event.prompt, key="memory")
        return allow()
"""

from .backend import BaseBackend, InMemoryBackend
from .base import Task, TaskResult, TaskStatus, task
from .depends import BackgroundTasks, PendingResults
from .testing import ImmediateBackend, MockBackend

__all__ = [
    # Core
    "task",
    "Task",
    "TaskResult",
    "TaskStatus",
    # Backends
    "BaseBackend",
    "InMemoryBackend",
    # DI Dependencies
    "BackgroundTasks",
    "PendingResults",
    # Testing
    "ImmediateBackend",
    "MockBackend",
]
