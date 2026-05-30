"""halt() (continue:false + stopReason) and additionalContext on decisions.

Spec: https://code.claude.com/docs/en/hooks.md (JSON output universal fields;
PreToolUse/PostToolUse additionalContext).
"""
from __future__ import annotations

import json

from fasthooks import HookApp, allow, context, deny, halt
from fasthooks.responses import HookResponse
from fasthooks.testing import MockEvent, TestClient

# ── halt() ───────────────────────────────────────────────────────────────────

def test_halt_serializes_continue_false_with_stop_reason():
    for event in ("PreToolUse", "Stop", "PostToolUse"):
        out = json.loads(halt("Build broken").to_json(event))
        assert out == {"continue": False, "stopReason": "Build broken"}


def test_halt_is_terminal_over_later_response():
    """continue:false takes precedence — a later handler can't overwrite it."""
    app = HookApp()

    @app.pre_tool("Bash")
    def first(event):
        return halt("stop now")

    @app.pre_tool("Bash")
    def second(event):
        return allow(modify={"command": "rewritten"})

    response = TestClient(app).send(MockEvent.bash(command="ls"))
    assert response is not None
    assert response.continue_ is False
    assert response.stop_reason == "stop now"


def test_halt_short_circuits_and_carries_output():
    assert halt("x").should_return() is True
    assert halt("x").carries_output() is True


def test_stop_reason_without_continue_false_does_not_emit():
    """stopReason only rides with continue:false."""
    assert HookResponse(decision="approve", stop_reason="x").to_json("PreToolUse") == ""


# ── additionalContext on decisions ───────────────────────────────────────────

def test_allow_with_additional_context_pretooluse():
    out = json.loads(allow(additional_context="env: prod").to_json("PreToolUse"))
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["additionalContext"] == "env: prod"


def test_deny_with_additional_context_carries_hook_event_name_off_pretooluse():
    """Off PreToolUse, hookSpecificOutput must include hookEventName (spec)."""
    out = json.loads(deny("bad", additional_context="see logs").to_json("PostToolUse"))
    assert out["decision"] == "deny"
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PostToolUse"
    assert hso["additionalContext"] == "see logs"


def test_allow_with_modify_and_context_together():
    out = json.loads(
        allow(modify={"command": "safe"}, additional_context="note").to_json("PreToolUse")
    )
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "allow"
    assert hso["updatedInput"] == {"command": "safe"}
    assert hso["additionalContext"] == "note"


def test_context_builder_works_on_any_event():
    """context() already supports tool events — guard against regression."""
    out = json.loads(context("note", hook_event="PostToolUse").to_json("PostToolUse"))
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PostToolUse"
    assert hso["additionalContext"] == "note"
