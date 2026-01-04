# Observability Spec

**Status**: Implemented
**Date**: 2026-01-04
**Branch**: `feature/strategies`

---

## Philosophy

**John Carmack, not Java Enterprise.** Minimal viable observability that enables future extensibility without over-engineering today.

- Zero overhead when unused (complete skip if no observers)
- Simple callback API for quick debugging
- Class-based API for third-party integrations
- Pydantic for DX (autocomplete, validation) with raw dict escape hatch (`.model_dump()`)
- Ship only what we need now; defer SQLiteObserver to studio spec

---

## Overview

Add observability to `HookApp` via a simple observer protocol. Observers receive events about hook lifecycle, handler execution, and decisions.

**What we're building (v1):**
- `HookObservabilityEvent` - Pydantic model for all events
- `BaseObserver` - Class with no-op defaults for third-party extensibility
- `@app.on_observe` - Decorator for callback-style observers
- `app.add_observer()` - Method for class-based observers
- `FileObserver` - Built-in for file-based logging (JSONL)
- `EventCapture` - Built-in for testing

**What we're NOT building (deferred):**
- `ObserverContext` - Dropped; not needed for v1 (see Decisions)
- `MetricsObserver` - Add when users need aggregated stats
- `SQLiteObserver` - Moves to `specs/studio.md`
- `StdOutObserver` - Cannot use stdout/stderr in hooks (see Built-in Observers section)

---

## Decisions

All design decisions with rationale. No implicit knowledge.

| Decision | Choice | Rationale | Alternatives Considered |
|----------|--------|-----------|------------------------|
| Event model | Pydantic `HookObservabilityEvent` | Autocomplete, validation, clear schema. Users can `.model_dump()` for raw dict. | Plain dict (flexible but no DX) |
| Observer registration | Both `@app.on_observe` callback AND `app.add_observer(class)` | Flexibility. Quick debugging vs structured third-party integrations. | Callbacks only (simpler but third parties reinvent filtering) |
| BaseObserver | Class with no-op default methods | Third parties override only what they need. IDE shows available methods. | Protocol/ABC (more strict, more boilerplate) |
| ObserverContext | **DROPPED for v1** | Event already contains session_id, handler_name, tool_name. Only extra was `registered_handlers` list - not needed for v1. Add later if dashboards need it. | Keep (more info to observers) |
| Skip events | Emit `handler_skip` for handlers that didn't run | Debugging "why didn't my handler fire" is common. | Silent skip (simpler but harder to debug) |
| Timing scope | Handler execution only, excludes DI resolution | Clean perf analysis. DI time is framework overhead, not handler perf. | Include DI (shows true cost but conflates concerns) |
| Observer errors | Swallow + log warning | Hook execution must not fail due to broken observer. | Propagate (surfaces bugs but breaks hooks) |
| Event sharing | Same instance to all observers | Performance. Document "don't mutate". Trust users. | Copy per observer (safe but memory cost) |
| Payload truncation | 4096 chars default | Balance debug utility vs size explosion. Covers most commands. | 256 (too small), unlimited (dangerous) |
| Hook ID | UUID per `app.run()` | Globally unique correlation across sessions. | Counter (not unique across sessions) |
| Async handling | Sync dispatch; async observers spawn tasks internally | Simple dispatch logic. Observer's problem to handle async. | Await async observers (complex dispatch) |
| Decision events | Emit for every handler (allow/deny/block) | Complete trace. Know exactly what each handler decided. | Only deny/block (less noise but incomplete) |
| Error detail | Type + message only (no traceback) | Compact. Users can enable full logging separately. | Full traceback (verbose) |
| Zero observers | Complete skip of event emission | Zero overhead when observability unused. | Always build events (consistent but wasteful) |
| Observer removal | Add only; restart to reconfigure | Simple. No need to handle removal during iteration. | Add + remove (more control, more edge cases) |
| Built-in observers | FileObserver + EventCapture only | File-based logging (stdout/stderr unusable in hooks). EventCapture for tests. | StdOutObserver (breaks hook protocol) |
| SQLiteObserver | Deferred to studio spec | Studio needs it, not core observability. Keep specs focused. | Include in v1 (scope creep) |
| Decorator name | `@app.on_observe` | Matches Strategy pattern. Familiar. | `@app.observe` (shorter), `@app.on_event` (generic) |
| Package location | `fasthooks.observability` | Extends existing `src/fasthooks/observability/` directory. | Top-level (clutters fasthooks namespace) |
| EventLogger | Deprecate in v1, remove in v2 | One way to do observability. Clean migration path. | Keep both (confusing, two systems) |

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

