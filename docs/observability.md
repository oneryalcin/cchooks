# Observability

Trace what your hooks are doing. See every event, every handler, every decision.

## Why Observability?

Hooks run as subprocesses - you can't just add print statements and see them. Observability gives you:

- **Debugging** - See exactly what your hooks receive and respond
- **Timing** - Know which handlers are slow
- **Logging** - Keep a record of all hook activity
- **Studio integration** - Feed data to the visual debugger

## Quick Start

Add an observer to your app:

```python
from fasthooks import HookApp
from fasthooks.observability import FileObserver

app = HookApp()
app.add_observer(FileObserver())  # Writes to ~/.fasthooks/hooks.jsonl

@app.pre_tool("Bash")
def check_bash(event):
    if "rm -rf" in event.command:
        return deny("Dangerous")

app.run()
```

Now every hook event is logged:

```bash
tail -f ~/.fasthooks/hooks.jsonl
```

```json
{"event_type": "hook_start", "hook_id": "abc-123", "tool_name": "Bash", ...}
{"event_type": "handler_start", "handler_name": "check_bash", ...}
{"event_type": "handler_end", "handler_name": "check_bash", "decision": "allow", "duration_ms": 0.5, ...}
{"event_type": "hook_end", "hook_id": "abc-123", "duration_ms": 12.3, ...}
```

## Built-in Observers

### FileObserver

Writes JSONL to a file. Great for debugging and log aggregation.

```python
from fasthooks.observability import FileObserver

# Default: ~/.fasthooks/hooks.jsonl
app.add_observer(FileObserver())

# Custom path
app.add_observer(FileObserver("/var/log/fasthooks.jsonl"))

# Per-session files
app.add_observer(FileObserver("~/.fasthooks/sessions/{session_id}.jsonl"))
```

**Features:**

- Errors are swallowed (won't crash your hooks)
- Appends to existing files
- Creates directories automatically
- Supports `{session_id}` placeholder in path

### SQLiteObserver

Writes to SQLite. Powers the studio visual debugger.

```python
from fasthooks.observability import SQLiteObserver

# Default: ~/.fasthooks/studio.db
app.add_observer(SQLiteObserver())

# Custom path
app.add_observer(SQLiteObserver("/tmp/debug.db"))
```

**Features:**

- Errors propagate (fail-fast for debugging)
- Indexed for fast queries
- Works with `fasthooks studio`

### EventCapture

Captures events in memory. Perfect for testing.

```python
from fasthooks.observability import EventCapture

capture = EventCapture()
app.add_observer(capture)

# Run your hook...
app.run()

# Check what happened
assert len(capture.events) == 4
assert capture.events[0].event_type == "hook_start"
assert capture.events[-1].event_type == "hook_end"
```

## Event Types

Every hook invocation produces these events:

| Event Type | When | Fields |
|------------|------|--------|
| `hook_start` | Hook begins | `hook_id`, `session_id`, `tool_name`, `hook_event_name` |
| `handler_start` | Handler begins | `handler_name` |
| `handler_end` | Handler completes | `handler_name`, `decision`, `duration_ms`, `reason` |
| `handler_skip` | Handler skipped (guard failed) | `handler_name`, `skip_reason` |
| `handler_error` | Handler threw exception | `handler_name`, `error_type`, `error_message` |
| `hook_end` | Hook completes | `duration_ms`, `decision` |
| `hook_error` | Hook failed | `error_type`, `error_message` |

## Callback-Style Observability

For simple one-off logging, use `@app.on_observe`:

```python
@app.on_observe("hook_end")
def log_slow_hooks(event):
    if event.duration_ms > 100:
        print(f"Slow hook: {event.hook_id} took {event.duration_ms}ms")

@app.on_observe("handler_end")
def log_denies(event):
    if event.decision == "deny":
        print(f"Denied: {event.handler_name} - {event.reason}")

@app.on_observe()  # All events
def log_everything(event):
    print(f"{event.event_type}: {event.handler_name or event.hook_id}")
```

## Building Custom Observers

Extend `BaseObserver` for full control:

```python
from fasthooks.observability import BaseObserver, HookObservabilityEvent

class SlackObserver(BaseObserver):
    """Send denials to Slack."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def on_handler_end(self, event: HookObservabilityEvent) -> None:
        if event.decision == "deny":
            self._send_slack(f"Hook denied: {event.reason}")

    def _send_slack(self, message: str) -> None:
        # Your Slack webhook logic
        pass

# Use it
app.add_observer(SlackObserver("https://hooks.slack.com/..."))
```

**Available hooks:**

```python
class BaseObserver:
    def on_hook_start(self, event): ...
    def on_hook_end(self, event): ...
    def on_hook_error(self, event): ...
    def on_handler_start(self, event): ...
    def on_handler_end(self, event): ...
    def on_handler_skip(self, event): ...
    def on_handler_error(self, event): ...
```

## HookObservabilityEvent

Every observer receives `HookObservabilityEvent` objects:

```python
@dataclass
class HookObservabilityEvent:
    event_type: str          # hook_start, handler_end, etc.
    hook_id: str             # UUID for this hook invocation
    timestamp: datetime      # When the event occurred
    session_id: str          # Claude session ID

    # Context (may be None depending on event type)
    hook_event_name: str | None   # PreToolUse, PostToolUse, Stop, etc.
    tool_name: str | None         # Bash, Write, Edit, etc.
    handler_name: str | None      # Your function name

    # Timing
    duration_ms: float | None     # Handler/hook duration

    # Decision
    decision: str | None          # allow, deny, block
    reason: str | None            # Denial reason

    # Error
    error_type: str | None        # Exception class name
    error_message: str | None     # Exception message

    # Skip
    skip_reason: str | None       # Why handler was skipped

    # Input preview (truncated JSON of tool input)
    input_preview: str | None
```

## Multiple Observers

Add as many observers as you need:

```python
app.add_observer(FileObserver())           # Log to file
app.add_observer(SQLiteObserver())         # Feed studio
app.add_observer(SlackObserver(webhook))   # Alert on denials
```

## Performance

Observers run synchronously in the hook process. Keep them fast:

- **FileObserver**: ~1ms per event (buffered writes)
- **SQLiteObserver**: ~1ms per event (per-write connection)
- **Custom**: Avoid network calls in hot paths; batch or queue instead

## Best Practices

1. **Use SQLiteObserver for debugging** - It powers the studio UI
2. **Use FileObserver for production** - Errors don't crash hooks
3. **Use EventCapture for testing** - Assert on captured events
4. **Keep observers fast** - Async/queue heavy work
5. **Filter events** - Use `@app.on_observe("handler_end")` not `@app.on_observe()`

## Next Steps

- [Studio](studio.md) - Visual debugger that uses SQLiteObserver
- [Testing](tutorial/testing.md) - Use EventCapture in tests
