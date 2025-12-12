"""Response builders for Claude Code hooks."""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class HookResponse:
    """Response from a hook handler."""

    decision: str | None = None
    reason: str | None = None
    modify: dict | None = None
    message: str | None = None
    interrupt: bool = False
    continue_: bool = True

    def to_json(self) -> str:
        """Serialize to Claude Code expected JSON format."""
        output: dict = {}

        if self.decision and self.decision != "approve":
            output["decision"] = self.decision
        if self.reason:
            output["reason"] = self.reason
        if self.modify:
            output["hookSpecificOutput"] = {"updatedInput": self.modify}
        if self.message:
            output["systemMessage"] = self.message
        if not self.continue_:
            output["continue"] = False
        if self.interrupt:
            output["continue"] = False

        return json.dumps(output) if output else ""


def allow(*, modify: dict | None = None, message: str | None = None) -> HookResponse:
    """Allow the action to proceed.

    Args:
        modify: Optional dict to modify tool input before execution
        message: Optional message shown to user

    Returns:
        HookResponse with approve decision
    """
    return HookResponse(decision="approve", modify=modify, message=message)


def deny(reason: str, *, interrupt: bool = False) -> HookResponse:
    """Deny/block the action.

    Args:
        reason: Explanation shown to Claude
        interrupt: If True, stops Claude entirely

    Returns:
        HookResponse with deny decision
    """
    return HookResponse(decision="deny", reason=reason, interrupt=interrupt)


def block(reason: str) -> HookResponse:
    """Block Stop/SubagentStop - force Claude to continue.

    Args:
        reason: Explanation of what Claude should do

    Returns:
        HookResponse with block decision
    """
    return HookResponse(decision="block", reason=reason)
