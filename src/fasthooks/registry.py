"""Handler registry base class for HookApp and Blueprint."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any, Literal

# Type alias for handler with optional guard
HandlerEntry = tuple[Callable[..., Any], Callable[..., Any] | None]

# Per-handler fail-mode is stashed on the function so it survives into dispatch
# without changing the HandlerEntry tuple shape (which ripples through Blueprint,
# strategy wrapping, and the test clients). Read by HookApp._run_handlers.
FAIL_MODE_ATTR = "_fasthooks_fail_mode"

FailMode = Literal["open", "closed"]


def _tag_fail_mode(func: Callable[..., Any], fail_mode: FailMode | None) -> None:
    """Stash a per-handler fail-mode override on the function, if given."""
    if fail_mode is not None:
        setattr(func, FAIL_MODE_ATTR, fail_mode)


class HandlerRegistry:
    """Base class for registering hook handlers.

    Provides decorator methods for registering handlers. Used by both
    HookApp (which adds runtime/dispatch/DI) and Blueprint (lightweight).
    """

    def __init__(self) -> None:
        self._pre_tool_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)
        self._post_tool_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)
        self._post_tool_failure_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)
        self._permission_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)
        self._lifecycle_handlers: dict[str, list[HandlerEntry]] = defaultdict(list)

    # ═══════════════════════════════════════════════════════════════
    # Tool Decorators
    # ═══════════════════════════════════════════════════════════════

    def pre_tool(
        self,
        *tools: str,
        when: Callable[..., Any] | None = None,
        fail_mode: FailMode | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a PreToolUse handler.

        Args:
            *tools: Tool names to match (e.g., "Bash", "Write").
                    If empty, registers as catch-all handler for ALL tools.
            when: Optional guard function that receives event, returns bool
            fail_mode: Override the app's fail mode for this handler. "closed"
                    means a crash in this handler denies the tool instead of
                    silently allowing it. Defaults to the app's setting.

        Returns:
            Decorator function
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _tag_fail_mode(func, fail_mode)
            targets = tools if tools else ("*",)
            for tool in targets:
                self._pre_tool_handlers[tool].append((func, when))
            return func

        return decorator

    def post_tool(
        self,
        *tools: str,
        when: Callable[..., Any] | None = None,
        fail_mode: FailMode | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a PostToolUse handler.

        Args:
            *tools: Tool names to match.
                    If empty, registers as catch-all handler for ALL tools.
            when: Optional guard function
            fail_mode: Override the app's fail mode for this handler (see
                    :meth:`pre_tool`).

        Returns:
            Decorator function
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _tag_fail_mode(func, fail_mode)
            targets = tools if tools else ("*",)
            for tool in targets:
                self._post_tool_handlers[tool].append((func, when))
            return func

        return decorator

    def post_tool_failure(
        self,
        *tools: str,
        when: Callable[..., Any] | None = None,
        fail_mode: FailMode | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a PostToolUseFailure handler.

        Fires after a tool call fails (errors or returns a failure result). The
        handler receives a :class:`ToolFailureEvent` with ``event.error``,
        ``event.is_interrupt``, and ``event.duration_ms`` alongside the usual
        ``tool_name``/``tool_input``. Matches on tool name like ``post_tool``.

        Args:
            *tools: Tool names to match. If empty, catch-all for ALL tools.
            when: Optional guard function.
            fail_mode: Override the app's fail mode for this handler.

        Returns:
            Decorator function
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _tag_fail_mode(func, fail_mode)
            targets = tools if tools else ("*",)
            for tool in targets:
                self._post_tool_failure_handlers[tool].append((func, when))
            return func

        return decorator

    # ═══════════════════════════════════════════════════════════════
    # Generic (event-name) Decorator
    # ═══════════════════════════════════════════════════════════════

    def on(
        self,
        event_name: str,
        when: Callable[..., Any] | None = None,
        fail_mode: FailMode | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a handler for any hook event by name.

        The generic, never-stale entry point: works for any Claude Code hook
        event — including ones with no dedicated typed decorator (e.g.
        ``FileChanged``, ``PostToolUseFailure``, ``CwdChanged``). The handler
        receives a :class:`GenericEvent` (or the typed event if one exists),
        so new upstream events are usable without a fasthooks release.

        Args:
            event_name: The ``hook_event_name`` to match (e.g. "FileChanged").
            when: Optional guard function that receives the event, returns bool.
            fail_mode: Override the app's fail mode for this handler (see
                    :meth:`pre_tool`). Only events with block semantics
                    (PreToolUse, PostToolUse, PermissionRequest, Stop,
                    SubagentStop) can fail closed; others always fail open.

        Example:
            @app.on("FileChanged")
            def on_change(event):
                print(event.file_path)  # extra fields preserved
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _tag_fail_mode(func, fail_mode)
            self._lifecycle_handlers[event_name].append((func, when))
            return func

        return decorator

    # ═══════════════════════════════════════════════════════════════
    # Lifecycle Decorators
    # ═══════════════════════════════════════════════════════════════

    def on_stop(
        self,
        when: Callable[..., Any] | None = None,
        fail_mode: FailMode | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for Stop events (main agent finished).

        ``fail_mode="closed"`` blocks the stop (forces Claude to continue) if
        this handler crashes, instead of silently letting the session end.
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _tag_fail_mode(func, fail_mode)
            self._lifecycle_handlers["Stop"].append((func, when))
            return func

        return decorator

    def on_subagent_stop(
        self,
        when: Callable[..., Any] | None = None,
        fail_mode: FailMode | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for SubagentStop events."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _tag_fail_mode(func, fail_mode)
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
        self,
        *tools: str,
        when: Callable[..., Any] | None = None,
        fail_mode: FailMode | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for PermissionRequest events.

        Args:
            *tools: Tool names to match (e.g., "Bash", "Write").
                    If empty, registers as catch-all handler for ALL tools.
            when: Optional guard function
            fail_mode: Override the app's fail mode for this handler. "closed"
                    denies the permission if this handler crashes.

        Returns:
            Decorator function
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            _tag_fail_mode(func, fail_mode)
            targets = tools if tools else ("*",)
            for tool in targets:
                self._permission_handlers[tool].append((func, when))
            return func

        return decorator
