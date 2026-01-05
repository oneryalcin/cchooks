"""Tests for HookApp observability system."""

from __future__ import annotations

import pytest

from fasthooks import HookApp, deny
from fasthooks.observability import (
    BaseObserver,
    EventCapture,
    FileObserver,
    HookObservabilityEvent,
)
from fasthooks.testing import MockEvent, TestClient


class TestHookObservabilityEvent:
    """Tests for HookObservabilityEvent model."""

    def test_required_fields_only(self) -> None:
        """Event can be created with required fields only."""
        event = HookObservabilityEvent(
            event_type="hook_start",
            hook_id="abc123",
            session_id="session-1",
            hook_event_name="PreToolUse",
        )
        assert event.event_type == "hook_start"
        assert event.hook_id == "abc123"
        assert event.timestamp is not None

    def test_all_fields(self) -> None:
        """Event can be created with all fields."""
        event = HookObservabilityEvent(
            event_type="handler_end",
            hook_id="abc123",
            session_id="session-1",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            handler_name="check_dangerous",
            duration_ms=2.5,
            decision="deny",
            reason="Blocked dangerous command",
        )
        assert event.handler_name == "check_dangerous"
        assert event.decision == "deny"
        assert event.duration_ms == 2.5

    def test_model_dump_returns_dict(self) -> None:
        """Users can get raw dict via .model_dump()."""
        event = HookObservabilityEvent(
            event_type="hook_start",
            hook_id="abc123",
            session_id="session-1",
            hook_event_name="PreToolUse",
        )
        raw = event.model_dump()
        assert isinstance(raw, dict)
        assert raw["event_type"] == "hook_start"


class TestBaseObserver:
    """Tests for BaseObserver class."""

    def test_all_methods_are_noops(self) -> None:
        """BaseObserver methods do nothing by default."""
        observer = BaseObserver()
        event = HookObservabilityEvent(
            event_type="hook_start",
            hook_id="abc123",
            session_id="session-1",
            hook_event_name="PreToolUse",
        )
        # All methods should be callable and not raise
        observer.on_hook_start(event)
        observer.on_hook_end(event)
        observer.on_hook_error(event)
        observer.on_handler_start(event)
        observer.on_handler_end(event)
        observer.on_handler_skip(event)
        observer.on_handler_error(event)

    def test_subclass_can_override_single_method(self) -> None:
        """Subclass can override just one method."""
        captured: list[HookObservabilityEvent] = []

        class MyObserver(BaseObserver):
            def on_handler_end(self, event: HookObservabilityEvent) -> None:
                captured.append(event)

        observer = MyObserver()
        event = HookObservabilityEvent(
            event_type="handler_end",
            hook_id="abc123",
            session_id="session-1",
            hook_event_name="PreToolUse",
        )
        observer.on_handler_end(event)
        assert len(captured) == 1

        # Other methods still work (no-op)
        observer.on_hook_start(event)


class TestHookAppObserverRegistration:
    """Tests for observer registration on HookApp."""

    def test_add_observer_stores_observer(self) -> None:
        """app.add_observer() adds to _observers list."""
        app = HookApp()
        observer = EventCapture()
        app.add_observer(observer)
        assert observer in app._observers

    def test_on_observe_decorator_no_parens(self) -> None:
        """@app.on_observe works without parentheses."""
        app = HookApp()
        captured: list[HookObservabilityEvent] = []

        @app.on_observe
        def log_all(event: HookObservabilityEvent) -> None:
            captured.append(event)

        assert len(app._callback_observers) == 1
        assert app._callback_observers[0][1] is None  # No filter

    def test_on_observe_decorator_with_parens(self) -> None:
        """@app.on_observe() works with empty parentheses."""
        app = HookApp()

        @app.on_observe()
        def log_all(event: HookObservabilityEvent) -> None:
            pass

        assert len(app._callback_observers) == 1
        assert app._callback_observers[0][1] is None

    def test_on_observe_with_event_type_filter(self) -> None:
        """@app.on_observe('handler_end') filters to specific event type."""
        app = HookApp()

        @app.on_observe("handler_end")
        def log_handler_end(event: HookObservabilityEvent) -> None:
            pass

        assert len(app._callback_observers) == 1
        assert app._callback_observers[0][1] == "handler_end"


