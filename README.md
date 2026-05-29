# fasthooks

<p align="center">
  <em>Claude Code Hook SDK for Python</em>
</p>

<p align="center">
<a href="https://pypi.org/project/fasthooks"><img src="https://img.shields.io/pypi/v/fasthooks?color=%2334D058&label=pypi" alt="PyPI version"></a>
<a href="https://pypi.org/project/fasthooks"><img src="https://img.shields.io/pypi/dm/fasthooks?color=%2334D058&label=downloads" alt="Downloads"></a>
<a href="https://github.com/oneryalcin/fasthooks"><img src="https://img.shields.io/github/stars/oneryalcin/fasthooks?style=flat&color=yellow" alt="GitHub stars"></a>
<a href="https://github.com/oneryalcin/fasthooks/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
</p>

<p align="center">
<strong><a href="https://oneryalcin.github.io/fasthooks/">Documentation</a></strong> · <strong><a href="https://github.com/oneryalcin/fasthooks">GitHub</a></strong> · <strong><a href="https://pypi.org/project/fasthooks/">PyPI</a></strong>
</p>

---

Delightful Claude Code hooks with a FastAPI-like developer experience.

```python
from fasthooks import HookApp, deny

app = HookApp()

@app.pre_tool("Bash")
def no_rm_rf(event):
    if "rm -rf" in event.command:
        return deny("Dangerous command")

if __name__ == "__main__":
    app.run()
```

## Features

- **Typed events** - Autocomplete for `event.command`, `event.file_path`, etc.
- **Decorators** - `@app.pre_tool("Bash")`, `@app.on_stop()`, `@app.on_session_start()`
- **Dependency injection** - `def handler(event, transcript: Transcript, state: State)`
- **Background tasks** - Spawn async work that feeds back in subsequent hooks
- **Claude sub-agents** - Use Claude Agent SDK for AI-powered background tasks
- **Blueprints** - Compose handlers from multiple modules
- **Middleware** - Cross-cutting concerns like timing and logging
- **Guards** - `@app.pre_tool("Bash", when=lambda e: "sudo" in e.command)`
- **Generic dispatch** - `@app.on("AnyEvent")` handles hook types without a typed model
- **HTTP transport** - `fasthooks serve` runs hooks as a persistent server (no per-event process spawn)
- **Recipes** - `fasthooks add kill-switch` scaffolds ready-made hook patterns
- **Studio** - `fasthooks studio` is a visual debugger for hook executions
- **Testing utilities** - `MockEvent` and `TestClient` for easy testing

## Installation

```bash
pip install fasthooks
```

Or with uv:

```bash
uv add fasthooks
```

## Quick Start

### 1. Create a hooks file

```bash
fasthooks init              # writes .claude/hooks.py
# or choose a path: fasthooks init -p hooks.py
```

### 2. Edit hooks.py

```python
from fasthooks import HookApp, allow, deny

app = HookApp()

@app.pre_tool("Bash")
def check_bash(event):
    # event.command has autocomplete!
    if "rm -rf" in event.command:
        return deny("Dangerous command blocked")
    return allow()

@app.pre_tool("Write")
def check_write(event):
    # event.file_path, event.content available
    if event.file_path.endswith(".env"):
        return deny("Cannot modify .env files")
    return allow()

@app.on_stop()
def on_stop(event):
    return allow()

if __name__ == "__main__":
    app.run()
```

### 3. Register with Claude Code

`fasthooks install` wires every event your handlers use into Claude Code's
`settings.json` for you — no hand-editing:

```bash
fasthooks install .claude/hooks.py     # project scope (default)
fasthooks status                       # verify what's registered
```

Use `--scope user|local` to install elsewhere, and `fasthooks uninstall` to remove.

## API Reference

### Responses

A handler returns a response to influence Claude Code, or returns nothing to
stay out of the way.

```python
from fasthooks import allow, deny, block, ask, halt, context

return None                                 # Pass / no opinion (the common case)
return deny("Reason shown to Claude")       # Block a tool (PreToolUse)
return block("Continue working on X")       # Don't stop yet (Stop/SubagentStop)
return ask("Confirm this command?")         # Escalate to the user (PreToolUse)
return halt("Build broken, fix it first")   # Stop Claude entirely (any event)

return allow()                              # Same as `return None` (no-op)
return allow(message="note")                # Allow, but show a message
return allow(modify={"command": "safe ls"}) # Allow with rewritten tool input
return allow(additional_context="env=prod") # Allow + inject context for Claude

# PermissionRequest hooks (a *different* response shape — see below)
return approve_permission()                 # Allow the permission
return approve_permission(modify={"command": "safe"})
return deny_permission("Not allowed")       # Deny the permission

# SessionStart / UserPromptSubmit - inject text into Claude's context
return context("Project uses Python 3.12", hook_event="SessionStart")
```

