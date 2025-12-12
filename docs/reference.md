# API Reference

Quick reference for fasthooks classes and functions.

## HookApp

Main application class.

```python
from fasthooks import HookApp

app = HookApp(
    state_dir=None,    # Directory for persistent state files
    log_dir=None,      # Directory for JSONL event logs
    log_level="INFO",  # Logging verbosity
)
```

### Decorators

```python
# Tool events
@app.pre_tool("Bash")           # Before tool executes
@app.pre_tool("*")              # All tools
@app.post_tool("Write")         # After tool executes
@app.permission_request("Bash") # Permission dialog shown

# Lifecycle events
@app.on_stop()                  # Claude stops
@app.on_subagent_stop()         # Subagent stops
@app.on_session_start()         # Session starts
@app.on_session_end()           # Session ends
@app.on_notification()          # Notification sent
@app.on_pre_compact()           # Before compaction
@app.on_user_prompt_submit()    # User submits prompt
```

### Guards

```python
@app.pre_tool("Bash", when=lambda e: "sudo" in e.command)
def check_sudo(event):
    return deny("No sudo")
```

### Methods

```python
app.run()                       # Run the hook (reads stdin, writes stdout)
app.include(blueprint)          # Include handlers from a Blueprint
```

## Responses

```python
from fasthooks import allow, deny, block

# Allow the action
allow()
allow(system_message="Warning: sensitive file")

# Deny the action (PreToolUse, PermissionRequest)
deny("Reason shown to Claude")
deny("Reason", system_message="Warning to user")

# Block stopping (Stop, SubagentStop)
block("Reason to continue")
```

## Events

### Base Fields (all events)

```python
event.session_id        # str
event.cwd               # str
event.permission_mode   # str
event.transcript_path   # str | None
event.hook_event_name   # str
```

### Tool Events

```python
event.tool_name         # str
event.tool_input        # dict
event.tool_use_id       # str
event.tool_response     # dict | None (PostToolUse only)
```

### Typed Tool Properties

| Tool | Properties |
|------|------------|
| Bash | `command`, `description`, `timeout` |
| Write | `file_path`, `content` |
| Edit | `file_path`, `old_string`, `new_string` |
| Read | `file_path`, `offset`, `limit` |
| Grep | `pattern`, `path` |
| Glob | `pattern`, `path` |

### Lifecycle Events

| Event | Properties |
|-------|------------|
| Stop | `stop_hook_active` |
| SessionStart | `source` |
| SessionEnd | `reason` |
| PreCompact | `trigger`, `custom_instructions` |
| UserPromptSubmit | `prompt` |
| Notification | `message`, `notification_type` |

## Testing

```python
from fasthooks.testing import MockEvent, TestClient

# Create mock events
MockEvent.bash(command="ls")
MockEvent.write(file_path="/tmp/f.txt", content="...")
MockEvent.stop()

# Test client
client = TestClient(app)
response = client.send(MockEvent.bash(command="rm -rf /"))
assert response.decision == "deny"
```

## Dependency Injection

```python
from fasthooks.depends import State, Transcript

@app.pre_tool("Bash")
def handler(event, state: State, transcript: Transcript):
    # state: persistent dict across hook calls
    state["count"] = state.get("count", 0) + 1

    # transcript: parsed conversation history
    stats = transcript.stats
    print(f"Tokens: {stats.total_tokens}")
```

## Blueprint

```python
from fasthooks import Blueprint

security = Blueprint()

@security.pre_tool("Bash")
def check(event):
    ...

# In main app
app.include(security)
```
