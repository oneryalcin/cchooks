# Tutorial

Learn fasthooks step by step.

## Overview

This tutorial covers:

1. **[Events](events.md)** - Understanding hook events and typed tool events
2. **[Responses](responses.md)** - Using `allow()`, `deny()`, and `block()`
3. **[Dependencies](dependencies.md)** - Inject State and Transcript into handlers
4. **[Transcript](transcript.md)** - Context engineering and memory editing
5. **[Background Tasks](background-tasks.md)** - Spawn async work that feeds back later
6. **[Blueprints](blueprints.md)** - Organize handlers into reusable modules
7. **[Middleware](middleware.md)** - Cross-cutting concerns (timing, logging)
8. **[Testing](testing.md)** - Writing tests with `MockEvent` and `TestClient`

## Core Concepts

### HookApp

The main class that registers and runs your handlers:

```python
from fasthooks import HookApp

app = HookApp()

@app.pre_tool("Bash")
def my_handler(event):
    ...

if __name__ == "__main__":
    app.run()
```

### Decorators

Register handlers for different hook events:

| Decorator | When it runs |
|-----------|--------------|
| `@app.pre_tool("Bash")` | Before a tool executes |
| `@app.post_tool("Write")` | After a tool executes |
| `@app.on_stop()` | When Claude stops |
| `@app.on_session_start()` | When a session starts |

### Typed Events

Each tool has typed event with autocomplete:

```python
@app.pre_tool("Bash")
def check(event):
    print(event.command)      # str
    print(event.description)  # str | None
    print(event.timeout)      # int | None
```

### Guards

Filter which events trigger your handler:

```python
@app.pre_tool("Bash", when=lambda e: "sudo" in e.command)
def check_sudo(event):
    return deny("No sudo allowed")
```

## Advanced Topics

- **[Dependencies](dependencies.md)** - Access conversation history and persistent state
- **[Background Tasks](background-tasks.md)** - Async work with Claude sub-agents
- **[Blueprints](blueprints.md)** - Split handlers into reusable modules
- **[Middleware](middleware.md)** - Add timing, logging, error handling to all handlers
