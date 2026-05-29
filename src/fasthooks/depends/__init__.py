"""Dependency injection components.

Lazy-loaded (PEP 562): importing this package is cheap; the pydantic-heavy
``Transcript`` machinery is only imported when actually accessed. This keeps
``import fasthooks`` fast for hooks that never touch a transcript.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fasthooks.depends.state import State
    from fasthooks.depends.transcript import Transcript, TranscriptStats

__all__ = ["State", "Transcript", "TranscriptStats"]

_LAZY = {
    "State": ("fasthooks.depends.state", "State"),
    "Transcript": ("fasthooks.depends.transcript", "Transcript"),
    "TranscriptStats": ("fasthooks.depends.transcript", "TranscriptStats"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(target[0]), target[1])
