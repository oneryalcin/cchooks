# cchooks vs fasthooks

[cchooks](https://github.com/anthropics/cchooks) is a Python SDK for building Claude Code hooks. This is the most direct comparison - both libraries solve the same problem with different approaches.

## Same Goal, Different Approaches

| Aspect | cchooks | fasthooks |
|--------|---------|-----------|
| **Pattern** | Context factory | Decorator handlers |
| **Philosophy** | Minimal, explicit | Batteries-included |
| **API Style** | `create_context()` → methods | `@app.pre_tool()` → return |

Both eliminate JSON boilerplate and provide type-safe hook development.

## Architecture

### cchooks: Context Factory Pattern

```python
from cchooks import create_context, PreToolUseContext

c = create_context()  # Reads stdin, detects hook type
assert isinstance(c, PreToolUseContext)

if c.tool_name == "Bash" and "rm -rf" in c.tool_input.get("command", ""):
    c.output.deny(reason="Dangerous command blocked")
else:
    c.output.allow()
```

**Flow:** stdin → `create_context()` → type-specific context → `output.method()`

### fasthooks: Decorator Handlers

```python
from fasthooks import HookApp, deny

app = HookApp()

@app.pre_tool("Bash")
def check_bash(event):
    if "rm -rf" in event.command:
        return deny("Dangerous command blocked")

if __name__ == "__main__":
    app.run()
```

**Flow:** stdin → `app.run()` → route to handler → return response

## Event Coverage

Both support all Claude Code hook events:

| Event | cchooks | fasthooks |
|-------|:-------:|:---------:|
| PreToolUse | ✅ | ✅ |
| PostToolUse | ✅ | ✅ |
| Stop | ✅ | ✅ |
| SubagentStop | ✅ | ✅ |
| SessionStart | ✅ | ✅ |
| SessionEnd | ✅ | ✅ |
| UserPromptSubmit | ✅ | ✅ |
| Notification | ✅ | ✅ |
| PreCompact | ✅ | ✅ |
| PermissionRequest | ❌ | ✅ |

## Response Format

### cchooks: Method Calls

```python
# PreToolUse
c.output.allow()
c.output.deny(reason="Blocked", system_message="Warning")
c.output.ask(reason="Please confirm")

# Stop
c.output.prevent(reason="Keep working")
c.output.halt(reason="Fatal error")

# SessionStart
c.output.add_context("Additional context for Claude")

# Exit codes
c.output.exit_success()      # exit 0
c.output.exit_non_block()    # exit 1
c.output.exit_block()        # exit 2
```

### fasthooks: Return Values

```python
from fasthooks import allow, deny, block

@app.pre_tool("Bash")
def check(event):
    return deny("Blocked")           # Prevent execution
    return allow(message="OK")       # Continue
    return None                      # Allow (implicit)

@app.on_stop()
def check_stop(event):
    return block("Keep working")     # Prevent stop
```

| Action | cchooks | fasthooks |
|--------|---------|-----------|
| Allow tool | `c.output.allow()` | `return allow()` or `None` |
| Deny tool | `c.output.deny(reason=...)` | `return deny("reason")` |
| Prevent stop | `c.output.prevent(reason=...)` | `return block("reason")` |
| Add context | `c.output.add_context(...)` | `return allow(message=...)` |

## Type Safety

### cchooks: Context Classes

```python
from cchooks import PreToolUseContext

c = create_context()
assert isinstance(c, PreToolUseContext)

c.tool_name      # str
c.tool_input     # dict[str, Any]
c.session_id     # str
c.transcript_path # str
c.cwd            # str
```

Manual dict access for tool_input: `c.tool_input.get("command", "")`

### fasthooks: Pydantic Models with Properties

```python
@app.pre_tool("Bash")
def check(event):
    event.command      # str - direct property
    event.description  # str | None
    event.timeout      # int | None
    event.tool_input   # dict - raw access if needed
```

IDE autocomplete works on properties like `event.command`.

## Handler Registration

### cchooks: Single Entry Point

```python
# hook.py - handles ONE hook type
from cchooks import create_context, PreToolUseContext

c = create_context()
# Must check type manually
if isinstance(c, PreToolUseContext):
    # handle PreToolUse
```

**Each hook type = separate file** (or manual dispatch).

### fasthooks: Multiple Handlers

```python
# hooks.py - handles ALL hook types
app = HookApp()

@app.pre_tool("Bash")
def check_bash(event): ...

@app.pre_tool("Write")
def check_write(event): ...

@app.on_stop()
def on_stop(event): ...

app.run()  # Routes automatically
```

**One file can handle multiple events** with automatic routing.

## Tool Matching

### cchooks: Manual Check

```python
c = create_context()
if c.tool_name == "Bash":
    # handle Bash
elif c.tool_name in ["Write", "Edit"]:
    # handle Write/Edit
```

### fasthooks: Decorator Routing + Guards

```python
@app.pre_tool("Bash")           # Single tool
def check_bash(event): ...

@app.pre_tool("Write", "Edit")  # Multiple tools
def check_write(event): ...

@app.pre_tool()                 # Catch-all
def check_any(event): ...

@app.pre_tool("Bash", when=lambda e: "sudo" in e.command)
def check_sudo(event): ...      # Conditional
```

## State Management

### cchooks: None Built-in

```python
# Must manually implement persistence
import json
from pathlib import Path

STATE_FILE = Path.home() / ".my-hook-state.json"

c = create_context()
state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
state["count"] = state.get("count", 0) + 1
STATE_FILE.write_text(json.dumps(state))
```

### fasthooks: Dependency Injection

```python
from fasthooks.depends import State, Transcript

@app.pre_tool("Bash")
def check(event, state: State, transcript: Transcript):
    # state: auto-loaded JSON, session-scoped
    state["count"] = state.get("count", 0) + 1
    state.save()

    # transcript: parsed conversation history
    if transcript.stats.tool_calls.get("Bash", 0) > 100:
        return deny("Rate limit exceeded")
```

## Feature Comparison

| Feature | cchooks | fasthooks |
|---------|:-------:|:---------:|
| **Typed Events** | ✅ (context classes) | ✅ (Pydantic models) |
| **Property Accessors** | ❌ (dict access) | ✅ (`event.command`) |
| **Response Helpers** | ✅ (methods) | ✅ (functions) |
| **Multi-Handler Routing** | ❌ | ✅ |
| **Guards/Filters** | ❌ | ✅ (`when=`) |
| **Catch-All Handlers** | ❌ | ✅ (`@app.pre_tool()`) |
| **State Persistence** | ❌ | ✅ (`State`) |
| **Transcript Parsing** | ❌ | ✅ (`Transcript`) |
| **Background Tasks** | ❌ | ✅ (`Tasks`) |
| **Blueprints** | ❌ | ✅ |
| **Middleware** | ❌ | ✅ |
| **Testing Utils** | ❌ | ✅ (`MockEvent`, `TestClient`) |
| **Tool Input Modification** | ✅ (`updated_input`) | ❌ |
| **Safe Error Handling** | ✅ (`safe_create_context`) | ✅ |

## Unique to cchooks

### Tool Input Modification

cchooks can modify tool inputs before execution:

```python
c = create_context()
if c.tool_name == "Write":
    # Redirect writes to safe location
    c.output.allow(
        updated_input={"file_path": "/safe/location/" + c.tool_input["file_path"]}
    )
```

fasthooks currently doesn't support `updated_input`.

### Exit Code Control

cchooks provides explicit exit code methods:

```python
c.output.exit_success()      # exit 0 - success, stdout in transcript
c.output.exit_non_block()    # exit 1 - error shown to user
c.output.exit_block()        # exit 2 - blocking error
```

## Unique to fasthooks

### Dependency Injection

```python
@app.pre_tool("Bash")
def handler(event, state: State, transcript: Transcript, tasks: Tasks):
    # All injected automatically based on type hints
```

### Blueprints

```python
security = Blueprint()

@security.pre_tool("Bash")
def no_sudo(event):
    if "sudo" in event.command:
        return deny("No sudo")

app.include(security)
```

### Middleware

```python
@app.middleware
def timing(event, call_next):
    start = time.time()
    response = call_next(event)
    print(f"Hook took {time.time() - start:.3f}s")
    return response
```

### Testing Utilities

```python
from fasthooks.testing import MockEvent, TestClient

def test_blocks_rm():
    client = TestClient(app)
    response = client.send(MockEvent.bash(command="rm -rf /"))
    assert response.decision == "deny"
```

### Background Tasks

```python
from fasthooks.tasks import task, Tasks

@task
def analyze(code: str) -> str:
    return expensive_analysis(code)

@app.pre_tool("Write")
def on_write(event, tasks: Tasks):
    tasks.add(analyze, event.content)
```

## Code Comparison

### Blocking Dangerous Commands

**cchooks:**
```python
#!/usr/bin/env python3
from cchooks import create_context, PreToolUseContext

c = create_context()
assert isinstance(c, PreToolUseContext)

if c.tool_name == "Bash":
    cmd = c.tool_input.get("command", "")
    if "rm -rf" in cmd:
        c.output.deny(reason="Dangerous command blocked")
    else:
        c.output.allow()
else:
    c.output.allow()
```

**fasthooks:**
```python
#!/usr/bin/env python3
from fasthooks import HookApp, deny

app = HookApp()

@app.pre_tool("Bash")
def check_bash(event):
    if "rm -rf" in event.command:
        return deny("Dangerous command blocked")

if __name__ == "__main__":
    app.run()
```

### Rate Limiting with State

**cchooks:**
```python
#!/usr/bin/env python3
import json
from pathlib import Path
from cchooks import create_context, PreToolUseContext

STATE_FILE = Path.home() / ".hook-state.json"

c = create_context()
assert isinstance(c, PreToolUseContext)

# Manual state management
state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
count = state.get("bash_count", 0) + 1
state["bash_count"] = count
STATE_FILE.write_text(json.dumps(state))

if count > 100:
    c.output.deny(reason=f"Rate limit: {count}/100 commands")
else:
    c.output.allow()
```

**fasthooks:**
```python
#!/usr/bin/env python3
from fasthooks import HookApp, deny
from fasthooks.depends import State

app = HookApp(state_dir="/tmp/hook-state")

@app.pre_tool("Bash")
def rate_limit(event, state: State):
    count = state.get("bash_count", 0) + 1
    state["bash_count"] = count
    state.save()

    if count > 100:
        return deny(f"Rate limit: {count}/100 commands")

if __name__ == "__main__":
    app.run()
```

## When to Use Each

### Use cchooks When:

- You want a **minimal, lightweight** SDK
- You prefer **explicit control** over magic
- You need **tool input modification** (`updated_input`)
- You're building **simple, single-purpose** hooks
- You don't need state management or testing utilities

### Use fasthooks When:

- You want **batteries-included** with DI, state, transcripts
- You prefer **decorator-based** handler registration
- You need **multiple handlers** in one file
- You want **guards and filters** for conditional logic
- You need **testing utilities** for TDD
- You're building **complex, multi-event** hook systems
- You want **blueprints** for modular organization

## Summary

| Aspect | cchooks | fasthooks |
|--------|---------|-----------|
| **Philosophy** | Minimal, explicit | Batteries-included |
| **API Style** | Context factory | Decorators |
| **Learning Curve** | Lower | Slightly higher |
| **Boilerplate** | More | Less |
| **Features** | Core only | Rich ecosystem |
| **Best For** | Simple hooks | Complex systems |
