"""CLI utilities for settings, locks, and paths."""

from __future__ import annotations

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

__all__ = [
    "backup_settings",
    "delete_lock",
    "find_project_root",
    "get_lock_path",
    "get_settings_path",
    "make_relative_command",
    "merge_hooks_config",
    "read_lock",
    "read_settings",
    "remove_hooks_by_command",
    "write_lock",
    "write_settings",
]
