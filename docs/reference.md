# API Reference

Quick reference for fasthooks classes and functions.

## HookApp

Main application class.

```python
from fasthooks import HookApp

app = HookApp(
    state_dir=None,       # Directory for persistent state files
    log_dir=None,         # Directory for JSONL event logs
    log_level="INFO",     # Logging verbosity
    task_backend=None,    # Backend for background tasks (default: InMemoryBackend)
)
```

### Decorators

```python
# Tool events
@app.pre_tool("Bash")           # Before tool executes
@app.pre_tool("*")              # All tools
@app.post_tool("Write")         # After tool executes
@app.on_permission("Bash")      # Permission dialog shown

# Lifecycle events
@app.on_stop()                  # Claude stops
@app.on_subagent_stop()         # Subagent stops
@app.on_session_start()         # Session starts
@app.on_session_end()           # Session ends
@app.on_notification()          # Notification sent
@app.on_pre_compact()           # Before compaction
@app.on_prompt()                # User submits prompt
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
allow(message="Warning: sensitive file")

# Deny the action (PreToolUse, PermissionRequest)
deny("Reason shown to Claude")
deny("Reason", interrupt=True)  # Stop Claude entirely

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
from fasthooks.tasks import Tasks

@app.pre_tool("Bash")
def handler(event, state: State, transcript: Transcript):
    # state: persistent dict across hook calls
    state["count"] = state.get("count", 0) + 1

    # transcript: parsed conversation history
    stats = transcript.stats
    print(f"Tokens: {stats.total_tokens}")

@app.pre_tool("Write")
def with_tasks(event, tasks: Tasks):
    # tasks: spawn background work + retrieve completed results
    pass
```

## Background Tasks

### Task Definition

```python
from fasthooks.tasks import task

@task
def simple_task(x: int) -> int:
    return x * 2

@task(ttl=600, priority=5)
def with_options(query: str) -> str:
    return search(query)

@task(transform=lambda r: r[:100])
def with_transform() -> str:
    return long_string()
```

### Tasks (recommended)

```python
from fasthooks.tasks import Tasks

@app.pre_tool("Write")
def handler(event, tasks: Tasks):
    # Default key is the function name; use explicit key for concurrent calls
    tasks.add(my_task, arg1)
    tasks.add(other_task, data, key="other:1")

    # Pop by function reference (no string typos)
    result = tasks.pop(my_task)
```

### BackgroundTasks

```python
from fasthooks.tasks import BackgroundTasks

@app.pre_tool("Write")
def handler(event, tasks: BackgroundTasks):
    tasks.add(my_task, arg1, key="unique-key")
    tasks.add(other_task, data, key="other", ttl=600)
    tasks.cancel("unique-key")
    tasks.cancel_all()
```

### PendingResults

```python
from fasthooks.tasks import PendingResults

@app.on_prompt()
def handler(event, pending: PendingResults):
    result = pending.pop("key")              # Pop completed result
    results = pending.pop_all()              # Pop all completed
    errors = pending.pop_errors()            # Pop failed as [(key, error), ...]
    task_result = pending.get("key")         # Get TaskResult without removing
    has_results = pending.has("key")         # Check if ready

    # Async waiting
    result = await pending.wait("key", timeout=10.0)
    results = await pending.wait_all(["k1", "k2"], timeout=30.0)
    key, result = await pending.wait_any(["k1", "k2"])
```

### TaskResult

```python
from fasthooks.tasks import TaskResult, TaskStatus

result: TaskResult
result.id           # str - Unique task ID
result.session_id   # str - Session that created this task
result.key          # str - User-provided key
result.status       # TaskStatus - PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
result.value        # Any - Result value (if completed)
result.error        # Exception | None - Error (if failed)
result.is_finished  # bool - True if done (success, fail, or cancelled)
```

## Claude Agent SDK Integration

Requires: `pip install fasthooks[claude]`

### ClaudeAgent

```python
from fasthooks.contrib.claude import ClaudeAgent

agent = ClaudeAgent(
    model="haiku",                    # haiku, sonnet, opus
    system_prompt="You are helpful.",
    allowed_tools=["Read", "Grep"],
    max_turns=5,
    max_budget_usd=0.10,
    cwd="/path/to/project",
)

# Query Claude
response = await agent.query("What is 2+2?")

# Override per-query
response = await agent.query(
    "Analyze this",
    system_prompt="Override prompt",
    max_turns=3,
)

# As context manager
async with ClaudeAgent(model="haiku") as agent:
    response = await agent.query("Hello")
```

### @agent_task Decorator

```python
from fasthooks.contrib.claude import ClaudeAgent, agent_task

@agent_task(
    model="haiku",
    system_prompt="You review code.",
    allowed_tools=["Read"],
    ttl=600,
    priority=5,
)
async def review_code(agent: ClaudeAgent, code: str) -> str:
    return await agent.query(f"Review:\n{code}")

# Use with Tasks
@app.pre_tool("Write")
def on_write(event, tasks: Tasks):
    tasks.add(review_code, event.content)
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
