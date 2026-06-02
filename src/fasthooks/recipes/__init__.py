"""Recipes: battle-tested hook patterns as composable, tested Blueprints.

Each recipe is split in two (the "engine + config" model):

- the **engine** — the tested mechanism — is imported from here and owned by
  fasthooks (e.g. :func:`kill_switch`);
- the **config** — the project-specific knobs — is a small file you scaffold
  into your repo with ``fasthooks add <name>`` and own outright.

:func:`include_recipes` loads every scaffolded config from a directory, so
adding a recipe is "drop a file" — no edit to your hooks file, no settings
change.
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from fasthooks.recipes.evaluator_gate import evaluator_gate
from fasthooks.recipes.evidence_gate import evidence_gate
from fasthooks.recipes.heartbeat import heartbeat
from fasthooks.recipes.kill_switch import kill_switch
from fasthooks.recipes.steer import steer

if TYPE_CHECKING:
    from fasthooks.app import HookApp
    from fasthooks.blueprint import Blueprint

__all__ = [
    "kill_switch",
    "steer",
    "evidence_gate",
    "evaluator_gate",
    "heartbeat",
    "RECIPES",
    "scaffold_for",
    "include_recipes",
]


class RecipeSpec(NamedTuple):
    """A recipe available to ``fasthooks add``."""

    factory: Callable[..., Blueprint]
    summary: str
    doc: str  # guidance written into the scaffolded config's docstring


RECIPES: dict[str, RecipeSpec] = {
    "kill-switch": RecipeSpec(
        factory=kill_switch,
        summary="Halt all tool calls while a sentinel file (AGENT_STOP) exists.",
        doc=(
            "Drop an AGENT_STOP file in your working directory to freeze the "
            "agent mid-run; delete it to resume."
        ),
    ),
    "steer": RecipeSpec(
        factory=steer,
        summary="Inject STEER.md into the next prompt as context, then clear it.",
        doc=(
            "Write guidance into STEER.md to redirect the agent on its next "
            "prompt (delivered once, then the file is removed)."
        ),
    ),
    "evidence-gate": RecipeSpec(
        factory=evidence_gate,
        summary="Default-FAIL: deny marking a result passing without Reading evidence first.",
        doc=(
            "Point results_file at your project's results file (e.g. "
            "test-results.json). The agent must open a screenshot or console "
            "log with the Read tool before it can write that file.\n\n"
            "Requires persistent state: construct your app as "
            "HookApp(state_dir=...) so the evidence read survives to the "
            "separate hook process that handles the write. Without it the gate "
            "fails open (and warns) rather than deadlocking."
        ),
    ),
    "evaluator-gate": RecipeSpec(
        factory=evaluator_gate,
        summary="Block Stop unless a fresh-context evaluator returns PASS.",
        doc=(
            "Edit `command` to your evaluator invocation (e.g. `claude --agent "
            "evaluator -p '...'`). On Stop it runs the evaluator and blocks "
            "unless the first output line is PASS; findings become the next "
            "turn's prompt. Fail-open + recursion-guarded."
        ),
    ),
    "heartbeat": RecipeSpec(
        factory=heartbeat,
        summary="Write a 'still alive' marker on every tool call (stall detection).",
        doc=(
            "Overwrites path with {ts, tool, session_id} on each tool call so a "
            "watchdog/dashboard can detect stalls. Passive (never blocks). If "
            "you run the SQLiteObserver/studio you already have timestamps "
            "there; this is the no-DB, tail-from-a-terminal alternative."
        ),
    ),
}


def scaffold_for(name: str) -> str:
    """Build the editable config file contents for recipe ``name``.

    The knob (the engine's first parameter) and its default are read from the
    signature so the scaffold can't drift from the actual default — and so each
    recipe can name its own knob (``sentinel``, ``results_file``, ...).
    """
    spec = RECIPES[name]
    fn = spec.factory.__name__
    knob = next(iter(inspect.signature(spec.factory).parameters.values()))
    return (
        f'"""{name} recipe — scaffolded by `fasthooks add`. You own this; edit freely.\n'
        f"\n{spec.doc}\n"
        f'"""\n'
        f"from fasthooks.recipes import {fn}\n"
        f"\n"
        f'recipe = {fn}({knob.name}="{knob.default}")\n'
    )


def include_recipes(
    app: HookApp, recipes_dir: str = ".claude/hooks/recipes"
) -> list[str]:
    """Discover and include every scaffolded recipe under ``recipes_dir``.

    Each ``*.py`` exporting a module-level ``recipe`` (a Blueprint) is included.
    Importing arbitrary user files is the riskiest surface here, so it **fails
    open per file**: a broken or throwing recipe is skipped with a warning and
    never takes down the other recipes or the server.

    Returns the stems of the recipe files successfully included.
    """
    directory = Path(recipes_dir)
    if not directory.is_dir():
        return []

    included: list[str] = []
    for file in sorted(directory.glob("*.py")):
        if file.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"_fasthooks_recipe_{file.stem}", file
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            recipe: Any = getattr(module, "recipe", None)
            if recipe is None:
                print(
                    f"[fasthooks] recipe {file.name}: no `recipe` defined, skipping",
                    file=sys.stderr,
                )
                continue
            app.include(recipe)
            included.append(file.stem)
        except Exception as e:  # fail open — one bad recipe can't break the rest
            print(
                f"[fasthooks] recipe {file.name} failed to load: {e}",
                file=sys.stderr,
            )
            continue
    return included
