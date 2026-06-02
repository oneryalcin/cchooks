"""Commit-on-stop recipe: auto-commit tracked changes at session end.

A backstop so work is durable across restarts even when the agent forgets to
commit (the dashboard's "WORK SAVED · committed every few minutes"). Uses
``git commit -am`` (tracked files only) on purpose — ephemeral artifacts
(screenshots, logs, scratch) shouldn't land in history; the agent ``git add``s
new source files itself.

Passive by design: it never blocks the stop and never raises. If there's no git
repo, nothing to commit, or the commit fails (no ``user.name``, a rejecting
hook, ...), it silently does nothing — it's a backstop, not a gate. Check
``git log`` periodically when relying on it.

**It commits on every Stop**, including ones a *later* Stop gate then blocks —
that's intended (the dashboard's "committed every few minutes"): in an
autonomous loop the stop fires each turn, so WIP is saved continuously. The
commits are working checkpoints (hence the ``wip checkpoint`` message), not a
claim the session ended. fasthooks short-circuits on the first blocking
handler, so if you instead want to commit *only when the stop is actually
allowed*, include this recipe **after** your blocking gates (e.g.
``include_recipes(...)`` then ``app.include(commit_on_stop())``) — a gate's
block will short-circuit before it runs.

Engine for ``fasthooks add commit-on-stop``. Ported from Anthropic's
cwc-long-running-agents (Apache-2.0) ``commit-on-stop.sh``.
"""
from __future__ import annotations

import subprocess
import time

from fasthooks.blueprint import Blueprint
from fasthooks.events.lifecycle import Stop

DEFAULT_PREFIX = "wip checkpoint"


def commit_on_stop(message_prefix: str = DEFAULT_PREFIX) -> Blueprint:
    """Commit tracked changes on Stop with ``"<message_prefix>: <timestamp>"``.

    Only commits when there are tracked (staged or unstaged) changes; untracked
    files are left alone. Always allows the stop. Fires on *every* Stop (a
    frequent WIP backstop) — see the module docstring for the interaction with
    blocking Stop gates and how to commit-only-on-allowed-stop.
    """
    bp = Blueprint("commit_on_stop")

    @bp.on_stop()
    def commit(event: Stop) -> None:
        cwd = event.cwd or None

        def git(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["git", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )

        try:
            if git("rev-parse", "--git-dir").returncode != 0:
                return None  # not a git repo
            # Tracked changes only (unstaged or staged) — mirrors cwc's
            # `! git diff --quiet || ! git diff --cached --quiet`.
            unstaged = git("diff", "--quiet").returncode != 0
            staged = git("diff", "--cached", "--quiet").returncode != 0
            if not (unstaged or staged):
                return None  # nothing tracked to commit
            stamp = time.strftime("%Y-%m-%d %H:%M")
            git("commit", "-am", f"{message_prefix}: {stamp}")
        except (OSError, subprocess.SubprocessError):
            pass  # backstop: a failed commit must never wedge the stop
        return None  # passive: always allows the stop

    return bp
