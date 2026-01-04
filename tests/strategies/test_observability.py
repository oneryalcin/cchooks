"""Tests for strategy observability."""

from pathlib import Path

from fasthooks import Blueprint, allow
from fasthooks.observability import (
    DecisionEvent,
    FileObservabilityBackend,
    ObservabilityEvent,
    Verbosity,
)
from fasthooks.strategies import Strategy
from fasthooks.testing import StrategyTestClient


class ObservableStrategy(Strategy):
    """Strategy for testing observability."""

    class Meta:
        name = "observable"
        version = "1.0.0"
        hooks = ["on_stop"]
        custom_events = ["test_event"]

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("observable")

        @bp.on_stop()
        def on_stop(event, state=None):
            self.emit_custom("test_event", {"key": "value"})
            return allow(message="observed")

        return bp


class FailingStrategy(Strategy):
    """Strategy that throws exceptions."""

    class Meta:
        name = "failing"
        version = "1.0.0"
        hooks = ["on_stop"]
        fail_mode = "open"

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("failing")

        @bp.on_stop()
        def on_stop(event, state=None):
            raise ValueError("Intentional failure")

        return bp


class TestEventEmission:
    """Event emission tests."""

    def test_emits_hook_enter_and_exit(self, tmp_path: Path):
        """Handler emits hook_enter and hook_exit events."""
        strategy = ObservableStrategy()
        events = []

        @strategy.on_observe
        def collect(event):
            events.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.trigger_stop()

        event_types = [e.event_type for e in events]
        assert "hook_enter" in event_types
        assert "hook_exit" in event_types

    def test_event_order_is_correct(self, tmp_path: Path):
        """Events emitted in order: hook_enter, custom, decision, hook_exit."""
        strategy = ObservableStrategy()
        events = []

        @strategy.on_observe
        def collect(event):
            events.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.trigger_stop()

        event_types = [e.event_type for e in events]

        # hook_enter should be first
        assert event_types[0] == "hook_enter"
        # hook_exit should be last
        assert event_types[-1] == "hook_exit"
        # custom and decision should be in between
        assert "custom" in event_types
        assert "decision" in event_types

    def test_decision_event_contains_details(self, tmp_path: Path):
        """Decision event has decision, reason, message."""
        strategy = ObservableStrategy()
        events = []

        @strategy.on_observe
        def collect(event):
            events.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.trigger_stop()

        decisions = [e for e in events if e.event_type == "decision"]
        assert len(decisions) == 1

        decision = decisions[0]
        assert hasattr(decision, "decision")
        assert decision.decision == "approve"
        assert decision.message == "observed"

    def test_hook_exit_has_duration(self, tmp_path: Path):
        """hook_exit event includes duration_ms."""
        strategy = ObservableStrategy()
        events = []

        @strategy.on_observe
        def collect(event):
            events.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.trigger_stop()

        exits = [e for e in events if e.event_type == "hook_exit"]
        assert len(exits) == 1
        assert exits[0].duration_ms is not None
        assert exits[0].duration_ms >= 0


class TestCustomEvents:
    """Custom event tests."""

    def test_custom_event_emitted(self, tmp_path: Path):
        """Custom events are captured."""
        strategy = ObservableStrategy()
        events = []

        @strategy.on_observe
        def collect(event):
            events.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.trigger_stop()

        custom = [e for e in events if e.event_type == "custom"]
        assert len(custom) == 1
        assert custom[0].custom_event_type == "test_event"
        assert custom[0].payload == {"key": "value"}

    def test_custom_event_has_context(self, tmp_path: Path):
        """Custom events include session_id, strategy_name, hook_name."""
        strategy = ObservableStrategy()
        events = []

        @strategy.on_observe
        def collect(event):
            events.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.trigger_stop()

        custom = [e for e in events if e.event_type == "custom"][0]
        assert custom.session_id == "test-session"
        assert custom.strategy_name == "observable"
        assert "stop" in custom.hook_name.lower()


class TestErrorEvents:
    """Error event tests."""

    def test_error_event_on_exception(self, tmp_path: Path):
        """Exception in handler emits error event."""
        strategy = FailingStrategy()
        events = []

        @strategy.on_observe
        def collect(event):
            events.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)

        # Handler throws, but we should still get error event
        try:
            client.trigger_stop()
        except ValueError:
            pass

        errors = [e for e in events if e.event_type == "error"]
        assert len(errors) == 1
        assert errors[0].error_type == "ValueError"
        assert "Intentional failure" in errors[0].error_message


