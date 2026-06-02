# Long-Running Agent Harness — Plan & Scratchpad

> **Living doc.** Captures our learnings + references for turning fasthooks into a
> clean substrate for long-running-agent harnesses. Update as we spike/ship.
> Tracks issue [#15](https://github.com/oneryalcin/fasthooks/issues/15).
> Last updated: 2026-06-02.

---

## TL;DR / the thesis

Express the harness as **composable recipes piped together**, not as a monolithic
`LongRunningStrategy` god-class. fasthooks owns the **hook-shaped primitives**
(gates, evaluator, heartbeat, operator controls) + the **observability stream**;
the **loop** and the **dashboard** live *outside* fasthooks. This matches
Anthropic's official reference design and fasthooks' own Blueprint/recipe model.

---

## References

| What | Where | Notes |
|---|---|---|
| Issue #15 | `gh issue view 15` | Original "harness via hooks" proposal (Dec 2025). Its 5 proposals are already implemented (see inventory). |
| **cwc-long-running-agents** (official Anthropic reference) | `github.com/anthropics/cwc-long-running-agents` (cloned to `/tmp`, last commit `ad107a9` 2026-05-12) | "Example ingredients, not a turnkey harness; not maintained." 5 shell hooks + evaluator subagent + handoff CLAUDE.md. |
| Blog: Effective Harnesses for Long-Running Agents | anthropic.com/engineering/effective-harnesses-for-long-running-agents (Nov 2025) | The 3 failure modes: one-shotting, premature victory, dirty state. |
| Blog: Harness Design for Long-Running Application Development | anthropic.com/engineering/harness-design-long-running-apps (Mar 2026) | Unattended loop, planner, sprint contracts, rubrics, browser-verified evaluator, re-simplify on model upgrades. |
| Booth dashboard demo ("THE AGENT" / Canopy) | `jschwar2552/cwc-2026-boot`, `localhost:6174/presenter` | Live visualization of every primitive — our showcase reference (photos in chat 2026-06-02). |
| Claude Code built-ins | `/goal`, `/loop`, `ralph-loop` plugin, Agent SDK | The loop layer — **out of fasthooks scope**. |

---

## Primitive inventory: cwc reference ↔ fasthooks

| Primitive (cwc) | Dashboard panel | fasthooks today | Action |
|---|---|---|---|
| `kill-switch.sh` (halt on `AGENT_STOP`) | operator control | ✅ `add kill-switch` recipe | keep |
| `steer.sh` (surface `STEER.md` once) | operator control | ✅ `add steer` recipe | keep |
| `commit-on-stop.sh` | WORK SAVED / git commits | ✅ `LongRunningStrategy.enforce_commits` | extract to recipe |
| Agent-maintained handoff (PROGRESS) | ITS OWN NOTES | ✅ `LongRunningStrategy` (richer: dynamic context inject, initializer/coding routing, pre-compact) | extract to recipe(s) |
| Default-FAIL contract — feature list | — | ✅ `feature_list.json` tracking | keep |
| **Default-FAIL contract — evidence gate** (`track-read`+`verify-gate`: can't mark pass without Reading evidence) | **PROOF IT LOOKED · HARD GATE** | ✅ **shipped** — `evidence_gate` recipe (P1) | done |
| **Fresh-context evaluator** (subagent PASS/NEEDS_WORK) | **SECOND OPINION · EVALUATOR** | ✅ **shipped** — `evaluator_gate` recipe (P2), 3 guards | done |
| **Stall / heartbeat** ("goes quiet → loop moves on") | **LAST CHECK-IN · WATCHDOG** | ✅ **shipped** — `heartbeat` recipe (P3) emits the signal; loop owns timeout | done |
| Token-budget warnings | — | ✅ `TokenBudgetStrategy` (100k/150k/180k) | keep |

---

## Spikes / proven

- **Evaluator-in-a-Stop-hook (2026-06-02): PROVEN.** A fasthooks `@app.on_stop()`
  handler shells out to an evaluator command, parses the first line as the
  verdict, and `block()`s on anything but `PASS` (surfacing findings); allows
  stop on `PASS`. Driven via `fasthooks test hooks.py -e Stop`. The stub script
  is a drop-in for `claude --agent evaluator -p "<review prompt>"`.
  - **Open / "is it polluting?":** the real `claude --agent` call risks
    **recursion** (nested claude re-firing the Stop hook → infinite eval loop),
    **cost**, and **latency**. Mitigations to verify: run the evaluator with a
    **no-loop-hooks config** (its own `--settings`/agent dir), a **sentinel
    env/file guard** so an evaluation can't trigger another, a **timeout**, and
    fail-open if the evaluator errors (never wedge the session).

---

## Plan (phased — pull one thread at a time)

- [x] **P1 · `evidence-gate` recipe** — ✅ shipped (2026-06-02). `PreToolUse`
      Read tracks evidence (screenshots/console-logs) into State; Write/Edit to
      the results file is denied unless evidence was read this session, and each
      gated write consumes it. State (JSON-backed) is the mechanism so it works
      across separate hook processes. Faithful to cwc (simple/teaching version,
      same documented gaps). `fasthooks add evidence-gate`. Also generalized
      `scaffold_for` to read each recipe's first knob (was hardcoded `sentinel`).
- [x] **P2 · `evaluator-gate` recipe** — ✅ shipped (2026-06-02). `on_stop`
      runs a configurable evaluator command, blocks the stop unless the first
      output line is `PASS` (findings → next turn). Three guards: recursion
      sentinel env (`FASTHOOKS_EVALUATOR_GATE_ACTIVE`), subprocess timeout,
      fail-open (missing/slow/erroring evaluator never wedges the session).
      `fasthooks add evaluator-gate`. All guards verified with a stub; a real
      `claude --agent` live test is still worth doing but the recipe is safe by
      design.
- [x] **P3 · `heartbeat` primitive** — ✅ shipped (2026-06-02). Catch-all
      `pre_tool` overwrites a marker file (`{ts, tool, session_id}`) on every
      tool call; passive (never blocks/raises). A watchdog/dashboard reads the
      freshest `ts` to detect stalls; the *timeout→next-feature* decision stays
      in the loop. Overlaps with the observer stream (which already timestamps
      every event) — the file is the no-DB, tail-from-a-terminal alternative.
      `fasthooks add heartbeat`.
- [x] **P4 · composable harness > `LongRunningStrategy`** — ✅ done (2026-06-02).
      Extracted the missing reusable mechanism (`commit_on_stop`, cwc-style
      auto-commit backstop) as the 6th recipe, and added
      `examples/long_running_harness.py` showing the recipe-composed harness.
      `LongRunningStrategy` stays as-is with a plain doc/docstring note pointing
      at the recipe approach. **No deprecation ceremony** — no users, greenfield;
      just state the current preferred shape. `fasthooks add commit-on-stop`.
- [ ] **P5 · dashboard showcase (separate repo)** — consumes fasthooks'
      `SQLiteObserver`/studio event stream + on-disk artifacts (PROGRESS, git
      log, tests.json, screenshots). fasthooks = substrate; dashboard = app.

---

## Boundaries / non-goals (keep fasthooks a library)

- **The loop is out.** build→evaluate→rebuild orchestration and "move to next
  feature on stall" = `/loop`, `ralph-loop`, or the Agent SDK. fasthooks ships
  the hook primitives the loop calls, not the loop.
- **The dashboard is a separate repo**, not in fasthooks. fasthooks only
  guarantees the observer event contract it reads.
- **The evaluator's agent config + prompt** are the user's; fasthooks ships the
  gate that runs it and acts on the verdict.

---

## DX principles (carried from this session)

- Composable recipes > god-class strategies. `app.include(recipe)` is the pipe.
- Don't reimplement what stdlib/Claude Code already do well (no loop, no pytest
  wrapper, no query DSL — see #24's removal for the precedent).
- Every primitive: typed, testable in isolation, faithful (no default-field
  pollution), and verified end-to-end (`fasthooks test` is the smoke loop).

---

## Existing assets to reuse (don't rebuild)

- Recipes: `src/fasthooks/recipes/` (`kill_switch`, `steer`, `include_recipes`).
- Strategies: `long_running`, `token_budget`, `clean_state` (+ `docs/strategies/`).
- Observability: `SQLiteObserver`, `studio` (the dashboard's data feed).
- `fasthooks test` (smoke-test command, #3) — drives any hook against a synthetic event.

---

## Decisions log

- 2026-06-02 — Reframe harness as composable recipes, not monolithic strategy.
- 2026-06-02 — Evaluator CAN run in a Stop hook (plumbing proven); pollution
  guards TBD before the real `claude --agent` call.
- 2026-06-02 — Loop + dashboard stay outside fasthooks.
- 2026-06-02 — P1 `evidence-gate`: ship the simple/faithful version (documented
  cwc gaps), not the tightened one. Generalized `scaffold_for` for non-`sentinel`
  knobs along the way.
- 2026-06-02 — P2 `evaluator-gate`: ship with 3 guards (recursion sentinel,
  timeout, fail-open). Plumbing + guards verified with a stub evaluator.
- 2026-06-02 — P4: extract `commit_on_stop` (cwc auto-commit backstop) as a
  recipe + add `examples/long_running_harness.py` (recipe-composed harness).
  **Decided NOT to deprecate** `LongRunningStrategy` — no users, greenfield, so a
  DeprecationWarning + migration ceremony is fluff. Just state the current
  preferred shape (recipes) with a plain doc note; leave the strategy as-is.
- 2026-06-02 — Deprecation needs a *replacement*, not just a warning: added
  `examples/long_running_harness.py` — the full harness composed from the 6
  recipes (with `state_dir`, gate-then-commit ordering, and the session-routing
  context as a plain `on_session_start` handler). Deprecation message + docs now
  point at it. Building it surfaced a real `fasthooks test` gap (SessionStart/
  SessionEnd/PreCompact/Notification envelopes missed their required fields) —
  fixed + tested.
- 2026-06-02 — P4 Codex review: standard pass flagged `commit_on_stop` +
  `evaluator_gate` ordering (commit fires before a later gate blocks). Resolved:
  this is the cwc primitive's intended *commit-on-every-stop* behavior (frequent
  WIP backstop), so kept it — but renamed the message `session checkpoint` ->
  `wip checkpoint` (was misleading), documented the interaction, and pinned both
  orders in a test (include AFTER gates to commit-only-on-allowed-stop, since
  dispatch short-circuits on first block). Adversarial pass: approve.
- 2026-06-02 — Codex review (2 passes) caught two real failure modes, both fixed:
  (a) evidence-gate would *deadlock* under the default `HookApp()` (NullState,
  no persistence) — now detects NullState and **fails open + warns** (and the
  scaffold doc requires `state_dir`); (b) evaluator-gate's fail-open missed
  non-zero subprocess exits (`subprocess.run` doesn't raise without
  `check=True`) — now `returncode != 0` fails open with a stderr diagnostic.
  Both have regression tests. **Both gates degrade open on misconfiguration.**

## Open questions

- Live pollution test: a real `claude --agent evaluator -p` from the gate —
  confirm recursion sentinel + cost behave in practice. Guards make it safe by
  design; the live run is confirmation, not a blocker.
- Decompose vs deprecate `LongRunningStrategy` — keep as a convenience bundle, or
  retire it for explicit `include_recipes`? (P4)
