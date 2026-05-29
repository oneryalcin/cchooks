# fasthooks — adversarial DevX review (2026-05-29)

Reviewing from the angle: *the project stalled; is it worth reviving, and if so what changes?*
Lens is developer experience, not code quality. Findings are evidence-backed where possible.

---

## TL;DR

The authoring API is genuinely good. But fasthooks optimized the **5% that was already pleasant** (writing a handler) and ignored the **95% that is actually clunky** (latency, install drift, debugging, keeping up with Claude Code). Meanwhile Claude Code has moved the ground under it on two fronts at once:

1. **The hook surface roughly tripled.** fasthooks types ~10 events; CC now fires ~30, plus 5 delivery mechanisms (fasthooks supports 1) and a native `if` matcher that overlaps with fasthooks' own matching.
2. **CC now ships an `http` hook type** — which is *the* fix for the latency problem that makes the current command-hook model unpleasant to dogfood.

These are the same story: **the `http` delivery model is the wedge for a revival.** Revive it as a *low-latency, always-current hook gateway*, not as a bigger authoring framework. Aggressively cut the parts that turned a hook library into a platform (studio, observability, strategies).

---

## The wedge (lead with this if reviving)

**Run fasthooks as a persistent process registered via CC's new `http` hook type — author once, pay startup once.**

### Why this is the wedge, with numbers

The command-hook model CC started with means *every* hook fires a fresh OS process. `PreToolUse`/`PostToolUse` fire on every tool call. Measured on this machine (`app.run()` reading a real PreToolUse payload):

| invocation | cold | warm |
|---|---|---|
| `uv run --with fasthooks hooks.py` (**what `fasthooks install` generates**) | ~2.5 s | ~0.3–0.5 s |
| direct `python hooks.py` (fasthooks pre-installed) | ~1.6 s | ~0.4–0.55 s |
| `import fasthooks` only (in-process) | — | ~0.27–0.33 s (v0.1.4) |

> **Correction (logged for honesty):** an earlier draft cited "~0.05–0.09 s" for a bare import. That number was a *failed* `ImportError` against a Python that didn't have fasthooks — it measured interpreter startup, not the import. The real v0.1.4 import is ~0.27–0.33 s, because `import fasthooks` eagerly built the pydantic schemas for the entire transcript/observability/tasks subsystems. **Phase 0 below cut that to ~0.12 s.** The import was a *bigger* share of the per-call tax than first claimed — which strengthens both the strip and the server arguments.

Two honest conclusions from this:

- **The bottleneck is Python-process startup + pydantic/anyio import (~300–500 ms), not uv.** Once uv's cache is warm, `uv run` is *no slower* than a plain interpreter. So the tempting "cheap fix" (generate a console-script instead of `uv run --with`) buys almost nothing — the cost is paying interpreter + import on every tool call. This is a structural problem, not a config problem.
- A 300–500 ms tax on every tool call is enough to make Claude Code feel sluggish when fasthooks is installed. That is a plausible reason the author stopped dogfooding it.

The only real fix is **don't start a process per event.** CC's `http` hook type lets fasthooks run as one long-lived server: imports paid once, pydantic models compiled once, response in single-digit ms. This also unlocks shared in-memory state, connection pools, and the studio/observability features *for free* (the server is already running) — instead of bolting a separate SQLite-writing sidecar onto a per-call process.

This reframes the whole project: **fasthooks becomes the hook gateway you point CC at, not a script you copy around.**

---

## How far behind the event surface is (evidence)

Pulled from `https://docs.claude.com/en/docs/claude-code/hooks.md` today.

**fasthooks types (10):** PreToolUse, PostToolUse, Stop, SubagentStop, SessionStart, SessionEnd, PreCompact, UserPromptSubmit, Notification, PermissionRequest.

**CC fires (~30):** all of the above **plus** Setup, UserPromptExpansion, PermissionDenied, PostToolUseFailure, PostToolBatch, MessageDisplay, SubagentStart, TaskCreated, TaskCompleted, StopFailure, TeammateIdle, InstructionsLoaded, ConfigChange, CwdChanged, FileChanged, WorktreeCreate, WorktreeRemove, PostCompact, Elicitation, ElicitationResult.

≈20 events unsupported (~67% gap), including ones with real DevX value: `FileChanged` (direnv-style reactive env), `CwdChanged`, `PostToolUseFailure`/`StopFailure` (error instrumentation — a first-class test target per your own CLAUDE.md), `PermissionDenied` with `{retry: true}`.

