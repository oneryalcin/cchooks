"""Main HookApp class."""
from __future__ import annotations

import inspect
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any, get_type_hints

from fasthooks._internal.io import read_stdin, write_stdout
from fasthooks.depends.state import NullState, State
from fasthooks.logging import EventLogger
from fasthooks.depends.transcript import Transcript
from fasthooks.events.base import BaseEvent
from fasthooks.events.lifecycle import (
    Notification,
    PreCompact,
    SessionEnd,
    SessionStart,
    Stop,
    SubagentStop,
    UserPromptSubmit,
)
from fasthooks.events.tools import (
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
from fasthooks.responses import HookResponse

# Type alias for handler with optional guard
HandlerEntry = tuple[Callable, Callable | None]

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

    def __init__(
        self,
        state_dir: str | None = None,
        log_dir: str | None = None,
        log_level: str = "INFO",
    ):
        """Initialize HookApp.

        Args:
            state_dir: Directory for persistent state files
            log_dir: Directory for JSONL event logs (enables built-in logging)
            log_level: Logging verbosity
        """
        self.state_dir = state_dir
        self.log_dir = log_dir
        self.log_level = log_level
        self._logger = EventLogger(log_dir) if log_dir else None
        # Handlers stored as (func, guard) tuples
        self._pre_tool_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)
        self._post_tool_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)
        self._lifecycle_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)
        self._middleware: list[Callable] = []

    # ═══════════════════════════════════════════════════════════════
    # Middleware
    # ═══════════════════════════════════════════════════════════════

    def middleware(self, func: Callable) -> Callable:
        """Decorator to register middleware.

        Middleware wraps all handler calls and can:
        - Execute code before/after handlers
        - Short-circuit by returning a response
        - Modify events or responses

        Example:
            @app.middleware
            def timing(event, call_next):
                start = time.time()
                response = call_next(event)
                print(f"Took {time.time() - start:.3f}s")
                return response
        """
        self._middleware.append(func)
        return func

    # ═══════════════════════════════════════════════════════════════
    # Blueprint
    # ═══════════════════════════════════════════════════════════════

    def include(self, blueprint: "Blueprint") -> None:
        """Include a blueprint's handlers.

        Args:
            blueprint: Blueprint to include
        """
        from fasthooks.blueprint import Blueprint

        # Copy pre_tool handlers
        for tool, handlers in blueprint._pre_tool_handlers.items():
            self._pre_tool_handlers[tool].extend(handlers)

        # Copy post_tool handlers
        for tool, handlers in blueprint._post_tool_handlers.items():
            self._post_tool_handlers[tool].extend(handlers)

        # Copy lifecycle handlers
        for event_type, handlers in blueprint._lifecycle_handlers.items():
            self._lifecycle_handlers[event_type].extend(handlers)

    # ═══════════════════════════════════════════════════════════════
    # Tool Decorators
    # ═══════════════════════════════════════════════════════════════

    def pre_tool(self, *tools: str, when: Callable | None = None) -> Callable:
        """Decorator to register a PreToolUse handler.

        Args:
            *tools: Tool names to match (e.g., "Bash", "Write").
                    If empty, registers as catch-all handler for ALL tools.
            when: Optional guard function that receives event, returns bool

        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            targets = tools if tools else ("*",)  # Empty = catch-all
            for tool in targets:
                self._pre_tool_handlers[tool].append((func, when))
            return func
        return decorator

    def post_tool(self, *tools: str, when: Callable | None = None) -> Callable:
        """Decorator to register a PostToolUse handler.

        Args:
            *tools: Tool names to match.
                    If empty, registers as catch-all handler for ALL tools.
            when: Optional guard function

        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            targets = tools if tools else ("*",)  # Empty = catch-all
            for tool in targets:
                self._post_tool_handlers[tool].append((func, when))
            return func
        return decorator

    # ═══════════════════════════════════════════════════════════════
    # Lifecycle Decorators
    # ═══════════════════════════════════════════════════════════════

    def on_stop(self, when: Callable | None = None) -> Callable:
        """Decorator for Stop events (main agent finished)."""
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

    def on_permission(self, when: Callable | None = None) -> Callable:
        """Decorator for PermissionRequest events."""
        def decorator(func: Callable) -> Callable:
            self._lifecycle_handlers["PermissionRequest"].append((func, when))
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

        # Log event BEFORE dispatch (runs for ALL events)
        if self._logger:
            try:
                self._logger.log(data)
            except Exception:
                pass  # Don't fail hook on logging error

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
            # Combine tool-specific handlers with catch-all ("*") handlers
            handlers = (
                self._pre_tool_handlers.get(tool_name, [])
                + self._pre_tool_handlers.get("*", [])
            )
            event = self._parse_tool_event(tool_name, data)
            return self._run_with_middleware(handlers, event)

        elif hook_type == "PostToolUse":
            tool_name = data.get("tool_name", "")
            # Combine tool-specific handlers with catch-all ("*") handlers
            handlers = (
                self._post_tool_handlers.get(tool_name, [])
                + self._post_tool_handlers.get("*", [])
            )
            event = self._parse_tool_event(tool_name, data)
            return self._run_with_middleware(handlers, event)

        # Lifecycle events
        elif hook_type in self._lifecycle_handlers:
            handlers = self._lifecycle_handlers[hook_type]
            event = self._parse_lifecycle_event(hook_type, data)
            return self._run_with_middleware(handlers, event)

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

    def _run_with_middleware(
        self,
        handlers: list[HandlerEntry],
        event: BaseEvent,
    ) -> HookResponse | None:
        """Run handlers wrapped in middleware chain.

        Args:
            handlers: List of (handler, guard) tuples
            event: Typed event object

        Returns:
            Response from middleware or handlers
        """
        # Build the innermost function (actual handler execution)
        def run_handlers(evt: BaseEvent) -> HookResponse | None:
            return self._run_handlers(handlers, evt)

        # Wrap with middleware (outermost first)
        chain = run_handlers
        for mw in reversed(self._middleware):
            chain = self._wrap_middleware(mw, chain)

        return chain(event)

    def _wrap_middleware(
        self,
        middleware: Callable,
        next_fn: Callable,
    ) -> Callable:
        """Wrap a middleware around the next function in chain."""
        def wrapped(event: BaseEvent) -> HookResponse | None:
            return middleware(event, next_fn)
        return wrapped

    def _run_handlers(
        self,
        handlers: list[HandlerEntry],
        event: BaseEvent,
    ) -> HookResponse | None:
        """Run handlers in order, stopping on deny/block.

        Args:
            handlers: List of (handler, guard) tuples
            event: Typed event object

        Returns:
            First deny/block response, or None
        """
        for handler, guard in handlers:
            try:
                # Check guard condition
                if guard is not None:
                    if not guard(event):
                        continue  # Guard failed, skip handler

                # Build dependencies based on type hints
                deps = self._resolve_dependencies(handler, event)
                response = handler(event, **deps)
                if response and response.decision in ("deny", "block"):
                    return response
            except Exception as e:
                # Log and continue (fail open)
                print(f"[cchooks] Handler {handler.__name__} failed: {e}", file=sys.stderr)
                continue

        return None

    def _resolve_dependencies(
        self,
        handler: Callable,
        event: BaseEvent,
    ) -> dict[str, Any]:
        """Resolve dependencies for a handler based on type hints.

        Args:
            handler: Handler function to inspect
            event: Event object (for transcript_path, session_id)

        Returns:
            Dict of parameter name -> dependency instance
        """
        deps: dict[str, Any] = {}

        try:
            hints = get_type_hints(handler)
        except Exception:
            return deps

        sig = inspect.signature(handler)
        for param_name, param in sig.parameters.items():
            if param_name == "event":
                continue

            hint = hints.get(param_name)
            if hint is Transcript:
                transcript_path = getattr(event, "transcript_path", None)
                deps[param_name] = Transcript(transcript_path)
            elif hint is State:
                if self.state_dir:
                    deps[param_name] = State.for_session(
                        event.session_id,
                        state_dir=Path(self.state_dir),
                    )
                else:
                    # No state_dir configured, provide no-op state
                    deps[param_name] = NullState()

        return deps
