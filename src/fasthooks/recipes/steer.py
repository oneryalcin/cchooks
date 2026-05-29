"""Steer recipe: surface a note to the agent once, then clear it.

Engine for ``fasthooks add steer``. Ported from Anthropic's
cwc-long-running-agents (Apache-2.0) ``steer.sh`` primitive.
"""
from __future__ import annotations

from pathlib import Path

from fasthooks.blueprint import Blueprint
from fasthooks.events.lifecycle import UserPromptSubmit
from fasthooks.responses import ContextResponse, context

DEFAULT_SENTINEL = "STEER.md"


def steer(sentinel: str = DEFAULT_SENTINEL) -> Blueprint:
    """Inject ``sentinel``'s contents into the next prompt, then delete it.

    On each user prompt, if a file named ``sentinel`` exists in the event's
    cwd, its contents are injected as context for Claude and the file is
    removed — so a redirect you write mid-run is delivered exactly once.
    """
    bp = Blueprint(f"steer[{sentinel}]")

    @bp.on_prompt()
    def inject(event: UserPromptSubmit) -> ContextResponse | None:
        path = Path(event.cwd) / sentinel
        if not path.exists():
            return None
        text = path.read_text().strip()
        path.unlink()  # deliver once
        if not text:
            return None
        return context(
            text,
            hook_event="UserPromptSubmit",
            system_message=f"Steered via {sentinel}",
        )

    return bp
