"""Main HookApp class."""
from __future__ import annotations

import sys
from collections import defaultdict
from collections.abc import Callable
from typing import IO, Any

from cchooks._internal.io import read_stdin, write_stdout
from cchooks.events.base import BaseEvent
from cchooks.events.lifecycle import (
    Notification,
    PreCompact,
    SessionEnd,
    SessionStart,
    Stop,
    SubagentStop,
    UserPromptSubmit,
)
from cchooks.events.tools import (
    Bash,
    Edit,
    Glob,
    Grep,
    Read,
    Task,
    ToolEvent,
    WebFetch,
    WebSearch,
    Write,
)
from cchooks.responses import HookResponse

# Map tool names to typed event classes
TOOL_EVENT_MAP: dict[str, type[ToolEvent]] = {
    "Bash": Bash,
    "Write": Write,
    "Read": Read,
    "Edit": Edit,
    "Grep": Grep,
    "Glob": Glob,
    "Task": Task,
    "WebSearch": WebSearch,
    "WebFetch": WebFetch,
}


class HookApp:
    """Main application for registering and running hook handlers."""

    def __init__(self, state_dir: str | None = None, log_level: str = "INFO"):
        """Initialize HookApp.

        Args:
            state_dir: Directory for persistent state files
            log_level: Logging verbosity
        """
        self.state_dir = state_dir
        self.log_level = log_level
        self._pre_tool_handlers: dict[str, list[Callable]] = defaultdict(list)
        self._post_tool_handlers: dict[str, list[Callable]] = defaultdict(list)
        self._lifecycle_handlers: dict[str, list[Callable]] = defaultdict(list)

    # ═══════════════════════════════════════════════════════════════
    # Tool Decorators
    # ═══════════════════════════════════════════════════════════════

    def pre_tool(self, *tools: str) -> Callable:
        """Decorator to register a PreToolUse handler.

        Args:
            *tools: Tool names to match (e.g., "Bash", "Write")

        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            for tool in tools:
                self._pre_tool_handlers[tool].append(func)
            return func
        return decorator

    def post_tool(self, *tools: str) -> Callable:
        """Decorator to register a PostToolUse handler.

        Args:
            *tools: Tool names to match

        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            for tool in tools:
                self._post_tool_handlers[tool].append(func)
            return func
        return decorator

    # ═══════════════════════════════════════════════════════════════
    # Lifecycle Decorators
    # ═══════════════════════════════════════════════════════════════

    def on_stop(self) -> Callable:
        """Decorator for Stop events (main agent finished)."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["Stop"].append(func)
            return func
        return decorator

    def on_subagent_stop(self) -> Callable:
        """Decorator for SubagentStop events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["SubagentStop"].append(func)
            return func
        return decorator

    def on_session_start(self) -> Callable:
        """Decorator for SessionStart events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["SessionStart"].append(func)
            return func
        return decorator

    def on_session_end(self) -> Callable:
        """Decorator for SessionEnd events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["SessionEnd"].append(func)
            return func
        return decorator

    def on_pre_compact(self) -> Callable:
        """Decorator for PreCompact events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["PreCompact"].append(func)
            return func
        return decorator

    def on_prompt(self) -> Callable:
        """Decorator for UserPromptSubmit events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["UserPromptSubmit"].append(func)
            return func
        return decorator

    def on_notification(self) -> Callable:
        """Decorator for Notification events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["Notification"].append(func)
            return func
        return decorator

    def on_permission(self) -> Callable:
        """Decorator for PermissionRequest events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["PermissionRequest"].append(func)
            return func
        return decorator

    # ═══════════════════════════════════════════════════════════════
    # Runtime
    # ═══════════════════════════════════════════════════════════════

    def run(
        self,
        stdin: IO[str] | None = None,
        stdout: IO[str] | None = None,
    ) -> None:
        """Run the hook app, processing stdin and writing to stdout.

        Args:
            stdin: Input stream (default: sys.stdin)
            stdout: Output stream (default: sys.stdout)
        """
        if stdin is None:
            stdin = sys.stdin
        if stdout is None:
            stdout = sys.stdout

        # Read input
        data = read_stdin(stdin)
        if not data:
            return

        # Route to handlers
        response = self._dispatch(data)

        # Write output
        if response:
            write_stdout(response, stdout)

    def _dispatch(self, data: dict[str, Any]) -> HookResponse | None:
        """Dispatch event to appropriate handlers.

        Args:
            data: Raw input data

        Returns:
            Response from first blocking handler, or None
        """
        hook_type = data.get("hook_event_name", "")

        # Tool events
        if hook_type == "PreToolUse":
            tool_name = data.get("tool_name", "")
            handlers = self._pre_tool_handlers.get(tool_name, [])
            event = self._parse_tool_event(tool_name, data)
            return self._run_handlers(handlers, event)

        elif hook_type == "PostToolUse":
            tool_name = data.get("tool_name", "")
            handlers = self._post_tool_handlers.get(tool_name, [])
            event = self._parse_tool_event(tool_name, data)
            return self._run_handlers(handlers, event)

        # Lifecycle events
        elif hook_type in self._lifecycle_handlers:
            handlers = self._lifecycle_handlers[hook_type]
            event = self._parse_lifecycle_event(hook_type, data)
            return self._run_handlers(handlers, event)

        # No matching handlers
        return None

    def _parse_tool_event(self, tool_name: str, data: dict[str, Any]) -> ToolEvent:
        """Parse data into typed tool event."""
        event_class = TOOL_EVENT_MAP.get(tool_name, ToolEvent)
        return event_class.model_validate(data)

    def _parse_lifecycle_event(self, hook_type: str, data: dict[str, Any]) -> BaseEvent:
        """Parse data into typed lifecycle event."""
        event_classes: dict[str, type[BaseEvent]] = {
            "Stop": Stop,
            "SubagentStop": SubagentStop,
            "SessionStart": SessionStart,
            "SessionEnd": SessionEnd,
            "PreCompact": PreCompact,
            "UserPromptSubmit": UserPromptSubmit,
            "Notification": Notification,
        }
        event_class = event_classes.get(hook_type, BaseEvent)
        return event_class.model_validate(data)

    def _run_handlers(
        self,
        handlers: list[Callable],
        event: BaseEvent,
    ) -> HookResponse | None:
        """Run handlers in order, stopping on deny/block.

        Args:
            handlers: List of handler functions
            event: Typed event object

        Returns:
            First deny/block response, or None
        """
        for handler in handlers:
            try:
                response = handler(event)
                if response and response.decision in ("deny", "block"):
                    return response
            except Exception as e:
                # Log and continue (fail open)
                print(f"[cchooks] Handler {handler.__name__} failed: {e}", file=sys.stderr)
                continue

        return None
