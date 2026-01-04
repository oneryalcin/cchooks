"""fasthooks status command implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from fasthooks.cli_utils import (
    find_project_root,
    get_lock_path,
    get_settings_path,
    read_lock,
    read_settings,
    validate_and_introspect,
)


@dataclass
class ScopeStatus:
    """Status information for a single scope."""

    scope: str
    installed: bool
    lock_data: dict[str, Any] | None = None
    hooks_path: Path | None = None
    current_handlers: list[str] | None = None
    validation_error: str | None = None
    handlers_match: bool = True
    added_handlers: set[str] | None = None
    removed_handlers: set[str] | None = None
    settings_in_sync: bool = True


def get_scope_display_path(scope: str) -> str:
    """Get human-readable display path for a scope."""
    if scope == "user":
        return "~/.claude/settings.json"
    elif scope == "local":
        return ".claude/settings.local.json"
    return ".claude/settings.json"


def check_settings_sync(
    lock_data: dict[str, Any], settings_path: Path, command: str
) -> tuple[bool, str | None]:
    """Check if settings.json contains expected hook entries.

    Returns:
        Tuple of (is_in_sync, error_message)
    """
    try:
        settings = read_settings(settings_path)
    except ValueError as e:
        return False, f"Invalid JSON in settings: {e}"

    hooks_section = settings.get("hooks", {})

    # Find events that should be in settings based on lock
    locked_events = set()
    for h in lock_data.get("hooks_registered", []):
        if ":" in h:
            locked_events.add(h.split(":")[0])
        else:
            locked_events.add(h)

    # Find events that have our command in settings
    found_events = set()
    for event_type, entries in hooks_section.items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                if hook.get("command") == command:
                    found_events.add(event_type)

    return locked_events == found_events, None


def get_scope_status(scope: str, project_root: Path) -> ScopeStatus:
    """Get status information for a single scope."""
    lock_path = get_lock_path(scope, project_root)
    lock_data = read_lock(lock_path)

    if lock_data is None:
        return ScopeStatus(scope=scope, installed=False)

    status = ScopeStatus(
        scope=scope,
        installed=True,
        lock_data=lock_data,
    )

    # Get hooks path
    hooks_rel_path = lock_data.get("hooks_path", "")
    if hooks_rel_path:
        status.hooks_path = project_root / hooks_rel_path

    # Validate hooks.py
    if status.hooks_path and status.hooks_path.exists():
        success, handlers, error = validate_and_introspect(status.hooks_path)
        if success:
            status.current_handlers = handlers
            # Compare handlers
            locked_handlers = set(lock_data.get("hooks_registered", []))
            current_set = set(handlers) if handlers else set()

            if locked_handlers != current_set:
                status.handlers_match = False
                status.added_handlers = current_set - locked_handlers
                status.removed_handlers = locked_handlers - current_set
        else:
            status.validation_error = error
    elif status.hooks_path:
        status.validation_error = f"File not found: {status.hooks_path}"

    # Check settings sync
    command = lock_data.get("command", "")
    if command:
        settings_path = get_settings_path(scope, project_root)
        in_sync, settings_error = check_settings_sync(
            lock_data, settings_path, command
        )
        status.settings_in_sync = in_sync
        if settings_error and not status.validation_error:
            status.validation_error = settings_error

    return status


def format_status_output(
    scopes: list[ScopeStatus], console: Console
) -> None:
    """Format and print status output using Rich."""
    lines: list[str] = []

    # Count installed scopes
    installed_count = sum(1 for s in scopes if s.installed)

    # Multi-scope warning
    if installed_count > 1:
        lines.append(
            "[yellow]⚠ Hooks active in MULTIPLE scopes (all will run)[/yellow]"
        )
        lines.append("")

    for status in scopes:
        display_path = get_scope_display_path(status.scope)
        lines.append(f"[bold]{status.scope.capitalize()} scope[/bold] ({display_path})")

        if status.installed:
            lock = status.lock_data or {}
            hooks_path = lock.get("hooks_path", "unknown")
            installed_at = lock.get("installed_at", "unknown")
            handlers = lock.get("hooks_registered", [])

            lines.append(f"  [green]✓[/green] Installed: {hooks_path}")
            lines.append(f"  [green]✓[/green] Installed at: {installed_at}")
            lines.append(f"  [green]✓[/green] Handlers: {', '.join(handlers)}")

            # Validation status
            if status.validation_error:
                lines.append(f"  [red]✗[/red] Validation error: {status.validation_error}")
            elif not status.handlers_match:
                lines.append("  [yellow]⚠[/yellow] Handlers changed since install:")
                if status.added_handlers:
                    lines.append(f"      Added: {', '.join(sorted(status.added_handlers))}")
                if status.removed_handlers:
                    lines.append(f"      Removed: {', '.join(sorted(status.removed_handlers))}")
                lines.append(
                    "      Run [cyan]fasthooks install <path> --force[/cyan] to resync"
                )
            else:
                lines.append("  [green]✓[/green] Hooks valid")

            # Settings sync status
            if status.settings_in_sync:
                lines.append("  [green]✓[/green] Settings in sync")
            else:
                lines.append("  [yellow]⚠[/yellow] Settings mismatch")
                lines.append(
                    "      Run [cyan]fasthooks install <path> --force[/cyan] to resync"
                )
        else:
            lines.append("  [dim]✗ Not installed[/dim]")

        lines.append("")

    # Multi-scope explanation
    if installed_count > 1:
        lines.append(
            "[dim]All installed scopes will execute for each event.[/dim]"
        )
        lines.append("[dim]Ensure they don't conflict.[/dim]")

    content = "\n".join(lines).rstrip()
    console.print(Panel(content, title="Hook Status", border_style="blue"))


def run_status(scope: str | None, console: Console) -> int:
    """
    Run the status command.

    Args:
        scope: Specific scope to check, or None for all scopes
        console: Rich console for output

    Returns:
        Exit code (0 for success)
    """
    project_root = find_project_root(Path.cwd())

    if scope:
        # Single scope
        if scope not in ("project", "user", "local"):
            console.print(f"[red]✗[/red] Invalid scope: {scope}")
            console.print("  Valid scopes: project, user, local")
            return 1
        scopes = [get_scope_status(scope, project_root)]
    else:
        # All scopes
        scopes = [
            get_scope_status(s, project_root)
            for s in ["project", "user", "local"]
        ]

    format_status_output(scopes, console)
    return 0
