"""Test client for integration testing hooks."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anyio

from fasthooks.events.base import BaseEvent
from fasthooks.responses import HookResponse

if TYPE_CHECKING:
    from fasthooks.app import HookApp


class TestClient:
    """Test client for invoking hook handlers.

    Allows testing hooks without stdin/stdout plumbing.

    Example:
        app = HookApp()

        @app.pre_tool("Bash")
        def handler(event):
            return allow()

        client = TestClient(app)
        response = client.send(MockEvent.bash(command="ls"))
        assert response is None  # allowed
    """

    def __init__(self, app: HookApp):
        """Initialize TestClient.

        Args:
            app: HookApp to test
        """
        self.app = app

    def send(self, event: BaseEvent) -> HookResponse | None:
        """Send an event to the app and return the response.

        Args:
            event: Typed event (from MockEvent or manual)

        Returns:
            HookResponse if deny/block, None if allowed
        """
        # Convert event to dict for dispatch
        data = event.model_dump()
        return anyio.run(self.app._dispatch, data)

    def send_raw(self, data: dict[str, Any]) -> HookResponse | None:
        """Send raw event data to the app.

        Args:
            data: Raw event dict (as Claude Code would send)

        Returns:
            HookResponse if deny/block, None if allowed
        """
        return anyio.run(self.app._dispatch, data)
