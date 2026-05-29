"""fasthooks - Delightful Claude Code hooks."""

__version__ = "0.1.4"

from fasthooks.app import HookApp
from fasthooks.blueprint import Blueprint
from fasthooks.events.base import GenericEvent, HookEventName
from fasthooks.events.tools import ToolEvent
from fasthooks.responses import (
    BaseHookResponse,
    ContextResponse,
    HookResponse,
    PermissionHookResponse,
    allow,
    approve_permission,
    ask,
    block,
    context,
    deny,
    deny_permission,
)

__all__ = [
    "__version__",
    "BaseHookResponse",
    "Blueprint",
    "ContextResponse",
    "GenericEvent",
    "HookApp",
    "HookEventName",
    "HookResponse",
    "PermissionHookResponse",
    "ToolEvent",
    "allow",
    "approve_permission",
    "ask",
    "block",
    "context",
    "deny",
    "deny_permission",
]
