"""Long-running agent harness, assembled from fasthooks recipes.

The composable replacement for the deprecated ``LongRunningStrategy``: each
mechanism is a small, tested recipe you pipe together, plus your *own*
session-start context (the part that was opinionated prompt content baked into
the old strategy). This is the "primitives as a pipeline, not a god-class"
shape — keep, drop, or swap any line.

Smoke-test the hooks without Claude Code (see `fasthooks test`):

    # the session-routing context (initializer vs coding)
    fasthooks test examples/long_running_harness.py -e SessionStart

    # the evidence gate denies marking results passing with no evidence Read
    fasthooks test examples/long_running_harness.py -e PreToolUse:Write \\
        -i '{"file_path": "test-results.json"}'

(`-e Stop` runs the real `evaluator_gate` command — i.e. spawns `claude` — so it
only makes sense once you've wired up an evaluator agent.)
"""
from pathlib import Path

from fasthooks import HookApp, context
from fasthooks.recipes import (
    commit_on_stop,
    evaluator_gate,
    evidence_gate,
    heartbeat,
    kill_switch,
    steer,
)

# evidence_gate tracks Reads across separate hook processes, so it needs
# PERSISTENT state — construct the app with a state_dir (without it the gate
# fails open and warns rather than enforcing).
app = HookApp(state_dir=".claude/state")

# ── The harness pipeline ──────────────────────────────────────────────────────
# Operator controls + the passive signal first; then the blocking gates; the
# commit backstop LAST so a gate's block short-circuits before the checkpoint
# (commit only when the stop is actually allowed).
app.include(kill_switch())          # freeze the agent via an AGENT_STOP file
app.include(steer())                # redirect mid-run via STEER.md
app.include(heartbeat())            # stall-detection marker on every tool call
app.include(evidence_gate(results_file="test-results.json"))  # default-FAIL contract
app.include(
    evaluator_gate(                 # fresh-context second opinion on Stop
        command=(
            "claude --agent evaluator -p 'Review the latest commit against its "
            "spec. First line PASS or NEEDS_WORK, then findings.'"
        ),
    )
)
app.include(commit_on_stop())       # durability backstop (after the gate)

# ── Your own session context (replaces the strategy's opinionated prompts) ────
FEATURE_LIST = "feature_list.json"


@app.on_session_start()
def route(event):
    """Initializer vs coding context — the bit that was prompt content before.

    First run (no feature list) → set the project up. Later runs → make
    incremental, verified progress. Adapt the wording to your project.
    """
    if not (Path(event.cwd) / FEATURE_LIST).exists():
        return context(
            "INITIALIZER: create feature_list.json (each feature "
            '{"passes": false}), a claude-progress.txt handoff file, and '
            "`git init` with a first commit. Then stop."
        )
    return context(
        "CODING: read claude-progress.txt, pick the next failing feature, "
        "implement it, verify it with a screenshot or console log (open it with "
        "Read), then mark it passing in test-results.json and commit. Update "
        "claude-progress.txt before you stop."
    )


if __name__ == "__main__":
    app.run()
