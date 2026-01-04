# Observability Spec

**Status**: Draft
**Author**: Auto-generated
**Date**: 2026-01-04

## Overview

Add observability to `HookApp` matching the capabilities already present in `Strategy`. This enables users to monitor, debug, and integrate hooks with external observability systems.

## Problem Statement

Currently:
- **Strategy** has rich observability via `on_observe()` callbacks
- **HookApp** has only basic `EventLogger` that logs raw input JSON
- Users cannot track handler timing, decisions, or errors in regular hook usage
- No way to integrate with external systems (LangSmith, Datadog, etc.)

## Goals

1. Add `on_observe()` pattern to HookApp (matching Strategy API)
2. Emit structured events for handler lifecycle
3. Provide built-in observers (stdout, file, metrics)
4. Enable third-party integrations via observer protocol
5. Maintain backward compatibility

---

## Current State

### Strategy Observability (Rich)

**Location**: `src/fasthooks/strategies/base.py` (lines 79-250)

```python
strategy = LongRunningStrategy()

@strategy.on_observe
def log_events(event):
    print(f"{event.event_type}: {event.duration_ms}ms")
```

**Events emitted** (`src/fasthooks/observability/events.py`):
| Event | Description |
|-------|-------------|
| `hook_enter` | Handler invocation started |
| `hook_exit` | Handler completed (includes `duration_ms`) |
| `decision` | Handler returned deny/block/approve |
| `error` | Handler raised exception (includes traceback) |
| `custom` | User-emitted via `strategy.emit_custom()` |

**Backend storage** (`src/fasthooks/observability/backend.py`):
- `FileObservabilityBackend` writes JSONL to `~/.fasthooks/observability/{session_id}.jsonl`
- Verbosity levels: MINIMAL, STANDARD, VERBOSE

### HookApp Observability (Basic)

**Location**: `src/fasthooks/logging.py`

```python
app = HookApp(log_dir="/tmp/logs")
```

**What it does**:
- Logs raw hook input JSON to `{log_dir}/hooks-{session_id}.jsonl`
- Flattens tool-specific fields for querying
- No handler timing, no decisions, no errors

### Gap Analysis

| Feature | Strategy | HookApp | Gap |
|---------|----------|---------|-----|
| Handler timing | ✓ `hook_enter`/`hook_exit` | ✗ | Need to add |
| Decision tracking | ✓ deny/block/approve | ✗ | Need to add |
| Error tracking | ✓ with traceback | ✗ | Need to add |
| Custom events | ✓ `emit_custom()` | ✗ | Need to add |
| Structured output | ✓ Pydantic models | ✗ | Need to add |
| Verbosity control | ✓ 3 levels | ✗ | Need to add |
| Session correlation | ✓ `request_id` | Partial | Need `hook_id` |

---

## Reference: LangChain Callback System

LangChain has a mature callback system we can learn from.

### Key Files (cloned to /tmp/langchain)

| File | Purpose |
|------|---------|
| `libs/core/langchain_core/callbacks/base.py` | Base handler classes, event methods |
| `libs/core/langchain_core/callbacks/manager.py` | CallbackManager, registration, dispatch |
| `libs/core/langchain_core/callbacks/stdout.py` | StdOutCallbackHandler |
| `libs/core/langchain_core/tracers/base.py` | BaseTracer for structured tracing |
| `libs/core/langchain_core/tracers/langchain.py` | LangSmith integration |

### LangChain Documentation

- Callbacks concept: https://python.langchain.com/docs/concepts/callbacks/
- Custom callbacks: https://python.langchain.com/docs/how_to/custom_callbacks/

### Key Design Patterns

#### 1. Handler Protocol with Event Methods

```python
# LangChain: libs/core/langchain_core/callbacks/base.py
class BaseCallbackHandler:
    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id, **kwargs): ...
    def on_llm_end(self, response, *, run_id, **kwargs): ...
    def on_llm_error(self, error, *, run_id, **kwargs): ...
    def on_chain_start(self, ...): ...
    def on_tool_start(self, ...): ...
    # etc.
```

**Key insight**: Every event gets `run_id` + `parent_run_id` for correlation.

#### 2. Event Filtering via Properties

