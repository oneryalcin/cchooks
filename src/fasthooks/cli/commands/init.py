"""fasthooks init command - create hooks.py boilerplate."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

HOOKS_TEMPLATE = '''\
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Claude Code hooks for this project.

Usage:
    fasthooks install .claude/hooks.py

After installing, restart Claude Code for hooks to take effect.
"""

from fasthooks import HookApp, deny

app = HookApp()


@app.pre_tool("Bash")
def check_bash(event):
    """Example: block dangerous commands."""
    if "rm -rf /" in event.command:
        return deny("Blocked dangerous command")
    # Return None to allow (default)


# Add more handlers as needed:
# @app.pre_tool("Write")
# @app.post_tool("*")  # catch-all
# @app.on_stop()
# @app.on_session_start()


if __name__ == "__main__":
    app.run()
'''


def run_init(path: str, force: bool, console: Console) -> int:
    """
    Create hooks.py boilerplate file.

    Args:
        path: Output path for hooks.py
        force: Overwrite existing file if True
        console: Rich console for output

    Returns:
        Exit code (0=success, 1=error)
    """
    target = Path(path)

    # Check if file exists
    if target.exists() and not force:
        console.print(f"[red]✗[/red] File already exists: {path}")
        console.print("  Use [bold]--force[/bold] to overwrite")
        return 1

    # Create parent directories and write template
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(HOOKS_TEMPLATE)
    except PermissionError:
        console.print(f"[red]✗[/red] Permission denied: {path}")
        return 1
    except OSError as e:
        console.print(f"[red]✗[/red] Cannot write {path}: {e}")
        return 1

    console.print(f"[green]✓[/green] Created {path}")
    console.print()
    console.print("Next steps:")
    console.print(f"  1. Edit [bold]{path}[/bold] to add your hooks")
    console.print(f"  2. Run [bold]fasthooks install {path}[/bold]")

    return 0
