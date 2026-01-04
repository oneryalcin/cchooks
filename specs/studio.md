# Studio Spec

**Status**: Placeholder (depends on observability implementation)
**Date**: 2026-01-04
**Depends on**: `specs/observability.md` must be implemented first

---

## Overview

fasthooks-studio is a visual debugging UI for hooks. It reads from SQLiteObserver's database and provides a web interface for exploring hook executions.

**This spec owns:**
- `SQLiteObserver` - Observer that writes to SQLite (foundation for studio)
- Studio backend (FastAPI server)
- Studio frontend (React UI)
- `fasthooks studio` CLI command

---

## Prerequisites

Before implementing studio:

1. **Observability spec must be complete** - `BaseObserver`, `ObservabilityEvent`, `@app.on_observe` working
2. **SQLiteObserver builds on BaseObserver** - Just another observer that writes to SQLite

---

## SQLiteObserver (Owned by This Spec)

Moved from observability spec to keep that spec focused on core protocol.

```python
# src/fasthooks/observability/observers/sqlite.py

from fasthooks.observability import BaseObserver, ObservabilityEvent
import sqlite3

class SQLiteObserver(BaseObserver):
    """Write events to SQLite for studio visualization."""

    def __init__(self, db_path: str = "~/.fasthooks/hooks.db"):
        self.db_path = Path(db_path).expanduser()
        self._init_db()

    def _init_db(self):
        """Create tables if not exist."""
        # Schema TBD

    def on_hook_start(self, event): ...
    def on_hook_end(self, event): ...
    def on_handler_end(self, event): ...
    # etc.
```

### SQLite Schema (TBD)

```sql
-- hooks table: one row per hook invocation
CREATE TABLE hooks (
    hook_id TEXT PRIMARY KEY,
    session_id TEXT,
    hook_event_name TEXT,
    tool_name TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    duration_ms REAL,
    final_decision TEXT,
    input_preview TEXT
);

-- handlers table: one row per handler execution
CREATE TABLE handlers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hook_id TEXT REFERENCES hooks(hook_id),
    handler_name TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    duration_ms REAL,
    decision TEXT,
    reason TEXT,
    error_type TEXT,
    error_message TEXT,
    skip_reason TEXT
);

-- indexes for common queries
CREATE INDEX idx_hooks_session ON hooks(session_id);
CREATE INDEX idx_hooks_time ON hooks(started_at);
CREATE INDEX idx_handlers_hook ON handlers(hook_id);
```

---

## Inspiration: ell-studio

ell-studio is the reference implementation we're learning from.

**Clone**: `gh repo clone MadcowD/ell /tmp/ell -- --depth 1`

### Key ell-studio Files

| File | Purpose |
|------|---------|
| `src/ell/studio/server.py` | FastAPI backend |
| `src/ell/studio/connection_manager.py` | WebSocket broadcast |
| `ell-studio/src/App.js` | React routing |
| `ell-studio/src/hooks/useBackend.js` | React Query API hooks |
| `ell-studio/src/components/depgraph/DependencyGraph.js` | ReactFlow graph |
| `ell-studio/src/components/HierarchicalTable.js` | Tree table with SVG connectors |

### Patterns to Adopt

1. **Real-time updates**: File watcher + WebSocket broadcast
2. **React Query**: Auto-cache invalidation on WebSocket messages
3. **Hierarchical visualization**: Hook → Handler tree with timing
4. **Time-series**: Aggregated stats by day/hour

---

## TODO (When We Implement)

- [ ] Design SQLite schema (finalize above draft)
- [ ] Implement SQLiteObserver
- [ ] Define REST API endpoints
- [ ] Design React component structure
- [ ] Implement `fasthooks studio` CLI command
- [ ] Add to fasthooks as optional dependency or separate package

---

*This spec will be expanded after observability implementation is complete.*
