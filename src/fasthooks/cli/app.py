"""fasthooks CLI application."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(
    name="fasthooks",
    help="Manage Claude Code hooks with ease.",
    rich_markup_mode="rich",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

console = Console()


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        from fasthooks import __version__

        console.print(f"[green]fasthooks[/green] version: [bold]{__version__}[/bold]")
        raise typer.Exit()


@app.callback()
def callback(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """
    [bold]fasthooks[/bold] - Manage Claude Code hooks with ease.

    Build hooks for Claude Code with a FastAPI-like developer experience.

    Read more: [link=https://github.com/oneryalcin/fasthooks]https://github.com/oneryalcin/fasthooks[/link]
    """
    pass


@app.command()
def init(
    path: Annotated[
        str,
        typer.Option(
            "--path",
            "-p",
            help="Output path for hooks.py",
        ),
    ] = ".claude/hooks.py",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Overwrite existing file",
        ),
    ] = False,
) -> None:
    """Create a new hooks.py with boilerplate."""
    console.print("[yellow]Not implemented yet[/yellow]")
    raise typer.Exit(code=0)


@app.command()
def install(
    path: Annotated[
        str,
        typer.Argument(help="Path to hooks.py file"),
    ],
    scope: Annotated[
        str,
        typer.Option(
            "--scope",
            "-s",
            help="Installation scope: project, user, or local",
        ),
    ] = "project",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Reinstall even if already installed",
        ),
    ] = False,
) -> None:
    """Register hooks with Claude Code."""
    console.print("[yellow]Not implemented yet[/yellow]")
    raise typer.Exit(code=0)


@app.command()
def uninstall(
    scope: Annotated[
        str,
        typer.Option(
            "--scope",
            "-s",
            help="Scope to uninstall from: project, user, or local",
        ),
    ] = "project",
) -> None:
    """Remove hooks from Claude Code."""
    console.print("[yellow]Not implemented yet[/yellow]")
    raise typer.Exit(code=0)


@app.command()
def status(
    scope: Annotated[
        str | None,
        typer.Option(
            "--scope",
            "-s",
            help="Specific scope to check (default: all)",
        ),
    ] = None,
) -> None:
    """Show installation state and validate."""
    console.print("[yellow]Not implemented yet[/yellow]")
    raise typer.Exit(code=0)