**`return None` vs `allow()`** — they're equivalent for a bare allow: both mean
"no opinion, proceed." The idiomatic guard just returns nothing (or `deny(...)`).
Reach for `allow(...)` only when you want to *attach* something — a `message`, or
a `modify` that rewrites the tool input before it runs.

**`allow()` vs `approve_permission()`** — same intent ("let it proceed"), two
different hook shapes. Regular tool hooks (`PreToolUse`, …) use `allow`/`deny`;
the separate `PermissionRequest` hook uses `approve_permission`/`deny_permission`.
The verbs differ because Claude Code's protocol uses a different field vocabulary
for each — fasthooks mirrors the wire shapes rather than papering over them.

**Injecting context** — `context(text, hook_event=...)` injects text into Claude's
context window and works on *any* event (`SessionStart`, `UserPromptSubmit`,
`PreToolUse`, `PostToolUse`, …). To attach context *to a decision* in one response,
pass `additional_context=` to `allow()`/`deny()`.

**`halt()`** stops Claude entirely (`continue: false`) with a message to the user.
It works on any event and takes precedence over other decisions — use it for
"something is broken, don't continue."

### Tool Decorators

```python
@app.pre_tool("Bash")                    # Single tool
@app.pre_tool("Write", "Edit")           # Multiple tools
@app.post_tool("Bash")                   # After execution
@app.post_tool_failure("Bash")           # After a failed call
```

`post_tool_failure` handlers receive a `ToolFailureEvent` with `event.error`,
`event.is_interrupt`, and `event.duration_ms` alongside the usual
`event.tool_name` / `event.tool_input`:

```python
@app.post_tool_failure("Bash")
def on_bash_error(event):
    log.warning("Bash failed in %dms: %s", event.duration_ms, event.error)
```

### Lifecycle Decorators

```python
@app.on_stop()                           # Main agent stops
@app.on_subagent_stop()                  # Subagent stops
@app.on_session_start()                  # Session begins
@app.on_session_end()                    # Session ends
@app.on_pre_compact()                    # Before compaction
@app.on_prompt()                         # User submits prompt
@app.on_notification()                   # Notification sent
@app.on_permission("Bash")               # Permission dialog shown (tool-specific)
@app.on_permission()                     # Permission dialog (catch-all)
```

### Typed Events

```python
@app.pre_tool("Bash")
def handle_bash(event):
    event.command      # str
    event.description  # str | None
    event.timeout      # int | None

@app.pre_tool("Write")
def handle_write(event):
    event.file_path    # str
    event.content      # str

@app.pre_tool("Edit")
def handle_edit(event):
    event.file_path    # str
    event.old_string   # str
    event.new_string   # str
```

### Generic Events

Claude Code ships new hook events regularly. `@app.on("EventName")` dispatches
any event — even ones without a dedicated typed model — so you don't have to
wait for a fasthooks release. Read event-specific fields straight off `event`:

```python
@app.on("FileChanged")
def on_file_changed(event):
    if event.file_path.endswith(".py"):
        return deny("Edit .py via the agent, not directly")

@app.on("PostToolUseFailure", when=lambda e: e.tool_name == "Bash")
def on_bash_failure(event):
    ...
```

### Custom & MCP tools

Typed accessors (`event.command`, `event.file_path`) exist for the built-in
tools. **Any other tool — including MCP tools — works too, via `event.tool_input`:**

```python
@app.pre_tool("mcp__server__search")
def guard(event):
    query = event.tool_input.get("query", "")   # always available, any tool
    if "secret" in query:
        return deny("No.")
```

That's the only thing you need. If you hook a custom tool *often* and want the
same typed-accessor / autocomplete experience as the built-ins, register a
`ToolEvent` subclass (opt-in — one registration covers pre/post/permission):

```python
from fasthooks import ToolEvent

class Search(ToolEvent):
    @property
    def query(self) -> str:
        return self.tool_input.get("query", "")

app.register_tool_event("mcp__server__search", Search)

@app.pre_tool("mcp__server__search")
def guard(event):           # event is a Search
    if "secret" in event.query:
        return deny("No.")
```

The payoff (autocomplete) costs one `@property` per field. Expose fields via
`@property` over `self.tool_input` and don't add **required** pydantic fields:
event parsing happens before your handler runs, so a validation error on a
missing field would fail *open* (allow) even under `fail_mode="closed"`.

### Dependency Injection

```python
from fasthooks.depends import Transcript, State

@app.on_stop()
def with_deps(event, transcript: Transcript, state: State):
    # transcript - lazy-parsed transcript with stats
    print(transcript.stats.tool_calls)  # {"Bash": 5, "Read": 3}
    print(transcript.stats.duration_seconds)

    # state - persistent dict (session-scoped)
    state["count"] = state.get("count", 0) + 1
    state.save()
```

### Guards