**Event flow example (3 handlers, 2nd denies):**

```
hook_start
  handler_start (handler_1)
  handler_end   (handler_1, decision=allow)
  handler_start (handler_2)
  handler_end   (handler_2, decision=deny, reason="blocked dangerous command")
  handler_skip  (handler_3, skip_reason="early deny from handler_2")
hook_end (final_decision=deny, duration_ms=15.2)
```

---

## Event Model

```python
# src/fasthooks/observability/events.py

from datetime import datetime, UTC
from pydantic import BaseModel, Field

class HookObservabilityEvent(BaseModel):
    """Event passed to observers. Immutable by convention (don't mutate)."""

    # Identity
    event_type: str              # hook_start, handler_end, etc.
    hook_id: str                 # UUID for this hook invocation
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Context
    session_id: str              # From Claude Code input
    hook_event_name: str         # PreToolUse, PostToolUse, Stop, etc.
    tool_name: str | None        # Bash, Write, etc. (None for Stop/lifecycle)
    handler_name: str | None     # Function name (None for hook-level events)

    # Timing (for *_end events only)
    duration_ms: float | None    # Handler execution time (excludes DI)

    # Decision (for handler_end, hook_end)
    decision: str | None         # "allow", "deny", "block"
    reason: str | None           # Denial reason if any

    # Content (truncated)
    input_preview: str | None    # First 4096 chars of hook input JSON

    # Error (for *_error events only)
    error_type: str | None       # Exception class name, e.g. "ValueError"
    error_message: str | None    # str(exception)

    # Skip info (for handler_skip only)
    skip_reason: str | None      # "early deny from {handler}", "guard failed"
```

**Raw dict access:**
```python
@app.on_observe
def my_callback(event: HookObservabilityEvent):
    raw = event.model_dump()  # Plain dict if needed
```

---

## API

### Callback-Style (Simple)

```python
from fasthooks import HookApp

app = HookApp()

# Receive ALL events
@app.on_observe
def log_everything(event):
    print(f"{event.event_type}: {event.handler_name}")

# Receive specific event type only
@app.on_observe("handler_end")
def log_timing(event):
    print(f"{event.handler_name}: {event.duration_ms}ms → {event.decision}")
```

### Class-Style (Third-Party Integrations)

```python
from fasthooks.observability import BaseObserver, FileObserver

app = HookApp()

# Built-in observer (writes to ~/.fasthooks/observability/events.jsonl)
app.add_observer(FileObserver())

# Custom observer - override only what you need
class MyObserver(BaseObserver):
    def on_handler_end(self, event):
        send_to_datadog(event.handler_name, event.duration_ms)

app.add_observer(MyObserver())
```

---

## BaseObserver

```python
# src/fasthooks/observability/base.py

from fasthooks.observability.events import HookObservabilityEvent

class BaseObserver:
    """
    Base class for observers. Override only the methods you care about.
    All methods have no-op defaults.
    """

    def on_hook_start(self, event: HookObservabilityEvent) -> None:
        """Called when hook invocation begins."""
        pass

    def on_hook_end(self, event: HookObservabilityEvent) -> None:
        """Called when hook invocation completes."""
        pass

    def on_hook_error(self, event: HookObservabilityEvent) -> None:
        """Called when hook-level error occurs."""
        pass

    def on_handler_start(self, event: HookObservabilityEvent) -> None:
        """Called when handler execution begins."""
        pass

    def on_handler_end(self, event: HookObservabilityEvent) -> None:
        """Called when handler execution completes."""
        pass

    def on_handler_skip(self, event: HookObservabilityEvent) -> None:
        """Called when handler is skipped due to early deny."""
        pass

    def on_handler_error(self, event: HookObservabilityEvent) -> None:
        """Called when handler raises exception."""
        pass
```

