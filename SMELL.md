# SMELL.md — fasthooks DevX ergonomics tracker

Living list of authoring-surface friction and smells, with status. Companion to
`REVIEW-devx.md` (which is the strategic/revival lens); this file is the focused
**authoring ergonomics** lens: how easy is it to write a correct hook, and what
bites you on the unhappy path.

Convention: each item has an ID, severity, status, evidence (`file:line`), and the
fix direction. Status: `open` → `in-progress` → `done` (link the commit/PR).

---

## S3 — Fail-open is invisible, unconfigurable for plain handlers, and `fail_mode="closed"` is a broken promise
**Severity:** high (this is a *guardrail* library; a crashed security hook silently allowing the tool is the scariest possible default)
**Status:** done — branch `devx/smell-tracking`

**Evidence:**
- A raising handler (incl. a DI miss → `TypeError`) is caught, logged to stderr,
  emitted as a `handler_error` event, and **the tool proceeds** — unconditionally.
  `src/fasthooks/app.py:851-868` (`_run_handlers`), `app.py:535` (serve path).
- `fail_mode: Literal["open","closed"]` exists on `StrategyMeta`
  (`strategies/base.py:45`) and is set by strategies (`clean_state.py:49`
  `fail_mode = "closed"  # Block if strategy errors - safety first`), but **`app.py`
  never references `fail_mode`** — it is never enforced. The strategy wrapper just
  re-raises (`base.py:253`) into the app's unconditional fail-open.
- Tests only assert the *declaration* (`meta.fail_mode == "closed"`,
  `tests/strategies/test_clean_state.py:234`), never the *behavior*. So the broken
  promise is untested.
- A plain `@app.pre_tool` guard has **no knob at all** to opt into fail-closed.

**Fix direction:**
1. Enforce `fail_mode` in dispatch: on a blocking-capable event (PreToolUse /
   PermissionRequest), a `closed` handler that raises returns `deny(...)` instead of
   silently continuing. Non-blocking events (Stop, lifecycle) stay fail-open — nothing
   to block — but still log/emit.
2. Expose the knob to plain handlers: app-level default (`HookApp(fail_mode=...)`)
   + per-decorator override (`@app.pre_tool("Bash", fail_mode="closed")`). Default
   stays `open` (backward compatible).
3. Propagate a strategy's `Meta.fail_mode` to its handlers when included, so
   `CleanStateStrategy` actually blocks on error.
4. Test **behavior**, not declaration: exception → deny when closed, → allow when open.

**Resolution (done):**
- `HookApp(fail_mode="open"|"closed")` default + per-decorator override
  (`@app.pre_tool(..., fail_mode="closed")`) on every block-capable decorator
  (`pre_tool`, `post_tool`, `on_permission`, `on`, `on_stop`, `on_subagent_stop`).
- Enforced in `_run_handlers` except-block: synthesizes the **event-appropriate**
  blocking response — `deny()` (PreToolUse), `deny_permission()` (PermissionRequest),
  `block()` (Stop/SubagentStop/PostToolUse); non-blocking events stay open.
- Strategy `Meta.fail_mode` tagged onto the handler wrapper (`base.py`), so
  `CleanStateStrategy`'s "closed" now actually blocks. Strategy mode is
  authoritative over the app default for its own handlers.
- **Guards fail open even in closed mode.** A `when=` guard is a filter, not the
  safety check — guard evaluation is in its own try/except that always skips the
  handler on error (only the handler *body* honors fail_mode). Caught in review:
  without this, a field-based guard raising on a `GenericEvent` payload would
  block the tool.
- **Event names are now a `HookEventName(str, Enum)`** (`events/base.py`) instead
  of scattered `"PreToolUse"` literals; used across dispatch (`tool_dicts`,
  `event_classes`, `_fail_closed_response`). str-subclass → drop-in with the raw
  wire strings as dict keys / in comparisons. (Tool *names* like "Bash" stay
  strings — open-ended set incl. MCP tools.)
- 13 behavior tests in `tests/test_fail_mode.py` (incl. DI-miss → deny,
  non-blocking-event → stays open, guard-raise → skip-not-block).
