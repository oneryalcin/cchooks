"""Blueprint for composing hook handlers."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any


class Blueprint:
    """Composable collection of hook handlers.

    Use blueprints to organize handlers into logical groups
    that can be included in the main HookApp.

    Example:
        security = Blueprint("security")

        @security.pre_tool("Bash")
        def no_sudo(event):
            if "sudo" in event.command:
                return deny("sudo not allowed")

        app = HookApp()
        app.include(security)
    """

    def __init__(self, name: str):
        """Initialize Blueprint.

        Args:
            name: Name for this blueprint (for debugging)
        """
        self.name = name
        self._pre_tool_handlers: dict[str, list[tuple[Callable, Callable | None]]] = defaultdict(list)
        self._post_tool_handlers: dict[str, list[tuple[Callable, Callable | None]]] = defaultdict(list)
        self._lifecycle_handlers: dict[str, list[tuple[Callable, Callable | None]]] = defaultdict(list)

    def pre_tool(self, *tools: str, when: Callable | None = None) -> Callable:
        """Decorator to register a PreToolUse handler.

        If no tools specified, registers as catch-all for ALL tools.
        """
        def decorator(func: Callable) -> Callable:
            targets = tools if tools else ("*",)
            for tool in targets:
                self._pre_tool_handlers[tool].append((func, when))
            return func
        return decorator

    def post_tool(self, *tools: str, when: Callable | None = None) -> Callable:
        """Decorator to register a PostToolUse handler.

        If no tools specified, registers as catch-all for ALL tools.
        """
        def decorator(func: Callable) -> Callable:
            targets = tools if tools else ("*",)
            for tool in targets:
                self._post_tool_handlers[tool].append((func, when))
            return func
        return decorator

    def on_stop(self, when: Callable | None = None) -> Callable:
        """Decorator for Stop events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["Stop"].append((func, when))
            return func
        return decorator

    def on_subagent_stop(self, when: Callable | None = None) -> Callable:
        """Decorator for SubagentStop events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["SubagentStop"].append((func, when))
            return func
        return decorator

    def on_session_start(self, when: Callable | None = None) -> Callable:
        """Decorator for SessionStart events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["SessionStart"].append((func, when))
            return func
        return decorator

    def on_session_end(self, when: Callable | None = None) -> Callable:
        """Decorator for SessionEnd events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["SessionEnd"].append((func, when))
            return func
        return decorator

    def on_pre_compact(self, when: Callable | None = None) -> Callable:
        """Decorator for PreCompact events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["PreCompact"].append((func, when))
            return func
        return decorator

    def on_prompt(self, when: Callable | None = None) -> Callable:
        """Decorator for UserPromptSubmit events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["UserPromptSubmit"].append((func, when))
            return func
        return decorator

    def on_notification(self, when: Callable | None = None) -> Callable:
        """Decorator for Notification events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["Notification"].append((func, when))
            return func
        return decorator