---

## Built-in Observers (v1)

### Why No Stdout/Stderr Observer?

Claude Code hooks use **stdin/stdout JSON protocol**:
- **stdout**: Reserved for JSON hook response. Any other output corrupts the response.
- **stderr**: Treated as hook error by Claude Code. Causes spurious error messages.

**File-based logging is the only safe option.** This matches the Strategy pattern's `FileObservabilityBackend`.

### FileObserver

For debugging and production logging. Writes JSONL to files.

```python
# src/fasthooks/observability/observers/file.py

class FileObserver(BaseObserver):
    """Write events to JSONL file for debugging/analysis."""

    def __init__(self, path: Path | str | None = None):
        if path is None:
            path = Path.home() / ".fasthooks" / "observability" / "events.jsonl"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, event: HookObservabilityEvent) -> None:
        with open(self.path, "a") as f:
            f.write(event.model_dump_json() + "\n")

    def on_hook_start(self, event): self._write(event)
    def on_hook_end(self, event): self._write(event)
    def on_hook_error(self, event): self._write(event)
    def on_handler_start(self, event): self._write(event)
    def on_handler_end(self, event): self._write(event)
    def on_handler_skip(self, event): self._write(event)
    def on_handler_error(self, event): self._write(event)
```

**Usage:**
```python
from fasthooks.observability import FileObserver

app = HookApp()
app.add_observer(FileObserver())  # Writes to ~/.fasthooks/observability/events.jsonl
app.add_observer(FileObserver("/tmp/my-hooks.jsonl"))  # Custom path
```

**Output format (JSONL):**
```json
{"event_type":"hook_start","hook_id":"a1b2c3d4-...","session_id":"...","hook_event_name":"PreToolUse","tool_name":"Bash",...}
{"event_type":"handler_end","hook_id":"a1b2c3d4-...","handler_name":"check_dangerous","duration_ms":1.2,"decision":"allow",...}
```

### EventCapture

For testing hooks in unit tests. Named to avoid pytest collection warnings.

```python
# src/fasthooks/observability/observers/capture.py

class EventCapture(BaseObserver):
    """Capture events for test assertions."""

    def __init__(self):
        self.events: list[HookObservabilityEvent] = []

    def _capture(self, event: HookObservabilityEvent) -> None:
        self.events.append(event)

    def on_hook_start(self, event): self._capture(event)
    def on_hook_end(self, event): self._capture(event)
    def on_hook_error(self, event): self._capture(event)
    def on_handler_start(self, event): self._capture(event)
    def on_handler_end(self, event): self._capture(event)
    def on_handler_skip(self, event): self._capture(event)
    def on_handler_error(self, event): self._capture(event)

    # Convenience methods for assertions
    def clear(self) -> None:
        """Clear captured events."""
        self.events.clear()

    def events_of_type(self, event_type: str) -> list[HookObservabilityEvent]:
        """Filter events by type."""
        return [e for e in self.events if e.event_type == event_type]

    def handler_events(self, handler_name: str) -> list[HookObservabilityEvent]:
        """Filter events for specific handler."""
        return [e for e in self.events if e.handler_name == handler_name]

    def decisions(self) -> list[str]:
        """Get all decisions from handler_end events."""
        return [e.decision for e in self.events_of_type("handler_end") if e.decision]
```