**Delivery types:** CC supports `command`, `http`, `prompt`, `agent`, `mcp_tool`. fasthooks supports `command` only — and doesn't generate the new `if` permission-rule matcher (`Bash(git *)`, `Edit(*.ts)`).

### Root cause — this gap is structural, not "needs a few PRs"

`TOOL_EVENT_MAP` (app.py) and `_parse_lifecycle_event`'s hardcoded dict mean **every new CC event and every new tool requires a library code change + release.** A library whose correctness is defined by a hand-maintained enum of an upstream surface that ships new events monthly will *always* lag. The architecture guarantees the staleness the author is feeling. A revival must invert this: parse generically by default (the untyped `ToolEvent`/`BaseEvent` already exists as fallback), and treat typed accessors as *progressive enhancement* over a never-stale generic core. Unknown event? Still dispatchable.

---

## Cut (this is likely *why* it stalled)

For a 0.1.4 hook library, the surface is enormous, and your own CLAUDE.md is the prosecution: *"ruthless simplicity wins. John Carmack mindset, not Java Enterprise astronautics."*

- **`studio/`** — a full React + Vite + FastAPI + SQLite + websockets app, bundled frontend, its own spec. This is a product, not a library feature. The last ~8 commits before the project went quiet are almost all studio/observability. **The scope creep and the stall are the same event.**
- **`observability/`** — observers, SQLite backend, capture/file backends, an event taxonomy. Justified *only* once there's a persistent server (the wedge) emitting to it cheaply. As a bolt-on to a per-call process it's overhead with nowhere good to write.
- **`strategies/`** — token_budget, long_running, clean_state, a registry with conflict detection. Abstraction built before there were enough concrete hooks to abstract *from*. Premature.
- **`tasks/` background tasks + `contrib/claude` sub-agents** — "spawn async work from a per-call process that exits immediately" is architecturally awkward; it only makes sense behind the persistent server.

None of this is bad code. It's the wrong *altitude* for where the project is. Recommendation: move studio/observability/strategies out of core (separate packages or a `extras`/plugins dir), get the core back to "type events + dispatch + test," ship that, then earn each extra back on top of the server.

---

## Keep (the foundation a revival stands on)

Credit where due — these are the genuinely delightful parts and the reason revival is worth it at all:

- **The FastAPI-like decorator API** (`@app.pre_tool("Bash")`, `@app.on_stop()`) — the headline DX, still the right idea.
- **Typed events with property accessors** (`event.command`, `event.file_path`) — autocomplete is the real sell. Keep as *enhancement over* a generic core (see above).
- **Dependency injection** (`State`, `Transcript`) via type hints — clean, and `Transcript.stats` is a real differentiator CC doesn't give you.
- **`TestClient` + `MockEvent`** — testing hooks is otherwise miserable; this is a moat. Lean into it (`fasthooks replay <transcript.jsonl>` against real session data — the `specs/data/*.jsonl` samples are already there).

---

## The adversarial question: is this layer disappearing?

A feature-gap list is a roadmap, not a review. The real threat to a revival is **CC commoditizing the layer fasthooks sits on.** Be honest about which parts are being eaten:

