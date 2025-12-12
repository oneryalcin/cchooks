"""Main HookApp class."""
from __future__ import annotations

import functools
import inspect
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import IO, Any, get_type_hints

import anyio

from fasthooks._internal.io import read_stdin, write_stdout
from fasthooks.blueprint import Blueprint
from fasthooks.depends.state import NullState, State
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
from fasthooks.logging import EventLogger
from fasthooks.registry import HandlerEntry, HandlerRegistry
from fasthooks.responses import BaseHookResponse

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


class HookApp(HandlerRegistry):
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
        super().__init__()
        self.state_dir = state_dir
        self.log_dir = log_dir
        self.log_level = log_level
        self._logger = EventLogger(log_dir) if log_dir else None
        self._middleware: list[Callable[..., Any]] = []

    # ═══════════════════════════════════════════════════════════════
    # Middleware
    # ═══════════════════════════════════════════════════════════════

    def middleware(self, func: Callable[..., Any]) -> Callable[..., Any]:
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

    def include(self, blueprint: Blueprint) -> None:
        """Include a blueprint's handlers.

        Args:
            blueprint: Blueprint to include
        """
        # Copy pre_tool handlers
        for tool, handlers in blueprint._pre_tool_handlers.items():
            self._pre_tool_handlers[tool].extend(handlers)

        # Copy post_tool handlers
        for tool, handlers in blueprint._post_tool_handlers.items():
            self._post_tool_handlers[tool].extend(handlers)

        # Copy permission handlers
        for tool, handlers in blueprint._permission_handlers.items():
            self._permission_handlers[tool].extend(handlers)

        # Copy lifecycle handlers
        for event_type, handlers in blueprint._lifecycle_handlers.items():
            self._lifecycle_handlers[event_type].extend(handlers)

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
        anyio.run(self._async_run, stdin, stdout)

    async def _async_run(
        self,
        stdin: IO[str] | None = None,
        stdout: IO[str] | None = None,
    ) -> None:
        """Async implementation of run()."""
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
        response = await self._dispatch(data)

        # Write output
        if response:
            write_stdout(response, stdout)

    async def _dispatch(
        self, data: dict[str, Any]
    ) -> BaseHookResponse | None:
        """Dispatch event to appropriate handlers.

        Args:
            data: Raw input data

        Returns:
            Response from first blocking handler, or None
        """
        hook_type = data.get("hook_event_name", "")
        event: BaseEvent
        handlers: list[HandlerEntry]

        # Tool events
        if hook_type == "PreToolUse":
            tool_name = data.get("tool_name", "")
            # Combine tool-specific handlers with catch-all ("*") handlers
            handlers = (
                self._pre_tool_handlers.get(tool_name, [])
                + self._pre_tool_handlers.get("*", [])
            )
            event = self._parse_tool_event(tool_name, data)
            return await self._run_with_middleware(handlers, event)

        elif hook_type == "PostToolUse":
            tool_name = data.get("tool_name", "")
            # Combine tool-specific handlers with catch-all ("*") handlers
            handlers = (
                self._post_tool_handlers.get(tool_name, [])
                + self._post_tool_handlers.get("*", [])
            )
            event = self._parse_tool_event(tool_name, data)
            return await self._run_with_middleware(handlers, event)

        elif hook_type == "PermissionRequest":
            tool_name = data.get("tool_name", "")
            # Combine tool-specific handlers with catch-all ("*") handlers
            handlers = (
                self._permission_handlers.get(tool_name, [])
                + self._permission_handlers.get("*", [])
            )
            event = self._parse_tool_event(tool_name, data)
            return await self._run_with_middleware(handlers, event)

        # Lifecycle events
        elif hook_type in self._lifecycle_handlers:
            handlers = self._lifecycle_handlers[hook_type]
            event = self._parse_lifecycle_event(hook_type, data)
            return await self._run_with_middleware(handlers, event)

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

    async def _run_with_middleware(
        self,
        handlers: list[HandlerEntry],
        event: BaseEvent,
    ) -> BaseHookResponse | None:
        """Run handlers wrapped in middleware chain.

        Args:
            handlers: List of (handler, guard) tuples
            event: Typed event object

        Returns:
            Response from middleware or handlers
        """
        # Build the innermost function (actual handler execution)
        async def run_handlers(evt: BaseEvent) -> BaseHookResponse | None:
            return await self._run_handlers(handlers, evt)

        # Wrap with middleware (outermost first)
        chain: Callable[
            [BaseEvent], Coroutine[Any, Any, BaseHookResponse | None]
        ] = run_handlers
        for mw in reversed(self._middleware):
            chain = self._wrap_middleware(mw, chain)

        return await chain(event)

    def _wrap_middleware(
        self,
        middleware: Callable[..., Any],
        next_fn: Callable[[BaseEvent], Coroutine[Any, Any, BaseHookResponse | None]],
    ) -> Callable[[BaseEvent], Coroutine[Any, Any, BaseHookResponse | None]]:
        """Wrap a middleware around the next function in chain."""

        if inspect.iscoroutinefunction(middleware):
            # Async middleware - can await next_fn directly
            async def async_wrapped(event: BaseEvent) -> BaseHookResponse | None:
                result: BaseHookResponse | None = await middleware(event, next_fn)
                return result

            return async_wrapped
        else:
            # Sync middleware - provide sync call_next that bridges to async
            async def sync_wrapped(event: BaseEvent) -> BaseHookResponse | None:
                def sync_call_next(evt: BaseEvent) -> BaseHookResponse | None:
                    # Bridge from threadpool back to event loop
                    return anyio.from_thread.run(next_fn, evt)

                return await anyio.to_thread.run_sync(
                    functools.partial(middleware, event, sync_call_next)
                )

            return sync_wrapped

    async def _run_handlers(
        self,
        handlers: list[HandlerEntry],
        event: BaseEvent,
    ) -> BaseHookResponse | None:
        """Run handlers in order, stopping when should_return() is True.

        Args:
            handlers: List of (handler, guard) tuples
            event: Typed event object

        Returns:
            First actionable response, or None
        """
        for handler, guard in handlers:
            try:
                # Check guard condition (supports async guards)
                if guard is not None:
                    if inspect.iscoroutinefunction(guard):
                        guard_result = await guard(event)
                    else:
                        guard_result = await anyio.to_thread.run_sync(
                            functools.partial(guard, event)
                        )
                    if not guard_result:
                        continue  # Guard failed, skip handler

                # Build dependencies based on type hints
                deps = self._resolve_dependencies(handler, event)

                # Run handler (supports async handlers)
                if inspect.iscoroutinefunction(handler):
                    response: BaseHookResponse | None = await handler(event, **deps)
                else:
                    response = await anyio.to_thread.run_sync(
                        functools.partial(handler, event, **deps)
                    )

                # Check if response should stop handler chain
                if response and response.should_return():
                    return response
            except Exception as e:
                # Log and continue (fail open)
                print(f"[fasthooks] Handler {handler.__name__} failed: {e}", file=sys.stderr)
                continue

        return None

    def _resolve_dependencies(
        self,
        handler: Callable[..., Any],
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
