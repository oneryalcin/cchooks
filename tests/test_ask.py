"""ask() — escalate a PreToolUse decision to the user (permissionDecision: "ask").

Spec: https://code.claude.com/docs/en/hooks.md (PreToolUse decision control).
"""
from __future__ import annotations

import json

from fasthooks import HookApp, ask, deny
from fasthooks.testing import MockEvent, TestClient


def test_ask_serializes_to_permission_decision_ask():
    out = json.loads(ask("Confirm this?").to_json("PreToolUse"))
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "ask"
    assert hso["permissionDecisionReason"] == "Confirm this?"


def test_ask_with_modify_stays_ask_not_allow():
    """ask + modify must serialize as 'ask' (show modified input), not 'allow'."""
    out = json.loads(ask("Confirm?", modify={"command": "safe ls"}).to_json("PreToolUse"))
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "ask"
    assert hso["updatedInput"] == {"command": "safe ls"}


def test_ask_is_noop_off_pretooluse():
    """ask is PreToolUse-only; on other events it serializes to nothing."""
    assert ask("x").to_json("Stop") == ""
    assert ask("x").to_json("PostToolUse") == ""


def test_ask_alone_is_returned():
    app = HookApp()

    @app.pre_tool("Bash")
    def confirm(event):
        return ask("Confirm this command?")

    response = TestClient(app).send(MockEvent.bash(command="ls"))
    assert response is not None
    assert response.decision == "ask"


def test_deny_beats_ask_precedence():
    """A later deny wins over an earlier ask (deny > ask precedence)."""
    app = HookApp()

    @app.pre_tool("Bash")
    def first(event):
        return ask("maybe?")

    @app.pre_tool("Bash")
    def second(event):
        return deny("no")

    response = TestClient(app).send(MockEvent.bash(command="ls"))
    assert response is not None
    assert response.decision == "deny"


def test_ask_carries_output():
    """A bare ask must be returned to Claude Code (not treated as no-op)."""
    assert ask("confirm?").carries_output() is True