```python
@app.pre_tool("Write", when=lambda e: e.file_path.endswith(".py"))
def python_only(event):
    # Only called for .py files
    pass

@app.on_session_start(when=lambda e: e.source == "startup")
def startup_only(event):
    # Only on fresh startup, not resume
    pass
```

### Fail mode (what happens when a handler crashes)

By default fasthooks **fails open** — if a handler raises, the error is logged and
the action proceeds. For a security guard you usually want the opposite: a crash
should **block**, not silently allow.

```python
app = HookApp(fail_mode="closed")          # app-wide default

@app.pre_tool("Bash", fail_mode="closed")  # or per-handler
def guard(event):
    ...
```

When `closed`, a crashed handler denies/blocks the event it was handling
(PreToolUse → deny, PermissionRequest → deny, Stop/SubagentStop/PostToolUse →
block). Events with no block semantics (SessionStart, Notification, …) always
fail open. Strategies declare their own `fail_mode` via `Meta`.

### Blueprints

```python
from fasthooks import Blueprint

security = Blueprint("security")

@security.pre_tool("Bash")
def no_sudo(event):
    if "sudo" in event.command:
        return deny("sudo not allowed")

# In main app
app.include(security)
```

### Middleware

```python
import time

@app.middleware
def timing(event, call_next):
    start = time.time()
    response = call_next(event)
    print(f"Took {time.time() - start:.3f}s")
    return response
```

### Background Tasks

Spawn async work that completes independently and feeds back results in subsequent hooks:

```python
from fasthooks import HookApp, allow
from fasthooks.tasks import task, Tasks

@task
def analyze_code(code: str) -> str:
    # Long-running analysis...
    return "Analysis result"

app = HookApp()

@app.pre_tool("Write")
def on_write(event, tasks: Tasks):
    # Spawn task (key defaults to function name)
    tasks.add(analyze_code, event.content)
    return allow()

@app.on_prompt()
def check_results(event, tasks: Tasks):
    # Pop by function reference (no string typos)
    if result := tasks.pop(analyze_code):
        return allow(message=f"Previous analysis: {result}")
    return allow()
```

### Claude Sub-Agents

Use Claude Agent SDK for AI-powered background tasks (requires `pip install fasthooks[claude]`):

```python
from fasthooks.contrib.claude import ClaudeAgent, agent_task
from fasthooks.tasks import Tasks

@agent_task(model="haiku", system_prompt="You review code for bugs.")
async def review_code(agent: ClaudeAgent, code: str) -> str:
    return await agent.query(f"Review this code:\n{code}")

@app.pre_tool("Write")
def on_write(event, tasks: Tasks):
    tasks.add(review_code, event.content)
    return allow()
```

## Testing

```python
from fasthooks.testing import MockEvent, TestClient

def test_no_rm_rf():
    app = HookApp()

    @app.pre_tool("Bash")
    def handler(event):
        if "rm" in event.command:
            return deny("No rm")
        return allow()

    client = TestClient(app)

    # Safe command - allowed
    response = client.send(MockEvent.bash(command="ls"))
    assert response is None

    # Dangerous command - denied
    response = client.send(MockEvent.bash(command="rm -rf /"))
    assert response.decision == "deny"
```

## Recipes

Scaffold ready-made hook patterns into your project:

```bash
fasthooks add kill-switch    # halt all tool calls while a sentinel file exists
fasthooks add steer          # surface a one-time note to the agent, then clear it
```

## HTTP Transport

By default Claude Code spawns a fresh process per hook event. For lower latency
(or shared in-memory state across events) run your hooks as a persistent server
(`pip install fasthooks[server]`):

```bash
fasthooks serve .claude/hooks.py                 # http://127.0.0.1:8765
fasthooks serve .claude/hooks.py --reload        # auto-reload on changes

# Point Claude Code at the running server:
fasthooks install .claude/hooks.py --http        # add --auth to require a shared secret
```

`serve` binds to loopback by default; a non-loopback bind requires `--token`
(or `$FASTHOOKS_TOKEN`) unless you pass `--allow-unauthenticated`. You can also
serve programmatically: `app.serve(host="127.0.0.1", port=8765, token=...)`.

## Studio

A visual debugger for hook executions — inspect events, decisions, and timings
(`pip install fasthooks[studio]`):

```bash
fasthooks studio            # opens http://127.0.0.1:5555
fasthooks studio --open     # and launch a browser
```

## CLI

```bash
fasthooks init                      # create .claude/hooks.py
fasthooks install hooks.py          # register with Claude Code (--scope, --http, --auth)
fasthooks status                    # show what's registered and validate
fasthooks uninstall                 # remove hooks (--scope)
fasthooks add <recipe>              # scaffold a recipe (kill-switch, steer)
fasthooks serve hooks.py            # run as a persistent HTTP server
fasthooks studio                    # launch the visual debugger
fasthooks --help                    # full help
```

## License

MIT