```python
class BaseCallbackHandler:
    @property
    def ignore_llm(self) -> bool:
        return False

    @property
    def ignore_chain(self) -> bool:
        return False
```

**Key insight**: Handlers can opt-out of event categories.

#### 3. Three-Level Registration

```python
# Global via env var
os.environ["LANGCHAIN_TRACING_V2"] = "true"

# Per-chain
chain = MyChain(callbacks=[handler])

# Per-invocation
chain.invoke(input, config={"callbacks": [handler]})
```

#### 4. Async Handling with `run_inline`

```python
class BaseCallbackHandler:
    run_inline: bool = False  # If True, run sync in event loop
```

**Key insight**: Tracers need `run_inline=True` for ordering guarantees.

#### 5. Context Propagation

```python
# Every event includes:
run_id: UUID          # Unique to this run
parent_run_id: UUID   # Links to parent (enables nesting)
tags: list[str]       # Inheritable tags
metadata: dict        # Inheritable metadata
```

---

## Proposed Design

### Observer Protocol

```python
# src/fasthooks/observability/protocol.py

from typing import Protocol, Any
from fasthooks.observability.events import ObservabilityEvent

class HookObserver(Protocol):
    """Protocol for observability handlers."""

    # Filtering (opt-out of event categories)
    @property
    def ignore_pre_tool(self) -> bool: ...
    @property
    def ignore_post_tool(self) -> bool: ...
    @property
    def ignore_lifecycle(self) -> bool: ...

    # Hook-level events
    def on_hook_start(self, event: ObservabilityEvent) -> None: ...
    def on_hook_end(self, event: ObservabilityEvent) -> None: ...
    def on_hook_error(self, event: ObservabilityEvent) -> None: ...

    # Handler-level events (granular)
    def on_handler_start(self, event: ObservabilityEvent) -> None: ...
    def on_handler_end(self, event: ObservabilityEvent) -> None: ...
    def on_handler_skip(self, event: ObservabilityEvent) -> None: ...

    # Custom events
    def on_custom_event(self, event: ObservabilityEvent) -> None: ...
```

### Event Model

```python
# Extend existing src/fasthooks/observability/events.py

class ObservabilityEvent(BaseModel):
    event_type: str           # hook_start, handler_end, etc.
    timestamp: datetime
    session_id: str
    hook_id: str              # Unique per hook invocation
    parent_hook_id: str | None

    # Context
    hook_event_name: str      # PreToolUse, Stop, etc.
    tool_name: str | None
    handler_name: str | None

    # Timing
    duration_ms: float | None

    # Result (for end events)
    decision: str | None      # allow, deny, block
    reason: str | None

    # Error (for error events)
    error_type: str | None
    error_message: str | None
    traceback: str | None

    # Custom
    custom_event_type: str | None
    payload: dict | None
```

### HookApp Integration

```python
# src/fasthooks/app.py additions

class HookApp:
    def __init__(self, ...):
        self._observers: list[HookObserver] = []

    def add_observer(self, observer: HookObserver) -> None:
        """Register an observer."""
        self._observers.append(observer)

    def on_observe(self, func: Callable) -> Callable:
        """Decorator to register a callback observer."""
        self._observers.append(_CallbackObserver(func))
        return func

    def _emit(self, event: ObservabilityEvent) -> None:
        """Dispatch event to all observers."""
        for observer in self._observers:
            if self._should_notify(observer, event):
                self._call_observer(observer, event)
```

### Built-in Observers

```python
# src/fasthooks/observability/observers.py

class StdOutObserver:
    """Print events to console."""

    def on_handler_end(self, event):
        print(f"[{event.handler_name}] {event.duration_ms:.1f}ms → {event.decision or 'allow'}")

class FileObserver:
    """Write events to JSONL file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def on_hook_end(self, event):
        with open(self.path, "a") as f:
            f.write(event.model_dump_json() + "\n")

class MetricsObserver:
    """Collect timing and decision statistics."""

    def __init__(self):
        self.handler_times: dict[str, list[float]] = defaultdict(list)
        self.decisions: Counter = Counter()

    def on_handler_end(self, event):
        self.handler_times[event.handler_name].append(event.duration_ms)
        if event.decision:
            self.decisions[event.decision] += 1

    @property
    def stats(self) -> dict:
        return {
            "handler_avg_ms": {k: sum(v)/len(v) for k, v in self.handler_times.items()},
            "decisions": dict(self.decisions),
        }
```

