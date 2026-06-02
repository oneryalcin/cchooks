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

Engine for ``fasthooks add commit-on-stop``. Ported from Anthropic's
cwc-long-running-agents (Apache-2.0) ``commit-on-stop.sh``.
"""
from __future__ import annotations

import subprocess
import time

from fasthooks.blueprint import Blueprint
from fasthooks.events.lifecycle import Stop

DEFAULT_PREFIX = "session checkpoint"


def commit_on_stop(message_prefix: str = DEFAULT_PREFIX) -> Blueprint:
    """Commit tracked changes on Stop with ``"<message_prefix>: <timestamp>"``.

    Only commits when there are tracked (staged or unstaged) changes; untracked
    files are left alone. Always allows the stop.
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
