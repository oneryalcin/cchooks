"""Observability module for fasthooks strategies.

Provides event models, backends, and utilities for strategy observability.
"""

from .backend import FileObservabilityBackend
from .enums import TerminalOutput, Verbosity
from .events import DecisionEvent, ErrorEvent, ObservabilityEvent

__all__ = [
    # Events
    "ObservabilityEvent",
    "DecisionEvent",
    "ErrorEvent",
    # Enums
    "Verbosity",
    "TerminalOutput",
    # Backends
    "FileObservabilityBackend",
]
