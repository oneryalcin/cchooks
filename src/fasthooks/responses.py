"""Response builders for Claude Code hooks."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypedDict

# ─────────────────────────────────────────────────────────────────────────────
# Wire-output shapes. These are the JSON objects Claude Code reads back from a
# hook. Modeled as TypedDicts (zero runtime cost — they're plain dicts) so mypy
# checks the camelCase key names: a typo like "permissionDecisonReason" is a
# silent no-op on the wire otherwise, since Claude Code just ignores unknown keys.
# ─────────────────────────────────────────────────────────────────────────────


class PermissionDecision(TypedDict, total=False):
    """Nested ``decision`` object for PermissionRequest hooks."""

    behavior: str  # "allow" | "deny"
    updatedInput: dict[str, Any]
    message: str
    interrupt: bool


class HookSpecificOutput(TypedDict, total=False):
    """``hookSpecificOutput`` across event shapes (every key optional)."""

    hookEventName: str
    permissionDecision: str  # PreToolUse: "allow" | "deny" | "ask"
    permissionDecisionReason: str  # PreToolUse
    updatedInput: dict[str, Any]  # PreToolUse
    additionalContext: str  # tool events / context
    decision: PermissionDecision  # PermissionRequest


# "continue" is a Python keyword, so the top-level output uses functional syntax.
HookOutput = TypedDict(
    "HookOutput",
    {
        "decision": str,  # top-level decision (block/deny) for non-PreToolUse
        "reason": str,
        "continue": bool,
        "stopReason": str,
        "systemMessage": str,
        "hookSpecificOutput": HookSpecificOutput,
    },
    total=False,
)


class BaseHookResponse(ABC):
    """Abstract base class for hook responses."""

    @abstractmethod
    def to_json(self, hook_event_name: str | None = None) -> str:
        """Serialize to Claude Code expected JSON format.

        Args:
            hook_event_name: The event being responded to. Some events (notably
                PreToolUse) require an event-specific output shape; pass it so
                the response serializes correctly.
        """
        ...

    def should_return(self) -> bool:
        """Whether this response should be returned (stop handler chain).

        Override in subclasses for custom behavior.
        Default: always return.
        """
        return True

    def carries_output(self) -> bool:
        """Whether this response produces output even if it doesn't block.

        Used by the dispatcher to return a non-blocking response (e.g.
        ``allow(modify=...)``) when no later handler blocks — without
        short-circuiting the chain, so a subsequent ``deny`` still wins.
        Default mirrors :meth:`should_return`.
        """
        return self.should_return()


@dataclass
class HookResponse(BaseHookResponse):
    """Response from a hook handler."""

    decision: str | None = None
    reason: str | None = None
    modify: dict[str, Any] | None = None
    message: str | None = None
    interrupt: bool = False
    continue_: bool = True
    stop_reason: str | None = None
    additional_context: str | None = None

    def to_json(self, hook_event_name: str | None = None) -> str:
        """Serialize to Claude Code expected JSON format."""
        output: HookOutput = {}

        if hook_event_name == "PreToolUse":
            # PreToolUse returns its decision inside hookSpecificOutput; the
            # top-level decision/reason form is deprecated for this event.
            # approve -> "allow", block -> "deny".
            hso: HookSpecificOutput = {"hookEventName": "PreToolUse"}
            if self.decision in ("deny", "block"):
                hso["permissionDecision"] = "deny"
            elif self.decision == "ask":
                # Escalate to the user. Checked before modify so ask(modify=...)
                # stays "ask" (show the modified input) rather than auto-allow.
                hso["permissionDecision"] = "ask"
            elif self.modify:
                # approve + updatedInput = auto-approve the modified input
                hso["permissionDecision"] = "allow"
            # A bare approve stays "no opinion" (empty output -> normal
            # permission flow), matching prior behavior.
            if "permissionDecision" in hso and self.reason:
                hso["permissionDecisionReason"] = self.reason
            if self.modify:
                hso["updatedInput"] = self.modify
            if self.additional_context:
                hso["additionalContext"] = self.additional_context
            if len(hso) > 1:  # more than just hookEventName
                output["hookSpecificOutput"] = hso
        else:
            # Top-level decision's only valid value off PreToolUse is "block"
            # (deny maps there too); "ask"/"approve" are PreToolUse-only or no-ops.
            # reason only rides along with an emitted decision — no orphan reason
            # (e.g. ask() off PreToolUse serializes to nothing).
            if self.decision and self.decision not in ("approve", "ask"):
                output["decision"] = self.decision
                if self.reason:
                    output["reason"] = self.reason
            hso_else: HookSpecificOutput = {}
            if self.modify:
                hso_else["updatedInput"] = self.modify
            if self.additional_context:
                # hookSpecificOutput requires hookEventName off PreToolUse.
                hso_else["hookEventName"] = hook_event_name or ""
                hso_else["additionalContext"] = self.additional_context
            if hso_else:
                output["hookSpecificOutput"] = hso_else

        if self.message:
            output["systemMessage"] = self.message
        if not self.continue_ or self.interrupt:
            output["continue"] = False
            if self.stop_reason:
                output["stopReason"] = self.stop_reason

        return json.dumps(output) if output else ""

    def should_return(self) -> bool:
        """deny/block, or a halt (continue=False), short-circuit the chain.

        continue=False takes precedence over event-specific decisions, so it
        must be terminal — otherwise a later handler could overwrite the halt.
        """
        return self.decision in ("deny", "block") or not self.continue_

    def carries_output(self) -> bool:
        """True when this response emits something beyond a bare allow.

        A bare ``allow()`` is "no opinion" (no-op); but ``allow(modify=...)``,
        ``allow(message=...)``, or an interrupt/continue change must still be
        returned to Claude Code even though they don't block.
        """
        return bool(
            self.decision in ("deny", "block", "ask")
            or self.modify
            or self.message
            or self.additional_context
            or self.interrupt
            or not self.continue_
        )


def allow(
    *,
    modify: dict[str, Any] | None = None,
    message: str | None = None,
    additional_context: str | None = None,
) -> HookResponse:
    """Allow the action to proceed.

    Args:
        modify: Optional dict to modify tool input before execution
        message: Optional message shown to user
        additional_context: Optional text injected into Claude's context
            alongside the tool result (PreToolUse/PostToolUse). For a bare
            context injection on any event, prefer :func:`context`.

    Returns:
        HookResponse with approve decision
    """
    return HookResponse(
        decision="approve",
        modify=modify,
        message=message,
        additional_context=additional_context,
    )


def deny(
    reason: str,
    *,
    interrupt: bool = False,
    additional_context: str | None = None,
) -> HookResponse:
    """Deny/block the action.

    Args:
        reason: Explanation shown to Claude
        interrupt: If True, stops Claude entirely
        additional_context: Optional extra context injected for Claude
            alongside the denial (PreToolUse/PostToolUse).

    Returns:
        HookResponse with deny decision
    """
    return HookResponse(
        decision="deny",
        reason=reason,
        interrupt=interrupt,
        additional_context=additional_context,
    )


def block(reason: str) -> HookResponse:
    """Block Stop/SubagentStop - force Claude to continue.

    Args:
        reason: Explanation of what Claude should do

    Returns:
        HookResponse with block decision
    """
    return HookResponse(decision="block", reason=reason)


def ask(reason: str, *, modify: dict[str, Any] | None = None) -> HookResponse:
    """Escalate a PreToolUse decision to the user (``permissionDecision: "ask"``).

    Instead of allowing or denying outright, prompt the user to confirm the tool
    call. ``reason`` is shown to the user (not Claude). Pass ``modify`` to show
    rewritten tool input in the prompt.

    PreToolUse only — on other events this is a no-op. ``ask`` does not
    short-circuit the handler chain, so a later ``deny`` still wins (matching the
    protocol's ``deny > ask > allow`` precedence). Among multiple non-blocking
    responses in one chain, the last one returned wins.

    Args:
        reason: Explanation shown to the user in the confirmation prompt.
        modify: Optional dict to rewrite tool input, shown to the user.

    Returns:
        HookResponse with ask decision
    """
    return HookResponse(decision="ask", reason=reason, modify=modify)


def halt(reason: str) -> HookResponse:
    """Stop Claude entirely (``continue: false``) with a message to the user.

    Works on any event and takes precedence over event-specific decisions:
    ``continue: false`` ends the turn. ``reason`` is the ``stopReason`` shown to
    the user (not Claude). This is terminal — it short-circuits the handler
    chain so a later handler can't override the halt.

    Args:
        reason: Message shown to the user explaining why Claude stopped.

    Returns:
        HookResponse that ends the turn.
    """
    return HookResponse(continue_=False, stop_reason=reason)


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

    def to_json(self, hook_event_name: str | None = None) -> str:
        """Serialize to Claude Code PermissionRequest format."""
        decision: PermissionDecision = {"behavior": self.behavior}

        if self.behavior == "allow" and self.modify:
            decision["updatedInput"] = self.modify
        elif self.behavior == "deny":
            if self.message:
                decision["message"] = self.message
            if self.interrupt:
                decision["interrupt"] = True

        output: HookOutput = {
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

    def to_json(self, hook_event_name: str | None = None) -> str:
        """Serialize to Claude Code format with additionalContext."""
        output: HookOutput = {
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
