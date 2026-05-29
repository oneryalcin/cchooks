"""fasthooks serve command - run hooks as a persistent HTTP server."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel

if TYPE_CHECKING:
    from fasthooks import HookApp

# Only genuine loopback addresses skip the auth requirement; an empty or
# wildcard host binds all interfaces and must not be treated as loopback.
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


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


def _reload_asgi_factory() -> Any:
    """ASGI factory uvicorn imports (by string) on each reload.

    Rebuilds the HookApp from the hooks file — re-running ``include_recipes`` —
    so handler/recipe edits are picked up without a manual restart. Config is
    read from the environment because the reloader runs in a fresh subprocess.
    """
    path = os.environ["FASTHOOKS_HOOKS_PATH"]
    app = _load_app(Path(path))
    if app is None:
        raise RuntimeError(f"No HookApp instance found in {path}")
    app._auth_token = os.environ.get("FASTHOOKS_TOKEN") or None
    return app._asgi_app


def run_serve(
    path: str,
    host: str,
    port: int,
    console: Console,
    *,
    token: str | None = None,
    allow_unauthenticated: bool = False,
    reload: bool = False,
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
    reload_note = "  [dim]auto-reload on (edit handlers/recipes freely)[/dim]\n" if reload else ""
    console.print(
        Panel(
            f"Serving [bold]{path}[/bold] at [bold]{url}[/bold]\n"
            f"{reload_note}\n"
            "Point a Claude Code [bold]http[/bold] hook at it:\n"
            f'  {{"type": "http", "url": "{url}"}}\n\n'
            "[dim]One endpoint handles every event. Ctrl+C to stop.[/dim]",
            border_style="blue",
        )
    )

    if reload:
        return _run_with_reload(
            hooks_path, host, port, console, token, allow_unauthenticated
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


def _run_with_reload(
    hooks_path: Path,
    host: str,
    port: int,
    console: Console,
    token: str | None,
    allow_unauthenticated: bool,
) -> int:
    """Serve with uvicorn auto-reload (rebuilds the app on file changes)."""
    import uvicorn

    resolved_token = token or os.environ.get("FASTHOOKS_TOKEN")
    if not resolved_token and host not in _LOOPBACK and not allow_unauthenticated:
        console.print(
            f"[red]✗[/red] Refusing to bind non-loopback host {host!r} without "
            "authentication. Set --token / $FASTHOOKS_TOKEN, or pass "
            "--allow-unauthenticated."
        )
        return 1

    # The reloader runs the factory in a fresh subprocess; pass config via env.
    os.environ["FASTHOOKS_HOOKS_PATH"] = str(hooks_path.resolve())
    if token:
        os.environ["FASTHOOKS_TOKEN"] = token

    reload_dirs = [str(hooks_path.resolve().parent)]
    recipes_dir = Path(".claude/hooks/recipes")
    if recipes_dir.is_dir():
        reload_dirs.append(str(recipes_dir.resolve()))

    try:
        uvicorn.run(
            "fasthooks.cli.commands.serve:_reload_asgi_factory",
            factory=True,
            host=host,
            port=port,
            reload=True,
            reload_dirs=reload_dirs,
            interface="asgi3",
            log_level="warning",
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
    return 0
