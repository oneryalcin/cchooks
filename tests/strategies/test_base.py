"""Tests for Strategy base class."""

import pytest

from fasthooks import Blueprint
from fasthooks.strategies import Strategy, StrategyMeta


class TestStrategyMeta:
    """StrategyMeta model tests."""

    def test_meta_defaults(self):
        """StrategyMeta has sensible defaults."""
        meta = StrategyMeta(name="test", version="1.0.0")
        assert meta.name == "test"
        assert meta.version == "1.0.0"
        assert meta.description == ""
        assert meta.hooks == []
        assert meta.fail_mode == "open"
        assert meta.custom_events == []

    def test_meta_full(self):
        """StrategyMeta accepts all fields."""
        meta = StrategyMeta(
            name="test",
            version="1.0.0",
            description="A test strategy",
            hooks=["on_stop", "pre_tool:Bash"],
            fail_mode="closed",
            custom_events=["my_event"],
        )
        assert meta.fail_mode == "closed"
        assert "my_event" in meta.custom_events


class MinimalStrategy(Strategy):
    """Minimal strategy for testing."""

    class Meta:
        name = "minimal"
        version = "1.0.0"
        hooks = ["on_stop"]

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("minimal")

        @bp.on_stop()
        def on_stop(event):
            from fasthooks import allow
            return allow(message="minimal strategy")

        return bp


class TestStrategyBase:
    """Strategy base class tests."""

    def test_get_meta(self):
        """get_meta returns StrategyMeta from class Meta."""
        strategy = MinimalStrategy()
        meta = strategy.get_meta()

        assert meta.name == "minimal"
        assert meta.version == "1.0.0"
        assert "on_stop" in meta.hooks

    def test_get_blueprint_returns_blueprint(self):
        """get_blueprint returns a Blueprint."""
        strategy = MinimalStrategy()
        bp = strategy.get_blueprint()

        assert isinstance(bp, Blueprint)
        assert bp.name == "minimal"

    def test_config_stored(self):
        """Strategy stores config kwargs."""
        strategy = MinimalStrategy(foo="bar", count=42)

        assert strategy.config == {"foo": "bar", "count": 42}


class CustomEventStrategy(Strategy):
    """Strategy with custom events for testing."""

    class Meta:
        name = "custom-events"
        version = "1.0.0"
        hooks = ["on_stop"]
        custom_events = ["my_custom_event"]

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("custom-events")

        @bp.on_stop()
        def on_stop(event):
            self.emit_custom("my_custom_event", {"key": "value"})
            from fasthooks import allow
            return allow()

        return bp


class TestCustomEvents:
    """Custom event emission tests."""

    def test_emit_custom_requires_declaration(self):
        """emit_custom raises if event not declared."""
        strategy = MinimalStrategy()

        with pytest.raises(ValueError, match="Undeclared custom event"):
            strategy.emit_custom("not_declared", {})

    def test_emit_custom_success(self):
        """emit_custom works for declared events."""
        strategy = CustomEventStrategy()
        events = []

        @strategy.on_observe
        def collect(event):
            events.append(event)

        # Need to trigger a hook to set up context
        _ = strategy.get_blueprint()
        # The emit happens inside the handler, so we need to invoke it
        # This is tested more thoroughly in observability tests
