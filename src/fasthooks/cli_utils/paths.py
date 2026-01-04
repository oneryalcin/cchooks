"""Path utilities for project root detection and path handling."""

from __future__ import annotations

from pathlib import Path


def find_project_root(start_path: Path) -> Path:
    """
    Find project root by looking for markers.

    Checks for (in order):
    1. .claude/ directory
    2. .git/ directory
    3. pyproject.toml
    4. package.json

    Falls back to start_path if no marker found.
    """
    current = start_path.resolve()

    while current != current.parent:
        if (current / ".claude").is_dir():
            return current
        if (current / ".git").is_dir():
            return current
        if (current / "pyproject.toml").is_file():
            return current
        if (current / "package.json").is_file():
            return current
        current = current.parent

    return start_path.resolve()


def make_relative_command(hooks_path: Path, project_root: Path) -> str:
    """
    Generate the hook command with $CLAUDE_PROJECT_DIR.

    Args:
        hooks_path: Absolute path to hooks.py
        project_root: Project root directory

    Returns:
        Command string like: uv run --with fasthooks "$CLAUDE_PROJECT_DIR/.claude/hooks.py"
    """
    relative = hooks_path.resolve().relative_to(project_root.resolve())
    return f'uv run --with fasthooks "$CLAUDE_PROJECT_DIR/{relative}"'


def get_settings_path(scope: str, project_root: Path) -> Path:
    """
    Get settings.json path for scope.

    Args:
        scope: 'project', 'user', or 'local'
        project_root: Project root directory

    Returns:
        Path to settings.json file
    """
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    elif scope == "local":
        return project_root / ".claude" / "settings.local.json"
    else:  # project
        return project_root / ".claude" / "settings.json"


def get_lock_path(scope: str, project_root: Path) -> Path:
    """
    Get lock file path for scope.

    Args:
        scope: 'project', 'user', or 'local'
        project_root: Project root directory

    Returns:
        Path to .fasthooks.lock file
    """
    if scope == "user":
        return Path.home() / ".claude" / ".fasthooks.lock"
    elif scope == "local":
        return project_root / ".claude" / ".fasthooks.local.lock"
    else:  # project
        return project_root / ".claude" / ".fasthooks.lock"