class TestEmission:
    """Tests for event emission."""

    def test_no_observers_skips_emission(self) -> None:
        """Zero overhead when no observers."""
        app = HookApp()
        # No observers registered

        @app.pre_tool("Bash")
        def check(event):
            return None

        client = TestClient(app)
        # Should not raise - emission is skipped
        result = client.send(MockEvent.bash("ls"))
        assert result is None or result.get("decision") != "block"

    def test_observer_exception_swallowed(self) -> None:
        """Bad observer doesn't break hook execution."""
        app = HookApp()

        class BadObserver(BaseObserver):
            def on_hook_start(self, event: HookObservabilityEvent) -> None:
                raise RuntimeError("I'm broken!")

        good_captured: list[HookObservabilityEvent] = []

        class GoodObserver(BaseObserver):
            def on_hook_start(self, event: HookObservabilityEvent) -> None:
                good_captured.append(event)

        app.add_observer(BadObserver())
        app.add_observer(GoodObserver())

        @app.pre_tool("Bash")
        def check(event):
            return None

        client = TestClient(app)
        result = client.send(MockEvent.bash("ls"))

        # Hook should still succeed
        assert result is None or result.get("decision") != "block"
        # Good observer should still be called
        assert len(good_captured) == 1

    def test_all_event_types_emitted(self) -> None:
        """Full flow emits hook_start, handler_start, handler_end, hook_end."""
        app = HookApp()
        observer = EventCapture()
        app.add_observer(observer)

        @app.pre_tool("Bash")
        def check(event):
            return None

        client = TestClient(app)
        client.send(MockEvent.bash("ls"))

        event_types = [e.event_type for e in observer.events]
        assert "hook_start" in event_types
        assert "handler_start" in event_types
        assert "handler_end" in event_types
        assert "hook_end" in event_types

    def test_handler_skip_emitted_on_early_deny(self) -> None:
        """Remaining handlers get skip events when one denies early."""
        app = HookApp()
        observer = EventCapture()
        app.add_observer(observer)

        @app.pre_tool("Bash")
        def handler_1(event):
            return deny("Blocked")

        @app.pre_tool("Bash")
        def handler_2(event):
            return None

        client = TestClient(app)
        client.send(MockEvent.bash("ls"))

        # handler_2 should be skipped
        skip_events = observer.events_of_type("handler_skip")
        assert len(skip_events) == 1
        assert skip_events[0].handler_name == "handler_2"
        assert "handler_1" in skip_events[0].skip_reason

    def test_handler_end_has_correct_decision_and_reason(self) -> None:
        """handler_end captures decision and reason from deny()."""
        app = HookApp()
        observer = EventCapture()
        app.add_observer(observer)

        @app.pre_tool("Bash")
        def check(event):
            return deny("Blocked dangerous command")

        client = TestClient(app)
        client.send(MockEvent.bash("rm -rf /"))

        handler_end = observer.events_of_type("handler_end")[0]
        assert handler_end.decision == "deny"
        assert handler_end.reason == "Blocked dangerous command"

        hook_end = observer.events_of_type("hook_end")[0]
        assert hook_end.decision == "deny"
        assert hook_end.reason == "Blocked dangerous command"

    def test_handler_error_emitted_on_exception(self) -> None:
        """Handler exceptions emit handler_error."""
        app = HookApp()
        observer = EventCapture()
        app.add_observer(observer)

        @app.pre_tool("Bash")
        def bad_handler(event):
            raise ValueError("oops")

        client = TestClient(app)
        client.send(MockEvent.bash("ls"))  # Should not raise (fail open)

        error_events = observer.events_of_type("handler_error")
        assert len(error_events) == 1
        assert error_events[0].error_type == "ValueError"
        assert "oops" in error_events[0].error_message

    def test_callback_filter_only_receives_matching_events(self) -> None:
        """Filtered callback only receives matching event type."""
        app = HookApp()
        all_events: list[str] = []
        handler_end_only: list[str] = []

        @app.on_observe
        def log_all(event: HookObservabilityEvent) -> None:
            all_events.append(event.event_type)

        @app.on_observe("handler_end")
        def log_handler_end(event: HookObservabilityEvent) -> None:
            handler_end_only.append(event.event_type)

        @app.pre_tool("Bash")
        def check(event):
            return None

        client = TestClient(app)
        client.send(MockEvent.bash("ls"))

        # All events received by unfiltered callback
        assert len(all_events) >= 4

        # Only handler_end received by filtered callback
        assert all(t == "handler_end" for t in handler_end_only)


