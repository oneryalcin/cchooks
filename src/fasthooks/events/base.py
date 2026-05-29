"""Base event model for all hook events."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class HookEventName(str, Enum):
    """Canonical Claude Code ``hook_event_name`` values.

    Subclasses ``str`` (like :class:`fasthooks.tasks.base.TaskStatus`), so
    members are drop-in interchangeable with the raw strings Claude Code sends
    — usable as dict keys, in ``==`` comparisons, and JSON-serialized to their
    wire value without conversion. Centralizes the magic strings the dispatcher
    keys off, instead of scattering literals like ``"PreToolUse"``.

    Note: this enumerates the events fasthooks models. Unknown/new events still
    dispatch via :class:`GenericEvent` — the enum is for the known set, not a
    closed-world constraint.
    """

    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    PERMISSION_REQUEST = "PermissionRequest"
    STOP = "Stop"
    SUBAGENT_STOP = "SubagentStop"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    PRE_COMPACT = "PreCompact"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    NOTIFICATION = "Notification"


class BaseEvent(BaseModel):
    """Base model for all Claude Code hook events.

    All events share these common fields from the hook input.

    ``extra="allow"``: every event keeps the fields Claude Code sends, even
    ones with no typed accessor. The typed attributes are a convenience layer
    over the raw payload, which stays fully reachable via :attr:`data`. This
    means upstream schema additions (new fields on existing events) are usable
    immediately — fasthooks never silently drops what it doesn't model.
    """

    model_config = ConfigDict(extra="allow")

    session_id: str
    cwd: str
    permission_mode: str | None = None  # Not always sent (e.g., SessionStart)
    hook_event_name: str
    transcript_path: str | None = None

    @property
    def data(self) -> dict[str, Any]:
        """The full event payload, including fields without typed accessors."""
        return self.model_dump()


class GenericEvent(BaseEvent):
    """Fallback event for hook types without a dedicated typed model.

    Claude Code ships new hook events regularly; this model lets fasthooks
    dispatch any of them without a release. It inherits field preservation and
    :attr:`data` from :class:`BaseEvent`, and additionally relaxes the common
    fields so an unfamiliar event never fails validation and becomes
    undispatchable.
    """

    session_id: str = ""
    cwd: str = ""
