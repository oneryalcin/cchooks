"""PostToolUseFailure — typed event + post_tool_failure decorator.

Spec: https://code.claude.com/docs/en/hooks.md (PostToolUseFailure). Fires after
a tool call errors; matches on tool name like post_tool.
"""
from __future__ import annotations

from fasthooks import HookApp, ToolFailureEvent
from fasthooks.blueprint import Blueprint
from fasthooks.strategies.base import Strategy
from fasthooks.testing import StrategyTestClient, TestClient


def _raw(tool: str = "Bash", **extra):
    base = {
        "hook_event_name": "PostToolUseFailure",
        "session_id": "s",
        "cwd": "/",
        "tool_name": tool,
        "tool_input": {"command": "npm test"},
        "tool_use_id": "t1",
        "error": "Command exited with non-zero status code 1",
        "is_interrupt": False,
        "duration_ms": 4187,
    }
    base.update(extra)
    return base


def test_decorator_fires_with_typed_failure_event():
    app = HookApp()
    seen = {}

    @app.post_tool_failure("Bash")
    def on_fail(event):
        seen["cls"] = type(event)
        seen["error"] = event.error
        seen["is_interrupt"] = event.is_interrupt
        seen["duration_ms"] = event.duration_ms
        seen["command"] = event.tool_input.get("command")

    TestClient(app).send_raw(_raw())
    assert seen["cls"] is ToolFailureEvent
    assert seen["error"] == "Command exited with non-zero status code 1"
    assert seen["is_interrupt"] is False
    assert seen["duration_ms"] == 4187
    assert seen["command"] == "npm test"


def test_matcher_filters_by_tool_name():
    app = HookApp()
    fired = []

    @app.post_tool_failure("Bash")
    def on_fail(event):
        fired.append(event.tool_name)

    TestClient(app).send_raw(_raw("Write"))  # different tool
    assert fired == []
    TestClient(app).send_raw(_raw("Bash"))
    assert fired == ["Bash"]


def test_catch_all_fires_for_any_tool():
    app = HookApp()
    fired = []

    @app.post_tool_failure()  # no args = catch-all
    def on_fail(event):
        fired.append(event.tool_name)

    TestClient(app).send_raw(_raw("Write"))
    assert fired == ["Write"]


def test_generic_on_still_fires():
    """@app.on('PostToolUseFailure') dispatches alongside the typed decorator."""
    app = HookApp()
    hit = {}

    @app.on("PostToolUseFailure")
    def generic(event):
        hit["error"] = event.error

    TestClient(app).send_raw(_raw())
    assert hit["error"].startswith("Command exited")


def test_missing_error_field_defaults_not_fails_open():
    """A payload missing 'error' must parse (default ""), not raise -> fail open."""
    app = HookApp()
    seen = {}

    @app.post_tool_failure("Bash")
    def on_fail(event):
        seen["error"] = event.error

    payload = _raw()
    del payload["error"]
    TestClient(app).send_raw(payload)
    assert seen["error"] == ""


def test_closed_failure_handler_fails_open():
    """The tool already failed; PostToolUseFailure has no block, so closed = open."""
    app = HookApp(fail_mode="closed")

    @app.post_tool_failure("Bash", fail_mode="closed")
    def boom(event):
        raise RuntimeError("x")

    assert TestClient(app).send_raw(_raw()) is None


# ── strategy path (the registry must be mirrored end to end) ──────────────────

class _FailWatcher(Strategy):
    class Meta:
        name = "fail-watcher"
        version = "1.0.0"
        hooks = ["post_tool_failure"]

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("fw")

        @bp.post_tool_failure("Bash")
        def on_fail(event):
            _FailWatcher.last_error = event.error

        return bp


def test_strategy_post_tool_failure_via_include():
    _FailWatcher.last_error = None
    app = HookApp()
    app.include_strategy(_FailWatcher())
    TestClient(app).send_raw(_raw(error="boom"))
    assert _FailWatcher.last_error == "boom"


def test_strategy_post_tool_failure_via_test_client():
    _FailWatcher.last_error = None
    client = StrategyTestClient(_FailWatcher())
    client.trigger_post_tool_failure("Bash", error="kaboom")
    assert _FailWatcher.last_error == "kaboom"
