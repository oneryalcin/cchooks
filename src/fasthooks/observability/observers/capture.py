"""Event capture observer for unit testing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fasthooks.observability.base import BaseObserver

if TYPE_CHECKING:
    from fasthooks.observability.events import HookObservabilityEvent


class EventCapture(BaseObserver):
    """Capture events for test assertions.

    Named to avoid pytest collection warnings (TestObserver triggers pytest).

    Example:
        capture = EventCapture()
        app.add_observer(capture)

        client.send(MockEvent.bash("ls"))

        assert len(capture.events) == 4
        assert capture.events[0].event_type == "hook_start"
        assert capture.decisions() == ["allow"]
    """

    def __init__(self) -> None:
        self.events: list[HookObservabilityEvent] = []

    def _capture(self, event: HookObservabilityEvent) -> None:
        self.events.append(event)

    def on_hook_start(self, event: HookObservabilityEvent) -> None:
        self._capture(event)

    def on_hook_end(self, event: HookObservabilityEvent) -> None:
        self._capture(event)

    def on_hook_error(self, event: HookObservabilityEvent) -> None:
        self._capture(event)

    def on_handler_start(self, event: HookObservabilityEvent) -> None:
        self._capture(event)

    def on_handler_end(self, event: HookObservabilityEvent) -> None:
        self._capture(event)

    def on_handler_skip(self, event: HookObservabilityEvent) -> None:
        self._capture(event)

    def on_handler_error(self, event: HookObservabilityEvent) -> None:
        self._capture(event)

    # Convenience methods for assertions

    def clear(self) -> None:
        """Clear captured events."""
        self.events.clear()

    def events_of_type(self, event_type: str) -> list[HookObservabilityEvent]:
        """Filter events by type."""
        return [e for e in self.events if e.event_type == event_type]

    def handler_events(self, handler_name: str) -> list[HookObservabilityEvent]:
        """Filter events for specific handler."""
        return [e for e in self.events if e.handler_name == handler_name]

    def decisions(self) -> list[str]:
        """Get all decisions from handler_end events."""
        return [e.decision for e in self.events_of_type("handler_end") if e.decision]
