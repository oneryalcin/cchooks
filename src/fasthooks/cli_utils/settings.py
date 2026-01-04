"""Settings.json read/write/merge utilities."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import json5


def read_settings(path: Path) -> dict[str, Any]:
    """
    Read settings.json, handling JSONC (comments).

    Args:
        path: Path to settings.json

    Returns:
        Parsed settings dict, or {} if file doesn't exist

    Raises:
        ValueError: If JSON is invalid
    """
    if not path.exists():
        return {}

    text = path.read_text()
    try:
        return json5.loads(text)  # type: ignore[no-any-return]
    except ValueError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}") from e


def write_settings(path: Path, data: dict[str, Any]) -> None:
    """
    Write settings.json (standard JSON, no comments).

    Note: Writing removes comments from the original file.
    The backup preserves the original with comments.

    Args:
        path: Path to settings.json
        data: Settings dict to write
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def backup_settings(path: Path) -> Path | None:
    """
    Create backup of settings file.

    Args:
        path: Path to settings.json

    Returns:
        Path to backup file, or None if original didn't exist
    """
    if not path.exists():
        return None

    backup_path = path.with_suffix(".json.bak")
    shutil.copy2(path, backup_path)
    return backup_path


def merge_hooks_config(
    existing: dict[str, Any], new: dict[str, Any], our_command: str
) -> dict[str, Any]:
    """
    Merge new hooks into existing settings.

    Strategy:
    1. First remove ALL entries with our_command from ALL event types
    2. Then add our new entries
    3. Preserve entries from other sources (different commands)

    Args:
        existing: Current settings.json content
        new: Generated hooks configuration
        our_command: The command we're installing (for identification)

    Returns:
        Merged settings dict
    """
    result = existing.copy()
    if "hooks" not in result:
        result["hooks"] = {}

    # Step 1: Remove ALL our old entries from ALL event types
    # This handles the case where we previously had handlers we no longer have
    for event_type in list(result["hooks"].keys()):
        result["hooks"][event_type] = [
            entry
            for entry in result["hooks"][event_type]
            if not any(hook.get("command") == our_command for hook in entry.get("hooks", []))
        ]
        # Clean up empty lists
        if not result["hooks"][event_type]:
            del result["hooks"][event_type]

    # Step 2: Add new entries
    for event_type, new_entries in new.get("hooks", {}).items():
        if event_type not in result["hooks"]:
            result["hooks"][event_type] = []
        result["hooks"][event_type].extend(new_entries)

    # Clean up empty hooks dict
    if not result.get("hooks"):
        result.pop("hooks", None)

    return result


def remove_hooks_by_command(
    settings: dict[str, Any], command: str
) -> tuple[dict[str, Any], int]:
    """
    Remove hook entries matching command.

    Args:
        settings: Current settings.json content
        command: Command to match and remove

    Returns:
        Tuple of (new settings dict, count of entries removed)
    """
    if "hooks" not in settings:
        return settings, 0

    result = settings.copy()
    result["hooks"] = {}
    removed = 0

    for event_type, entries in settings["hooks"].items():
        kept = []
        for entry in entries:
            hooks = entry.get("hooks", [])
            # Filter out hooks matching our command, keep the rest
            remaining = [h for h in hooks if h.get("command") != command]
            removed += len(hooks) - len(remaining)

            if remaining:
                # Keep entry with remaining hooks
                new_entry = entry.copy()
                new_entry["hooks"] = remaining
                kept.append(new_entry)
        if kept:
            result["hooks"][event_type] = kept

    if not result["hooks"]:
        del result["hooks"]

    return result, removed
