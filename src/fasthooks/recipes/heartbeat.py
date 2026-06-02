"""Heartbeat recipe: write a "still alive" marker on every tool call.

A watchdog (or the dashboard's LAST CHECK-IN panel) reads the marker to detect
stalls: if ``now - ts`` exceeds your threshold, the agent has gone quiet. The
*timeout → move to the next feature* decision is the loop's, not the hook's —
this primitive only emits the signal.

Passive by design: it never affects the tool decision and never raises (a
heartbeat that could block or crash a hook would be worse than no heartbeat).

Note: if you run the SQLiteObserver / studio, every hook event is already
timestamped there — this file is the no-DB, ``watch``/tail-from-a-terminal
alternative (``watch -n 2 cat .claude/heartbeat.json``).

Engine for ``fasthooks add heartbeat``.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fasthooks.blueprint import Blueprint
from fasthooks.events.tools import ToolEvent

DEFAULT_PATH = ".claude/heartbeat.json"


def heartbeat(path: str = DEFAULT_PATH) -> Blueprint:
    """Overwrite ``path`` (relative to the event cwd) with the latest activity.

    The marker is ``{ts, tool, session_id}`` rewritten on every tool call, so a
    watchdog can read the freshest ``ts`` to tell whether the agent is still
    making progress.
    """
    bp = Blueprint(f"heartbeat[{path}]")

    @bp.pre_tool()  # catch-all: every tool is a beat
    def beat(event: ToolEvent) -> None:
        marker = Path(event.cwd) / path
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(
                json.dumps(
                    {
                        "ts": time.time(),
                        "tool": event.tool_name,
                        "session_id": event.session_id,
                    }
                )
            )
        except OSError:
            pass  # a heartbeat must never break the hook it rides on
        return None  # passive: never affects the decision

    return bp