**Usage in tests:**
```python
def test_handler_denies_dangerous_command():
    app = HookApp()
    capture = EventCapture()
    app.add_observer(capture)

    @app.pre_tool("Bash")
    def check(event):
        if "rm -rf" in event.command:
            return deny("Dangerous command")

    client = TestClient(app)
    client.send(MockEvent.bash("rm -rf /"))

    assert len(capture.events) == 4  # hook_start, handler_start, handler_end, hook_end
    assert capture.events_of_type("handler_end")[0].decision == "deny"
    assert "Dangerous" in capture.events_of_type("handler_end")[0].reason
```

---

## HookApp Integration

### New Attributes

```python
# In src/fasthooks/app.py

class HookApp:
    def __init__(self, ...):
        # Existing code...

        # NEW: Observer storage
        self._observers: list[BaseObserver] = []
        self._callback_observers: list[tuple[Callable, str | None]] = []
```

### New Methods

```python
    def add_observer(self, observer: BaseObserver) -> None:
        """Register a class-based observer."""
        self._observers.append(observer)

    def on_observe(self, event_type_or_func: str | Callable | None = None):
        """
        Decorator to register a callback observer.

        Usage:
            @app.on_observe           # All events
            @app.on_observe()         # All events (explicit)
            @app.on_observe("handler_end")  # Specific event type
        """
        # Handle @app.on_observe without parentheses
        if callable(event_type_or_func):
            func = event_type_or_func
            self._callback_observers.append((func, None))
            return func

        # Handle @app.on_observe() or @app.on_observe("handler_end")
        event_type = event_type_or_func

        def decorator(func: Callable) -> Callable:
            self._callback_observers.append((func, event_type))
            return func

        return decorator
```

### Emission Logic

```python
    def _emit(self, event: HookObservabilityEvent) -> None:
        """
        Dispatch event to all observers.

        - No-op if no observers registered (zero overhead)
        - Swallows observer exceptions (logs warning)
        - Calls class-based observers via on_{event_type} method
        - Calls callback observers with optional type filtering
        """
        # Zero overhead when unused
        if not self._observers and not self._callback_observers:
            return

        # Dispatch to class-based observers
        for observer in self._observers:
            method_name = f"on_{event.event_type}"
            method = getattr(observer, method_name, None)
            if method:
                try:
                    method(event)
                except Exception as e:
                    logger.warning(f"Observer {observer.__class__.__name__}.{method_name} raised: {e}")

        # Dispatch to callback observers
        for callback, filter_type in self._callback_observers:
            if filter_type is None or filter_type == event.event_type:
                try:
                    callback(event)
                except Exception as e:
                    logger.warning(f"Observer callback {callback.__name__} raised: {e}")
```

---

## Instrumentation Points

Where to add `_emit()` calls in existing code.

### In `_dispatch()` (hook-level events)

**File**: `src/fasthooks/app.py`, method `_dispatch()`

```python
def _dispatch(self, data: dict) -> dict:
    hook_id = str(uuid4())
    start_time = time.perf_counter()

    # Extract context from input
    session_id = data.get("session_id", "unknown")
    hook_event_name = data.get("hook_event_name", "unknown")
    tool_name = data.get("tool_name")  # None for Stop, etc.
    input_preview = json.dumps(data)[:4096]  # Truncate

    # Emit hook_start
    self._emit(HookObservabilityEvent(
        event_type="hook_start",
        hook_id=hook_id,
        session_id=session_id,
        hook_event_name=hook_event_name,
        tool_name=tool_name,
        handler_name=None,
        duration_ms=None,
        decision=None,
        reason=None,
        input_preview=input_preview,
        error_type=None,
        error_message=None,
        skip_reason=None,
    ))

    try:
        # Run handlers (this emits handler_* events internally)
        result = self._run_handlers(data, hook_id, session_id, hook_event_name, tool_name)
        final_decision = result.get("decision", "allow")
    except Exception as e:
        # Emit hook_error
        self._emit(HookObservabilityEvent(
            event_type="hook_error",
            hook_id=hook_id,
            session_id=session_id,
            hook_event_name=hook_event_name,
            tool_name=tool_name,
            handler_name=None,
            duration_ms=None,
            decision=None,
            reason=None,
            input_preview=input_preview,
            error_type=type(e).__name__,
            error_message=str(e),
            skip_reason=None,
        ))
        raise

    # Emit hook_end
    duration_ms = (time.perf_counter() - start_time) * 1000
    self._emit(HookObservabilityEvent(
        event_type="hook_end",
        hook_id=hook_id,
        session_id=session_id,
        hook_event_name=hook_event_name,
        tool_name=tool_name,
        handler_name=None,
        duration_ms=duration_ms,
        decision=final_decision,
        reason=result.get("reason"),
        input_preview=None,  # Already sent in hook_start
        error_type=None,
        error_message=None,
        skip_reason=None,
    ))

    return result
```