### Registration Levels

```python
# 1. App-level
app = HookApp()
app.add_observer(StdOutObserver())

# 2. Decorator style
@app.on_observe
def log_all(event):
    logger.info(f"{event.event_type}: {event.handler_name}")

# 3. Environment variable (future)
# FASTHOOKS_OBSERVER=stdout  → auto-register StdOutObserver
# FASTHOOKS_OBSERVER=file:/tmp/hooks.jsonl  → auto-register FileObserver
```

---

## Implementation Plan

### Phase 1: Core Observer Infrastructure
- [ ] Add `HookObserver` protocol
- [ ] Add observer registration to `HookApp`
- [ ] Instrument `_dispatch()` and `_run_with_middleware()` to emit events
- [ ] Add `hook_id` generation (UUID per invocation)

### Phase 2: Built-in Observers
- [ ] `StdOutObserver` - Console output
- [ ] `FileObserver` - JSONL file output
- [ ] `MetricsObserver` - Statistics collection

### Phase 3: Unify with Strategy
- [ ] Ensure event models match between HookApp and Strategy
- [ ] Consider shared base class or mixin
- [ ] Document migration path

### Phase 4: Third-party Integration Hooks
- [ ] Environment variable registration
- [ ] `register_observer_hook()` for third-party packages
- [ ] Example: LangSmith integration

---

## Open Questions

1. **Should we share code with Strategy?**
   - Option A: HookApp uses same `on_observe()` pattern, Strategy stays separate
   - Option B: Extract shared `ObservableMixin` used by both
   - Option C: Strategy observability moves to HookApp, Strategy extends it

2. **Async handling?**
   - HookApp supports async handlers
   - Should observers be async-capable?
   - LangChain pattern: `run_inline` flag for sync-in-event-loop

3. **Verbosity levels?**
   - Strategy has MINIMAL/STANDARD/VERBOSE
   - Should HookApp observers have same concept?
   - Or just let users filter via `ignore_*` properties?

4. **Backward compatibility?**
   - Existing `EventLogger` (log_dir parameter) - deprecate or keep?
   - Strategy `on_observe` - ensure API matches

---

## References

### fasthooks Code
- Strategy observability: `src/fasthooks/strategies/base.py:79-250`
- Observability events: `src/fasthooks/observability/events.py`
- Observability backend: `src/fasthooks/observability/backend.py`
- HookApp dispatch: `src/fasthooks/app.py:_dispatch()`, `_run_with_middleware()`
- EventLogger: `src/fasthooks/logging.py`

### fasthooks Specs
- Strategy spec: `specs/strategies.md` (if exists)
- CLI spec: `specs/cli.md`

### LangChain Code (clone: `gh repo clone langchain-ai/langchain /tmp/langchain -- --depth 1`)
- Base handlers: `libs/core/langchain_core/callbacks/base.py`
- Manager: `libs/core/langchain_core/callbacks/manager.py`
- StdOut handler: `libs/core/langchain_core/callbacks/stdout.py`
- Base tracer: `libs/core/langchain_core/tracers/base.py`
- LangSmith tracer: `libs/core/langchain_core/tracers/langchain.py`

### LangChain Docs
- Callbacks concept: https://python.langchain.com/docs/concepts/callbacks/
- Custom callbacks: https://python.langchain.com/docs/how_to/custom_callbacks/
- Tracing: https://python.langchain.com/docs/how_to/callbacks_attach/

---

## Reference: ell-studio (Visual Tracing)

ell is an LLM programming framework with a visual studio for tracing. Highly relevant for building a hooks studio.

**Clone**: `gh repo clone MadcowD/ell /tmp/ell -- --depth 1`

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│               User Code (@ell.simple decorated)          │
└──────────────────────┬──────────────────────────────────┘
                       │ (function calls)
                       ▼
┌─────────────────────────────────────────────────────────┐
│          _track() decorator wrapper                      │
│  - Captures: timing, tokens, params, results            │
│  - Thread-local stack for parent/child tracking         │
└──────────────┬────────────────────────────┬─────────────┘
               │                            │
               ▼                            ▼
