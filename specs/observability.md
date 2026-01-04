# Observability Spec

**Status**: Draft
**Date**: 2026-01-04

## Overview

Add observability to `HookApp` via a simple observer protocol. Observers receive events about hook lifecycle, handler execution, and decisions. Zero overhead when no observers registered.

## Goals

1. Simple `@app.on_observe` decorator and `app.add_observer()` API
2. Emit events for hook/handler lifecycle and decisions
3. Ship built-in observers: Stdout, File, Metrics, SQLite, Test
4. Zero overhead when unused
5. Foundation for future fasthooks-studio

## Non-Goals

- Verbosity levels (event filtering is sufficient)
- Async observer methods (fire-and-forget; observers handle their own async)
- Identical API to Strategy (similar pattern, not identical)
- Runtime observer removal (add only; restart to change)

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Skip events | Emit `handler_skip` for handlers that didn't run due to early deny | Debugging "why didn't my handler fire" |
| Timing scope | Handler execution only, excludes DI resolution | Clean perf analysis |
| Observer errors | Swallow + log warning | Hook execution must not fail due to broken observer |
| Event sharing | Same instance to all observers | Trust users, document "don't mutate" |
| Payload truncation | 4096 chars default | Balance debug utility vs. size explosion |
| Hook ID | UUID per `app.run()` | Globally unique correlation |
| Async handling | Sync calls only; async observers spawn tasks internally | Simple dispatch, observer's problem |
| Decision events | Emit for every handler (allow/deny/block) | Complete trace |
| Error detail | Type + message only (no traceback) | Compact; enable full logging separately |
| Zero observers | Complete skip of event emission | Zero overhead when unused |
| Observer removal | Add only | Simple; restart to reconfigure |

---

## Event Types

```
hook_start       → Hook invocation begins (hook_id generated)
hook_end         → Hook invocation completes (includes total duration, final decision)
hook_error       → Hook-level error (rare; usually handler_error)

handler_start    → Handler execution begins
handler_end      → Handler execution completes (includes duration, decision)
handler_skip     → Handler would have run but was skipped (early deny from prior handler)
handler_error    → Handler raised exception (type + message)
```

**Event flow for 3 handlers where 2nd denies:**
```
hook_start
  handler_start (handler_1)
  handler_end   (handler_1, decision=allow)
  handler_start (handler_2)
  handler_end   (handler_2, decision=deny)
  handler_skip  (handler_3, reason="early deny")
hook_end (final_decision=deny)
```

---

## Event Model

```python
class ObservabilityEvent(BaseModel):
    """Immutable event passed to observers."""

    # Identity
    event_type: str              # hook_start, handler_end, etc.
    hook_id: str                 # UUID for this hook invocation
    timestamp: datetime

    # Context
    session_id: str              # From Claude Code
    hook_event_name: str         # PreToolUse, PostToolUse, Stop, etc.
    tool_name: str | None        # Bash, Write, etc. (None for Stop)
    handler_name: str | None     # Function name (None for hook-level events)

    # Timing (for *_end events)
    duration_ms: float | None

    # Decision (for handler_end, hook_end)
    decision: str | None         # allow, deny, block
    reason: str | None           # Denial reason if any

    # Content (truncated to 4096 chars)
    input_preview: str | None    # First 4096 chars of hook input

    # Error (for *_error events)
    error_type: str | None       # Exception class name
    error_message: str | None    # str(exception)

    # Skip info (for handler_skip)
    skip_reason: str | None      # "early deny", "guard failed", etc.
```

---

## Observer Context

Observers receive a context object with curated read-only info:

```python
class ObserverContext:
    """Read-only context available to observers."""

    app_name: str                          # HookApp name if set
    session_id: str                        # Current session
    hook_count: int                        # Hooks processed this session
    registered_handlers: list[HandlerInfo] # Name, tool, event type

@dataclass
class HandlerInfo:
    name: str
    event_type: str      # PreToolUse, PostToolUse, Stop
    tool_name: str | None
```

---

## API

### Registration

