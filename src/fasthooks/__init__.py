"""fasthooks - Delightful Claude Code hooks."""

__version__ = "0.1.4"

from fasthooks.app import HookApp
from fasthooks.blueprint import Blueprint
from fasthooks.responses import (
    BaseHookResponse,
    ContextResponse,
    HookResponse,
    PermissionHookResponse,
    allow,
    approve_permission,
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
    "HookApp",
    "HookResponse",
    "PermissionHookResponse",
    "allow",
    "approve_permission",
    "block",
    "context",
    "deny",
    "deny_permission",
]
