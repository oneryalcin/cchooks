"""Base event model for all hook events."""
from __future__ import annotations

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
