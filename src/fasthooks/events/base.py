"""Base event model for all hook events."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class BaseEvent(BaseModel):
    """Base model for all Claude Code hook events.

    All events share these common fields from the hook input.
    """

    model_config = ConfigDict(extra="ignore")

    session_id: str
    cwd: str
    permission_mode: str | None = None  # Not always sent (e.g., SessionStart)
    hook_event_name: str
    transcript_path: str | None = None


class GenericEvent(BaseEvent):
    """Fallback event for hook types without a dedicated typed model.

    Claude Code ships new hook events regularly; this model lets fasthooks
    dispatch any of them without a release. Unlike the typed events it keeps
    every field Claude Code sends (``extra="allow"``), so handlers can read
    event-specific fields either as attributes (``event.file_path``) or as a
    dict via ``event.data``.
    """

    model_config = ConfigDict(extra="allow")

    # Common fields aren't guaranteed on every event type, so relax them: an
    # unfamiliar event should never fail validation and become undispatchable.
    session_id: str = ""
    cwd: str = ""

    @property
    def data(self) -> dict[str, Any]:
        """All fields received, including those without typed accessors."""
        return self.model_dump()
