"""Strategy registry with conflict detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Strategy, StrategyMeta


class StrategyConflictError(Exception):
    """Raised when two strategies register conflicting hooks.

    A conflict occurs when two strategies both declare the same hook
    in their Meta.hooks. This prevents unpredictable behavior when
    multiple strategies might block/deny the same event.

    Example:
        StrategyConflictError: Conflict detected!

          Hook: on_stop
          Strategy 1: long-running v1.0.0
          Strategy 2: security-check v2.0.0

        Resolution options:
          1. Remove one strategy from configuration
          2. Configure one strategy to use a different hook
          3. Create a combined strategy that handles both concerns
    """

    def __init__(
        self,
        hook: str,
        existing: StrategyMeta,
        incoming: StrategyMeta,
    ):
        self.hook = hook
        self.existing = existing
        self.incoming = incoming

        message = self._format_message()
        super().__init__(message)

    def _format_message(self) -> str:
        return (
            f"Conflict detected!\n\n"
            f"  Hook: {self.hook}\n"
            f"  Strategy 1: {self.existing.name} v{self.existing.version}\n"
            f"  Strategy 2: {self.incoming.name} v{self.incoming.version}\n\n"
            f"Resolution options:\n"
            f"  1. Remove one strategy from configuration\n"
            f"  2. Configure one strategy to use a different hook\n"
            f"  3. Create a combined strategy that handles both concerns"
        )


class StrategyRegistry:
    """Manages strategy registration and conflict detection.

    Tracks which strategies have registered which hooks. When a new
    strategy is registered, checks for conflicts with existing strategies.

    Example:
        registry = StrategyRegistry()

        # First strategy registers fine
        registry.register(long_running_strategy)

        # Second strategy with same hooks raises error
        registry.register(another_stop_strategy)  # StrategyConflictError!
    """

    def __init__(self) -> None:
        self._hooks: dict[str, StrategyMeta] = {}
        self._strategies: list[Strategy] = []

    @property
    def strategies(self) -> list[Strategy]:
        """All registered strategies."""
        return self._strategies.copy()

    @property
    def hooks(self) -> dict[str, StrategyMeta]:
        """Map of hook -> strategy that registered it."""
        return self._hooks.copy()

    def register(self, strategy: Strategy) -> None:
        """Register a strategy, checking for conflicts.

        Args:
            strategy: Strategy to register.

        Raises:
            StrategyConflictError: If strategy's hooks conflict with
                an already-registered strategy.
        """
        meta = strategy.get_meta()

        # Check each hook for conflicts
        for hook in meta.hooks:
            if hook in self._hooks:
                existing = self._hooks[hook]
                raise StrategyConflictError(
                    hook=hook,
                    existing=existing,
                    incoming=meta,
                )

        # No conflicts - register all hooks
        for hook in meta.hooks:
            self._hooks[hook] = meta

        self._strategies.append(strategy)

    def is_registered(self, strategy_name: str) -> bool:
        """Check if a strategy is already registered.

        Args:
            strategy_name: Name of strategy to check.

        Returns:
            True if registered, False otherwise.
        """
        return any(s.get_meta().name == strategy_name for s in self._strategies)

    def get_strategy(self, name: str) -> Strategy | None:
        """Get a registered strategy by name.

        Args:
            name: Strategy name.

        Returns:
            Strategy if found, None otherwise.
        """
        for s in self._strategies:
            if s.get_meta().name == name:
                return s
        return None

    def clear(self) -> None:
        """Clear all registered strategies."""
        self._hooks.clear()
        self._strategies.clear()