```python
from fasthooks import HookApp
from fasthooks.observability import FileObserver, StdOutObserver

app = HookApp()

# Class-based observer
app.add_observer(FileObserver("/tmp/hooks.jsonl"))
app.add_observer(StdOutObserver())

# Callback observer (receives all events)
@app.on_observe
def log_all(event: ObservabilityEvent, ctx: ObserverContext):
    print(f"{event.event_type}: {event.handler_name}")

# Callback observer (filtered to specific event)
@app.on_observe("handler_end")
def log_handler_timing(event: ObservabilityEvent, ctx: ObserverContext):
    print(f"{event.handler_name}: {event.duration_ms}ms")
```

### BaseObserver

```python
from fasthooks.observability import BaseObserver, ObservabilityEvent, ObserverContext

class MyObserver(BaseObserver):
    """Override only methods you care about."""

    def on_handler_end(self, event: ObservabilityEvent, ctx: ObserverContext) -> None:
        # Called for each handler_end event
        print(f"{event.handler_name}: {event.decision}")

    # Other methods have no-op defaults:
    # on_hook_start, on_hook_end, on_hook_error
    # on_handler_start, on_handler_end, on_handler_skip, on_handler_error
```

---

## Built-in Observers

### StdOutObserver

```python
from fasthooks.observability import StdOutObserver

app.add_observer(StdOutObserver())

# Output:
# [hook_start] PreToolUse:Bash hook_id=abc123
# [handler_end] check_bash 2.3ms → allow
# [handler_end] log_command 0.8ms → allow
# [hook_end] PreToolUse:Bash 3.5ms → allow
```

### FileObserver

```python
from fasthooks.observability import FileObserver

app.add_observer(FileObserver("/tmp/hooks.jsonl"))

# Writes JSONL, one event per line
# Observer decides buffering strategy (default: flush on hook_end)
```

### MetricsObserver

```python
from fasthooks.observability import MetricsObserver

metrics = MetricsObserver()
app.add_observer(metrics)

# After hooks run:
print(metrics.stats)
# {
#   "total_hooks": 42,
#   "total_handlers": 156,
#   "decisions": {"allow": 150, "deny": 6},
#   "handler_avg_ms": {"check_bash": 2.1, "log_command": 0.5},
#   "errors": 0
# }
```

### SQLiteObserver

```python
from fasthooks.observability import SQLiteObserver

app.add_observer(SQLiteObserver("~/.fasthooks/hooks.db"))

# Foundation for fasthooks-studio
# Schema: hooks, handlers, decisions tables
# Handles buffering internally
```

### TestObserver

```python
from fasthooks.observability import TestObserver

observer = TestObserver()
app.add_observer(observer)

# Run hooks...
client.run(mock_event)

# Assert on captured events
assert len(observer.events) == 5
assert observer.events[0].event_type == "hook_start"
assert observer.events[-1].decision == "allow"

# Filter helpers
assert observer.handler_events("check_bash")[0].duration_ms < 10
assert observer.decisions() == ["allow", "allow"]
```

---

## Implementation

### Package Structure

```
src/fasthooks/observability/
├── __init__.py          # Public exports
├── events.py            # ObservabilityEvent model
├── context.py           # ObserverContext, HandlerInfo
├── base.py              # BaseObserver class
├── observers/
│   ├── __init__.py
│   ├── stdout.py        # StdOutObserver
│   ├── file.py          # FileObserver
│   ├── metrics.py       # MetricsObserver
│   ├── sqlite.py        # SQLiteObserver
│   └── test.py          # TestObserver
└── _emit.py             # Internal emission logic
```

### HookApp Integration

```python
# In app.py

class HookApp:
    def __init__(self, ...):
        self._observers: list[BaseObserver] = []
        self._callback_observers: list[tuple[Callable, str | None]] = []

    def add_observer(self, observer: BaseObserver) -> None:
        self._observers.append(observer)

    def on_observe(self, event_type: str | None = None):
        """Decorator for callback observers."""
        def decorator(func):
            self._callback_observers.append((func, event_type))
            return func

        # Handle @app.on_observe without parens
        if callable(event_type):
            func = event_type
            self._callback_observers.append((func, None))
            return func
        return decorator

    def _emit(self, event: ObservabilityEvent) -> None:
        """Dispatch event to all observers. No-op if none registered."""
        if not self._observers and not self._callback_observers:
            return  # Zero overhead

        ctx = self._build_context()

        for observer in self._observers:
            try:
                method = getattr(observer, f"on_{event.event_type}", None)
                if method:
                    method(event, ctx)
            except Exception as e:
                logger.warning(f"Observer {observer} raised: {e}")

        for callback, filter_type in self._callback_observers:
            if filter_type is None or filter_type == event.event_type:
                try:
                    callback(event, ctx)
                except Exception as e:
                    logger.warning(f"Observer callback raised: {e}")
```

