# SPEC-GAPS.md — Claude Code hooks protocol coverage

How fasthooks tracks against the **current** Claude Code hooks protocol. This is the
*protocol-coverage* lens (what the wire supports vs what fasthooks models); the
*authoring-ergonomics* lens lives in `SMELL.md`.

**Authoritative source** (verified against, 2026-05-30):
- Reference: https://code.claude.com/docs/en/hooks.md
- Guide: https://code.claude.com/docs/en/hooks-guide.md

## TL;DR

Everything fasthooks *implements* serializes correctly and is current — including
PreToolUse's `hookSpecificOutput.permissionDecision` shape and the deprecation where
top-level `approve`/`block` map to `allow`/`deny` (hooks.md "PreToolUse decision
control"). **No incorrect behavior found.** The gaps below are all *missing newer
features*, not bugs. The `@app.on("EventName")` generic decorator keeps every
unmodeled event dispatchable without a release, so "not typed" ≠ "not usable".

---

## Event coverage

fasthooks ships typed event models (with accessors + dedicated decorators) for ~10 of
the ~40 protocol events. The rest dispatch via `@app.on("EventName")` as a
`GenericEvent` (all fields preserved). Grouped by lifecycle cadence (per the docs'
lifecycle diagram):

Legend: ✅ typed model + decorator · ⚙️ via `@app.on()` only (no typed model)

### Once per session
| Event | fasthooks | Notes |
|-------|-----------|-------|
| `SessionStart` | ✅ | Missing decision extras — see below |
| `SessionEnd` | ✅ | |
| `Setup` | ⚙️ | `--init`/`--maintenance`/`--init-only` prep |
| `InstructionsLoaded` | ⚙️ | CLAUDE.md / rules loaded; audit/observability |

### Each turn
| Event | fasthooks | Notes |
|-------|-----------|-------|
| `UserPromptSubmit` | ✅ | |
| `Stop` | ✅ | |
| `UserPromptExpansion` | ⚙️ | slash-command expansion; can block |
| `StopFailure` | ⚙️ | turn ended on API error; output ignored |
| `TeammateIdle` | ⚙️ | agent-teams; can block (keep working) |

### Agentic loop (per tool call)
| Event | fasthooks | Notes |
|-------|-----------|-------|
| `PreToolUse` | ✅ | typed tool events; see decision-field gaps |
| `PostToolUse` | ✅ | |
| `PermissionRequest` | ✅ | shape exact; missing `updatedPermissions` |
| `SubagentStop` | ✅ | |
| `PostToolUseFailure` | ✅ | `@app.post_tool_failure("Bash")` → `ToolFailureEvent` (`.error`) |
| `PostToolBatch` | ⚙️ | after a parallel batch; can block the loop |
| `PermissionDenied` | ⚙️ | auto-mode denial; `retry: true` unsupported |
| `SubagentStart` | ⚙️ | |
| `TaskCreated` / `TaskCompleted` | ⚙️ | can block (roll back / prevent complete) |
| `Elicitation` / `ElicitationResult` | ⚙️ | MCP user-input round trip; can block |

### Async / reactive / side-channel
| Event | fasthooks | Notes |
|-------|-----------|-------|
| `Notification` | ✅ | |
| `PreCompact` | ✅ | |
| `PostCompact` | ⚙️ | |
| `ConfigChange` | ⚙️ | can block (except policy_settings) |
| `CwdChanged` | ⚙️ | direnv-style reactive env |
| `FileChanged` | ⚙️ | matcher = watched filenames (special rules) |
| `WorktreeCreate` / `WorktreeRemove` | ⚙️ | isolation lifecycle; Create blocks on any non-zero |
| `MessageDisplay` | ⚙️ | display-time; no decision control |

> The `HookEventName(str, Enum)` added in the DevX pass enumerates only the ~10 typed
> events. It's intentionally a known-set convenience, not a closed world — but it could
> grow as events get typed.

---

## Decision-control & output-field gaps

| Gap | Spec | fasthooks today | Priority |
|-----|------|-----------------|----------|
| ~~`permissionDecision: "ask"`~~ | PreToolUse decision control | ✅ **done** — `ask(reason, modify=)` builder | — |
| `permissionDecision: "defer"` | PreToolUse, "Defer a tool call" | unsupported | LOW — headless/SDK-resume niche |
| ~~`stopReason` (with `continue: false`)~~ | JSON output universal fields | ✅ **done** — `halt(reason)` builder + `stop_reason` field | — |
| `updatedPermissions` | PermissionRequest decision control | unsupported | LOW — addRules/setMode entries |
| SessionStart extras: `initialUserMessage`, `watchPaths`, `sessionTitle`, `reloadSkills` | SessionStart decision control | only `additionalContext` | LOW/MED |
| ~~`additionalContext` on tool events~~ | PreToolUse/PostToolUse | ✅ **done** — `context()` works on any event; `allow/deny(additional_context=)` to combine with a decision | — |
| `suppressOutput`, `terminalSequence` | JSON output universal fields | unmodeled | LOW |
| `PermissionDenied` → `retry: true` | PermissionDenied | unsupported (event also untyped) | LOW |

---

## Recommended order (when we pick this up)

1. **`ask` permission decision** — small, high-value. Add an `ask()`/`ask_permission()`
   builder so a hook can escalate to the user instead of only allow/deny. Wire into the
   PreToolUse `permissionDecision` serialization that already exists.
2. ~~**Typed `PostToolUseFailure`**~~ — ✅ **done.** `@app.post_tool_failure(*tools)`
   decorator + `ToolFailureEvent` (`.error`, `.is_interrupt`, `.duration_ms`). Fails
   open on a handler crash (the tool already failed; nothing to block).
3. ~~**`stopReason`** + **`additionalContext` on tool events**~~ — ✅ **done.**
   `halt(reason)` (continue:false + stopReason, terminal); `allow/deny(additional_context=)`
   and `context()` on any event.
4. Type the next tranche of agentic-loop events (`PostToolBatch`, `PermissionDenied`
   with `retry`, `SubagentStart`).
5. Advanced/niche: `updatedPermissions`, SessionStart extras, `defer`, `terminalSequence`.

None of these block correctness — they extend coverage. Verified: the response layer
fasthooks already ships matches the live spec exactly.
