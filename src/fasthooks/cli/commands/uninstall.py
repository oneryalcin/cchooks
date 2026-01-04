"""Uninstall command implementation."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from fasthooks.cli_utils import (
    backup_settings,
    delete_lock,
    find_project_root,
    get_lock_path,
    get_settings_path,
    read_lock,
    read_settings,
    remove_hooks_by_command,
    write_settings,
)


def run_uninstall(scope: str, console: Console) -> int:
    """
    Uninstall hooks from Claude Code settings.

    Args:
        scope: Installation scope (project, user, local)
        console: Rich console for output

    Returns:
        Exit code (0=success, 1=error)
    """
    # Step 1: Find project root and lock path
    project_root = find_project_root(Path.cwd())
    lock_path = get_lock_path(scope, project_root)

    # Step 2: Read lock file - error if not found
    lock_data = read_lock(lock_path)
    if lock_data is None:
        console.print(f"[red]✗[/red] No hooks installed in {scope} scope.")
        console.print("  Nothing to uninstall.")
        return 1

    # Show relative path if possible
    try:
        lock_rel = lock_path.relative_to(project_root)
        console.print(f"[green]✓[/green] Found installation in {lock_rel}")
    except ValueError:
        console.print(f"[green]✓[/green] Found installation in {lock_path}")

    # Step 3: Get command from lock
    command = lock_data.get("command", "")
    if not command:
        console.print("[red]✗[/red] Lock file is corrupted (no command).")
        return 1

    # Step 4: Backup settings
    settings_path = get_settings_path(scope, project_root)
    if settings_path.exists():
        backup_path = backup_settings(settings_path)
        if backup_path:
            try:
                backup_rel = backup_path.relative_to(project_root)
                settings_rel = settings_path.relative_to(project_root)
                console.print(
                    f"[green]✓[/green] Backed up {settings_rel} → {backup_rel}"
                )
            except ValueError:
                console.print(f"[green]✓[/green] Backed up {backup_path}")

    # Step 5: Remove entries matching command
    current_settings = read_settings(settings_path)
    new_settings, removed_count = remove_hooks_by_command(current_settings, command)

    # Step 6: Write settings
    try:
        write_settings(settings_path, new_settings)
    except PermissionError:
        console.print(f"[red]✗[/red] Permission denied: {settings_path}")
        return 1
    except OSError as e:
        console.print(f"[red]✗[/red] Cannot write {settings_path}: {e}")
        return 1

    console.print(f"[green]✓[/green] Removed {removed_count} hook entries")

    # Step 7: Delete lock file
    try:
        deleted = delete_lock(lock_path)
        if deleted:
            try:
                lock_rel = lock_path.relative_to(project_root)
                console.print(f"[green]✓[/green] Deleted {lock_rel}")
            except ValueError:
                console.print(f"[green]✓[/green] Deleted {lock_path}")
    except PermissionError:
        console.print(f"[red]✗[/red] Permission denied: {lock_path}")
        return 1
    except OSError as e:
        console.print(f"[red]✗[/red] Cannot delete {lock_path}: {e}")
        return 1

    # Step 8: Print restart reminder
    console.print()
    console.print(
        Panel(
            "Restart Claude Code to deactivate hooks.",
            border_style="blue",
        )
    )

    return 0
