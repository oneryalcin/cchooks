"""Strategy base class with observability."""

from __future__ import annotations

import functools
import time
import traceback
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from fasthooks import Blueprint

from ..observability import DecisionEvent, ErrorEvent, ObservabilityEvent


class StrategyMeta(BaseModel):
    """Strategy metadata."""

    name: str
    version: str
    description: str = ""
    hooks: list[str] = Field(default_factory=list)
    fail_mode: Literal["open", "closed"] = "open"
    custom_events: list[str] = Field(default_factory=list)
    state_namespace: str | None = None  # Defaults to strategy name if None


class Strategy(ABC):
    """Base class for fasthooks strategies.

    Strategies are reusable hook patterns with built-in observability.
    Subclasses implement _build_blueprint() to define handlers.

    Example:
        class MyStrategy(Strategy):
            class Meta:
                name = "my-strategy"
                version = "1.0.0"
                hooks = ["pre_tool:Bash"]

            def _build_blueprint(self) -> Blueprint:
                bp = Blueprint("my-strategy")

                @bp.pre_tool("Bash")
                def check(event):
                    if "dangerous" in event.command:
                        return deny("blocked")

                return bp

        # Usage
        app = HookApp()
        strategy = MyStrategy()
        app.include(strategy.get_blueprint())
    """

    class Meta:
        """Strategy metadata. Override in subclasses."""

        name: str = "unnamed"
        version: str = "0.0.0"
        description: str = ""
        hooks: list[str] = []
        fail_mode: Literal["open", "closed"] = "open"
        custom_events: list[str] = []
        state_namespace: str | None = None  # Defaults to strategy name if None

    def __init__(self, **config: Any):
        """Initialize strategy with configuration.

        Args:
            **config: Strategy-specific configuration options.
        """
        self.config = config
        self._observers: list[Callable[[ObservabilityEvent], None]] = []
        self._current_session_id: str | None = None
        self._current_request_id: str | None = None
        self._current_hook: str | None = None
        self._validate_config()

    def _validate_config(self) -> None:
        """Override to validate configuration. Raise on invalid."""
        pass

    def on_observe(
        self, callback: Callable[[ObservabilityEvent], None]
    ) -> Callable[[ObservabilityEvent], None]:
        """Register observer callback.

        Args:
            callback: Function called with each ObservabilityEvent.

        Returns:
            The callback (for use as decorator).
        """
        self._observers.append(callback)
        return callback

    def _emit(self, event: ObservabilityEvent) -> None:
        """Emit event to all observers."""
        for callback in self._observers:
            try:
                callback(event)
            except Exception:
                pass  # Don't let observer errors break strategy

    def emit_custom(self, event_type: str, payload: dict[str, Any]) -> None:
        """Emit custom event (must be declared in Meta.custom_events).

        Args:
            event_type: Name of custom event (declared in Meta.custom_events).
            payload: Event payload data.

        Raises:
            ValueError: If event_type not declared in Meta.custom_events.
        """
        custom_events = getattr(self.Meta, "custom_events", [])
        if event_type not in custom_events:
            raise ValueError(
                f"Undeclared custom event: {event_type}. "
                f"Declare in Meta.custom_events: {custom_events}"
            )

        self._emit(
            ObservabilityEvent(
                session_id=self._current_session_id or "unknown",
                request_id=self._current_request_id or str(uuid.uuid4()),
                event_type="custom",
                custom_event_type=event_type,
                strategy_name=self.Meta.name,
                hook_name=self._current_hook or "unknown",
                payload=payload,
            )
        )

    def get_blueprint(self) -> Blueprint:
        """Returns blueprint with observability wrapping.

        Calls _build_blueprint() and wraps all handlers with observability.
        """
        bp = self._build_blueprint()
        return self._wrap_blueprint(bp)

    @abstractmethod
    def _build_blueprint(self) -> Blueprint:
        """Subclass implements: return unwrapped blueprint with handlers."""
        raise NotImplementedError

    def _wrap_blueprint(self, bp: Blueprint) -> Blueprint:
        """Post-process: wrap all handlers with observability."""
        # Wrap pre_tool handlers
        for tool, handlers in bp._pre_tool_handlers.items():
            bp._pre_tool_handlers[tool] = [
                (self._wrap_handler(h, f"pre_tool:{tool}"), guard)
                for h, guard in handlers
            ]
        # Wrap post_tool handlers
        for tool, handlers in bp._post_tool_handlers.items():
            bp._post_tool_handlers[tool] = [
                (self._wrap_handler(h, f"post_tool:{tool}"), guard)
                for h, guard in handlers
            ]
        # Wrap lifecycle handlers
        for event_name, handlers in bp._lifecycle_handlers.items():
            bp._lifecycle_handlers[event_name] = [
                (self._wrap_handler(h, f"on_{event_name.lower()}"), guard)
                for h, guard in handlers
            ]
        # Wrap permission handlers
        for tool, handlers in bp._permission_handlers.items():
            bp._permission_handlers[tool] = [
                (self._wrap_handler(h, f"on_permission:{tool}"), guard)
                for h, guard in handlers
            ]
        return bp

    def _wrap_handler(
        self, handler: Callable[..., Any], hook_name: str
    ) -> Callable[..., Any]:
        """Wrap single handler with observability."""

        @functools.wraps(handler)
        def wrapped(event: Any, *args: Any, **kwargs: Any) -> Any:
            self._current_session_id = getattr(event, "session_id", "unknown")
            self._current_request_id = str(uuid.uuid4())
            self._current_hook = hook_name

            # Emit hook_enter
            self._emit(
                ObservabilityEvent(
                    session_id=self._current_session_id,
                    request_id=self._current_request_id,
                    event_type="hook_enter",
                    strategy_name=self.Meta.name,
                    hook_name=hook_name,
                )
            )

            start = time.perf_counter()
            try:
                result = handler(event, *args, **kwargs)

                # Emit decision if result returned
                if result is not None:
                    decision = getattr(result, "decision", "approve")
                    self._emit(
                        DecisionEvent(
                            session_id=self._current_session_id,
                            request_id=self._current_request_id,
                            strategy_name=self.Meta.name,
                            hook_name=hook_name,
                            decision=decision,
                            reason=getattr(result, "reason", None),
                            message=getattr(result, "message", None),
                        )
                    )
                return result

            except Exception as e:
                self._emit(
                    ErrorEvent(
                        session_id=self._current_session_id,
                        request_id=self._current_request_id,
                        strategy_name=self.Meta.name,
                        hook_name=hook_name,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        traceback=traceback.format_exc(),
                    )
                )
                raise

            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                self._emit(
                    ObservabilityEvent(
                        session_id=self._current_session_id,
                        request_id=self._current_request_id,
                        event_type="hook_exit",
                        strategy_name=self.Meta.name,
                        hook_name=hook_name,
                        duration_ms=duration_ms,
                    )
                )

        return wrapped

    def get_meta(self) -> StrategyMeta:
        """Return strategy metadata."""
        return StrategyMeta(
            name=self.Meta.name,
            version=self.Meta.version,
            description=getattr(self.Meta, "description", ""),
            hooks=getattr(self.Meta, "hooks", []),
            fail_mode=getattr(self.Meta, "fail_mode", "open"),
            custom_events=getattr(self.Meta, "custom_events", []),
            state_namespace=getattr(self.Meta, "state_namespace", None),
        )

    @classmethod
    def from_yaml(cls, path: str) -> Strategy:
        """Load configuration from YAML file.

        Args:
            path: Path to YAML config file.

        Returns:
            Strategy instance with loaded configuration.

        Note:
            Requires PyYAML to be installed.
        """
        import yaml  # type: ignore[import-untyped]

        with open(path) as f:
            config = yaml.safe_load(f)

        strategy_config = config.get(cls.Meta.name, {})
        return cls(**strategy_config)
