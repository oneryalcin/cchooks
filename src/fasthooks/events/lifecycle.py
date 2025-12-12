"""Lifecycle event models (Stop, SessionStart, etc.)."""
from __future__ import annotations

from typing import Any

from pydantic import ConfigDict

from fasthooks.events.base import BaseEvent


class Stop(BaseEvent):
    """Stop event - main agent finished responding."""

    model_config = ConfigDict(extra="ignore")

    stop_hook_active: bool = False


class SubagentStop(BaseEvent):
    """SubagentStop event - subagent finished responding."""

    model_config = ConfigDict(extra="ignore")

    agent_id: str | None = None
    stop_hook_active: bool = False


class SessionStart(BaseEvent):
    """SessionStart event - session begins or resumes."""

    model_config = ConfigDict(extra="ignore")

    source: str  # startup, resume, clear, compact


class SessionEnd(BaseEvent):
    """SessionEnd event - session ends."""

    model_config = ConfigDict(extra="ignore")

    reason: str  # clear, logout, prompt_input_exit, other


class PreCompact(BaseEvent):
    """PreCompact event - before context compaction."""

    model_config = ConfigDict(extra="ignore")

    trigger: str  # manual, auto
    custom_instructions: str | None = None


class UserPromptSubmit(BaseEvent):
    """UserPromptSubmit event - user submits a prompt."""

    model_config = ConfigDict(extra="ignore")

    prompt: str


class Notification(BaseEvent):
    """Notification event - notification sent."""

    model_config = ConfigDict(extra="ignore")

    message: str
    notification_type: str  # permission_prompt, idle_prompt, etc.


class PermissionRequest(BaseEvent):
    """PermissionRequest event - permission dialog shown."""

    model_config = ConfigDict(extra="ignore")

    tool_name: str
    tool_input: dict[str, Any]