| fasthooks provides | CC native equivalent | Verdict |
|---|---|---|
| `when=` guards, regex matchers | `if: "Bash(git *)"` permission-rule matcher | **Commoditized** — stop competing here; *generate* `if`, don't reinvent it |
| `command` delivery, process model | `http`/`agent`/`prompt`/`mcp_tool` types | **Commoditized delivery** — adopt `http`, don't fight it |
| Routing one command to many events | settings.json hand-editing | Thin value; install ceremony (below) is the real ask |
| **Typed events + accessors** | raw JSON on stdin | **Durable** — CC won't ship Python types |
| **DI: `State`, `Transcript.stats`** | nothing | **Durable** — genuine value-add |
| **`TestClient`/replay** | nothing | **Durable** — strongest moat |
| **Persistent server + cross-hook state** | nothing (you'd hand-roll a server) | **Durable** — the wedge |

So: matching and delivery are being absorbed; **typed authoring, DI, testing, and a persistent gateway are not.** Revive *toward* the durable column.

**Go/no-go: GO.** Competition is not the constraint — most people still wire hooks as bare shell/Python scripts, so the bar is simply "more ergonomic than a raw script," not "beat an incumbent framework." That bar is low and fasthooks already clears it on authoring. The risk was never *whether* to revive; it's *what to revive* — and the answer is the durable column above (typed events, DI, testing, persistent gateway), not the commoditized one (matching, delivery).

---

## Install ceremony & drift (secondary, but real)

`fasthooks install` introspects handlers and writes a **point-in-time snapshot** into settings.json (with lock file, `.bak` backup, restart reminder). Add a handler → settings.json is now stale → must re-run `install`. The `status` command exists *specifically to detect this drift* — which is a tell that the drift shouldn't exist in the first place.

The persistent-server model dissolves this: settings.json points at one stable `http` endpoint forever; *which* events you handle is decided at runtime by what's registered, so adding a handler needs no re-install and no restart. `fasthooks install` shrinks from "snapshot generator" to "register one endpoint once."

---

## Suggested shape of a revival (not a plan, a direction)

1. **Generic-first core** — dispatch any event by name; typed classes are optional enhancement. Kills the structural staleness.
2. **`http` server mode** as the default delivery — pay startup once; fixes latency; unlocks state/observability cheaply.
3. **Cut studio/observability/strategies** out of core to extras/plugins; earn them back on the server.
4. **Generate CC-native `if` matchers** instead of competing with `when=`/regex.
5. **Lean into the moat**: `fasthooks replay` against real transcripts; keep DI + `TestClient` front and center.
6. **Then** decide go/no-go after a competitive scan.

---

# Product direction: recipes as the ecosystem

> Go/no-go is settled (GO). This section is the *product*, not the audit. North star, stated by the project owner: **easy to use, easy to add.** Every decision below is graded against that.

## Positioning

Most people still wire Claude Code hooks as **bare shell/Python scripts** — copy-pasted, untyped, untested, re-edited per project. Anthropic's own [`cwc-long-running-agents`](https://github.com/anthropics/cwc-long-running-agents) (Apache-2.0) is the honest face of this: standalone `.sh` files, explicitly *"example ingredients, not a turnkey harness… not maintained and not accepting contributions."* The patterns are excellent; the **delivery** is copy-paste bash that rots.

**That gap is the product.** fasthooks is *the maintained, typed, tested home for hook patterns* — the layer between "raw script you fork and forget" and "feature Anthropic will never ship as a Python framework."

- **Target user:** someone building an agent harness (long-running loops, verify-gates, kill-switches, auto-commit) who today copies cwc's bash and adapts it by hand.
- **Job to be done:** *"give me a battle-tested hook pattern I can drop in, tweak the 3 project-specific bits, and trust — without reading 200 pages of hook docs or debugging stdin JSON parsing."*

## The recipe — and the one load-bearing design decision

A **recipe** is a named, versioned, tested hook pattern. The trap is defining it as "a Blueprint you `import`" — because harness patterns are *inherently project-specific* (your results file, your evaluator prompt, your evidence globs). cwc proves this: every primitive ships with "adjust this for your project." A pure import-and-configure model bets you can anticipate every knob — and for an evaluator *prompt*, you can't.

So a recipe is a **split**, not a single artifact:

| Part | What | Where it lives | Who owns it |
|---|---|---|---|
| **Engine** | the stable, tested mechanism (e.g. *"deny write to results-file unless Read first"*) | imported from `fasthooks` — versioned, type-checked, covered by `TestClient` | **us** |
| **Config/glue** | the volatile project-specific bits (paths, globs, the evaluator prompt) | **scaffolded into the user's repo** as an editable file they own | **the user** |

This is the **shadcn/ui model**: the high-value, hard-to-get-right machinery is a dependency; the part you *must* edit is copied into your tree so you own it outright. Recipes need editing *more* than UI components do — so lean into eject for the volatile half, keep import for the tested half. **This decision is the foundation of the whole recipe product**; "recipe = Blueprint" quietly gets it wrong.

This is also what beats a bare script on the only axis that matters: the engine is **tested and typed** (a bash script is neither), while the config stays as **editable as the script was**. Better *and* not more rigid.

## "Easy to use, easy to add" — the two flows that must be frictionless

**Use** (the consumer flow — optimize this to the bone):
```
fasthooks add long-running-harness
```
→ pulls the engine (already a dep), scaffolds the editable config into `.claude/hooks/`, wires the endpoint into settings.json **once**, prints the 3 lines you need to edit. No restart-per-change, no re-introspection drift (see install-ceremony fix above). `fasthooks list` / `fasthooks search verify` to discover.

**Add** (the contributor flow — low barrier is the moat):
a recipe is *one engine file + one test + one docstring + a scaffold template*. `fasthooks new-recipe` stamps the skeleton; `make check` is the quality bar; PR. If a contributor can't ship a recipe in an afternoon, the ecosystem won't form.

## Two tiers — and why recipes *require* the server

Don't force the server on the casual user; let the tiers reinforce each other.

- **Tier 1 — command hook (on-ramp).** One "block `rm -rf`" recipe at ~300 ms occasionally is annoying-but-survivable. Zero infra. "Just try it."
- **Tier 2 — server mode (power user / many recipes).** The 300 ms tax is only *fatal* when many recipes fire across many events. That's exactly the harness user. The persistent `http` server makes **"install 8 recipes" free** — startup paid once.

So the coupling is clean: **recipes are what justify building the server; the server is what makes a rich recipe stack usable.** Two caveats to honor or the tier is a fake win:
- Server lifecycle must be **invisible** — auto-start, auto-reload on code change. A daemon you babysit just moves the clunk.
- CC's `http` hooks **fail open** on connection failure (per the docs) — a dead fasthooks server won't block the agent loop. That de-risks the whole tier; say so.

## Sequencing guardrail (my own diagnosis, applied to myself)

This review's thesis is *scope creep killed it* — studio/observability/strategies built before the core earned them. **A registry + contribution portal + gallery + `new-recipe` scaffolding built before a single recipe is consumed is the same mistake in a new hat.** The pull toward "people contributing" is the risk vector. Sequence hard:

1. **Now:** ship 5–8 killer recipes **in-tree** (cwc hands you most), behind `fasthooks add`. The product is a *seeded catalog*, not a marketplace.
2. **Only after they demonstrably get consumed:** build the contribution loop (`new-recipe`, docs, gallery).
3. **Only if community volume demands it:** an external recipe index — at which point **trust becomes a real product problem** (a recipe is code that runs on every tool call in your dev loop = supply-chain/RCE surface; needs provenance, pinning, official-vs-community labels). Do not build this speculatively.

**Conflict detection** (two recipes both handling `Stop`, both denying writes): keep the *idea* from the cut `strategies` module — it finds its justification here — but ship it **when the second recipe touching the same event lands**, not day one. Don't let the reconciliation re-inflate the scope I just argued to cut.

## Seed catalog (port from cwc — Apache-2.0, credit the source)

Patterns aren't ownable; the port is clean with attribution. Each becomes an engine + scaffolded config:

| Recipe | Engine (tested, ours) | Scaffolded config (user edits) |
|---|---|---|
| **default-fail gate** | deny write to results-file unless evidence Read first | `RESULTS_FILE`, evidence glob patterns |
| **fresh-context evaluator** | Stop hook spawns evaluator, blocks on non-`PASS` | the evaluator prompt / `agent.md` |
| **commit-on-stop** | git add+commit backstop at session end | commit-message convention, paths |
| **kill-switch** | halt all tool calls while `AGENT_STOP` exists | sentinel filename |
| **steer** | surface `STEER.md` to the agent once, then clear | sentinel filename |

These five alone make fasthooks *the* ergonomic way to run the harness patterns Anthropic is publishing as throwaway bash — which is the entire pitch.

---

# Build sequence (minimal revival)

The goal of this sequence is **one vertical slice that proves the whole thesis**, not a finished product. Acceptance test for "minimal revival done":

> In a fresh project: `fasthooks init` → server running → `fasthooks add kill-switch` → restart Claude Code **once** → kill-switch works with **single-digit-ms** latency → then `fasthooks add default-fail-gate` works with **no settings change and no restart.**

That last property (recipe #2 needs no re-install) is the killer DevX proof and the antidote to the install-drift problem. Everything below builds to it. Each phase ends with a **runnable** check — per the project's own rule, nothing is "done" until its output is seen.

**Key architectural fact that makes this small:** `HookApp._dispatch(data) -> BaseHookResponse | None` already is the engine. `run()` (stdin→stdout) is one transport over it; the server is a second. We are not rewriting the core — we are adding a transport and removing hardcoding.

---

### Phase 0 — Strip to core (subtractive, do this first)

*Fight entropy before adding.* Get `import fasthooks` lean so latency wins are real and the core is legible again.

- Move `studio/`, `observability/`, `strategies/`, `tasks/`, `contrib/claude` out of the default import path → optional extras (`pip install fasthooks[studio]` etc.). **Move, don't delete** — git keeps them; they get earned back on the server.
- Ensure `fasthooks/__init__.py` and `app.py` import none of them at module load.

**Verify:** `python -c "import fasthooks"` import time drops; `make test` stays green. Measure import time before/after and record it.

> **STATUS: DONE** (branch `revival/phase0-strip-core`). The evidence redirected the approach: the cost wasn't extra *dependencies* (observability/tasks add no 3rd-party deps) — it was **eagerly building pydantic schemas** for the transcript/observability/tasks subsystems at module load. So the lever was **lazy-loading, not pyproject extras**: PEP 562 `__getattr__` on `depends/`, `observability/`, `tasks/` `__init__.py`, plus deferring those imports in `app.py` (transcript + task deps resolved by qualified-name in `_resolve_dependencies`, so a handler pays for `Transcript` only if it annotates it).
> **Result:** deterministic `-X importtime` cumulative **311.7 ms → 123.7 ms (−60%)**; transcript/observers/tasks/strategies no longer load at `import fasthooks`; **600/600 tests pass**, mypy clean, changed files lint-clean. Subsystems still work — they import lazily on first use.
> **Logged follow-up (runtime, not import):** `_dispatch` constructs `HookObservabilityEvent` (a pydantic model) ~8× per hook call *even with zero observers registered* — wasted work on every invocation. Guard event construction behind an observer-presence check in Phase 1/2.
> **Pre-existing lint debt** (not introduced here): ~20 ruff errors in `transcript/` and `testing/` remain — worth a separate cleanup pass.

---

### Phase 1 — Generic-first core (kills the structural staleness)

Today `TOOL_EVENT_MAP` and `_parse_lifecycle_event`'s dict mean a new CC event = a library release. Invert it.

- `_dispatch` routes **any** `hook_event_name` to registered handlers; unknown events parse as the generic `BaseEvent`/`ToolEvent` (both already exist as fallbacks). No more "unhandled because the enum doesn't list it."
- Add a generic registration path: `@app.on("FileChanged")`, `@app.on("PostToolUseFailure")`. Keep the typed sugar (`@app.pre_tool("Bash")`, `event.command`) as **progressive enhancement** layered on top — a typed-class registry you can extend, not a hardcoded gate.
- **Audit the response format while here:** `to_json()` emits legacy `{"decision","reason"}`; current docs show `hookSpecificOutput.permissionDecision` for `PreToolUse`. Confirm which CC still honors and align. (This is a correctness task, not cosmetic.)

**Verify:** through `TestClient`, feed a `FileChanged` and a `PostToolUseFailure` payload (neither exists in today's code) and assert a handler registered via `@app.on(...)` fires. That test failing today and passing after is the proof the staleness is fixed.

> **STATUS: DONE** (branch `revival/phase0-strip-core`, continued).
> - **`GenericEvent`** (`events/base.py`, `extra="allow"`) is the fallback for any event with no typed model — it *preserves every field* (the crux: `BaseEvent` is `extra="ignore"`, which would silently drop the `FileChanged` filename and make generic dispatch useless). Fields readable as attributes (`event.file_path`) or via `event.data`. Common fields relaxed so an unfamiliar event never fails validation.
> - **`@app.on(event_name, when=...)`** (`registry.py`) registers a handler for *any* event by name — the never-stale entry point. Works on `HookApp` and `Blueprint`.
> - **Dispatch is generic** (`app.py`): tool events still get matcher + `"*"` + any `on()` handlers; everything else routes by name and parses as the typed event if one exists, else `GenericEvent`. Unknown events with no handler dispatch cleanly to `None`.
> - **Verify result:** new `tests/test_generic_events.py` — `@app.on("FileChanged")` and `@app.on("PostToolUseFailure")` fire, read event-specific fields, honor `when=` guards, and unknown-event-no-handler is a clean no-op. **605/605 tests pass**, mypy + ruff clean.
> - **Observer-guard (the logged Phase-0 follow-up): DONE.** `_emit` now constructs the `HookObservabilityEvent` *after* the no-observer early-return. Empirically verified: **0 pydantic constructions per hook call with no observers** (was ~4–8), 4 when an observer is registered.
> - **Adversarial + standard Codex review (against `main`): findings triaged and addressed.** Both reproduced empirically before acting.
>   - *[HIGH] Fail-open broken by a raising guard* — `_run_handlers` bound `handler_start` only after the guard ran, so a guard that raises (e.g. a field-based guard on a `GenericEvent` missing that field — exactly what `@app.on()` invites) hit the error path with an `UnboundLocalError`, aborting dispatch so later handlers never ran. Pre-existing, but Phase 1 made it reachable and my first test missed it. **Fixed:** bind the timer before the guard; a raising guard now emits `handler_error` and continues (fails open). Regression test added.
>   - *[MEDIUM] Field loss on known events* — `@app.on("PreToolUse")` parsed through the typed model (`extra="ignore"`), dropping upstream-added fields and offering no `.data` — inconsistent with `GenericEvent`. **Fixed:** all event models now `extra="allow"` and `BaseEvent` exposes `.data`, so the "never lose data" contract holds for schema-drift on existing events too. Regression test added. (607/607 pass, mypy + ruff clean.)
>   - *[P2] `uv.lock` resolver cutoff* — `exclude-newer` + private-package exceptions leaked from the local env. **Not ours** — never staged on this branch; left for the maintainer's environment to handle.
> - **`to_json` format audit: investigated, change DEFERRED (with evidence).** Per hooks.md L1368, top-level `decision`/`reason` is **deprecated for PreToolUse** (use `hookSpecificOutput.permissionDecision`/`Reason`; `approve`/`block` → `allow`/`deny`) but remains **the current, correct format for PostToolUse and Stop**. fasthooks' `deny()`/`allow()` are event-agnostic, so correct serialization needs *event-aware* output at dispatch time — a behavior-sensitive change that should be validated against live Claude Code, not guessed. The deprecated path still functions, so this is non-breaking today; tracking it as a dedicated verified task (also re-check `PermissionHookResponse` against the `hookSpecificOutput.decision.behavior` shape).

---

### Phase 2 — `http` server transport (the latency wedge)

CC `http` hooks POST the event JSON and expect the same output JSON; **any error fails open** (non-blocking) — so a dead server never stalls the agent. This makes the server tier safe to ship early.

- Add `app.serve(host, port)` and a `fasthooks serve` command: a minimal ASGI app (FastAPI is already an optional dep) with one route that does `data = await request.json(); resp = await app._dispatch(data); return resp.to_json()` (200 + empty body when `resp is None`).
- One endpoint handles **all** events — dispatch already keys off `hook_event_name`. No per-event routes.

**Verify (the empirical payoff — measure it):** start the server, `curl` a `PreToolUse` `rm -rf` payload, assert the deny JSON comes back, and time it: it should be **single-digit ms** vs the ~300 ms command-hook path measured in this review. Record both numbers side by side — that delta *is* the pitch.

> **STATUS: DONE** (branch `revival/phase0-strip-core`, continued).
> - **`HookApp.serve(host, port)`** + **`_asgi_app`** (`app.py`): a minimal raw-ASGI handler — no FastAPI/Starlette, just `uvicorn` (new `server` extra). One endpoint dispatches every event (`_dispatch` already keys off `hook_event_name`); the *same* `to_json()` output as the stdin path. Per the hooks reference, any error **fails open** (empty 200), so a server fault never blocks the agent loop. (Gotcha fixed: uvicorn mis-detected the bound-method app as ASGI 2.0 — pinned `interface="asgi3"`.)
> - **`fasthooks serve <path>`** (`cli/commands/serve.py`): loads the `HookApp` from a hooks file and serves it; prints the exact `{"type":"http","url":...}` snippet to drop into settings.json.
> - **Measured, side by side:** `curl` of a `PreToolUse` `rm -rf` payload returns `{"decision":"deny",...}` in **avg 0.95 ms (min 0.84, max 1.25, n=30)** — vs **~300 ms** for the warm `uv run` command-hook path. **~300× faster per tool call.** Generic events (`FileChanged`) and malformed JSON both return clean 200s.
> - **Tests:** `tests/test_serve.py` drives `_asgi_app` directly (mock ASGI scope/receive/send — no live server needed): deny→JSON, allow→empty 200, generic-event-over-http, fail-open on bad JSON, lifespan startup/shutdown. **612/612 pass**, mypy + ruff clean.
> - **Out of scope (still, per the plan):** invisible lifecycle (auto-start/reload) — `fasthooks serve` is run manually for now; that polish is deferred until the slice is consumed.
>
> **Codex review round 2 (adversarial + standard, against `main`): triaged.**
> - *[HIGH] Unauthenticated HTTP endpoint.* The endpoint dispatches any received event into arbitrary handler code; the `--host` knob exposed that with no auth. Default bind is loopback (safe). **Cheap defenses shipped** (chosen over full auth, to fit the minimal slice): reject non-`POST` (405), and a loud stderr warning when binding a non-loopback host. The endpoint docstring states the trust boundary. **Follow-up logged:** an optional shared-secret token (fits CC's http-hook `headers` + `allowedEnvVars`) before recommending any non-loopback/remote use. Tests: 405-on-GET, warning-fires-on-`0.0.0.0`.
> - *[MED/P2] HTTP path bypassed `log_dir` logging* (both reviewers). Confirmed: the stdin path logged the raw event before dispatch, the HTTP path didn't — silently losing the JSONL audit trail in server mode. **Fixed:** `_asgi_app` now logs before `_dispatch` under the same best-effort guard. Regression test added (`log_dir` file written in server mode).
> - *[P2] `uv.lock` resolver cutoff* (standard, repeat). Still not ours — dirty working tree, never staged; left for the maintainer's environment.
> - 614/614 pass, mypy + ruff clean.

---

### Phase 3 — `fasthooks add` + first recipe, end-to-end (the engine/config split, made real)

Implement the recipe contract with **one** recipe chosen for being the cleanest vertical slice: **kill-switch** (pure `PreToolUse` deny, single config knob = sentinel filename). It exercises every moving part without state or subprocess complexity.

- **Engine** (ours, tested): `fasthooks.recipes.kill_switch` exports a Blueprint factory, e.g. `kill_switch(sentinel="AGENT_STOP") -> Blueprint`. Covered by `TestClient`.
- **Config/glue** (user owns): `fasthooks add kill-switch` (a) scaffolds an editable stub into `.claude/hooks/` wiring `app.include(kill_switch(sentinel="AGENT_STOP"))`, (b) ensures the server endpoint is registered in settings.json **once** (idempotent — re-running `add` for recipe #2 touches no settings).
- Credit cwc (Apache-2.0) in the recipe's docstring/source.

**Verify the full acceptance test:** in a temp project, `fasthooks add kill-switch` → `touch AGENT_STOP` → POST a `PreToolUse` payload to the running server → **denied**; `rm AGENT_STOP` → **allowed**. Then `fasthooks add default-fail-gate` (second recipe) and confirm settings.json is unchanged and no restart is needed — recipe #2 just registers at server runtime.

> **STATUS: DONE** (branch `revival/phase0-strip-core`, continued).
> - **The engine/config split, realized.** `fasthooks/recipes/` ships two tested **engines** (Blueprint factories): `kill_switch(sentinel="AGENT_STOP")` (catch-all `PreToolUse` deny while the sentinel exists) and `steer(sentinel="STEER.md")` (inject the file into the next prompt as context, then delete it) — both ported from cwc (Apache-2.0, credited in source). The **config** is a small editable file you own.
> - **`fasthooks add <recipe>`** scaffolds `.claude/hooks/recipes/<name>.py` (engine import + the one config knob, default derived from the engine signature so it can't drift). It **never touches settings.json** — that's *why* adding recipe #2 needs no Claude Code restart.
> - **`include_recipes(app, dir)`** discovers and includes every scaffolded `recipe`. It **fails open per file** (advisor + my own F1 contract): a broken/throwing recipe is skipped with a stderr warning so it can't take down the others or the server — covered by a deliberately-broken-recipe test. The `fasthooks init` template now calls it, so recipes are drop-in.
> - **Acceptance test proven through the real assembly, not just unit tests:** `fasthooks add kill-switch` → `fasthooks serve hooks.py` (whose `include_recipes(app)` discovered the recipe) → live `curl` returned the deny while `AGENT_STOP` existed, allowed once removed. Unit tests cover both engines, scaffolding, fail-open discovery, and "add is settings-neutral / idempotent."
> - **623/623 pass**, mypy + ruff clean. Core `import fasthooks` stays lean — recipes are not pulled in.
> - **Honest scope caveat:** `fasthooks install` still emits the *old* `uv run` command-hook config; nothing yet writes `{"type":"http","url":...}` into settings.json (`serve` only prints the snippet). So full "restart Claude Code once → works" still needs a one-time manual settings edit. What is *proven* is the narrower, still-strong claim: **adding recipes never touches settings.json.** Wiring `install`/a new command to emit the http config is the natural next step.

---

# Post-slice: `install --http` (close the settings gap)

> **STATUS: DONE** (the settings→http gap above is now closed).
> - **`fasthooks install <path> --http [--host --port]`** writes `{"type":"http","url":...}` entries into settings.json instead of the `uv run` command — so "restart Claude Code once → works" no longer needs a manual edit. The identity used for dedup/uninstall/status generalized from "command string" to **command-*or*-url** (`hook_identity`), so the merge/lock/remove machinery works for both transports. Verified end-to-end: install → reinstall `--force` (dedups, no duplicate) → uninstall (removes by url, deletes lock).
> - **Codex round-3 findings, triaged:**
>   - *[P2 standard] Generic-tool-event coverage collapsed at install time.* `@app.on("PreToolUse")` beside `@app.pre_tool("Bash")` introspected to `['PreToolUse:Bash','PreToolUse']` and `generate_settings` kept only the `Bash` matcher — so Claude Code would never deliver Edit/Write/etc. to the catch-all, even though `_dispatch` handles them. **Fixed:** a bare registration of a tool-capable event (`PreToolUse`/`PostToolUse`/`PostToolUseFailure`/`PermissionRequest`/`PermissionDenied`) now installs as a `*` matcher. Regression tests added. A genuine install-vs-dispatch divergence the review caught.
>   - *[HIGH adversarial] Unauthenticated endpoint — escalated, now FIXED with a shared-secret token.* The reviewer escalated the Phase-2 auth finding to no-ship (loopback isn't a real boundary — a local process or a browser page can POST to localhost) and tied the fix to the generated config.
> - 629/629 pass, mypy clean (my files; ~33 pre-existing transitive errors in `strategies/` etc. remain and are not mine), ruff clean.

---

# Auth: shared-secret token for the http transport

> **STATUS: DONE.** Closes the escalated [HIGH] adversarial finding.
> - **`serve(token=...)`** (or `$FASTHOOKS_TOKEN`, or `serve --token`): when set, `_asgi_app` requires `Authorization: Bearer <token>` and rejects missing/invalid with **401 before reading or dispatching the body** (constant-time `hmac.compare_digest`), so a forged request never reaches handler code. No token → current open behavior (loopback default); a non-loopback bind *without* a token now warns harder.
> - **`fasthooks install --http --auth`** generates a 32-byte URL-safe secret, emits `headers: {Authorization: "Bearer ${FASTHOOKS_TOKEN}"}` + `allowedEnvVars: ["FASTHOOKS_TOKEN"]` into the hook config (Claude Code's native env-interpolation), and **prints the secret once for you to export** — the secret itself is never written to settings.json. Both Claude Code and the server read `FASTHOOKS_TOKEN` from the environment, so they share the secret without it touching disk.
> - **Verified** through unit tests (valid/missing/invalid token → dispatch/401/401; config has the env-ref header, not the secret) *and* a live server (`FASTHOOKS_TOKEN=… serve` → curl: no token 401, bad token 401, good token dispatched). 632/632 pass, mypy + ruff clean.
> - Chosen posture: token is **opt-in** (default stays loopback-open for the zero-config local case). Refusing non-loopback binds without a token was offered but not chosen — the hard warning covers it.

---

### Explicitly OUT of the minimal slice (name it, so scope can't creep)

Defer until the slice above is consumed and proven:

- Invisible server lifecycle (auto-start, auto-reload) — minimal slice runs `fasthooks serve` manually; polish later.
- **Conflict detection** — ship it the moment the *second* recipe touching the same event lands, not before.
- Contribution tooling (`new-recipe`, gallery, docs site), external recipe **index**, and the trust/provenance model that an index forces.
- Native `if:` matcher generation, `prompt`/`agent`/`mcp_tool` delivery types.

These are the right *next* bets — but shipping any of them before the vertical slice is consumed repeats the exact scope creep that stalled the project.
