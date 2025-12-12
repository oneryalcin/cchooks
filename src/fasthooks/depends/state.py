"""Persistent session-scoped state."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


class State(dict[str, Any]):
    """Persistent dict backed by JSON file.

    Behaves like a regular dict but can save/load from file.
    Use as context manager for auto-save on exit.
    """

    def __init__(self, state_file: Path | str):
        """Initialize State.

        Args:
            state_file: Path to JSON file for persistence
        """
        self._file = Path(state_file)
        super().__init__(self._load())

    def _load(self) -> dict[str, Any]:
        """Load state from file."""
        if not self._file.exists():
            return {}
        try:
            return cast(dict[str, Any], json.loads(self._file.read_text()))
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self) -> None:
        """Save state to file."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(dict(self), indent=2))

    def __enter__(self) -> State:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - always saves."""
        self.save()

    @classmethod
    def for_session(cls, session_id: str, state_dir: Path | str) -> State:
        """Create state scoped to a session.

        Args:
            session_id: Session identifier
            state_dir: Directory for state files

        Returns:
            State instance for this session
        """
        state_dir = Path(state_dir)
        state_file = state_dir / f"{session_id}.json"
        return cls(state_file)


class NullState(dict[str, Any]):
    """No-op state that doesn't persist.

    Used when no state_dir is configured. Behaves like dict
    but save() does nothing.
    """

    def save(self) -> None:
        """No-op save."""
        pass

    def __enter__(self) -> NullState:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - no-op."""
        pass
