"""Main HookApp class."""
from __future__ import annotations

import functools
import inspect
import json
import logging
import sys
import time
import warnings
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, get_type_hints
from uuid import uuid4

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
from fasthooks.observability.events import HookObservabilityEvent
from fasthooks.registry import HandlerEntry, HandlerRegistry
from fasthooks.responses import BaseHookResponse
from fasthooks.tasks.backend import BaseBackend, InMemoryBackend
from fasthooks.tasks.depends import BackgroundTasks, PendingResults, Tasks

# Valid event types for @app.on_observe filter
VALID_OBSERVER_EVENT_TYPES = frozenset({
    "hook_start",
    "hook_end",
    "hook_error",
    "handler_start",
    "handler_end",
    "handler_skip",
    "handler_error",
})

if TYPE_CHECKING:
    from fasthooks.observability.base import BaseObserver
    from fasthooks.observability.events import HookObservabilityEvent
    from fasthooks.strategies.base import Strategy
    from fasthooks.strategies.registry import StrategyRegistry as StrategyRegistryType

logger = logging.getLogger(__name__)

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
        task_backend: BaseBackend | None = None,
    ):
        """Initialize HookApp.

        Args:
            state_dir: Directory for persistent state files
            log_dir: Directory for JSONL event logs (enables built-in logging)
            log_level: Logging verbosity
            task_backend: Backend for background tasks (default: InMemoryBackend)
        """
        super().__init__()
        self.state_dir = state_dir
        self.log_dir = log_dir
        self.log_level = log_level

        # Deprecation warning for log_dir
        if log_dir is not None:
            warnings.warn(
                "log_dir is deprecated. Use app.add_observer(FileObserver(path)) instead. "
                "Will be removed in v2.0.",
                DeprecationWarning,
                stacklevel=2,
            )
        self._logger = EventLogger(log_dir) if log_dir else None
        self._middleware: list[Callable[..., Any]] = []
        self._task_backend: BaseBackend | None = task_backend  # Lazy init
        self._strategy_registry: StrategyRegistryType | None = None  # Lazy init

        # Observability
        self._observers: list[BaseObserver] = []
        self._callback_observers: list[tuple[Callable[..., Any], str | None]] = []

    @property
    def task_backend(self) -> BaseBackend:
        """Get the task backend, creating default InMemoryBackend if needed."""
        if self._task_backend is None:
            self._task_backend = InMemoryBackend()
        return self._task_backend

    @property
    def strategy_registry(self) -> StrategyRegistryType:
        """Get the strategy registry, creating if needed."""
        if self._strategy_registry is None:
            from fasthooks.strategies.registry import StrategyRegistry

            self._strategy_registry = StrategyRegistry()
        return self._strategy_registry

    # ═══════════════════════════════════════════════════════════════
    # Observability
    # ═══════════════════════════════════════════════════════════════

    def add_observer(self, observer: BaseObserver) -> None:
        """Register a class-based observer.

        Example:
            from fasthooks.observability import FileObserver
            app.add_observer(FileObserver())
        """
        self._observers.append(observer)

    def on_observe(
        self, event_type_or_func: str | Callable[..., Any] | None = None
    ) -> Callable[..., Any]:
        """Decorator to register a callback observer.

        Usage:
            @app.on_observe           # All events
            @app.on_observe()         # All events (explicit)
            @app.on_observe("handler_end")  # Specific event type

        Example:
            @app.on_observe("handler_end")
            def log_timing(event):
                print(f"{event.handler_name}: {event.duration_ms}ms")
        """
        # Handle @app.on_observe without parentheses
        if callable(event_type_or_func):
            func = event_type_or_func
            self._callback_observers.append((func, None))
            return func

        # Handle @app.on_observe() or @app.on_observe("handler_end")
        event_type = event_type_or_func

        # Validate event_type if provided
        if event_type is not None and event_type not in VALID_OBSERVER_EVENT_TYPES:
            warnings.warn(
                f"Unknown observer event type: {event_type!r}. "
                f"Valid types: {', '.join(sorted(VALID_OBSERVER_EVENT_TYPES))}",
                UserWarning,
                stacklevel=2,
            )

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._callback_observers.append((func, event_type))
            return func

        return decorator

    def _emit(self, event: HookObservabilityEvent) -> None:
        """Dispatch event to all observers.

        - No-op if no observers registered (zero overhead)
        - Swallows observer exceptions (logs warning)
        """
        # Zero overhead when unused
        if not self._observers and not self._callback_observers:
            return

        # Dispatch to class-based observers
        for observer in self._observers:
            method_name = f"on_{event.event_type}"
            method = getattr(observer, method_name, None)
            if method:
                try:
                    method(event)
                except Exception as e:
                    logger.warning(
                        f"Observer {observer.__class__.__name__}.{method_name} raised: {e}"
                    )

        # Dispatch to callback observers
        for callback, filter_type in self._callback_observers:
            if filter_type is None or filter_type == event.event_type:
                try:
                    callback(event)
                except Exception as e:
                    logger.warning(f"Observer callback {callback.__name__} raised: {e}")

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

    def include_strategy(self, strategy: Strategy) -> None:
        """Include a strategy with conflict detection.

        Registers the strategy and includes its blueprint. Raises an error
        if the strategy's hooks conflict with an already-registered strategy.

        Args:
            strategy: Strategy to include.

        Raises:
            StrategyConflictError: If strategy's hooks conflict with
                an existing strategy.

        Example:
            app = HookApp()

            # First strategy registers fine
            app.include_strategy(LongRunningStrategy())

            # Second strategy with same hooks raises error
            app.include_strategy(AnotherStopStrategy())
            # StrategyConflictError: Conflict on 'on_stop'
        """
        # Register with conflict detection
        self.strategy_registry.register(strategy)

        # Include the blueprint
        self.include(strategy.get_blueprint())

    @property
    def strategies(self) -> list[Strategy]:
        """All registered strategies."""
        return self.strategy_registry.strategies

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
        # Observability context
        hook_id = str(uuid4())
        start_time = time.perf_counter()
        session_id = data.get("session_id", "unknown")
        hook_event_name = data.get("hook_event_name", "unknown")
        tool_name = data.get("tool_name")
        input_preview = json.dumps(data)[:4096] if data else None

        # Emit hook_start
        self._emit(
            HookObservabilityEvent(
                event_type="hook_start",
                hook_id=hook_id,
                session_id=session_id,
                hook_event_name=hook_event_name,
                tool_name=tool_name,
                input_preview=input_preview,
            )
        )

        hook_type = hook_event_name
        event: BaseEvent
        handlers: list[HandlerEntry]
        response: BaseHookResponse | None = None

        try:
            # Tool events
            if hook_type == "PreToolUse":
                tool_name_str = data.get("tool_name", "")
                # Combine tool-specific handlers with catch-all ("*") handlers
                handlers = (
                    self._pre_tool_handlers.get(tool_name_str, [])
                    + self._pre_tool_handlers.get("*", [])
                )
                event = self._parse_tool_event(tool_name_str, data)
                response = await self._run_with_middleware(
                    handlers, event, hook_id, session_id, hook_event_name, tool_name
                )

            elif hook_type == "PostToolUse":
                tool_name_str = data.get("tool_name", "")
                # Combine tool-specific handlers with catch-all ("*") handlers
                handlers = (
                    self._post_tool_handlers.get(tool_name_str, [])
                    + self._post_tool_handlers.get("*", [])
                )
                event = self._parse_tool_event(tool_name_str, data)
                response = await self._run_with_middleware(
                    handlers, event, hook_id, session_id, hook_event_name, tool_name
                )

            elif hook_type == "PermissionRequest":
                tool_name_str = data.get("tool_name", "")
                # Combine tool-specific handlers with catch-all ("*") handlers
                handlers = (
                    self._permission_handlers.get(tool_name_str, [])
                    + self._permission_handlers.get("*", [])
                )
                event = self._parse_tool_event(tool_name_str, data)
                response = await self._run_with_middleware(
                    handlers, event, hook_id, session_id, hook_event_name, tool_name
                )

            # Lifecycle events
            elif hook_type in self._lifecycle_handlers:
                handlers = self._lifecycle_handlers[hook_type]
                event = self._parse_lifecycle_event(hook_type, data)
                response = await self._run_with_middleware(
                    handlers, event, hook_id, session_id, hook_event_name, tool_name
                )

        except Exception as e:
            # Emit hook_error
            self._emit(
                HookObservabilityEvent(
                    event_type="hook_error",
                    hook_id=hook_id,
                    session_id=session_id,
                    hook_event_name=hook_event_name,
                    tool_name=tool_name,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            )
            raise

        # Emit hook_end
        duration_ms = (time.perf_counter() - start_time) * 1000
        final_decision = None
        final_reason = None
        if response:
            # Extract decision from response
            final_decision = getattr(response, "decision", None)
            final_reason = getattr(response, "reason", None)

        self._emit(
            HookObservabilityEvent(
                event_type="hook_end",
                hook_id=hook_id,
                session_id=session_id,
                hook_event_name=hook_event_name,
                tool_name=tool_name,
                duration_ms=duration_ms,
                decision=final_decision,
                reason=final_reason,
            )
        )

        return response

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
        hook_id: str = "",
        session_id: str = "",
        hook_event_name: str = "",
        tool_name: str | None = None,
    ) -> BaseHookResponse | None:
        """Run handlers wrapped in middleware chain.

        Args:
            handlers: List of (handler, guard) tuples
            event: Typed event object
            hook_id: UUID for observability correlation
            session_id: Session ID for observability
            hook_event_name: Hook event name for observability
            tool_name: Tool name for observability

        Returns:
            Response from middleware or handlers
        """
        # Build the innermost function (actual handler execution)
        async def run_handlers(evt: BaseEvent) -> BaseHookResponse | None:
            return await self._run_handlers(
                handlers, evt, hook_id, session_id, hook_event_name, tool_name
            )

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
        hook_id: str = "",
        session_id: str = "",
        hook_event_name: str = "",
        tool_name: str | None = None,
    ) -> BaseHookResponse | None:
        """Run handlers in order, stopping when should_return() is True.

        Args:
            handlers: List of (handler, guard) tuples
            event: Typed event object
            hook_id: UUID for observability correlation
            session_id: Session ID for observability
            hook_event_name: Hook event name for observability
            tool_name: Tool name for observability

        Returns:
            First actionable response, or None
        """
        # Cache for dependencies that should be shared across handlers
        dep_cache: dict[str, Any] = {}

        for i, (handler, guard) in enumerate(handlers):
            handler_name = handler.__name__

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
                        # Emit handler_skip for guard failure
                        self._emit(
                            HookObservabilityEvent(
                                event_type="handler_skip",
                                hook_id=hook_id,
                                session_id=session_id,
                                hook_event_name=hook_event_name,
                                tool_name=tool_name,
                                handler_name=handler_name,
                                skip_reason="guard failed",
                            )
                        )
                        continue

                # Emit handler_start
                self._emit(
                    HookObservabilityEvent(
                        event_type="handler_start",
                        hook_id=hook_id,
                        session_id=session_id,
                        hook_event_name=hook_event_name,
                        tool_name=tool_name,
                        handler_name=handler_name,
                    )
                )

                handler_start = time.perf_counter()

                # Build dependencies based on type hints
                deps = self._resolve_dependencies(handler, event, dep_cache)

                # Run handler (supports async handlers)
                if inspect.iscoroutinefunction(handler):
                    response: BaseHookResponse | None = await handler(event, **deps)
                else:
                    response = await anyio.to_thread.run_sync(
                        functools.partial(handler, event, **deps)
                    )

                handler_duration = (time.perf_counter() - handler_start) * 1000

                # Determine decision from response
                decision = "allow"
                reason = None
                if response:
                    decision = getattr(response, "decision", None) or "allow"
                    reason = getattr(response, "reason", None)

                # Emit handler_end
                self._emit(
                    HookObservabilityEvent(
                        event_type="handler_end",
                        hook_id=hook_id,
                        session_id=session_id,
                        hook_event_name=hook_event_name,
                        tool_name=tool_name,
                        handler_name=handler_name,
                        duration_ms=handler_duration,
                        decision=decision,
                        reason=reason,
                    )
                )

                # Check if response should stop handler chain
                if response and response.should_return():
                    # Emit handler_skip for remaining handlers
                    for remaining_handler, _ in handlers[i + 1 :]:
                        self._emit(
                            HookObservabilityEvent(
                                event_type="handler_skip",
                                hook_id=hook_id,
                                session_id=session_id,
                                hook_event_name=hook_event_name,
                                tool_name=tool_name,
                                handler_name=remaining_handler.__name__,
                                skip_reason=f"early {decision} from {handler_name}",
                            )
                        )
                    return response

            except Exception as e:
                # Calculate duration up to exception
                error_duration = (time.perf_counter() - handler_start) * 1000
                # Emit handler_error
                self._emit(
                    HookObservabilityEvent(
                        event_type="handler_error",
                        hook_id=hook_id,
                        session_id=session_id,
                        hook_event_name=hook_event_name,
                        tool_name=tool_name,
                        handler_name=handler_name,
                        duration_ms=error_duration,
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
                )
                # Log and continue (fail open)
                print(
                    f"[fasthooks] Handler {handler_name} failed: {e}", file=sys.stderr
                )
                continue

        return None

    def _resolve_dependencies(
        self,
        handler: Callable[..., Any],
        event: BaseEvent,
        cache: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve dependencies for a handler based on type hints.

        Args:
            handler: Handler function to inspect
            event: Event object (for transcript_path, session_id)
            cache: Optional cache dict for sharing deps across handlers

        Returns:
            Dict of parameter name -> dependency instance
        """
        deps: dict[str, Any] = {}
        if cache is None:
            cache = {}

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
                # Cache Transcript per event to avoid redundant loads
                if "transcript" not in cache:
                    transcript_path = getattr(event, "transcript_path", None)
                    cache["transcript"] = Transcript(transcript_path)
                deps[param_name] = cache["transcript"]
            elif hint is State:
                if self.state_dir:
                    deps[param_name] = State.for_session(
                        event.session_id,
                        state_dir=Path(self.state_dir),
                    )
                else:
                    # No state_dir configured, provide no-op state
                    deps[param_name] = NullState()
            elif hint is BackgroundTasks:
                deps[param_name] = BackgroundTasks(
                    self.task_backend,
                    event.session_id,
                )
            elif hint is Tasks:
                deps[param_name] = Tasks(
                    self.task_backend,
                    event.session_id,
                )
            elif hint is PendingResults:
                deps[param_name] = PendingResults(
                    self.task_backend,
                    event.session_id,
                )

        return deps
