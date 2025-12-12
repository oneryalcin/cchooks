"""cchooks - Delightful Claude Code hooks."""
from fasthooks.app import HookApp
from fasthooks.blueprint import Blueprint
from fasthooks.responses import (
    BaseHookResponse,
    HookResponse,
    PermissionHookResponse,
    allow,
    approve_permission,
    block,
    deny,
    deny_permission,
)

__all__ = [
    "BaseHookResponse",
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
