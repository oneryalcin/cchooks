# Dependency Injection

fasthooks automatically injects dependencies into your handlers based on type hints. This gives you access to conversation history, persistent state, and more.

## Why Dependency Injection?

Without DI, your handler only sees the **current event**:

```python
@app.pre_tool("Bash")
def check(event):
    # Only know about THIS bash command
    # No context about what happened before
    pass
```

With DI, you get **full conversation context**:

```python
@app.pre_tool("Bash")
def check(event, transcript: Transcript, state: State):
    # transcript: Full conversation history, token counts, all tool calls
    # state: Persistent dict that survives between hook invocations
    pass
```

## Available Dependencies

### Transcript

Access the full conversation history. **Lazy-loaded and cached** - no performance penalty if unused.

```python
from fasthooks.depends import Transcript

@app.pre_tool("Bash")
def check(event, transcript: Transcript):
    stats = transcript.stats

    # Token usage
    print(f"Input tokens: {stats.input_tokens}")
    print(f"Output tokens: {stats.output_tokens}")
    print(f"Cache read: {stats.cache_read_tokens}")

    # Tool usage
    print(f"Tool calls: {stats.tool_calls}")  # {"Bash": 5, "Write": 2}
    print(f"Files read: {stats.files_read_count}")
    print(f"Files written: {stats.files_written_count}")

    # Session info
    print(f"Duration: {stats.duration_seconds}s")
    print(f"Compacts: {stats.compact_count}")
```

#### Transcript Properties

| Property | Type | Description |
|----------|------|-------------|
| `stats` | `TranscriptStats` | Aggregated statistics |
| `messages` | `list[dict]` | All user/assistant messages |
| `last_assistant_message` | `str` | Text of last assistant response |
| `bash_commands` | `list[str]` | All bash commands in session |

#### TranscriptStats Fields

| Field | Type | Description |
|-------|------|-------------|
| `input_tokens` | `int` | Total input tokens used |
| `output_tokens` | `int` | Total output tokens used |
| `cache_read_tokens` | `int` | Tokens read from cache |
| `cache_creation_tokens` | `int` | Tokens added to cache |
| `tool_calls` | `dict[str, int]` | Tool name → call count |
| `files_read_count` | `int` | Unique files read |
| `files_written_count` | `int` | Unique files written |
| `duration_seconds` | `float` | Session duration |
| `compact_count` | `int` | Number of context compactions |
| `message_counts` | `dict[str, int]` | Message type counts |

### State

Persistent dict that survives between hook invocations. Backed by a JSON file.

```python
from fasthooks.depends import State

# Enable state by configuring state_dir
app = HookApp(state_dir="/tmp/fasthooks-state")

@app.pre_tool("Bash")
def rate_limit(event, state: State):
    # Count commands per session
    count = state.get("bash_count", 0) + 1
    state["bash_count"] = count
    state.save()  # Persist to disk

    if count > 100:
        return deny("Too many bash commands in this session")
```

#### State Methods

| Method | Description |
|--------|-------------|
| `state.save()` | Persist to disk |
| `state.get(key, default)` | Get with default |
| `state[key] = value` | Set value |
| `key in state` | Check existence |

State is scoped to the session - each session gets its own JSON file.

## Use Cases

### Rate Limiting

```python
@app.pre_tool("Bash")
def rate_limit(event, state: State):
    count = state.get("commands", 0) + 1
    state["commands"] = count
    state.save()

    if count > 50:
        return deny(f"Rate limit: {count}/50 commands used")
```

### Token Budget

```python
@app.on_stop()
def check_budget(event, transcript: Transcript):
    stats = transcript.stats
    total = stats.input_tokens + stats.output_tokens

    if total > 100_000:
        return allow(system_message=f"Warning: {total:,} tokens used")
```

### Command History Analysis

```python
@app.pre_tool("Bash")
def no_repeated_failures(event, transcript: Transcript):
    # Check if same command failed recently
    recent_commands = transcript.bash_commands[-5:]
    if event.command in recent_commands:
        return deny("This command was already tried recently")
```

### Audit Logging

```python
@app.post_tool("Write")
def audit_writes(event, state: State):
    writes = state.get("writes", [])
    writes.append({
        "file": event.file_path,
        "time": datetime.now().isoformat(),
    })
    state["writes"] = writes
    state.save()
```

### Context-Aware Decisions

```python
@app.pre_tool("Bash")
def context_check(event, transcript: Transcript):
    stats = transcript.stats

    # More permissive if user has been working a while
    if stats.duration_seconds > 3600:  # 1 hour
        return allow()

    # Stricter for new sessions
    if "rm" in event.command:
        return deny("Destructive commands require established session")
```

## How It Works

1. fasthooks inspects your handler's type hints
2. For each `Transcript` or `State` parameter, it creates the dependency
3. Dependencies are passed when calling your handler

```python
# fasthooks sees: def check(event, transcript: Transcript, state: State)
# And calls: check(event, transcript=Transcript(...), state=State(...))
```

Dependencies are created fresh for each hook invocation, but:
- `Transcript` lazily loads and caches parsed data
- `State` loads from disk and persists on `.save()`
