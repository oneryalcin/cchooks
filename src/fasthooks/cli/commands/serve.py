"""fasthooks serve command - run hooks as a persistent HTTP server."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from fasthooks import HookApp


def _load_app(path: Path) -> HookApp | None:
    """Import the hooks file and return its HookApp instance (or None).

    Mirrors the discovery order used by the install-time introspector: known
    variable names first, then any module-level HookApp.
    """
    from fasthooks import HookApp

    resolved = path.resolve()
    sys.path.insert(0, str(resolved.parent))
    spec = importlib.util.spec_from_file_location("_fasthooks_hooks", resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for name in ("app", "hooks", "hook_app", "application"):
        obj = getattr(module, name, None)
        if isinstance(obj, HookApp):
            return obj
    for name in dir(module):
        if not name.startswith("_"):
            obj = getattr(module, name)
            if isinstance(obj, HookApp):
                return obj
    return None


def run_serve(
    path: str,
    host: str,
    port: int,
    console: Console,
    *,
    token: str | None = None,
    allow_unauthenticated: bool = False,
) -> int:
    """Run a hooks file as a persistent HTTP server.

    Args:
        path: Path to hooks.py file.
        host: Interface to bind.
        port: Port to bind.
        console: Rich console for output.

    Returns:
        Exit code (0=success/clean shutdown, 1=error).
    """
    hooks_path = Path(path)
    if not hooks_path.exists():
        console.print(f"[red]✗[/red] File not found: {path}")
        return 1

    try:
        import uvicorn  # noqa: F401
    except ImportError:
        console.print("[red]✗[/red] serve requires the 'server' extra.")
        console.print("  Install with: [bold]pip install 'fasthooks[server]'[/bold]")
        return 1

    try:
        hook_app = _load_app(hooks_path)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load {path}: {e}")
        return 1

    if hook_app is None:
        console.print(f"[red]✗[/red] No HookApp instance found in {path}")
        return 1

    url = f"http://{host}:{port}/"
    console.print(
        Panel(
            f"Serving [bold]{path}[/bold] at [bold]{url}[/bold]\n\n"
            "Point a Claude Code [bold]http[/bold] hook at it:\n"
            f'  {{"type": "http", "url": "{url}"}}\n\n'
            "[dim]One endpoint handles every event. Ctrl+C to stop.[/dim]",
            border_style="blue",
        )
    )

    try:
        hook_app.serve(
            host=host,
            port=port,
            token=token,
            allow_unauthenticated=allow_unauthenticated,
        )
    except RuntimeError as e:
        console.print(f"[red]✗[/red] {e}")
        return 1
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
    return 0
