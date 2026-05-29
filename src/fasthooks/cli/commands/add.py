"""fasthooks add command - scaffold a recipe's editable config into a project."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel


def run_add(recipe: str, recipes_dir: str, force: bool, console: Console) -> int:
    """Scaffold a recipe config file.

    Writes only the editable config (engine + knobs) the user owns. It does NOT
    touch settings.json — the http endpoint is configured once (see
    ``fasthooks serve``), so adding a recipe never changes your Claude Code
    settings or requires a restart of Claude Code itself.

    Args:
        recipe: Recipe name (e.g. "kill-switch").
        recipes_dir: Directory to scaffold into.
        force: Overwrite an existing config.
        console: Rich console for output.

    Returns:
        Exit code (0=success, 1=error).
    """
    from fasthooks.recipes import RECIPES, scaffold_for

    if recipe not in RECIPES:
        console.print(f"[red]✗[/red] Unknown recipe: [bold]{recipe}[/bold]")
        console.print("\nAvailable recipes:")
        for name, spec in sorted(RECIPES.items()):
            console.print(f"  [bold]{name}[/bold] — {spec.summary}")
        return 1

    directory = Path(recipes_dir)
    target = directory / f"{recipe.replace('-', '_')}.py"

    if target.exists() and not force:
        console.print(
            f"[yellow]Already added:[/yellow] {target}\n"
            "  Use [bold]--force[/bold] to overwrite."
        )
        return 0

    try:
        directory.mkdir(parents=True, exist_ok=True)
        target.write_text(scaffold_for(recipe))
    except OSError as e:
        console.print(f"[red]✗[/red] Cannot write {target}: {e}")
        return 1

    console.print(f"[green]✓[/green] Scaffolded [bold]{target}[/bold]")
    console.print()
    console.print(
        Panel(
            f"Edit [bold]{target}[/bold] to tune it — you own it.\n\n"
            "Make sure your hooks file loads recipes once:\n"
            "  [bold]from fasthooks.recipes import include_recipes[/bold]\n"
            "  [bold]include_recipes(app)[/bold]\n\n"
            "Then (re)start your server: [bold]fasthooks serve <hooks.py>[/bold].\n"
            "[dim]No settings.json change needed — adding recipes never touches it.[/dim]",
            border_style="blue",
        )
    )
    return 0
