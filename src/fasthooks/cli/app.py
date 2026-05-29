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
    from fasthooks.cli.commands.init import run_init

    raise typer.Exit(code=run_init(path, force, console))


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
    http: Annotated[
        bool,
        typer.Option(
            "--http",
            help="Register an http hook (point at a running 'fasthooks serve')",
        ),
    ] = False,
    host: Annotated[
        str,
        typer.Option("--host", help="Server host for --http"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="Server port for --http"),
    ] = 8765,
    auth: Annotated[
        bool,
        typer.Option(
            "--auth",
            help="Generate a shared secret and require it (http mode only)",
        ),
    ] = False,
) -> None:
    """Register hooks with Claude Code."""
    from fasthooks.cli.commands.install import run_install

    raise typer.Exit(
        code=run_install(
            path, scope, force, console, http=http, host=host, port=port, auth=auth
        )
    )


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
    from fasthooks.cli.commands.uninstall import run_uninstall

    raise typer.Exit(code=run_uninstall(scope, console))


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
    from fasthooks.cli.commands.status import run_status

    raise typer.Exit(code=run_status(scope, console))


@app.command()
def add(
    recipe: Annotated[
        str,
        typer.Argument(help="Recipe name (e.g. kill-switch, steer)"),
    ],
    recipes_dir: Annotated[
        str,
        typer.Option("--dir", help="Directory to scaffold the recipe config into"),
    ] = ".claude/hooks/recipes",
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite an existing recipe config"),
    ] = False,
) -> None:
    """Scaffold a recipe (e.g. kill-switch) into your project."""
    from fasthooks.cli.commands.add import run_add

    raise typer.Exit(code=run_add(recipe, recipes_dir, force, console))


@app.command()
def serve(
    path: Annotated[
        str,
        typer.Argument(help="Path to hooks.py file"),
    ],
    host: Annotated[
        str,
        typer.Option("--host", help="Host to bind to"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="Port to bind to"),
    ] = 8765,
    token: Annotated[
        str | None,
        typer.Option(
            "--token",
            help="Require this shared secret (defaults to $FASTHOOKS_TOKEN)",
        ),
    ] = None,
    allow_unauthenticated: Annotated[
        bool,
        typer.Option(
            "--allow-unauthenticated",
            help="Permit a non-loopback bind with no token (unsafe)",
        ),
    ] = False,
    reload: Annotated[
        bool,
        typer.Option(
            "--reload",
            help="Auto-reload on handler/recipe changes (needs fasthooks[reload])",
        ),
    ] = False,
) -> None:
    """Run hooks as a persistent HTTP server (Claude Code http hook)."""
    from fasthooks.cli.commands.serve import run_serve

    raise typer.Exit(
        code=run_serve(
            path,
            host,
            port,
            console,
            token=token,
            allow_unauthenticated=allow_unauthenticated,
            reload=reload,
        )
    )


@app.command()
def studio(
    db: Annotated[
        str | None,
        typer.Option(
            "--db",
            help="Path to studio.db (default: ~/.fasthooks/studio.db)",
        ),
    ] = None,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help="Host to bind to",
        ),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option(
            "--port",
            help="Port to bind to",
        ),
    ] = 5555,
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open",
            help="Open browser automatically",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            help="Enable debug logging",
        ),
    ] = False,
) -> None:
    """Launch FastHooks Studio - visual debugger for hooks."""
    try:
        from fasthooks.studio.__main__ import main as studio_main
    except ImportError:
        console.print("[red]Studio requires extra dependencies.[/red]")
        console.print("Install with: [bold]pip install fasthooks[studio][/bold]")
        raise typer.Exit(1)

    import sys

    args = []
    if db:
        args.extend(["--db", db])
    args.extend(["--host", host])
    args.extend(["--port", str(port)])
    if open_browser:
        args.append("--open")
    if verbose:
        args.append("--verbose")

    sys.argv = ["fasthooks-studio", *args]
    studio_main()
