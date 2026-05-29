"""Typed events for custom / MCP tools via register_tool_event.

Built-in tools ship typed accessors; everything else falls back to bare
ToolEvent (read via event.tool_input). Registration extends the typed-accessor
experience to custom tools — opt-in, per-app, covering pre/post/permission.
"""
from __future__ import annotations

import pytest

from fasthooks import HookApp, ToolEvent
from fasthooks.testing import TestClient


class Search(ToolEvent):
    """A custom MCP tool event with a typed accessor over tool_input."""

    @property
    def query(self) -> str:
        return self.tool_input.get("query", "")


def _raw(hook_event_name: str = "PreToolUse", tool: str = "mcp__srv__search"):
    return {
        "hook_event_name": hook_event_name,
        "session_id": "s",
        "cwd": "/",
        "tool_name": tool,
        "tool_input": {"query": "hello"},
        "tool_use_id": "t1",
    }


def test_registered_tool_gets_typed_event():
    app = HookApp()
    app.register_tool_event("mcp__srv__search", Search)
    seen = {}

    @app.pre_tool("mcp__srv__search")
    def handler(event):
        seen["type"] = type(event)
        seen["query"] = event.query  # typed accessor

    TestClient(app).send_raw(_raw())
    assert seen["type"] is Search
    assert seen["query"] == "hello"


def test_one_registration_covers_post_tool():
    """A single registration applies to PostToolUse too (not just pre)."""
    app = HookApp()
    app.register_tool_event("mcp__srv__search", Search)
    seen = {}

    @app.post_tool("mcp__srv__search")
    def handler(event):
        seen["type"] = type(event)

    TestClient(app).send_raw(_raw(hook_event_name="PostToolUse"))
    assert seen["type"] is Search


def test_unregistered_tool_falls_back_to_bare_tool_event():
    """Unknown tools parse as ToolEvent; tool_input works, accessors don't exist."""
    app = HookApp()
    captured = {}

    @app.pre_tool("mcp__srv__search")
    def handler(event):
        captured["event"] = event

    TestClient(app).send_raw(_raw())
    event = captured["event"]
    assert type(event) is ToolEvent
    # The raw payload is always reachable...
    assert event.tool_input["query"] == "hello"
    # ...but there's no typed accessor — it raises, it does not silently return None.
    with pytest.raises(AttributeError):
        _ = event.query


def test_register_rejects_non_tool_event():
    app = HookApp()
    with pytest.raises(TypeError):
        app.register_tool_event("X", dict)  # type: ignore[arg-type]

    class NotAToolEvent:
        pass

    with pytest.raises(TypeError):
        app.register_tool_event("X", NotAToolEvent)  # type: ignore[arg-type]


def test_registration_is_per_app():
    """Registering on one app must not leak into another (no global mutation)."""
    registered = HookApp()
    registered.register_tool_event("mcp__srv__search", Search)

    plain = HookApp()
    captured = {}

    @plain.pre_tool("mcp__srv__search")
    def handler(event):
        captured["type"] = type(event)

    TestClient(plain).send_raw(_raw())
    assert captured["type"] is ToolEvent  # unaffected by the other app
