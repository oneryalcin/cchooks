"""Event models for Claude Code hooks."""
from fasthooks.events.base import BaseEvent, GenericEvent, HookEventName
from fasthooks.events.lifecycle import (
    Notification,
    PermissionRequest,
    PreCompact,
    SessionEnd,
    SessionStart,
    Stop,
    SubagentStop,
    UserPromptSubmit,
)
from fasthooks.events.tools import (
    Bash,
    Edit,
    Glob,
    Grep,
    Read,
    Task,
    ToolEvent,
    ToolFailureEvent,
    WebFetch,
    WebSearch,
    Write,
)

__all__ = [
    # Base
    "BaseEvent",
    "GenericEvent",
    "HookEventName",
    # Tools
    "Bash",
    "Edit",
    "Glob",
    "Grep",
    "Read",
    "Task",
    "ToolEvent",
    "ToolFailureEvent",
    "WebFetch",
    "WebSearch",
    "Write",
    # Lifecycle
    "Notification",
    "PermissionRequest",
    "PreCompact",
    "SessionEnd",
    "SessionStart",
    "Stop",
    "SubagentStop",
    "UserPromptSubmit",
]
