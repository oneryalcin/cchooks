"""Generic-first dispatch: any hook event is handleable without a release.

These tests use event names that fasthooks has NO dedicated typed model for
(FileChanged, PostToolUseFailure, CwdChanged). They must still dispatch via
@app.on(name) and the handler must be able to read the event-specific fields —
proving the GenericEvent fallback preserves the payload (the whole point;
BaseEvent's extra="ignore" would silently drop them).
"""
from __future__ import annotations

from fasthooks import HookApp, deny
from fasthooks.events.base import GenericEvent
from fasthooks.testing import TestClient


def test_on_dispatches_unknown_event_and_preserves_fields():
    app = HookApp()
    seen = {}

    @app.on("FileChanged")
    def on_change(event):
        # Event-specific field must survive parsing (extra="allow")
        seen["path"] = event.file_path
        seen["type"] = type(event).__name__

    client = TestClient(app)
    response = client.send_raw(
        {
            "hook_event_name": "FileChanged",
            "session_id": "s1",
            "cwd": "/repo",
            "file_path": "/repo/src/main.py",
        }
    )

    assert response is None  # no decision -> allow
    assert seen["path"] == "/repo/src/main.py"
    assert seen["type"] == "GenericEvent"


def test_on_can_block_a_new_tool_event():
    """A new tool-style event (no typed model) can still deny via on()."""
    app = HookApp()

    @app.on("PostToolUseFailure")
    def on_fail(event):
        if event.tool_name == "Bash":
            return deny(f"Bash failed: {event.data.get('error', 'unknown')}")

    client = TestClient(app)
    response = client.send_raw(
        {
            "hook_event_name": "PostToolUseFailure",
            "session_id": "s1",
            "cwd": "/repo",
            "tool_name": "Bash",
            "error": "command not found",
        }
    )

    assert response is not None
    assert response.decision == "deny"
    assert "command not found" in response.reason


def test_unknown_event_without_handler_is_noop():
    """An event with no registered handler dispatches cleanly to None."""
    app = HookApp()
    client = TestClient(app)
    response = client.send_raw(
        {"hook_event_name": "CwdChanged", "session_id": "s1", "cwd": "/new"}
    )
    assert response is None


def test_on_guard_filters_events():
    app = HookApp()
    calls = []

    @app.on("FileChanged", when=lambda e: e.file_path.endswith(".py"))
    def only_python(event):
        calls.append(event.file_path)

    client = TestClient(app)
    client.send_raw(
        {"hook_event_name": "FileChanged", "session_id": "s", "cwd": "/r",
         "file_path": "/r/README.md"}
    )
    client.send_raw(
        {"hook_event_name": "FileChanged", "session_id": "s", "cwd": "/r",
         "file_path": "/r/app.py"}
    )
    assert calls == ["/r/app.py"]


def test_generic_event_missing_common_fields_still_parses():
    """GenericEvent relaxes session_id/cwd so an unfamiliar event never fails."""
    event = GenericEvent.model_validate({"hook_event_name": "WeirdNewEvent", "x": 1})
    assert event.hook_event_name == "WeirdNewEvent"
    assert event.session_id == ""
    assert event.data["x"] == 1


# ── Regression: adversarial review findings ──────────────────────────────────


def test_raising_guard_fails_open_and_runs_later_handlers():
    """A guard that raises must not abort dispatch (fail-open contract).

    Field-based guards on GenericEvent payloads will hit missing attributes;
    before the fix this raised UnboundLocalError in the error path and aborted
    the whole hook, so later handlers never ran.
    """
    app = HookApp()
    later_ran = []

    @app.on("FileChanged", when=lambda e: e.file_path.endswith(".py"))
    def needs_field(event):  # guard raises: payload has no file_path
        later_ran.append("first")

    @app.on("FileChanged")
    def always(event):
        later_ran.append("second")

    client = TestClient(app)
    # No file_path -> first handler's guard raises
    response = client.send_raw(
        {"hook_event_name": "FileChanged", "session_id": "s", "cwd": "/r"}
    )

    assert response is None  # failed open, not crashed
    assert later_ran == ["second"]  # subsequent handler still ran


def test_known_event_preserves_upstream_fields_and_exposes_data():
    """on() handlers on KNOWN events must also keep unmodeled fields + .data.

    extra='allow' on the typed events means upstream schema additions on
    existing event names aren't silently dropped.
    """
    app = HookApp()
    seen = {}

    @app.on("PreToolUse")
    def h(event):
        seen["type"] = type(event).__name__
        seen["new_field"] = getattr(event, "new_upstream_field", "<DROPPED>")
        seen["via_data"] = event.data.get("new_upstream_field")

    client = TestClient(app)
    client.send_raw(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "s",
            "cwd": "/r",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_use_id": "t",
            "new_upstream_field": "kept",
        }
    )

    assert seen["type"] == "Bash"  # still the typed event
    assert seen["new_field"] == "kept"  # but the new field survived
    assert seen["via_data"] == "kept"  # and .data is available on typed events
