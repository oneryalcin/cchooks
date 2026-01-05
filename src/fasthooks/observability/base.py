"""Base observer class for HookApp observability."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fasthooks.observability.events import HookObservabilityEvent


class BaseObserver:
    """Base class for HookApp observers.

    Override only the methods you care about. All methods have no-op defaults.

    Example:
        class MyObserver(BaseObserver):
            def on_handler_end(self, event):
                print(f"{event.handler_name}: {event.duration_ms}ms")

        app.add_observer(MyObserver())
    """

    def on_hook_start(self, event: HookObservabilityEvent) -> None:
        """Called when hook invocation begins."""
        pass

    def on_hook_end(self, event: HookObservabilityEvent) -> None:
        """Called when hook invocation completes."""
        pass

    def on_hook_error(self, event: HookObservabilityEvent) -> None:
        """Called when hook-level error occurs."""
        pass

    def on_handler_start(self, event: HookObservabilityEvent) -> None:
        """Called when handler execution begins."""
        pass

    def on_handler_end(self, event: HookObservabilityEvent) -> None:
        """Called when handler execution completes."""
        pass

    def on_handler_skip(self, event: HookObservabilityEvent) -> None:
        """Called when handler is skipped due to early deny."""
        pass

    def on_handler_error(self, event: HookObservabilityEvent) -> None:
        """Called when handler raises exception."""
        pass
