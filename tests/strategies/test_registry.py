"""Tests for strategy registry and conflict detection."""

import pytest

from fasthooks import Blueprint, HookApp, allow
from fasthooks.strategies import (
    Strategy,
    StrategyConflictError,
    StrategyRegistry,
)


class StopStrategy(Strategy):
    """Strategy that uses on_stop hook."""

    class Meta:
        name = "stop-strategy"
        version = "1.0.0"
        hooks = ["on_stop"]

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("stop-strategy")

        @bp.on_stop()
        def on_stop(event: object) -> object:
            return allow()

        return bp


class AnotherStopStrategy(Strategy):
    """Another strategy that uses on_stop hook."""

    class Meta:
        name = "another-stop"
        version = "2.0.0"
        hooks = ["on_stop"]

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("another-stop")

        @bp.on_stop()
        def on_stop(event: object) -> object:
            return allow()

        return bp


class BashStrategy(Strategy):
    """Strategy that uses pre_tool:Bash hook."""

    class Meta:
        name = "bash-strategy"
        version = "1.0.0"
        hooks = ["pre_tool:Bash"]

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("bash-strategy")

        @bp.pre_tool("Bash")
        def check_bash(event: object) -> None:
            pass

        return bp


class CatchAllToolStrategy(Strategy):
    """Strategy that uses catch-all post_tool:* hook."""

    class Meta:
        name = "catch-all-tool"
        version = "1.0.0"
        hooks = ["post_tool:*"]

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("catch-all-tool")

        @bp.post_tool()
        def on_any_tool(event: object) -> None:
            pass

        return bp


class SpecificToolStrategy(Strategy):
    """Strategy that uses specific post_tool:Write hook."""

    class Meta:
        name = "specific-tool"
        version = "1.0.0"
        hooks = ["post_tool:Write"]

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("specific-tool")

        @bp.post_tool("Write")
        def on_write(event: object) -> None:
            pass

        return bp


class EmptyHooksStrategy(Strategy):
    """Strategy with no hooks declared."""

    class Meta:
        name = "empty-hooks"
        version = "1.0.0"
        hooks = []

    def _build_blueprint(self) -> Blueprint:
        return Blueprint("empty-hooks")


class MultiHookStrategy(Strategy):
    """Strategy with multiple hooks."""

    class Meta:
        name = "multi-hook"
        version = "1.0.0"
        hooks = ["on_stop", "pre_tool:Bash"]

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("multi-hook")

        @bp.on_stop()
        def on_stop(event: object) -> object:
            return allow()

        @bp.pre_tool("Bash")
        def check_bash(event: object) -> None:
            pass

        return bp


class TestStrategyRegistry:
    """StrategyRegistry tests."""

    def test_register_single_strategy(self) -> None:
        """Single strategy registers without error."""
        registry = StrategyRegistry()
        strategy = StopStrategy()

        registry.register(strategy)

        assert registry.is_registered("stop-strategy")
        assert len(registry.strategies) == 1

    def test_register_non_conflicting_strategies(self) -> None:
        """Non-conflicting strategies register successfully."""
        registry = StrategyRegistry()

        registry.register(StopStrategy())
        registry.register(BashStrategy())

        assert registry.is_registered("stop-strategy")
        assert registry.is_registered("bash-strategy")
        assert len(registry.strategies) == 2

    def test_conflict_on_same_hook(self) -> None:
        """Conflicting hooks raise StrategyConflictError."""
        registry = StrategyRegistry()

        registry.register(StopStrategy())

        with pytest.raises(StrategyConflictError) as exc_info:
            registry.register(AnotherStopStrategy())

        assert exc_info.value.hook == "on_stop"
        assert exc_info.value.existing.name == "stop-strategy"
        assert exc_info.value.incoming.name == "another-stop"

    def test_conflict_with_multi_hook_strategy(self) -> None:
        """Conflict detected when multi-hook strategy overlaps."""
        registry = StrategyRegistry()

        registry.register(StopStrategy())

        with pytest.raises(StrategyConflictError) as exc_info:
            registry.register(MultiHookStrategy())

        assert exc_info.value.hook == "on_stop"

    def test_get_strategy_by_name(self) -> None:
        """Can retrieve registered strategy by name."""
        registry = StrategyRegistry()
        strategy = StopStrategy()

        registry.register(strategy)

        retrieved = registry.get_strategy("stop-strategy")
        assert retrieved is strategy

    def test_get_nonexistent_strategy(self) -> None:
        """Returns None for non-registered strategy."""
        registry = StrategyRegistry()

        assert registry.get_strategy("nonexistent") is None

    def test_clear_registry(self) -> None:
        """Clear removes all strategies."""
        registry = StrategyRegistry()
        registry.register(StopStrategy())
        registry.register(BashStrategy())

        registry.clear()

        assert len(registry.strategies) == 0
        assert not registry.is_registered("stop-strategy")

    def test_hooks_property(self) -> None:
        """Hooks property returns copy of hook map."""
        registry = StrategyRegistry()
        registry.register(StopStrategy())

        hooks = registry.hooks
        assert "on_stop" in hooks
        assert hooks["on_stop"].name == "stop-strategy"

    def test_same_strategy_twice_conflicts(self) -> None:
        """Same strategy class registered twice conflicts."""
        registry = StrategyRegistry()
        registry.register(StopStrategy())

        with pytest.raises(StrategyConflictError) as exc_info:
            registry.register(StopStrategy())  # New instance, same hooks

        assert exc_info.value.hook == "on_stop"

    def test_empty_hooks_registers(self) -> None:
        """Strategy with empty hooks list registers without issue."""
        registry = StrategyRegistry()

        registry.register(EmptyHooksStrategy())

        assert registry.is_registered("empty-hooks")
        assert len(registry.hooks) == 0

    def test_catch_all_conflicts_with_specific(self) -> None:
        """Catch-all hook conflicts with specific hook."""
        registry = StrategyRegistry()
        registry.register(SpecificToolStrategy())  # post_tool:Write

        with pytest.raises(StrategyConflictError) as exc_info:
            registry.register(CatchAllToolStrategy())  # post_tool:*

        assert exc_info.value.hook == "post_tool:*"
        assert exc_info.value.existing.name == "specific-tool"

    def test_specific_conflicts_with_catch_all(self) -> None:
        """Specific hook conflicts with already registered catch-all."""
        registry = StrategyRegistry()
        registry.register(CatchAllToolStrategy())  # post_tool:*

        with pytest.raises(StrategyConflictError) as exc_info:
            registry.register(SpecificToolStrategy())  # post_tool:Write

        assert exc_info.value.hook == "post_tool:Write"
        assert exc_info.value.existing.name == "catch-all-tool"

    def test_different_prefixes_no_conflict(self) -> None:
        """Different hook prefixes don't conflict."""
        registry = StrategyRegistry()

        # pre_tool:Bash and post_tool:* have different prefixes
        registry.register(BashStrategy())  # pre_tool:Bash
        registry.register(CatchAllToolStrategy())  # post_tool:*

        assert len(registry.strategies) == 2


