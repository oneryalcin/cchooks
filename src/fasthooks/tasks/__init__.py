"""
Background tasks for fasthooks.

Enables hooks to spawn async work that feeds back results in subsequent hook calls.

Usage:
    from fasthooks.tasks import task, Tasks

    @task
    def memory_lookup(query: str) -> str:
        return search_db(query)

    @app.on_prompt()  # Recommended unified dependency
    def check_memory(event, tasks: Tasks):
        if result := tasks.pop(memory_lookup):
            return allow(message=f"Found: {result}")

        # Default key is function name; use explicit key for concurrent calls
        tasks.add(memory_lookup, event.prompt)
        return allow()

Lazy-loaded (PEP 562): importing this package is cheap; the task backends and
DI helpers (each pulling pydantic models) load only when accessed, so hooks
that never use background tasks don't pay for them at ``import fasthooks``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .backend import BaseBackend, InMemoryBackend
    from .base import Task, TaskResult, TaskStatus, task
    from .depends import BackgroundTasks, PendingResults, Tasks
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
    "Tasks",
    "BackgroundTasks",
    "PendingResults",
    # Testing
    "ImmediateBackend",
    "MockBackend",
]

_LAZY = {
    "task": ".base",
    "Task": ".base",
    "TaskResult": ".base",
    "TaskStatus": ".base",
    "BaseBackend": ".backend",
    "InMemoryBackend": ".backend",
    "Tasks": ".depends",
    "BackgroundTasks": ".depends",
    "PendingResults": ".depends",
    "ImmediateBackend": ".testing",
    "MockBackend": ".testing",
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(module, __name__), name)
