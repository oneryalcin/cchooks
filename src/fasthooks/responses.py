"""Response builders for Claude Code hooks."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class BaseHookResponse(ABC):
    """Abstract base class for hook responses."""

    @abstractmethod
    def to_json(self) -> str:
        """Serialize to Claude Code expected JSON format."""
        ...

    def should_return(self) -> bool:
        """Whether this response should be returned (stop handler chain).

        Override in subclasses for custom behavior.
        Default: always return.
        """
        return True


@dataclass
class HookResponse(BaseHookResponse):
    """Response from a hook handler."""

    decision: str | None = None
    reason: str | None = None
    modify: dict[str, Any] | None = None
    message: str | None = None
    interrupt: bool = False
    continue_: bool = True

    def to_json(self) -> str:
        """Serialize to Claude Code expected JSON format."""
        output: dict[str, Any] = {}

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

    def should_return(self) -> bool:
        """Only return deny/block responses."""
        return self.decision in ("deny", "block")


def allow(
    *, modify: dict[str, Any] | None = None, message: str | None = None
) -> HookResponse:
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


# ═══════════════════════════════════════════════════════════════════════════
# PermissionRequest responses (different JSON format from PreToolUse)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class PermissionHookResponse(BaseHookResponse):
    """Response for PermissionRequest hooks."""

    behavior: str  # "allow" or "deny"
    message: str | None = None
    interrupt: bool = False
    modify: dict[str, Any] | None = None

    def to_json(self) -> str:
        """Serialize to Claude Code PermissionRequest format."""
        decision: dict[str, Any] = {"behavior": self.behavior}

        if self.behavior == "allow" and self.modify:
            decision["updatedInput"] = self.modify
        elif self.behavior == "deny":
            if self.message:
                decision["message"] = self.message
            if self.interrupt:
                decision["interrupt"] = True

        output = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": decision,
            }
        }
        return json.dumps(output)


def approve_permission(
    *, modify: dict[str, Any] | None = None
) -> PermissionHookResponse:
    """Approve a permission request.

    Args:
        modify: Optional dict to modify tool input before execution

    Returns:
        PermissionHookResponse with allow behavior
    """
    return PermissionHookResponse(behavior="allow", modify=modify)


def deny_permission(
    message: str | None = None, *, interrupt: bool = False
) -> PermissionHookResponse:
    """Deny a permission request.

    Args:
        message: Explanation shown to Claude
        interrupt: If True, stops Claude entirely

    Returns:
        PermissionHookResponse with deny behavior
    """
    return PermissionHookResponse(behavior="deny", message=message, interrupt=interrupt)


# ═══════════════════════════════════════════════════════════════════════════
# SessionStart/UserPromptSubmit responses (additionalContext format)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ContextResponse(BaseHookResponse):
    """Response for SessionStart/UserPromptSubmit hooks that adds context."""

    hook_event_name: str  # "SessionStart" or "UserPromptSubmit"
    additional_context: str
    system_message: str | None = None

    def to_json(self) -> str:
        """Serialize to Claude Code format with additionalContext."""
        output: dict[str, Any] = {
            "hookSpecificOutput": {
                "hookEventName": self.hook_event_name,
                "additionalContext": self.additional_context,
            }
        }
        if self.system_message:
            output["systemMessage"] = self.system_message
        return json.dumps(output)

    def should_return(self) -> bool:
        """Always return context responses."""
        return True


def context(
    text: str,
    *,
    hook_event: str = "SessionStart",
    system_message: str | None = None,
) -> ContextResponse:
    """Add context to SessionStart or UserPromptSubmit hooks.

    This injects text into Claude's context (not just shown to user).

    Args:
        text: Context text to inject into Claude's conversation
        hook_event: Either "SessionStart" or "UserPromptSubmit"
        system_message: Optional warning message shown to user

    Returns:
        ContextResponse that adds context to Claude
    """
    return ContextResponse(
        hook_event_name=hook_event,
        additional_context=text,
        system_message=system_message,
    )
