"""File-based observability backend."""

from __future__ import annotations

from pathlib import Path

from .enums import Verbosity
from .events import ObservabilityEvent


class FileObservabilityBackend:
    """Backend that writes JSONL per session."""

    def __init__(
        self,
        base_dir: Path | str | None = None,
        verbosity: Verbosity = Verbosity.STANDARD,
    ):
        if base_dir is None:
            base_dir = Path.home() / ".fasthooks" / "observability"
        self.base_dir = Path(base_dir)
        self.verbosity = verbosity
        self._queue: list[ObservabilityEvent] = []

    def handle_event(self, event: ObservabilityEvent) -> None:
        """Queue event for write."""
        if self._should_include(event):
            self._queue.append(event)

    def _should_include(self, event: ObservabilityEvent) -> bool:
        """Filter based on verbosity level."""
        if self.verbosity == Verbosity.MINIMAL:
            return event.event_type in ("decision", "error")
        return True  # STANDARD and VERBOSE include all

    def flush(self, session_id: str | None = None) -> Path | None:
        """Write queued events to file.

        Args:
            session_id: Optional session ID. If not provided, uses first event's.

        Returns:
            Path to written file, or None if queue was empty.
        """
        if not self._queue:
            return None

        # Get session_id from first event if not provided
        sid = session_id or self._queue[0].session_id
        file_path = self.base_dir / f"{sid}.jsonl"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "a") as f:
            for event in self._queue:
                f.write(event.model_dump_json() + "\n")

        self._queue.clear()
        return file_path

    def clear(self) -> None:
        """Clear queued events without writing."""
        self._queue.clear()

    @property
    def pending_count(self) -> int:
        """Number of events waiting to be flushed."""
        return len(self._queue)