┌──────────────────────┐    ┌────────────────────────────┐
│ Invocation nesting   │    │ Storage Layer              │
│ (thread-local stack) │    │ - SQLite + gzip blobs      │
└──────────────────────┘    │ - Postgres for production  │
                            └────────────────────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────┐
                        │   ell-studio Backend     │
                        │ FastAPI + WebSocket      │
                        └──────────────────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────┐
                        │   ell-studio Frontend    │
                        │ React + ReactFlow + D3   │
                        └──────────────────────────┘
```

### Key Backend Patterns

#### 1. Decorator-Based Instrumentation
```python
# /tmp/ell/src/ell/lmp/_track.py:47-197
# Wrap function, capture before/after execution
_start_time = utc_now()
(result, invocation_api_params, metadata) = func_to_track(*args, **kwargs)
latency_ms = (utc_now() - _start_time).total_seconds() * 1000
```

#### 2. Thread-Local Context Stack
```python
# /tmp/ell/src/ell/lmp/_track.py:26-44
_invocation_stack = threading.local()

def get_current_invocation() -> Optional[str]:
    return _invocation_stack.stack[-1] if _invocation_stack.stack else None

def push_invocation(invocation_id: str):
    _invocation_stack.stack.append(invocation_id)
```

#### 3. Two-Phase Storage (Dedup + Every Call)
```python
# Phase 1: Store LMP definition once (deduplicated by hash)
# /tmp/ell/src/ell/lmp/_track.py:201-257
serialized_lmp = SerializedLMP(
    lmp_id=func.__ell_hash__,  # Content-based hash
    name=func.__qualname__,
    source=fn_closure[0],
    version_number=len(existing) + 1,
)

# Phase 2: Store every invocation
# /tmp/ell/src/ell/lmp/_track.py:260-310
_write_invocation(
    func, invocation_id, latency_ms, prompt_tokens, completion_tokens,
    state_cache_key, invocation_api_params, cleaned_invocation_params,
    consumes, result, parent_invocation_id,
)
```

#### 4. Large Payload Externalization
```python
# /tmp/ell/src/ell/stores/sql.py:469-510
# Payloads >100KB externalized to blob store (gzip compressed)
if size > 100_000:
    contents.is_external = True
    blob_store.write(invocation_id, gzip.compress(data))
```

### Data Models

**File**: `/tmp/ell/src/ell/stores/models/core.py:26-210`

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `SerializedLMP` | LMP definition (versioned) | `lmp_id`, `name`, `source`, `version_number` |
| `Invocation` | Single execution | `id`, `lmp_id`, `latency_ms`, `prompt_tokens`, `used_by_id` |
| `InvocationContents` | Params/results | `params`, `results`, `is_external` |
| `InvocationTrace` | Many-to-many dependency | `consumer_id`, `consumed_id` |

### Real-Time Updates

```python
# /tmp/ell/src/ell/studio/__main__.py:70-104
# File watcher detects DB changes
observer = Observer()
observer.schedule(DatabaseChangeHandler(), db_path)

# /tmp/ell/src/ell/studio/connection_manager.py:1-18
# WebSocket broadcasts to all clients
async def broadcast(message: str):
    for connection in self.active_connections:
        await connection.send_text(message)