- **Known limitation:** per-handler mode is stashed as a function attribute, so
  registering the *same function object* under two `fail_mode`s lets the last win.
  Rare; documented. Lifting it would mean carrying mode in the `HandlerEntry` tuple.

---

## S2 — "Typed events" is partial and the fallback is undocumented
**Severity:** medium
**Status:** done — branch `devx/smell-tracking`

**Evidence:**
- ~10 built-in tools have typed accessors (`events/tools.py`); **any custom or MCP
  tool falls back to bare `ToolEvent`** with no accessors —
  `app.py` `TOOL_EVENT_MAP.get(tool_name, ToolEvent)`. The author must know to use
  `event.tool_input`; accessing a non-modeled field (`event.query`) raises
  `AttributeError` (verified — *not* a silent `None`, so the gap is discoverability
  + no autocomplete, not wrong values).

**Resolution (done):**
- **Docs first** (the diagnosed gap was discoverability): README "Custom & MCP tools"
  leads with "`event.tool_input` always works for any tool," then presents the opt-in.
- **Opt-in mechanism:** `app.register_tool_event(name, ToolEventSubclass)` — per-app
  (no global mutation / test leakage), validates the subclass (fast-fail TypeError),
  one registration covers pre/post/permission. Resolution order in
  `_parse_tool_event`: per-app override → built-in map → bare ToolEvent.
- Exported `ToolEvent`, `HookEventName`, `GenericEvent` at top level for ergonomic
  subclassing/import.
- **Documented constraint (cross-feature interaction):** custom event classes must be
  `@property`-only and keep `extra="allow"` — a *required* pydantic field would make
  parsing (which runs in `_dispatch`, *outside* `_run_handlers`) fail **open** on a
  missing field, punching a hole through `fail_mode="closed"`. Same interaction class
  as the S3 guard-raise bug.
- 5 tests in `tests/test_tool_event_registration.py` (typed pre + post, bare fallback
  + AttributeError, subclass validation, per-app isolation).

**Not done (deliberately):** the built-in `tools.py` accessors are still a hand-maintained
`@property` wall; registration pushes that same boilerplate onto custom-tool authors.
Acceptable (it's the durable pattern, opt-in) but a future ticket could explore a
schema-driven accessor generator.

---

## S1 — "Yes" has three faces and one verb flips
**Severity:** low (mostly docs — the split is protocol-inherited, not fasthooks' invention)
**Status:** done — branch `devx/smell-tracking`

**Evidence:**
- `allow()` → decision `"approve"`; `return None` also allows; permission requests use
  a different family — `approve_permission()` → wire `behavior:"allow"`. So
  `allow`↔`approve` swap meaning between the two response families.
- The split is **inherited from the Claude Code protocol** (top-level
  `decision: approve/block` vs PreToolUse `permissionDecision: allow/deny` vs
  PermissionRequest `behavior: allow/deny`); `responses.py:63` already translates
  approve→allow. So the builders already shield the author — the gap is docs.

**Fix direction:** docs only — say *when* to use `return None` vs `allow()`, and that
`allow()`/`approve_permission()` are the same intent across two protocol shapes. Do
NOT rename builders. Tracked alongside issue #26 (observability vocabulary unification).

**Resolution (done):** README "Responses" section rewritten. Verified empirically
that a bare `allow()` is dispatch-equivalent to `return None` (both non-blocking, no
output). Added: "`return None` vs `allow()`" (equivalent for bare allow; reach for
`allow(...)` only to attach a `message`/`modify`) and "`allow()` vs
`approve_permission()`" (same intent, two protocol shapes — regular tool hooks vs the
separate PermissionRequest hook; verbs mirror the wire vocabulary). No code change.

---

## Out of scope here (internal maintainability, author never touches)
- DI resolved by `module-name == "..." and name == "..."` string match (`app.py:900+`) —
  sturdy enough, but a module rename silently breaks injection. A registry would be safer.
- `HookResponse` is one dataclass with per-event `to_json` branching — mild god-object,
  hidden well by the builder functions.