### In handler execution loop (handler-level events)

**File**: `src/fasthooks/app.py`, inside handler iteration

```python
# For each handler that should run:
handler_start_time = time.perf_counter()

self._emit(HookObservabilityEvent(
    event_type="handler_start",
    hook_id=hook_id,
    session_id=session_id,
    hook_event_name=hook_event_name,
    tool_name=tool_name,
    handler_name=handler.__name__,
    # ... other fields None
))

try:
    result = handler(event, **resolved_deps)
    handler_duration = (time.perf_counter() - handler_start_time) * 1000

    # Determine decision from result
    if result is None:
        decision = "allow"
        reason = None
    else:
        decision = result.decision  # "deny" or "block"
        reason = result.reason

    self._emit(HookObservabilityEvent(
        event_type="handler_end",
        hook_id=hook_id,
        session_id=session_id,
        hook_event_name=hook_event_name,
        tool_name=tool_name,
        handler_name=handler.__name__,
        duration_ms=handler_duration,
        decision=decision,
        reason=reason,
        # ... other fields None
    ))

    # If deny/block, emit skip events for remaining handlers
    if decision in ("deny", "block"):
        for remaining_handler in remaining_handlers:
            self._emit(HookObservabilityEvent(
                event_type="handler_skip",
                hook_id=hook_id,
                session_id=session_id,
                hook_event_name=hook_event_name,
                tool_name=tool_name,
                handler_name=remaining_handler.__name__,
                skip_reason=f"early deny from {handler.__name__}",
                # ... other fields None
            ))
        break  # Stop processing

except Exception as e:
    self._emit(HookObservabilityEvent(
        event_type="handler_error",
        hook_id=hook_id,
        session_id=session_id,
        hook_event_name=hook_event_name,
        tool_name=tool_name,
        handler_name=handler.__name__,
        error_type=type(e).__name__,
        error_message=str(e),
        # ... other fields None
    ))
    raise
```

---

## Package Structure

```
src/fasthooks/observability/
├── __init__.py              # Public exports
├── events.py                # ObservabilityEvent model
├── base.py                  # BaseObserver class
└── observers/
    ├── __init__.py
    ├── file.py              # FileObserver
    └── capture.py           # EventCapture
```

**Public exports** (`__init__.py`):
```python
from fasthooks.observability.events import HookObservabilityEvent
from fasthooks.observability.base import BaseObserver
from fasthooks.observability.observers.file import FileObserver
from fasthooks.observability.observers.capture import EventCapture

__all__ = [
    "HookObservabilityEvent",
    "BaseObserver",
    "FileObserver",
    "EventCapture",
]
```

---

## Migration: EventLogger Deprecation

**Current** (`src/fasthooks/logging.py`):
```python
app = HookApp(log_dir="/tmp/logs")  # Old way
```

**Action**:
1. Add deprecation warning when `log_dir` is passed to `HookApp.__init__()`
2. Document migration in changelog
3. Remove in v2.0

