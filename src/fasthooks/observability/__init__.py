"""Observability module for fasthooks.

Provides:
- HookApp observability: HookObservabilityEvent, BaseObserver, FileObserver,
  EventCapture, SQLiteObserver
- Strategy observability: ObservabilityEvent, DecisionEvent, ErrorEvent,
  FileObservabilityBackend

Lazy-loaded (PEP 562): importing this package does not eagerly pull in the
observer backends (SQLite, file, capture). The core dispatch path only needs
``HookObservabilityEvent`` from ``.events``; everything else loads on access.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .backend import FileObservabilityBackend
    from .base import BaseObserver
    from .enums import TerminalOutput, Verbosity
    from .events import (
        DecisionEvent,
        ErrorEvent,
        HookObservabilityEvent,
        ObservabilityEvent,
    )
    from .observers import EventCapture, FileObserver, SQLiteObserver

__all__ = [
    # HookApp observability
    "HookObservabilityEvent",
    "BaseObserver",
    "FileObserver",
    "EventCapture",
    "SQLiteObserver",
    # Strategy observability (existing)
    "ObservabilityEvent",
    "DecisionEvent",
    "ErrorEvent",
    # Enums
    "Verbosity",
    "TerminalOutput",
    # Backends
    "FileObservabilityBackend",
]

_LAZY = {
    "HookObservabilityEvent": ".events",
    "DecisionEvent": ".events",
    "ErrorEvent": ".events",
    "ObservabilityEvent": ".events",
    "BaseObserver": ".base",
    "FileObservabilityBackend": ".backend",
    "TerminalOutput": ".enums",
    "Verbosity": ".enums",
    "EventCapture": ".observers",
    "FileObserver": ".observers",
    "SQLiteObserver": ".observers",
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(module, __name__), name)
