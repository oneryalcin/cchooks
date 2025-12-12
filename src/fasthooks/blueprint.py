"""Blueprint for composing hook handlers."""
from __future__ import annotations

from fasthooks.registry import HandlerRegistry


class Blueprint(HandlerRegistry):
    """Composable collection of hook handlers.

    Use blueprints to organize handlers into logical groups
    that can be included in the main HookApp.

    Example:
        security = Blueprint("security")

        @security.pre_tool("Bash")
        def no_sudo(event):
            if "sudo" in event.command:
                return deny("sudo not allowed")

        app = HookApp()
        app.include(security)
    """

    def __init__(self, name: str):
        """Initialize Blueprint.

        Args:
            name: Name for this blueprint (for debugging)
        """
        super().__init__()
        self.name = name
