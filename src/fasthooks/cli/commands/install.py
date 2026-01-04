"""Install command implementation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from fasthooks.cli_utils import (
    backup_settings,
    check_uv_installed,
    find_project_root,
    generate_settings,
    get_lock_path,
    get_settings_path,
    make_relative_command,
    merge_hooks_config,
    read_lock,
    read_settings,
    validate_and_introspect,
    write_lock,
    write_settings,
)


def run_install(path: str, scope: str, force: bool, console: Console) -> int:
    """
    Install hooks to Claude Code settings.

    Args:
        path: Path to hooks.py file
        scope: Installation scope (project, user, local)
        force: Reinstall even if already installed
        console: Rich console for output

    Returns:
        Exit code (0=success, 1=error, 2=validation error)
    """
    hooks_path = Path(path)

    # Step 1: Validate path exists (handled by validate_and_introspect)
    # Step 2: Check uv installed
    if not check_uv_installed():
        console.print(
            "[yellow]⚠[/yellow] uv not found in PATH. Hooks may fail at runtime.\n"
            "  Install: https://docs.astral.sh/uv/getting-started/installation/"
        )

    # Steps 3-4: Validate and introspect
    success, hooks, error = validate_and_introspect(hooks_path)
    if not success:
        # Determine exit code based on error type
        if error and "No handlers registered" in error:
            console.print(f"[red]✗[/red] {error}")
            console.print(
                "  Add handlers with @app.pre_tool(), @app.on_stop(), etc."
            )
            return 2
        console.print(f"[red]✗[/red] {error}")
        return 1

    # Type guard: success implies hooks is set
    assert hooks is not None

    console.print(f"[green]✓[/green] Validated {path}")
    console.print(f"[green]✓[/green] Found {len(hooks)} handlers:")
    for hook in hooks:
        console.print(f"    {hook}")

    # Resolve path for project root detection
    hooks_resolved = hooks_path.resolve()

    # Step 6: Find project root
    project_root = find_project_root(hooks_resolved)

    # Step 5: Check lock file (after project root, we need it for lock path)
    lock_path = get_lock_path(scope, project_root)
    existing_lock = read_lock(lock_path)
    if existing_lock and not force:
        console.print()
        console.print(
            "[yellow]Already installed.[/yellow] Use --force to reinstall."
        )
        return 0

    # Step 7: Generate command
    command = make_relative_command(hooks_resolved, project_root)

    # Step 8: Generate settings
    new_config = generate_settings(hooks, command)

    # Step 9: Backup existing settings
    settings_path = get_settings_path(scope, project_root)
    backup_path = backup_settings(settings_path)
    if backup_path:
        # Show relative path for cleaner output
        try:
            backup_rel = backup_path.relative_to(project_root)
            settings_rel = settings_path.relative_to(project_root)
            console.print(
                f"[green]✓[/green] Backed up {settings_rel} → {backup_rel}"
            )
        except ValueError:
            # User scope - paths not relative to project
            console.print(f"[green]✓[/green] Backed up {backup_path}")

    # Step 10: Merge and write settings
    existing = read_settings(settings_path)
    merged = merge_hooks_config(existing, new_config, command)
    try:
        write_settings(settings_path, merged)
    except PermissionError:
        console.print(f"[red]✗[/red] Permission denied: {settings_path}")
        return 1
    except OSError as e:
        console.print(f"[red]✗[/red] Cannot write {settings_path}: {e}")
        return 1

    try:
        settings_rel = settings_path.relative_to(project_root)
        console.print(f"[green]✓[/green] Updated {settings_rel}")
    except ValueError:
        console.print(f"[green]✓[/green] Updated {settings_path}")

    # Step 11: Write lock file
    # Calculate relative hooks path for lock
    try:
        hooks_rel = hooks_resolved.relative_to(project_root)
    except ValueError:
        hooks_rel = hooks_resolved

    lock_data = {
        "version": 1,
        "installed_at": datetime.now(UTC).isoformat(),
        "hooks_path": str(hooks_rel),
        "hooks_registered": hooks,
        "settings_file": str(settings_path.relative_to(project_root))
        if settings_path.is_relative_to(project_root)
        else str(settings_path),
        "command": command,
    }
    try:
        write_lock(lock_path, lock_data)
    except PermissionError:
        console.print(f"[red]✗[/red] Permission denied: {lock_path}")
        return 1
    except OSError as e:
        console.print(f"[red]✗[/red] Cannot write {lock_path}: {e}")
        return 1

    try:
        lock_rel = lock_path.relative_to(project_root)
        console.print(f"[green]✓[/green] Created {lock_rel}")
    except ValueError:
        console.print(f"[green]✓[/green] Created {lock_path}")

    # Step 12: Print restart reminder
    console.print()
    console.print(
        Panel(
            "Restart Claude Code to activate hooks.",
            border_style="blue",
        )
    )

    return 0