class TestFileBackend:
    """FileObservabilityBackend tests."""

    def test_creates_jsonl_file(self, tmp_path: Path):
        """Backend writes events to JSONL file."""
        backend = FileObservabilityBackend(base_dir=tmp_path)

        event = ObservabilityEvent(
            session_id="test-session",
            event_type="hook_enter",
            strategy_name="test",
            hook_name="on_stop",
        )
        backend.handle_event(event)
        result_path = backend.flush()

        assert result_path is not None
        assert result_path.exists()
        assert result_path.suffix == ".jsonl"

    def test_appends_to_existing_file(self, tmp_path: Path):
        """Backend appends to existing file."""
        backend = FileObservabilityBackend(base_dir=tmp_path)

        # First event
        event1 = ObservabilityEvent(
            session_id="test-session",
            event_type="hook_enter",
            strategy_name="test",
            hook_name="on_stop",
        )
        backend.handle_event(event1)
        backend.flush()

        # Second event
        event2 = ObservabilityEvent(
            session_id="test-session",
            event_type="hook_exit",
            strategy_name="test",
            hook_name="on_stop",
        )
        backend.handle_event(event2)
        backend.flush()

        # Check file has two lines
        result_path = tmp_path / "test-session.jsonl"
        lines = result_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_pending_count(self, tmp_path: Path):
        """pending_count tracks unflushed events."""
        backend = FileObservabilityBackend(base_dir=tmp_path)

        assert backend.pending_count == 0

        backend.handle_event(ObservabilityEvent(
            session_id="test",
            event_type="hook_enter",
            strategy_name="test",
            hook_name="on_stop",
        ))
        assert backend.pending_count == 1

        backend.flush()
        assert backend.pending_count == 0

    def test_clear_discards_events(self, tmp_path: Path):
        """clear() discards pending events."""
        backend = FileObservabilityBackend(base_dir=tmp_path)

        backend.handle_event(ObservabilityEvent(
            session_id="test",
            event_type="hook_enter",
            strategy_name="test",
            hook_name="on_stop",
        ))
        assert backend.pending_count == 1

        backend.clear()
        assert backend.pending_count == 0


class TestVerbosityFiltering:
    """Verbosity level filtering tests."""

    def test_minimal_only_decisions_and_errors(self, tmp_path: Path):
        """MINIMAL verbosity only includes decisions and errors."""
        backend = FileObservabilityBackend(
            base_dir=tmp_path,
            verbosity=Verbosity.MINIMAL,
        )

        # Add various events
        backend.handle_event(ObservabilityEvent(
            session_id="test",
            event_type="hook_enter",
            strategy_name="test",
            hook_name="on_stop",
        ))
        backend.handle_event(DecisionEvent(
            session_id="test",
            strategy_name="test",
            hook_name="on_stop",
            decision="approve",
        ))
        backend.handle_event(ObservabilityEvent(
            session_id="test",
            event_type="hook_exit",
            strategy_name="test",
            hook_name="on_stop",
        ))

        # Only decision should be queued
        assert backend.pending_count == 1

    def test_standard_includes_all(self, tmp_path: Path):
        """STANDARD verbosity includes all events."""
        backend = FileObservabilityBackend(
            base_dir=tmp_path,
            verbosity=Verbosity.STANDARD,
        )

        backend.handle_event(ObservabilityEvent(
            session_id="test",
            event_type="hook_enter",
            strategy_name="test",
            hook_name="on_stop",
        ))
        backend.handle_event(DecisionEvent(
            session_id="test",
            strategy_name="test",
            hook_name="on_stop",
            decision="approve",
        ))

        assert backend.pending_count == 2


class TestMultipleObservers:
    """Multiple observer callback tests."""

    def test_all_observers_called(self, tmp_path: Path):
        """All registered observers receive events."""
        strategy = ObservableStrategy()
        events1 = []
        events2 = []

        @strategy.on_observe
        def collect1(event):
            events1.append(event)

        @strategy.on_observe
        def collect2(event):
            events2.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.trigger_stop()

        assert len(events1) > 0
        assert len(events2) > 0
        assert len(events1) == len(events2)

    def test_observer_error_does_not_break_others(self, tmp_path: Path):
        """One failing observer doesn't stop other observers."""
        strategy = ObservableStrategy()
        events = []

        @strategy.on_observe
        def failing_observer(event):
            raise RuntimeError("Observer failed")

        @strategy.on_observe
        def good_observer(event):
            events.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.trigger_stop()

        # Good observer should still receive events
        assert len(events) > 0
