"""Kill-switch recipe: halt all tool calls while a sentinel file exists.

Engine for ``fasthooks add kill-switch``. Ported from Anthropic's
cwc-long-running-agents (Apache-2.0) ``kill-switch.sh`` primitive.
"""
from __future__ import annotations

from pathlib import Path

from fasthooks.blueprint import Blueprint
from fasthooks.events.tools import ToolEvent
from fasthooks.responses import HookResponse, deny

DEFAULT_SENTINEL = "AGENT_STOP"


def kill_switch(sentinel: str = DEFAULT_SENTINEL) -> Blueprint:
    """Deny every tool call while ``sentinel`` exists in the event's cwd.

    Drop a file named ``sentinel`` in the working directory to freeze the agent
    mid-run; delete it to resume.

    Note: the sentinel is checked relative to ``event.cwd``, which can change
    during a session (e.g. after the agent ``cd``s — see ``CwdChanged``). Keep
    the file at the directory Claude Code is launched from.
    """
    bp = Blueprint(f"kill_switch[{sentinel}]")

    @bp.pre_tool()  # catch-all: every tool
    def halt(event: ToolEvent) -> HookResponse | None:
        if (Path(event.cwd) / sentinel).exists():
            return deny(f"Halted: {sentinel} is present. Delete it to resume.")
        return None

    return bp