```python
# In HookApp.__init__
if log_dir is not None:
    warnings.warn(
        "log_dir is deprecated. Use app.add_observer(FileObserver(path)) instead. "
        "Will be removed in v2.0.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Keep working for backward compat
    self._event_logger = EventLogger(log_dir)
```

---

## Testing Plan

### Unit Tests to Write

```python
# tests/test_observability.py

class TestObservabilityEvent:
    def test_model_dump_returns_dict(self):
        """Users can get raw dict via .model_dump()"""

    def test_all_fields_optional_except_required(self):
        """Only event_type, hook_id, timestamp, session_id, hook_event_name required"""

class TestBaseObserver:
    def test_all_methods_are_noops(self):
        """BaseObserver methods do nothing by default"""

    def test_subclass_can_override_single_method(self):
        """Don't need to override all methods"""

class TestHookAppObserverRegistration:
    def test_add_observer_stores_observer(self):
        """app.add_observer() adds to _observers list"""

    def test_on_observe_decorator_no_parens(self):
        """@app.on_observe works without parentheses"""

    def test_on_observe_decorator_with_parens(self):
        """@app.on_observe() works with empty parentheses"""

    def test_on_observe_with_event_type_filter(self):
        """@app.on_observe("handler_end") only receives that type"""

class TestEmission:
    def test_no_observers_skips_emission(self):
        """Zero overhead when no observers"""

    def test_observer_exception_swallowed(self):
        """Bad observer doesn't break hook execution"""

    def test_all_event_types_emitted(self):
        """Full flow emits hook_start, handler_start, handler_end, hook_end"""

    def test_handler_skip_emitted_on_early_deny(self):
        """Remaining handlers get skip events"""

    def test_handler_error_emitted_on_exception(self):
        """Handler exceptions emit handler_error"""

class TestFileObserver:
    def test_writes_to_file(self, tmp_path):
        """FileObserver writes JSONL to file"""

class TestEventCapture:
    def test_captures_all_events(self):
        """EventCapture.events contains all emitted events"""

    def test_events_of_type_filters(self):
        """events_of_type() returns filtered list"""

    def test_handler_events_filters(self):
        """handler_events() returns events for specific handler"""

    def test_decisions_property(self):
        """decisions property returns list of decision strings"""

    def test_clear_empties_events(self):
        """clear() empties the events list"""
```

---

## Implementation Order

1. **Create `HookObservabilityEvent` model** - `events.py`
2. **Create `BaseObserver` class** - `base.py`
3. **Add `add_observer()` and `on_observe()` to HookApp** - `app.py`
4. **Add `_emit()` method to HookApp** - `app.py`
5. **Instrument `_dispatch()` with hook-level events** - `app.py`
6. **Instrument handler loop with handler-level events** - `app.py`
7. **Create `FileObserver`** - `observers/file.py`
8. **Create `EventCapture`** - `observers/capture.py`
9. **Write tests**
10. **Add EventLogger deprecation warning**

---

## Deferred to Future

| Feature | Deferred To | Reason |
|---------|-------------|--------|
| `ObserverContext` | v2 if needed | Event already has enough context |
| `FileObserver` | When users need persistent logs | Start minimal |
| `MetricsObserver` | When users need aggregated stats | Start minimal |
| `SQLiteObserver` | `specs/studio.md` | Studio-specific, not core observability |
| Async observer dispatch | If performance requires | Sync is simpler, observers can spawn tasks |
| Observer removal | If hot-reload needed | Add-only is simpler |

---

## References

### Files to Modify

| File | Changes |
|------|---------|
| `src/fasthooks/app.py` | Add `_observers`, `_callback_observers`, `add_observer()`, `on_observe()`, `_emit()`. Instrument `_dispatch()` and handler loop. |
| `src/fasthooks/observability/__init__.py` | Add public exports |
| `src/fasthooks/observability/events.py` | Create `HookObservabilityEvent` model |
| `src/fasthooks/observability/base.py` | Create `BaseObserver` class |
| `src/fasthooks/observability/observers/__init__.py` | New file |
| `src/fasthooks/observability/observers/file.py` | Create `FileObserver` |
| `src/fasthooks/observability/observers/capture.py` | Create `EventCapture` |
| `tests/test_observability.py` | New test file |

