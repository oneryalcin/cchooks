"""File-based observer for logging events to JSONL."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fasthooks.observability.base import BaseObserver

if TYPE_CHECKING:
    from fasthooks.observability.events import HookObservabilityEvent


class FileObserver(BaseObserver):
    """Write events to JSONL file for debugging/analysis.

    Why file-based logging?
    - stdout is reserved for JSON hook response (would corrupt output)
    - stderr is treated as hook error by Claude Code (causes spurious errors)
    - File-based logging is the only safe option for hooks

    Example:
        app.add_observer(FileObserver())  # ~/.fasthooks/observability/events.jsonl
        app.add_observer(FileObserver("/tmp/my-hooks.jsonl"))  # Custom path
    """

    def __init__(self, path: Path | str | None = None) -> None:
        """Initialize observer.

        Args:
            path: Path to JSONL file. Defaults to ~/.fasthooks/observability/events.jsonl
        """
        if path is None:
            path = Path.home() / ".fasthooks" / "observability" / "events.jsonl"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, event: HookObservabilityEvent) -> None:
        with open(self.path, "a") as f:
            f.write(event.model_dump_json() + "\n")

    def on_hook_start(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_hook_end(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_hook_error(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_start(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_end(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_skip(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_error(self, event: HookObservabilityEvent) -> None:
        self._write(event)
