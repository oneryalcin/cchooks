"""Handler registry base class for HookApp and Blueprint."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

# Type alias for handler with optional guard
HandlerEntry = tuple[Callable[..., Any], Callable[..., Any] | None]


class HandlerRegistry:
    """Base class for registering hook handlers.

    Provides decorator methods for registering handlers. Used by both
    HookApp (which adds runtime/dispatch/DI) and Blueprint (lightweight).
    """

    def __init__(self) -> None:
        self._pre_tool_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)
        self._post_tool_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)
        self._permission_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)
        self._lifecycle_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)

    # ═══════════════════════════════════════════════════════════════
    # Tool Decorators
    # ═══════════════════════════════════════════════════════════════

    def pre_tool(
        self, *tools: str, when: Callable[..., Any] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a PreToolUse handler.

        Args:
            *tools: Tool names to match (e.g., "Bash", "Write").
                    If empty, registers as catch-all handler for ALL tools.
            when: Optional guard function that receives event, returns bool

        Returns:
            Decorator function
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            targets = tools if tools else ("*",)
            for tool in targets:
                self._pre_tool_handlers[tool].append((func, when))
            return func

        return decorator

    def post_tool(
        self, *tools: str, when: Callable[..., Any] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a PostToolUse handler.

        Args:
            *tools: Tool names to match.
                    If empty, registers as catch-all handler for ALL tools.
            when: Optional guard function

        Returns:
            Decorator function
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            targets = tools if tools else ("*",)
            for tool in targets:
                self._post_tool_handlers[tool].append((func, when))
            return func

        return decorator

    # ═══════════════════════════════════════════════════════════════
    # Lifecycle Decorators
    # ═══════════════════════════════════════════════════════════════

    def on_stop(
        self, when: Callable[..., Any] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for Stop events (main agent finished)."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._lifecycle_handlers["Stop"].append((func, when))
            return func

        return decorator

    def on_subagent_stop(
        self, when: Callable[..., Any] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for SubagentStop events."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._lifecycle_handlers["SubagentStop"].append((func, when))
            return func

        return decorator

    def on_session_start(
        self, when: Callable[..., Any] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for SessionStart events."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._lifecycle_handlers["SessionStart"].append((func, when))
            return func

        return decorator

    def on_session_end(
        self, when: Callable[..., Any] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for SessionEnd events."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._lifecycle_handlers["SessionEnd"].append((func, when))
            return func

        return decorator

    def on_pre_compact(
        self, when: Callable[..., Any] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for PreCompact events."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._lifecycle_handlers["PreCompact"].append((func, when))
            return func

        return decorator

    def on_prompt(
        self, when: Callable[..., Any] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for UserPromptSubmit events."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._lifecycle_handlers["UserPromptSubmit"].append((func, when))
            return func

        return decorator

    def on_notification(
        self, when: Callable[..., Any] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for Notification events."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._lifecycle_handlers["Notification"].append((func, when))
            return func

        return decorator

    def on_permission(
        self, *tools: str, when: Callable[..., Any] | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for PermissionRequest events.

        Args:
            *tools: Tool names to match (e.g., "Bash", "Write").
                    If empty, registers as catch-all handler for ALL tools.
            when: Optional guard function

        Returns:
            Decorator function
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            targets = tools if tools else ("*",)
            for tool in targets:
                self._permission_handlers[tool].append((func, when))
            return func

        return decorator
