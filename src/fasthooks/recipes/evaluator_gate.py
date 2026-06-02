"""Evaluator-gate recipe: a fresh-context second opinion on Stop.

The builder shouldn't grade its own work. On Stop, run a separate evaluator
(e.g. ``claude --agent evaluator -p ...``) with no memory of the build, and
**block the stop on anything but PASS** — its findings become the next turn's
starting point. This closes the build → evaluate → rebuild loop from the hook
side; the loop itself is yours (``/loop``, ralph-loop, the SDK).

Engine for ``fasthooks add evaluator-gate``. Mirrors the cwc reference's
"custom Stop hook runs the evaluator as a fresh process and blocks on non-PASS."

Three guards make it safe to run an LLM from inside a hook:

- **recursion** — the evaluator subprocess inherits a sentinel env var; if it
  ever re-enters this gate (e.g. the evaluator is pointed at the same hooks),
  the gate sees the sentinel and skips, so an evaluation can't trigger another.
- **timeout** — the subprocess is bounded.
- **fail-open** — if the evaluator times out, is missing, or errors, the gate
  allows the stop. A broken evaluator must never wedge the session.
"""
from __future__ import annotations

import os
import shlex
import subprocess

from fasthooks.blueprint import Blueprint
from fasthooks.events.lifecycle import Stop
from fasthooks.responses import HookResponse, block

# Single-quote the inner prompt so the scaffolded `command="..."` stays valid.
DEFAULT_COMMAND = (
    "claude --agent evaluator -p "
    "'Review the most recent commit against its spec. "
    "Respond with PASS or NEEDS_WORK on the first line, then findings.'"
)
_GUARD_ENV = "FASTHOOKS_EVALUATOR_GATE_ACTIVE"


def evaluator_gate(
    command: str = DEFAULT_COMMAND,
    *,
    timeout: int = 120,
    pass_marker: str = "PASS",
) -> Blueprint:
    """Block Stop unless ``command``'s first output line is ``pass_marker``.

    ``command`` is the evaluator invocation (edit it to your agent/prompt); it
    runs in the session's cwd with the recursion sentinel set. The first line of
    stdout is the verdict; anything but ``pass_marker`` blocks the stop and
    surfaces the remaining lines as findings.
    """
    bp = Blueprint("evaluator_gate")

    @bp.on_stop()
    def evaluate(event: Stop) -> HookResponse | None:
        # Recursion guard: an evaluation must not trigger another evaluation.
        if os.environ.get(_GUARD_ENV):
            return None
        try:
            proc = subprocess.run(
                shlex.split(command),
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=event.cwd or None,
                env={**os.environ, _GUARD_ENV: "1"},
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # Fail open: a broken/slow/missing evaluator must not wedge the loop.
            return None

        lines = proc.stdout.strip().splitlines()
        verdict = lines[0].strip() if lines else ""
        if verdict == pass_marker:
            return None
        findings = "\n".join(lines[1:]).strip() or proc.stdout.strip()
        return block(f"Evaluator: {verdict or 'NEEDS_WORK'}\n{findings}".rstrip())

    return bp
