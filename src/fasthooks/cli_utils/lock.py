"""Lock file management utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_lock(path: Path) -> dict[str, Any] | None:
    """
    Read lock file.

    Args:
        path: Path to .fasthooks.lock

    Returns:
        Lock data dict, or None if file doesn't exist or is invalid
    """
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        # Corrupt lock file - treat as not installed
        return None


def write_lock(path: Path, data: dict[str, Any]) -> None:
    """
    Write lock file.

    Args:
        path: Path to .fasthooks.lock
        data: Lock data dict to write
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def delete_lock(path: Path) -> bool:
    """
    Delete lock file.

    Args:
        path: Path to .fasthooks.lock

    Returns:
        True if file was deleted, False if it didn't exist
    """
    if not path.exists():
        return False

    path.unlink()
    return True
