# fasthooks

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
- **Blueprints** - Compose handlers from multiple modules
- **Middleware** - Cross-cutting concerns like timing and logging
- **Guards** - `@app.pre_tool("Bash", when=lambda e: "sudo" in e.command)`
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

### 1. Create a hooks project

```bash
fasthooks init my-hooks
cd my-hooks
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

### 3. Configure Claude Code

Add to your `settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [{"command": "python /path/to/hooks.py"}],
    "Stop": [{"command": "python /path/to/hooks.py"}]
  }
}
```

## API Reference

### Responses

```python
from fasthooks import allow, deny, block

return allow()                              # Proceed
return allow(message="Approved by hook")    # With message
return deny("Reason shown to Claude")       # Block tool
return block("Continue working on X")       # For Stop hooks
```

### Tool Decorators

```python
@app.pre_tool("Bash")                    # Single tool
@app.pre_tool("Write", "Edit")           # Multiple tools
@app.post_tool("Bash")                   # After execution
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

## CLI

```bash
# Initialize a new project
fasthooks init my-hooks

# Show help
fasthooks --help

# Run hooks (called by Claude Code)
fasthooks run hooks.py
```

## License

MIT