class TestFileObserver:
    """Tests for FileObserver."""

    def test_writes_to_file(self, tmp_path) -> None:
        """FileObserver writes JSONL to file."""
        import json

        log_file = tmp_path / "events.jsonl"
        app = HookApp()
        app.add_observer(FileObserver(log_file))

        @app.pre_tool("Bash")
        def check(event):
            return None

        client = TestClient(app)
        client.send(MockEvent.bash("ls"))

        # Verify file was written
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) >= 4  # hook_start, handler_start, handler_end, hook_end

        # Verify JSONL format
        for line in lines:
            event = json.loads(line)
            assert "event_type" in event
            assert "hook_id" in event


class TestEventCapture:
    """Tests for EventCapture."""

    def test_captures_all_events(self) -> None:
        """EventCapture.events contains all emitted events."""
        app = HookApp()
        observer = EventCapture()
        app.add_observer(observer)

        @app.pre_tool("Bash")
        def check(event):
            return None

        client = TestClient(app)
        client.send(MockEvent.bash("ls"))

        assert len(observer.events) >= 4

    def test_events_of_type_filters(self) -> None:
        """events_of_type() returns filtered list."""
        app = HookApp()
        observer = EventCapture()
        app.add_observer(observer)

        @app.pre_tool("Bash")
        def check(event):
            return None

        client = TestClient(app)
        client.send(MockEvent.bash("ls"))

        hook_starts = observer.events_of_type("hook_start")
        assert len(hook_starts) == 1
        assert hook_starts[0].event_type == "hook_start"

    def test_handler_events_filters(self) -> None:
        """handler_events() returns events for specific handler."""
        app = HookApp()
        observer = EventCapture()
        app.add_observer(observer)

        @app.pre_tool("Bash")
        def my_handler(event):
            return None

        client = TestClient(app)
        client.send(MockEvent.bash("ls"))

        handler_events = observer.handler_events("my_handler")
        assert len(handler_events) >= 2  # start + end
        assert all(e.handler_name == "my_handler" for e in handler_events)

    def test_decisions_property(self) -> None:
        """decisions property returns list of decision strings."""
        app = HookApp()
        observer = EventCapture()
        app.add_observer(observer)

        @app.pre_tool("Bash")
        def check(event):
            return None

        client = TestClient(app)
        client.send(MockEvent.bash("ls"))

        decisions = observer.decisions()
        assert "allow" in decisions

    def test_clear_empties_events(self) -> None:
        """clear() empties the events list."""
        app = HookApp()
        observer = EventCapture()
        app.add_observer(observer)

        @app.pre_tool("Bash")
        def check(event):
            return None

        client = TestClient(app)
        client.send(MockEvent.bash("ls"))

        assert len(observer.events) > 0
        observer.clear()
        assert len(observer.events) == 0


class TestGuardSkipEvents:
    """Tests for guard-related skip events."""

    def test_guard_failure_emits_skip(self) -> None:
        """When guard returns False, handler_skip is emitted."""
        app = HookApp()
        observer = EventCapture()
        app.add_observer(observer)

        @app.pre_tool("Bash", when=lambda e: False)
        def guarded_handler(event):
            return None

        client = TestClient(app)
        client.send(MockEvent.bash("ls"))

        skip_events = observer.events_of_type("handler_skip")
        assert len(skip_events) == 1
        assert skip_events[0].handler_name == "guarded_handler"
        assert skip_events[0].skip_reason == "guard failed"
