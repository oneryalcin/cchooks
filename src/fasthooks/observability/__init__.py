"""Observability module for fasthooks.

Provides:
- HookApp observability: HookObservabilityEvent, BaseObserver, FileObserver, EventCapture
- Strategy observability: ObservabilityEvent, DecisionEvent, ErrorEvent, FileObservabilityBackend
"""

from .backend import FileObservabilityBackend
from .base import BaseObserver
from .enums import TerminalOutput, Verbosity
from .events import DecisionEvent, ErrorEvent, HookObservabilityEvent, ObservabilityEvent
from .observers import EventCapture, FileObserver

__all__ = [
    # HookApp observability
    "HookObservabilityEvent",
    "BaseObserver",
    "FileObserver",
    "EventCapture",
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
