"""CLI utilities for settings, locks, paths, and introspection."""

from __future__ import annotations

from fasthooks.cli_utils.introspect import generate_settings
from fasthooks.cli_utils.lock import delete_lock, read_lock, write_lock
from fasthooks.cli_utils.paths import (
    find_project_root,
    get_lock_path,
    get_settings_path,
    make_relative_command,
)
from fasthooks.cli_utils.settings import (
    backup_settings,
    merge_hooks_config,
    read_settings,
    remove_hooks_by_command,
    write_settings,
)
from fasthooks.cli_utils.validation import check_uv_installed, validate_and_introspect

__all__ = [
    "backup_settings",
    "check_uv_installed",
    "delete_lock",
    "find_project_root",
    "generate_settings",
    "get_lock_path",
    "get_settings_path",
    "make_relative_command",
    "merge_hooks_config",
    "read_lock",
    "read_settings",
    "remove_hooks_by_command",
    "validate_and_introspect",
    "write_lock",
    "write_settings",
]
