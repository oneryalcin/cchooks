"""cchooks - Delightful Claude Code hooks."""
from fasthooks.app import HookApp
from fasthooks.blueprint import Blueprint
from fasthooks.responses import (
    HookResponse,
    PermissionHookResponse,
    allow,
    approve_permission,
    block,
    deny,
    deny_permission,
)

__all__ = [
    "Blueprint",
    "HookApp",
    "HookResponse",
    "PermissionHookResponse",
    "allow",
    "approve_permission",
    "block",
    "deny",
    "deny_permission",
]