class TestStrategyConflictError:
    """StrategyConflictError tests."""

    def test_error_message_format(self) -> None:
        """Error message contains relevant info."""
        registry = StrategyRegistry()
        registry.register(StopStrategy())

        try:
            registry.register(AnotherStopStrategy())
        except StrategyConflictError as e:
            message = str(e)
            assert "on_stop" in message
            assert "stop-strategy" in message
            assert "another-stop" in message
            assert "Resolution options" in message

    def test_error_attributes(self) -> None:
        """Error has hook, existing, and incoming attributes."""
        registry = StrategyRegistry()
        registry.register(StopStrategy())

        try:
            registry.register(AnotherStopStrategy())
        except StrategyConflictError as e:
            assert e.hook == "on_stop"
            assert e.existing.name == "stop-strategy"
            assert e.existing.version == "1.0.0"
            assert e.incoming.name == "another-stop"
            assert e.incoming.version == "2.0.0"


class TestHookAppIncludeStrategy:
    """HookApp.include_strategy() tests."""

    def test_include_strategy_registers(self) -> None:
        """include_strategy registers the strategy."""
        app = HookApp()

        app.include_strategy(StopStrategy())

        assert len(app.strategies) == 1
        assert app.strategies[0].get_meta().name == "stop-strategy"

    def test_include_multiple_non_conflicting(self) -> None:
        """Multiple non-conflicting strategies work."""
        app = HookApp()

        app.include_strategy(StopStrategy())
        app.include_strategy(BashStrategy())

        assert len(app.strategies) == 2

    def test_include_conflicting_raises(self) -> None:
        """Conflicting strategies raise error."""
        app = HookApp()

        app.include_strategy(StopStrategy())

        with pytest.raises(StrategyConflictError):
            app.include_strategy(AnotherStopStrategy())

    def test_strategies_property_returns_copy(self) -> None:
        """strategies property returns a copy."""
        app = HookApp()
        app.include_strategy(StopStrategy())

        strategies = app.strategies
        strategies.clear()  # Modify the returned list

        assert len(app.strategies) == 1  # Original unchanged

    def test_include_via_blueprint_skips_conflict_detection(self) -> None:
        """Using include() directly skips conflict detection."""
        app = HookApp()

        # Use include_strategy for first
        app.include_strategy(StopStrategy())

        # Use include() directly for second - no conflict check
        second = AnotherStopStrategy()
        app.include(second.get_blueprint())  # No error

        # But only first is in strategies list
        assert len(app.strategies) == 1


class TestRealStrategyIntegration:
    """Integration tests with real built-in strategies."""

    def test_token_budget_and_clean_state_no_conflict(self) -> None:
        """TokenBudgetStrategy and CleanStateStrategy don't conflict."""
        from fasthooks.strategies import CleanStateStrategy, TokenBudgetStrategy

        app = HookApp()

        # TokenBudgetStrategy uses post_tool:*
        # CleanStateStrategy uses on_stop
        # Different hook types - no conflict
        app.include_strategy(TokenBudgetStrategy())
        app.include_strategy(CleanStateStrategy())

        assert len(app.strategies) == 2

    def test_long_running_and_token_budget_conflict(self) -> None:
        """LongRunningStrategy and TokenBudgetStrategy conflict on post_tool."""
        from fasthooks.strategies import LongRunningStrategy, TokenBudgetStrategy

        app = HookApp()

        # LongRunningStrategy uses post_tool:Write, post_tool:Edit, post_tool:Bash
        app.include_strategy(LongRunningStrategy())

        # TokenBudgetStrategy uses post_tool:* which conflicts
        with pytest.raises(StrategyConflictError) as exc_info:
            app.include_strategy(TokenBudgetStrategy())

        assert exc_info.value.hook == "post_tool:*"
        assert exc_info.value.existing.name == "long-running"

    def test_long_running_and_clean_state_conflict(self) -> None:
        """LongRunningStrategy and CleanStateStrategy conflict on on_stop."""
        from fasthooks.strategies import CleanStateStrategy, LongRunningStrategy

        app = HookApp()

        app.include_strategy(LongRunningStrategy())

        with pytest.raises(StrategyConflictError) as exc_info:
            app.include_strategy(CleanStateStrategy())

        assert exc_info.value.hook == "on_stop"
        assert exc_info.value.existing.name == "long-running"
        assert exc_info.value.incoming.name == "clean-state"
