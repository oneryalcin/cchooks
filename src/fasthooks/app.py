"""Main HookApp class."""

from __future__ import annotations

import functools
import hmac
import inspect
import json
import logging
import os
import sys
import time
import warnings
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, get_type_hints
from uuid import uuid4

import anyio

from fasthooks._internal.io import read_stdin, serialize_response, write_stdout
from fasthooks.blueprint import Blueprint
from fasthooks.depends.state import NullState, State
from fasthooks.events.base import BaseEvent, GenericEvent, HookEventName
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
from fasthooks.registry import FAIL_MODE_ATTR, FailMode, HandlerEntry, HandlerRegistry
from fasthooks.responses import BaseHookResponse, block, deny, deny_permission

# Valid event types for @app.on_observe filter
VALID_OBSERVER_EVENT_TYPES = frozenset(
    {
        "hook_start",
        "hook_end",
        "hook_error",
        "handler_start",
        "handler_end",
        "handler_skip",
        "handler_error",
    }
)

if TYPE_CHECKING:
    from fasthooks.observability.base import BaseObserver
    from fasthooks.observability.events import HookObservabilityEvent
    from fasthooks.strategies.base import Strategy
    from fasthooks.strategies.registry import StrategyRegistry as StrategyRegistryType
    from fasthooks.tasks.backend import BaseBackend

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
        fail_mode: FailMode = "open",
    ):
        """Initialize HookApp.

        Args:
            state_dir: Directory for persistent state files
            log_dir: Directory for JSONL event logs (enables built-in logging)
            log_level: Logging verbosity
            task_backend: Backend for background tasks (default: InMemoryBackend)
            fail_mode: Default behavior when a handler raises. "open" (default)
                logs the error and lets the action proceed; "closed" denies the
                action for events that can block (PreToolUse, PostToolUse,
                PermissionRequest, Stop, SubagentStop). Override per handler via
                the decorator's ``fail_mode=`` argument.
        """
        super().__init__()
        self.state_dir = state_dir
        self.log_dir = log_dir
        self.log_level = log_level
        self.fail_mode: FailMode = fail_mode
        # Per-app typed-event overrides for custom/MCP tools, checked before the
        # built-in TOOL_EVENT_MAP. Per-instance (not a global mutation) so apps
        # and tests don't leak registrations into each other.
        self._tool_event_overrides: dict[str, type[ToolEvent]] = {}

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

        # Shared secret required by the http transport (set by serve()).
        self._auth_token: str | None = None

    @property
    def task_backend(self) -> BaseBackend:
        """Get the task backend, creating default InMemoryBackend if needed."""
        if self._task_backend is None:
            from fasthooks.tasks.backend import InMemoryBackend

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

    def _emit(self, event_type: str, **fields: Any) -> None:
        """Build and dispatch an observability event to all observers.

        - No-op if no observers registered: the event object is not even
          constructed, so the common (no-observer) path pays nothing — not
          even building a pydantic model per hook call.
        - Swallows observer exceptions (logs warning)
        """
        # Zero overhead when unused — return before constructing the event.
        if not self._observers and not self._callback_observers:
            return

        event = HookObservabilityEvent(event_type=event_type, **fields)

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
            write_stdout(response, stdout, data.get("hook_event_name"))

    # ═══════════════════════════════════════════════════════════════
    # HTTP server transport (Claude Code "http" hooks)
    # ═══════════════════════════════════════════════════════════════

    def serve(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        *,
        token: str | None = None,
        allow_unauthenticated: bool = False,
        log_level: str = "warning",
    ) -> None:
        """Run the hook app as a persistent HTTP server.

        The command-hook model (:meth:`run`) spawns a fresh Python process —
        and re-pays interpreter + import cost — on *every* tool call. As a
        Claude Code ``http`` hook instead, the app starts once and answers
        every event over HTTP in milliseconds. Point a ``type: "http"`` hook
        at ``http://{host}:{port}/`` (one endpoint handles all events; dispatch
        keys off ``hook_event_name``).

        Requires the ``server`` extra: ``pip install 'fasthooks[server]'``.

        The endpoint dispatches whatever event JSON it receives into your
        (arbitrary) handlers. Set ``token`` (or the ``FASTHOOKS_TOKEN`` env var)
        to require an ``Authorization: Bearer <token>`` header — recommended
        for any non-loopback bind, and worthwhile even on loopback (a local
        process or a browser page can POST to localhost). ``fasthooks install
        --http --auth`` generates a token and wires it into the hook config.

        Args:
            host: Interface to bind (default: loopback only).
            port: Port to bind.
            token: Shared secret to require. Defaults to ``$FASTHOOKS_TOKEN``.
            allow_unauthenticated: Permit a non-loopback bind without a token.
                Off by default: binding a public host with no auth is refused.
            log_level: uvicorn log level.
        """
        self._auth_token = token or os.environ.get("FASTHOOKS_TOKEN") or None

        # An unauthenticated non-loopback bind exposes arbitrary hook execution
        # to any reachable client. Fail closed unless explicitly allowed.
        # Checked before importing uvicorn so the refusal is fast and unconditional.
        # Only genuine loopback addresses bypass the auth requirement. An empty
        # or wildcard host (""/"0.0.0.0"/"::") binds all interfaces and must NOT
        # be treated as loopback.
        is_loopback = host in ("127.0.0.1", "localhost", "::1")
        if not self._auth_token and not is_loopback:
            if not allow_unauthenticated:
                raise RuntimeError(
                    f"Refusing to bind non-loopback host {host!r} without "
                    "authentication. Set a token (FASTHOOKS_TOKEN or "
                    "`install --http --auth`), or pass allow_unauthenticated=True "
                    "(`serve --allow-unauthenticated`) to override."
                )
            print(
                f"[fasthooks] WARNING: serving on {host!r} with NO authentication "
                "(--allow-unauthenticated) — any client that can reach this port "
                "can trigger your hooks.",
                file=sys.stderr,
            )

        try:
            import uvicorn
        except ImportError as e:  # pragma: no cover - import guard
            raise RuntimeError(
                "serve() requires uvicorn. Install with: "
                "pip install 'fasthooks[server]'"
            ) from e

        # interface="asgi3": _asgi_app is a bound method, which uvicorn's
        # auto-detection otherwise mistakes for the legacy ASGI 2.0 (one-arg
        # factory) protocol. Be explicit.
        uvicorn.run(
            self._asgi_app,
            host=host,
            port=port,
            log_level=log_level,
            interface="asgi3",
        )

    async def _asgi_app(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Any],
        send: Callable[[dict[str, Any]], Any],
    ) -> None:
        """Minimal ASGI handler backing :meth:`serve`.

        Claude Code ``http`` hooks POST the event JSON and expect the same
        JSON output format as command hooks. Per the hooks reference, any
        non-2xx/connection error fails open (execution continues), so on any
        internal error we return an empty 200 ("no decision") rather than
        risk blocking the agent loop.
        """
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return

        # Claude Code only ever POSTs hook events; reject anything else so the
        # endpoint isn't a general-purpose surface.
        if scope.get("method", "GET") != "POST":
            await send(
                {
                    "type": "http.response.start",
                    "status": 405,
                    "headers": [(b"allow", b"POST")],
                }
            )
            await send({"type": "http.response.body", "body": b""})
            return

        # Enforce the shared secret before reading/dispatching anything, so a
        # forged request can't reach handler code. Constant-time compare.
        if self._auth_token is not None:
            presented = ""
            for name, value in scope.get("headers", []):
                if name == b"authorization":
                    presented = value.decode("latin-1")
                    break
            expected = f"Bearer {self._auth_token}"
            if not hmac.compare_digest(presented, expected):
                await send({"type": "http.response.start", "status": 401, "headers": []})
                await send({"type": "http.response.body", "body": b""})
                return

        # Read the request body with a hard cap to bound memory. The cap is
        # generous (25 MiB) so legitimate large payloads — e.g. a PreToolUse
        # Write with big file content — still reach a protective handler rather
        # than 413ing (Claude Code treats non-2xx as fail-open, which would skip
        # the guard). Only pathological/abusive bodies exceed it; for those the
        # client controls its own payload anyway, so the fail-open is not an
        # escalation.
        max_body = 25 * 1024 * 1024  # 25 MiB
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > max_body:
                await send({"type": "http.response.start", "status": 413, "headers": []})
                await send({"type": "http.response.body", "body": b""})
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)

        output = ""
        try:
            data = json.loads(body) if body else {}
            if data:
                # Mirror the stdin path: log the raw event before dispatch so
                # the log_dir audit trail isn't lost in server mode.
                if self._logger:
                    try:
                        self._logger.log(data)
                    except Exception:
                        pass  # Don't fail the hook on a logging error
                response = await self._dispatch(data)
                if response:
                    output = serialize_response(response, data.get("hook_event_name"))
        except Exception as e:  # fail open — never block the agent loop
            print(f"[fasthooks] serve handler error: {e}", file=sys.stderr)

        payload = output.encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": payload})

    async def _dispatch(self, data: dict[str, Any]) -> BaseHookResponse | None:
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
            event_type="hook_start",
            hook_id=hook_id,
            session_id=session_id,
            hook_event_name=hook_event_name,
            tool_name=tool_name,
            input_preview=input_preview,
        )

        hook_type = hook_event_name
        event: BaseEvent
        handlers: list[HandlerEntry]
        response: BaseHookResponse | None = None

        try:
            # Tool events
            # Tool events carry a tool_name and support matcher + "*" handlers.
            tool_dicts = {
                HookEventName.PRE_TOOL_USE: self._pre_tool_handlers,
                HookEventName.POST_TOOL_USE: self._post_tool_handlers,
                HookEventName.PERMISSION_REQUEST: self._permission_handlers,
            }

            if hook_type in tool_dicts:
                tool_name_str = data.get("tool_name", "")
                registry = tool_dicts[hook_type]
                # Tool-specific + catch-all ("*") + any generic on() handlers
                handlers = (
                    registry.get(tool_name_str, [])
                    + registry.get("*", [])
                    + self._lifecycle_handlers.get(hook_type, [])
                )
                event = self._parse_tool_event(tool_name_str, data)
            else:
                # Generic path: any event name registered via on() or a typed
                # lifecycle decorator. Unknown events still dispatch (handlers
                # may be empty) and parse as GenericEvent, preserving all fields.
                handlers = self._lifecycle_handlers.get(hook_type, [])
                event = self._parse_lifecycle_event(hook_type, data)

            if handlers:
                response = await self._run_with_middleware(
                    handlers, event, hook_id, session_id, hook_event_name, tool_name
                )

        except Exception as e:
            # Emit hook_error
            self._emit(
                event_type="hook_error",
                hook_id=hook_id,
                session_id=session_id,
                hook_event_name=hook_event_name,
                tool_name=tool_name,
                error_type=type(e).__name__,
                error_message=str(e),
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
            event_type="hook_end",
            hook_id=hook_id,
            session_id=session_id,
            hook_event_name=hook_event_name,
            tool_name=tool_name,
            duration_ms=duration_ms,
            decision=final_decision,
            reason=final_reason,
        )

        return response

    def _fail_closed_response(
        self, hook_event_name: str, handler_name: str, error: Exception
    ) -> BaseHookResponse | None:
        """Synthesize an event-appropriate blocking response for a crashed handler.

        Used when the effective fail mode is "closed". Each event has its own
        block shape, so we reuse the response builders (a bare ``deny()`` would
        serialize wrong for a PermissionRequest). Events with no block semantics
        return ``None`` — there's nothing to block, so they stay fail-open.
        """
        reason = (
            f"Hook '{handler_name}' errored and fail_mode is closed "
            f"({type(error).__name__}: {error})"
        )
        if hook_event_name == HookEventName.PRE_TOOL_USE:
            return deny(reason)
        if hook_event_name == HookEventName.PERMISSION_REQUEST:
            return deny_permission(reason)
        if hook_event_name in (
            HookEventName.STOP,
            HookEventName.SUBAGENT_STOP,
            HookEventName.POST_TOOL_USE,
        ):
            return block(reason)
        # SessionStart/End, Notification, PreCompact, UserPromptSubmit, unknown:
        # no block semantics -> fail open even when closed.
        return None

    def register_tool_event(
        self, tool_name: str, event_class: type[ToolEvent]
    ) -> None:
        """Register a typed event class for a custom or MCP tool.

        Built-in tools (Bash, Write, ...) ship typed accessors; any other tool
        falls back to the bare :class:`ToolEvent`, where you read fields via
        ``event.tool_input``. Register a :class:`ToolEvent` subclass to get the
        same typed-accessor / autocomplete experience for your own tool. One
        registration covers PreToolUse, PostToolUse, and PermissionRequest.

        The subclass should expose fields via ``@property`` over
        ``self.tool_input`` and must NOT add required pydantic fields: parsing
        happens before the handler runs, so a validation error on a missing
        field would fail open (allow) even under ``fail_mode="closed"``.

        Args:
            tool_name: The tool's ``tool_name`` (e.g. "mcp__server__search").
            event_class: A ToolEvent subclass.

        Example:
            class Search(ToolEvent):
                @property
                def query(self) -> str:
                    return self.tool_input.get("query", "")

            app.register_tool_event("mcp__server__search", Search)
        """
        if not (isinstance(event_class, type) and issubclass(event_class, ToolEvent)):
            raise TypeError(
                f"event_class must be a ToolEvent subclass, got {event_class!r}"
            )
        self._tool_event_overrides[tool_name] = event_class

    def _parse_tool_event(self, tool_name: str, data: dict[str, Any]) -> ToolEvent:
        """Parse data into typed tool event.

        Resolution order: per-app override → built-in map → bare ToolEvent.
        """
        event_class = self._tool_event_overrides.get(tool_name) or TOOL_EVENT_MAP.get(
            tool_name, ToolEvent
        )
        return event_class.model_validate(data)

    def _parse_lifecycle_event(self, hook_type: str, data: dict[str, Any]) -> BaseEvent:
        """Parse data into typed lifecycle event."""
        event_classes: dict[str, type[BaseEvent]] = {
            HookEventName.STOP: Stop,
            HookEventName.SUBAGENT_STOP: SubagentStop,
            HookEventName.SESSION_START: SessionStart,
            HookEventName.SESSION_END: SessionEnd,
            HookEventName.PRE_COMPACT: PreCompact,
            HookEventName.USER_PROMPT_SUBMIT: UserPromptSubmit,
            HookEventName.NOTIFICATION: Notification,
        }
        # Unknown events fall back to GenericEvent (preserves all fields) so any
        # current or future Claude Code hook is dispatchable without a release.
        event_class = event_classes.get(hook_type, GenericEvent)
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
        chain: Callable[[BaseEvent], Coroutine[Any, Any, BaseHookResponse | None]] = run_handlers
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
        # A non-blocking response that still carries output (e.g.
        # allow(modify=...)). Held and returned only if no later handler blocks,
        # so deny/block precedence is preserved.
        pending: BaseHookResponse | None = None

        for i, (handler, guard) in enumerate(handlers):
            handler_name = handler.__name__
            handler_start = time.perf_counter()

            # A `when=` guard is a filter, not the safety check. If it can't be
            # evaluated (e.g. a field-based guard raising on an unfamiliar
            # GenericEvent payload), the handler simply doesn't match. Guard
            # errors ALWAYS fail open (skip the handler), independent of
            # fail_mode — only the handler body below honors fail_mode.
            if guard is not None:
                try:
                    if inspect.iscoroutinefunction(guard):
                        guard_result = await guard(event)
                    else:
                        guard_result = await anyio.to_thread.run_sync(
                            functools.partial(guard, event)
                        )
                except Exception as e:
                    self._emit(
                        event_type="handler_skip",
                        hook_id=hook_id,
                        session_id=session_id,
                        hook_event_name=hook_event_name,
                        tool_name=tool_name,
                        handler_name=handler_name,
                        skip_reason=f"guard error: {type(e).__name__}",
                    )
                    print(
                        f"[fasthooks] Guard for {handler_name} errored "
                        f"(skipping handler): {e}",
                        file=sys.stderr,
                    )
                    continue
                if not guard_result:
                    # Emit handler_skip for guard failure
                    self._emit(
                        event_type="handler_skip",
                        hook_id=hook_id,
                        session_id=session_id,
                        hook_event_name=hook_event_name,
                        tool_name=tool_name,
                        handler_name=handler_name,
                        skip_reason="guard failed",
                    )
                    continue

            try:
                # Emit handler_start
                self._emit(
                    event_type="handler_start",
                    hook_id=hook_id,
                    session_id=session_id,
                    hook_event_name=hook_event_name,
                    tool_name=tool_name,
                    handler_name=handler_name,
                )

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

                # Check if response should stop handler chain
                if response and response.should_return():
                    # Emit handler_skip for remaining handlers
                    for remaining_handler, _ in handlers[i + 1 :]:
                        self._emit(
                            event_type="handler_skip",
                            hook_id=hook_id,
                            session_id=session_id,
                            hook_event_name=hook_event_name,
                            tool_name=tool_name,
                            handler_name=remaining_handler.__name__,
                            skip_reason=f"early {decision} from {handler_name}",
                        )
                    return response

                # Non-blocking but actionable (e.g. allow(modify=...)): keep it
                # in case nothing later blocks; latest such response wins.
                if response is not None and response.carries_output():
                    pending = response

            except Exception as e:
                # Calculate duration up to exception
                error_duration = (time.perf_counter() - handler_start) * 1000
                # Emit handler_error
                self._emit(
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
                # Fail open (allow) or closed (block) depending on the
                # effective mode: per-handler override (stashed by the decorator
                # / strategy wrapper) falls back to the app default.
                effective_mode = getattr(handler, FAIL_MODE_ATTR, None) or self.fail_mode
                if effective_mode == "closed":
                    closed = self._fail_closed_response(hook_event_name, handler_name, e)
                    if closed is not None:
                        print(
                            f"[fasthooks] Handler {handler_name} failed; "
                            f"failing closed: {e}",
                            file=sys.stderr,
                        )
                        return closed

                # Log and continue (fail open)
                print(f"[fasthooks] Handler {handler_name} failed: {e}", file=sys.stderr)
                continue

        return pending

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
            if hint is None:
                continue

            # Detect injectable deps by qualified name rather than identity so
            # the pydantic-heavy Transcript/Tasks modules stay lazily imported
            # (see depends/tasks __init__). get_type_hints() above already
            # imported the module if — and only if — the handler annotates it.
            mod = getattr(hint, "__module__", "")
            name = getattr(hint, "__name__", "")

            if hint is State:
                if self.state_dir:
                    deps[param_name] = State.for_session(
                        event.session_id,
                        state_dir=Path(self.state_dir),
                    )
                else:
                    # No state_dir configured, provide no-op state
                    deps[param_name] = NullState()
            elif mod == "fasthooks.transcript.core" and name == "Transcript":
                # Cache Transcript per event to avoid redundant loads
                if "transcript" not in cache:
                    from fasthooks.depends.transcript import Transcript

                    transcript_path = getattr(event, "transcript_path", None)
                    cache["transcript"] = Transcript(transcript_path)
                deps[param_name] = cache["transcript"]
            elif mod == "fasthooks.tasks.depends" and name == "BackgroundTasks":
                from fasthooks.tasks.depends import BackgroundTasks

                deps[param_name] = BackgroundTasks(self.task_backend, event.session_id)
            elif mod == "fasthooks.tasks.depends" and name == "Tasks":
                from fasthooks.tasks.depends import Tasks

                deps[param_name] = Tasks(self.task_backend, event.session_id)
            elif mod == "fasthooks.tasks.depends" and name == "PendingResults":
                from fasthooks.tasks.depends import PendingResults

                deps[param_name] = PendingResults(self.task_backend, event.session_id)

        return deps
