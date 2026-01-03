# Blueprints

Blueprints let you organize handlers into reusable, composable modules.

## Why Blueprints?

As your hooks grow, a single file becomes hard to manage:

```python
# hooks.py - getting messy!
@app.pre_tool("Bash")
def security_check(event): ...

@app.pre_tool("Write")
def security_write(event): ...

@app.pre_tool("Bash")
def logging_bash(event): ...

@app.post_tool("Write")
def logging_write(event): ...

@app.on_stop()
def cleanup(event): ...
```

Blueprints let you **split by concern**:

```
hooks/
├── __init__.py      # Main app
├── security.py      # Security rules
├── logging.py       # Audit logging
└── cleanup.py       # Session cleanup
```

## Basic Usage

```python
# security.py
from fasthooks import Blueprint, deny

security = Blueprint("security")

@security.pre_tool("Bash")
def no_dangerous_commands(event):
    if "rm -rf" in event.command:
        return deny("Dangerous command blocked")

@security.pre_tool("Write")
def protect_sensitive_files(event):
    if ".env" in event.file_path:
        return deny("Cannot modify .env files")
```

```python
# hooks.py
from fasthooks import HookApp
from security import security

app = HookApp()
app.include(security)

if __name__ == "__main__":
    app.run()
```

## Blueprint API

Blueprints support the same decorators as HookApp:

```python
from fasthooks import Blueprint

bp = Blueprint("my-blueprint")

# Tool events
@bp.pre_tool("Bash")
def check(event): ...

@bp.post_tool("Write")
def after(event): ...

@bp.on_permission("Bash")
def perm(event): ...

# Lifecycle events
@bp.on_stop()
def stop(event): ...

@bp.on_session_start()
def start(event): ...
```

## Real-World Examples

### Security Blueprint

```python
# blueprints/security.py
from fasthooks import Blueprint, deny

security = Blueprint("security")

DANGEROUS_PATTERNS = [
    "rm -rf",
    "mkfs",
    "> /dev/sd",
    "dd if=",
]

PROTECTED_PATHS = [
    ".env",
    ".ssh",
    "credentials",
    "secrets",
]

@security.pre_tool("Bash")
def block_dangerous_commands(event):
    for pattern in DANGEROUS_PATTERNS:
        if pattern in event.command:
            return deny(f"Blocked: contains '{pattern}'")

@security.pre_tool("Write")
def protect_files(event):
    for path in PROTECTED_PATHS:
        if path in event.file_path:
            return deny(f"Cannot write to {path}")

@security.pre_tool("Edit")
def protect_edits(event):
    for path in PROTECTED_PATHS:
        if path in event.file_path:
            return deny(f"Cannot edit {path}")
```

### Logging Blueprint

```python
# blueprints/logging.py
from fasthooks import Blueprint
from fasthooks.depends import State
from datetime import datetime

logging = Blueprint("logging")

@logging.post_tool("Bash")
def log_bash(event, state: State):
    logs = state.get("bash_log", [])
    logs.append({
        "command": event.command,
        "time": datetime.now().isoformat(),
    })
    state["bash_log"] = logs[-100:]  # Keep last 100
    state.save()

@logging.post_tool("Write")
def log_write(event, state: State):
    logs = state.get("write_log", [])
    logs.append({
        "file": event.file_path,
        "time": datetime.now().isoformat(),
    })
    state["write_log"] = logs[-100:]
    state.save()
```

### Rate Limiting Blueprint

```python
# blueprints/rate_limit.py
from fasthooks import Blueprint, deny
from fasthooks.depends import State

rate_limit = Blueprint("rate-limit")

LIMITS = {
    "Bash": 100,
    "Write": 50,
    "Edit": 50,
}

@rate_limit.pre_tool("*")
def check_rate(event, state: State):
    tool = event.tool_name
    if tool not in LIMITS:
        return

    key = f"rate_{tool}"
    count = state.get(key, 0) + 1
    state[key] = count
    state.save()

    limit = LIMITS[tool]
    if count > limit:
        return deny(f"Rate limit exceeded: {count}/{limit} {tool} calls")
```

### Composing Multiple Blueprints

```python
# hooks.py
from fasthooks import HookApp
from blueprints.security import security
from blueprints.logging import logging
from blueprints.rate_limit import rate_limit

app = HookApp(state_dir="/tmp/fasthooks-state")

# Include all blueprints
app.include(security)
app.include(logging)
app.include(rate_limit)

# Add app-specific handlers
@app.on_stop()
def final_check(event):
    ...

if __name__ == "__main__":
    app.run()
```

## When to Use Blueprints

| Scenario | Blueprint? |
|----------|------------|
| Single file with <10 handlers | No |
| Handlers grouped by concern (security, logging) | Yes |
| Reusable rules across projects | Yes |
| Team members working on different features | Yes |
| Conditionally enabling feature sets | Yes |

## Blueprint vs Middleware

- **Blueprints**: Organize handlers by feature/concern
- **Middleware**: Cross-cutting logic that wraps ALL handlers

Use blueprints when you want **modular organization**.
Use middleware when you want **universal behavior** (timing, logging every call).