### Existing Code to Understand

| File | Relevant For |
|------|--------------|
| `src/fasthooks/app.py:_dispatch()` | Where to emit hook_start/hook_end |
| `src/fasthooks/app.py:_run_with_middleware()` | Where handlers are executed |
| `src/fasthooks/logging.py` | EventLogger to deprecate |
| `src/fasthooks/strategies/base.py:79-250` | Existing Strategy observability (similar pattern) |

---

## Appendix: Third-Party Integration Example

Shows how third parties would build integrations using this API.

```python
# Example: fasthooks-datadog (hypothetical package)

from fasthooks.observability import BaseObserver, HookObservabilityEvent
from datadog import statsd

class DatadogObserver(BaseObserver):
    """Send hook metrics to Datadog."""

    def __init__(self, prefix: str = "fasthooks"):
        self.prefix = prefix

    def on_hook_end(self, event: HookObservabilityEvent) -> None:
        # Count hooks by event type
        statsd.increment(
            f"{self.prefix}.hooks",
            tags=[f"event:{event.hook_event_name}", f"tool:{event.tool_name}"]
        )
        # Track duration
        statsd.histogram(
            f"{self.prefix}.hook_duration_ms",
            event.duration_ms,
            tags=[f"event:{event.hook_event_name}"]
        )

    def on_handler_end(self, event: HookObservabilityEvent) -> None:
        # Track handler performance
        statsd.histogram(
            f"{self.prefix}.handler_duration_ms",
            event.duration_ms,
            tags=[f"handler:{event.handler_name}"]
        )
        # Count decisions
        statsd.increment(
            f"{self.prefix}.decisions",
            tags=[f"decision:{event.decision}", f"handler:{event.handler_name}"]
        )

# User usage:
from fasthooks_datadog import DatadogObserver
app.add_observer(DatadogObserver(prefix="myapp.hooks"))
```

---

## Appendix: Observability System Comparison

### Comparison Table

| Aspect | Strategy (current) | HookApp (this spec) | LangChain | ell |
|--------|-------------------|---------------------|-----------|-----|
| **Registration** | `@strategy.on_observe` | `@app.on_observe` + `add_observer()` | `callbacks=[handler]` param | Implicit via `ell.init(store=)` |
| **Observer type** | Callback function only | Callback + BaseObserver class | BaseCallbackHandler class | Store interface only |
| **Event model** | Dict-like events | Pydantic HookObservabilityEvent | Separate params per method | Internal models |
| **Third-party extensibility** | Limited (callbacks only) | **Good** (class-based protocol) | **Excellent** (mature ecosystem) | **Poor** (store-only) |
| **Event filtering** | None | `@app.on_observe("handler_end")` | `ignore_*` properties | None |
| **Async support** | Sync only | Fire-and-forget | Both sync + async handlers | Sync (internal) |
| **Built-in integrations** | File backend only | Stdout, Test (v1) | LangSmith, Datadog, W&B, etc. | SQLite/Postgres only |

### Why This Design

- **Better than Strategy**: Class-based observers + event filtering
- **Simpler than LangChain**: No run_id inheritance, no async dispatch complexity
- **More extensible than ell**: Observers vs monolithic Store interface

### LangChain Patterns Adopted

| Pattern | Adopted? | Notes |
|---------|----------|-------|
| Base class with no-ops | ✓ | `BaseObserver` |
| Event filtering | ✓ | `@app.on_observe("handler_end")` |
| run_id correlation | ✓ | `hook_id` per invocation |
| Swallow observer errors | ✓ | Log warning, continue |
| tags/metadata inheritance | ✗ | Not needed (single hook invocation) |
| 3-level registration | ✗ | App-level only (simpler) |
| Async observer support | Partial | Fire-and-forget |