### Instrumentation Points

```python
# In _dispatch() and _run_handler()

def _dispatch(self, data: dict) -> dict:
    hook_id = str(uuid4())
    start = time.perf_counter()

    self._emit(ObservabilityEvent(
        event_type="hook_start",
        hook_id=hook_id,
        # ... other fields
    ))

    try:
        result = self._run_handlers(data, hook_id)
    except Exception as e:
        self._emit(ObservabilityEvent(
            event_type="hook_error",
            hook_id=hook_id,
            error_type=type(e).__name__,
            error_message=str(e),
        ))
        raise
    finally:
        self._emit(ObservabilityEvent(
            event_type="hook_end",
            hook_id=hook_id,
            duration_ms=(time.perf_counter() - start) * 1000,
            decision=result.get("decision", "allow"),
        ))

    return result
```

---

## Migration

### EventLogger Deprecation

```python
# Old (deprecated in v1.x, removed in v2.0)
app = HookApp(log_dir="/tmp/logs")

# New
from fasthooks.observability import FileObserver
app = HookApp()
app.add_observer(FileObserver("/tmp/logs/hooks.jsonl"))
```

Deprecation warning added when `log_dir` is used.

---

## Testing

### Unit Tests

```python
def test_observer_receives_events():
    app = HookApp()
    observer = TestObserver()
    app.add_observer(observer)

    @app.pre_tool("Bash")
    def check(event):
        return None

    client = TestClient(app)
    client.run(MockEvent.bash("ls"))

    assert len(observer.events) == 4  # hook_start, handler_start, handler_end, hook_end
    assert observer.events[0].event_type == "hook_start"
    assert observer.events[-1].decision == "allow"

def test_zero_observers_no_overhead():
    app = HookApp()
    # No observers added

    # _emit should return immediately
    # (verify with mock/spy that event object not created)

def test_observer_error_swallowed():
    app = HookApp()

    class BadObserver(BaseObserver):
        def on_hook_start(self, event, ctx):
            raise RuntimeError("boom")

    app.add_observer(BadObserver())

    @app.pre_tool("Bash")
    def check(event):
        return None

    client = TestClient(app)
    result = client.run(MockEvent.bash("ls"))  # Should not raise
    assert result["decision"] == "allow"
```

---

## Future: Studio Integration

SQLiteObserver provides the foundation for fasthooks-studio:

```
SQLiteObserver writes to:
~/.fasthooks/hooks.db

Schema:
- hooks (hook_id, session_id, event_name, tool_name, started_at, ended_at, final_decision)
- handlers (handler_id, hook_id, name, started_at, ended_at, decision, duration_ms)
- errors (error_id, hook_id, handler_id, error_type, message, timestamp)

fasthooks-studio (separate package) reads this DB and serves UI.
```

This is documented in a separate `specs/studio.md` (future).

---

## Appendix: Observability System Comparison

### Comparison Table

| Aspect | Strategy (current) | HookApp (new spec) | LangChain | ell |
|--------|-------------------|-------------------|-----------|-----|
| **Registration** | `@strategy.on_observe` | `@app.on_observe` + `add_observer()` | `callbacks=[handler]` param | Implicit via `ell.init(store=)` |
| **Observer type** | Callback function only | Callback + BaseObserver class | BaseCallbackHandler class | Store interface only |
| **Event model** | Dict-like events | Pydantic ObservabilityEvent | Separate params per method | Internal models |
| **Third-party extensibility** | Limited (callbacks only) | **Good** (class-based protocol) | **Excellent** (mature ecosystem) | **Poor** (store-only) |
| **Event filtering** | None | `@app.on_observe("event_type")` | `ignore_*` properties | None |
| **Context access** | None | ObserverContext object | run_id, parent_run_id, tags | Config singleton |
| **Async support** | Sync only | Fire-and-forget | Both sync + async handlers | Sync (internal) |
| **Built-in integrations** | File backend only | Stdout, File, Metrics, SQLite, Test | LangSmith, Datadog, Weights&Biases, etc. | SQLite/Postgres only |

