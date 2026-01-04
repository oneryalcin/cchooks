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

    Conflict rules:
    - Exact hook match: on_stop vs on_stop
    - Catch-all overlap: post_tool:* vs post_tool:Bash

    Example:
        registry = StrategyRegistry()

        # First strategy registers fine
        registry.register(long_running_strategy)

        # Second strategy with same hooks raises error
        registry.register(another_stop_strategy)  # StrategyConflictError!
    """

    def __init__(self) -> None:
        self._hook_owners: dict[str, StrategyMeta] = {}
        self._strategies: list[Strategy] = []

    @property
    def strategies(self) -> list[Strategy]:
        """All registered strategies."""
        return self._strategies.copy()

    @property
    def hooks(self) -> dict[str, StrategyMeta]:
        """Map of hook -> strategy that owns it."""
        return self._hook_owners.copy()

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
            conflict = self._find_conflict(hook)
            if conflict:
                raise StrategyConflictError(
                    hook=hook,
                    existing=conflict,
                    incoming=meta,
                )

        # No conflicts - register all hooks
        for hook in meta.hooks:
            self._hook_owners[hook] = meta

        self._strategies.append(strategy)

    def _find_conflict(self, hook: str) -> StrategyMeta | None:
        """Find conflicting hook owner, if any.

        Checks for:
        1. Exact match (on_stop vs on_stop)
        2. Catch-all overlap (post_tool:* vs post_tool:Bash)

        Args:
            hook: Hook to check.

        Returns:
            StrategyMeta of conflicting strategy, or None.
        """
        # Exact match
        if hook in self._hook_owners:
            return self._hook_owners[hook]

        # Catch-all conflicts
        if hook.endswith(":*"):
            # New hook is catch-all, check for specific hooks
            prefix = hook[:-1]  # "post_tool:" from "post_tool:*"
            for existing_hook, owner in self._hook_owners.items():
                if existing_hook.startswith(prefix) and existing_hook != hook:
                    return owner
        else:
            # New hook is specific, check for catch-all
            parts = hook.split(":")
            if len(parts) == 2:
                catch_all = f"{parts[0]}:*"
                if catch_all in self._hook_owners:
                    return self._hook_owners[catch_all]

        return None

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
        self._hook_owners.clear()
        self._strategies.clear()