```

### Studio Server Endpoints

**File**: `/tmp/ell/src/ell/studio/server.py`

| Endpoint | Purpose |
|----------|---------|
| `GET /api/latest/lmps` | Latest version of each LMP |
| `GET /api/invocations` | Query invocations (hierarchical) |
| `GET /api/traces` | Dependency graph edges |
| `GET /api/invocations/aggregate` | Time-series stats |
| `GET /api/blob/{id}` | Externalized large payloads |

### Frontend Visualization

**Technology Stack**:
- React 18 + React Router
- React Query (caching + auto-invalidation)
- ReactFlow + D3 (dependency graph)
- Tailwind CSS (dark mode first)
- react-syntax-highlighter (code display)

#### Key Visualization Components

| Component | File | Purpose |
|-----------|------|---------|
| Dependency Graph | `/tmp/ell/ell-studio/src/components/depgraph/DependencyGraph.js` | ReactFlow + D3 force layout |
| Layout Algorithm | `/tmp/ell/ell-studio/src/components/depgraph/layoutUtils.js:129-269` | Hierarchical positioning |
| Invocation Tree | `/tmp/ell/ell-studio/src/components/HierarchicalTable.js:8-250` | SVG connectors + expand/collapse |
| Code Highlighting | `/tmp/ell/ell-studio/src/components/source/CodeHighlighter.js` | Prism + diff view |
| JSON Renderer | `/tmp/ell/ell-studio/src/components/IORenderer.js:54-292` | Type-aware pretty-printing |
| Metrics Display | `/tmp/ell/ell-studio/src/components/evaluations/MetricDisplay.js` | Animated KPI cards |

#### WebSocket Auto-Refresh

```javascript
// /tmp/ell/ell-studio/src/hooks/useBackend.js:22-59
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.entity === "database_updated") {
    queryClient.invalidateQueries({ queryKey: ["traces"] });
    queryClient.invalidateQueries({ queryKey: ["invocations"] });
    // ... invalidate all caches
  }
};
```

### Lessons for fasthooks-studio

| Pattern | ell Implementation | fasthooks Adaptation |
|---------|-------------------|---------------------|
| **Instrumentation** | Decorators wrap functions | Already have `@app.pre_tool()` |
| **Context tracking** | Thread-local stack | Track handler chains within hook |
| **Deduplication** | Hash-based LMP IDs | Hash handler definitions |
| **Invocations** | Store every call | Store every hook execution |
| **Large payloads** | Externalize >100KB | Externalize transcript content |
| **Real-time** | File watcher + WebSocket | Same pattern |
| **Storage** | SQLite (dev) / Postgres (prod) | Same |
| **Graph viz** | ReactFlow + D3 | Same for handler dependency |
| **Tree view** | Custom SVG connectors | For nested handler calls |

### ell Key Files Reference

**Backend (Python)**:
| File | Lines | Purpose |
|------|-------|---------|
| `src/ell/lmp/_track.py` | 47-197 | Main tracking decorator |
| `src/ell/lmp/_track.py` | 260-310 | Invocation persistence |
| `src/ell/stores/sql.py` | 35-510 | SQLite/Postgres storage |
| `src/ell/stores/models/core.py` | 26-210 | Data models |
| `src/ell/studio/server.py` | 36-349 | FastAPI endpoints |
| `src/ell/configurator.py` | 35-243 | Global config singleton |

**Frontend (React)**:
| File | Lines | Purpose |
|------|-------|---------|
| `ell-studio/src/App.js` | 44-109 | Main routing |
| `ell-studio/src/hooks/useBackend.js` | 1-348 | All API queries |
| `ell-studio/src/components/depgraph/DependencyGraph.js` | 31-140 | Graph visualization |
| `ell-studio/src/components/depgraph/layoutUtils.js` | 20-269 | D3 force + layout |
| `ell-studio/src/components/HierarchicalTable.js` | 8-250 | Tree table + SVG |
| `ell-studio/src/components/source/CodeHighlighter.js` | 1-89 | Syntax highlighting |
| `ell-studio/src/components/IORenderer.js` | 1-318 | JSON rendering |
| `ell-studio/tailwind.config.js` | 1-73 | Theme + colors |
| `ell-studio/src/styles/globals.css` | 5-107 | CSS vars + animations |

---

## Appendix: Event Flow Diagram

```
User calls app.run()
        │
        ▼
┌─────────────────────────────────┐
│ _dispatch(data)                 │
│   emit(hook_start)  ◄───────────┼──── hook_id generated
│        │                        │
│        ▼                        │
│   Find matching handlers        │
│        │                        │
│        ▼                        │
│   For each handler:             │
│     emit(handler_start)         │
│     try:                        │
│       result = handler(event)   │
│       emit(handler_end)         │
│     except:                     │
│       emit(handler_error)       │
│        │                        │
│        ▼                        │
│   Build response                │
│   emit(hook_end)  ◄─────────────┼──── includes decision, duration
│        │                        │
└────────┼────────────────────────┘
         ▼
    Return response
```