### Third-Party Integration Analysis

#### LangChain (most extensible)

```python
# Third party creates handler class
class DatadogCallbackHandler(BaseCallbackHandler):
    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        datadog.increment("llm.calls")

    def on_llm_end(self, response, *, run_id, **kwargs):
        datadog.timing("llm.duration", ...)

# User registers
chain.invoke(input, config={"callbacks": [DatadogCallbackHandler()]})
```

**Why it works**:
- Clear protocol (BaseCallbackHandler)
- Rich context (run_id, parent_run_id, tags, metadata)
- Event-specific methods (`on_llm_start`, `on_chain_end`, etc.)
- Mature ecosystem (dozens of integrations exist)

#### ell (least extensible)

```python
# Only option: implement Store interface
class MyStore(Store):
    def write_lmp(self, lmp, uses_ids): ...
    def write_invocation(self, invocation, consumes): ...
    # 20+ methods required

ell.init(store=MyStore())
```

**Limitation**: Must implement entire storage interface. No callback hooks for third-party integrations like Datadog - you'd need to fork ell.

#### HookApp (new spec) - Good Balance

```python
# Third party creates observer
class DatadogObserver(BaseObserver):
    def on_handler_end(self, event: ObservabilityEvent, ctx: ObserverContext):
        datadog.increment("fasthooks.handlers")
        datadog.timing("fasthooks.handler_duration", event.duration_ms)

# User registers
app.add_observer(DatadogObserver())
```

**Why it will work**:
- Clear protocol (BaseObserver with no-op defaults)
- Rich context (ObserverContext with handler registry)
- Event-specific methods (`on_hook_start`, `on_handler_end`, etc.)
- Pydantic event model (easy to serialize/transform)

### What We Get From LangChain Patterns

| Pattern | Adopted? | Notes |
|---------|----------|-------|
| Base class with no-ops | ✓ | `BaseObserver` - override what you need |
| Event filtering | ✓ | `@app.on_observe("handler_end")` |
| Context propagation | ✓ | `ObserverContext` with session/handler info |
| run_id correlation | ✓ | `hook_id` per invocation |
| parent_run_id | Partial | Could add for nested scenarios |
| tags/metadata inheritance | ✗ | Not needed for hooks (single invocation) |
| 3-level registration | ✗ | App-level only (simpler) |
| Async handler support | Partial | Fire-and-forget (observer handles async) |

### Adding a Third-Party Observer (Example)

```python
# fasthooks-langsmith (hypothetical package)
from fasthooks.observability import BaseObserver, ObservabilityEvent
from langsmith import Client

class LangSmithObserver(BaseObserver):
    def __init__(self, project: str):
        self.client = Client()
        self.project = project

    def on_hook_start(self, event, ctx):
        self.client.create_run(
            name=f"{event.hook_event_name}:{event.tool_name}",
            run_type="chain",
            project_name=self.project,
            id=event.hook_id,
        )

    def on_hook_end(self, event, ctx):
        self.client.update_run(
            run_id=event.hook_id,
            end_time=event.timestamp,
            outputs={"decision": event.decision},
        )

# User
from fasthooks_langsmith import LangSmithObserver
app.add_observer(LangSmithObserver(project="my-hooks"))
```

**Verdict**: The new spec enables third-party integrations as easily as LangChain, without the complexity of ell's store-only approach.

---

## References

### fasthooks Code
- HookApp: `src/fasthooks/app.py`
- Strategy observability: `src/fasthooks/strategies/base.py:79-250`
- Current EventLogger: `src/fasthooks/logging.py`

### Inspiration
- LangChain callbacks: `libs/core/langchain_core/callbacks/base.py`
- ell-studio: `/tmp/ell/src/ell/lmp/_track.py` (instrumentation pattern)
