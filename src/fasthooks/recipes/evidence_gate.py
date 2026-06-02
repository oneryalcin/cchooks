"""Evidence-gate recipe: the default-FAIL contract.

An agent can't mark a result "passing" until it has actually *looked* — opened a
screenshot or console log with the Read tool. A ``PreToolUse`` hook denies any
write to the results file unless evidence was read this session; reading
evidence "unlocks" the next write, and each gated write consumes it so the next
change needs fresh proof. This is the structural answer to "premature victory"
(one of the three long-running-agent failure modes).

State (the JSON-backed session dict) is the mechanism on purpose: each hook fires
as a separate process in Claude Code, so the read tracked in one invocation must
be visible to the write gate in another — in-memory wouldn't survive.

Engine for ``fasthooks add evidence-gate``. Ported from Anthropic's
cwc-long-running-agents (Apache-2.0) ``track-read.sh`` + ``verify-gate.sh``.
This is a teaching example, not a security boundary — see the known gaps below.
"""
from __future__ import annotations

from fasthooks.blueprint import Blueprint
from fasthooks.depends import State
from fasthooks.events.tools import ToolEvent
from fasthooks.responses import HookResponse, deny

DEFAULT_RESULTS_FILE = "test-results.json"

# What counts as "the agent actually looked" (cwc track-read.sh patterns).
_EVIDENCE_MARKERS = ("screenshots/", "-console.txt", "-result.txt", ".png")
_STATE_KEY = "evidence_gate.reads"


def _is_evidence(path: str) -> bool:
    return any(marker in path for marker in _EVIDENCE_MARKERS)


def _is_results(path: str, results_file: str) -> bool:
    # Anchor on a path separator so e.g. vitest-results.json doesn't match.
    return path == results_file or path.endswith("/" + results_file)


def evidence_gate(results_file: str = DEFAULT_RESULTS_FILE) -> Blueprint:
    """Deny writes to ``results_file`` unless evidence was Read this session.

    Point ``results_file`` at your project's results file (e.g.
    ``test-results.json``). The agent must open a screenshot / console log with
    the Read tool before it can mark anything passing there.

    Faithful to the cwc reference (a teaching example, not a security boundary).
    Shared known gaps: only Write/Edit are gated — a Bash ``sed``/``jq`` can
    rewrite the file unchecked; the evidence match is substring-based; and any
    evidence read unlocks any results write, not the corresponding row.
    """
    bp = Blueprint(f"evidence_gate[{results_file}]")

    @bp.pre_tool("Read")
    def track_read(event: ToolEvent, state: State) -> None:
        path = event.tool_input.get("file_path", "")
        if _is_evidence(path):
            state.setdefault(_STATE_KEY, []).append(path)
            state.save()

    @bp.pre_tool("Write", "Edit")
    def gate_results(event: ToolEvent, state: State) -> HookResponse | None:
        path = event.tool_input.get("file_path", "")
        if not _is_results(path, results_file):
            return None
        if not state.get(_STATE_KEY):
            return deny(
                f"Cannot modify {results_file}: no screenshot or console-log "
                "evidence has been Read this session. Open the evidence file "
                "with the Read tool first, then retry."
            )
        state[_STATE_KEY] = []  # consume — the next change needs fresh proof
        state.save()
        return None

    return bp
