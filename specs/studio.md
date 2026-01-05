# Studio Spec

**Status**: Implemented
**Date**: 2026-01-05
**Depends on**: `specs/observability.md` (implemented)

---

## Philosophy

**Minimal viable studio for development debugging.**

- SQLite DB is **throwable** - no migrations, delete and recreate freely
- Development tool, not production infrastructure
- Start with raw event dump, iterate schema based on UI needs
- Real-time updates via file watcher (ell pattern)
- Ship SQLiteObserver first, studio UI second

---

## Overview

fasthooks-studio is a visual debugging UI for hooks. Users can:
- See hook events in real-time (not just file logs)
- Explore hook → handler hierarchy
- Filter by session, tool, decision type
- Debug "why did my handler deny/allow?"

**This spec owns:**
- `SQLiteObserver` - Observer that writes to SQLite
- Studio backend (FastAPI server)
- Studio frontend (React UI)
- `fasthooks studio` CLI command

---

## Design Decisions

### SQLiteObserver Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Connection strategy | Per-write | Like FileObserver. Simple, no state management. ~1ms overhead acceptable. |
| WAL mode | No (default DELETE) | Simpler, single file. Concurrent write perf not critical for dev tool. |
| Error handling | **Let propagate** | Fail-fast for dev tool. Unlike FileObserver which swallows. User sees errors immediately. |
| DB location | `~/.fasthooks/studio.db` | Top-level, easy to find/delete. Clear separation from JSONL logs. |
| input_preview storage | Every event | Redundant but simpler queries. Match FileObserver behavior. No joins needed. |
| Import path | `fasthooks.observability` | First-class citizen alongside FileObserver. sqlite3 is stdlib, no extra deps. |
| Schema version | None | Truly throwable. YAGNI. Delete and recreate. |
| Query methods | Write-only | Pure observer. Studio server opens DB directly with its own queries. |
| DB deletion handling | Init once, fail on delete | Simpler. If user deletes mid-run, restart hook to recover. |
| Timestamp format | Unix epoch REAL | Native sorting/comparison. Milliseconds precision (3 decimals). |
| Public export | Yes | `from fasthooks.observability import SQLiteObserver` |
| Latency | Acceptable | Studio is opt-in debugging. Users accept tradeoff when enabled. |

### Studio Decisions (Future)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Schema approach | Minimal v1, iterate later | Throwable DB = no migration burden |
| Real-time mechanism | File watcher + WebSocket | Proven pattern from ell, simple |
| Event storage | Single `events` table (v1) | Dump raw events, normalize later if needed |
| Studio packaging | Optional dependency | `pip install fasthooks[studio]` |
| Frontend framework | React + React Query | Matches ell pattern, good DX |
| Test file | Separate `test_sqlite_observer.py` | Room to grow if studio tests expand |

---

## What We Learned from ell-studio

**Reference**: Clone with `gh repo clone MadcowD/ell /tmp/ell -- --depth 1`

### Architecture Overview

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Hook Execution │────▶│  SQLite DB   │◀────│  File Watcher   │
│  (SQLiteObserver)     │  (studio.db) │     │  (polls mtime)  │
└─────────────────┘     └──────────────┘     └────────┬────────┘
                                                      │
                                                      ▼
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  React Frontend │◀────│  WebSocket   │◀────│  FastAPI Server │
│  (React Query)  │     │  broadcast   │     │  (REST + WS)    │
└─────────────────┘     └──────────────┘     └─────────────────┘
```

### Key ell Files & Patterns

| File | What It Does | Key Pattern |
|------|--------------|-------------|
| `/tmp/ell/src/ell/studio/server.py` | FastAPI app factory | `create_app(config)` returns app with `notify_clients()` method attached |
| `/tmp/ell/src/ell/studio/connection_manager.py` | WebSocket hub | Simple list of connections, `broadcast(message)` to all |
| `/tmp/ell/src/ell/studio/__main__.py:74-109` | File watcher | Polls DB file stats every 0.1s, broadcasts on change |
| `/tmp/ell/ell-studio/src/hooks/useBackend.js:22-59` | React Query + WS | WebSocket message triggers `queryClient.invalidateQueries()` |
| `/tmp/ell/src/ell/stores/sql.py` | SQLModel ORM | Session-per-request via `Depends(get_session)` |

### Real-Time Update Pattern (ell)

**Server side** (`__main__.py:74-109`):
```python
async def db_watcher(db_path, app):
    last_stat = None
    while True:
        await asyncio.sleep(0.1)  # Poll every 100ms
        current_stat = db_path.stat()

        # Check mtime, size, or inode changed
        if changed(current_stat, last_stat):
            await app.notify_clients("database_updated")

        last_stat = current_stat
```

**Client side** (`useBackend.js:33-45`):
```javascript
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.entity === "database_updated") {
    // Invalidate all relevant queries - React Query refetches automatically
    queryClient.invalidateQueries({ queryKey: ["hooks"] });
    queryClient.invalidateQueries({ queryKey: ["handlers"] });
  }
};
```

### WebSocket Manager (ell)

**File**: `/tmp/ell/src/ell/studio/connection_manager.py`

```python
class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)
```

---

## SQLiteObserver (v1 - Minimal)

Start with the simplest thing that works: dump raw events to a single table.

### Schema v1

```sql
-- Single events table - just dump everything
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    event_type TEXT NOT NULL,        -- hook_start, handler_end, etc.
    hook_id TEXT NOT NULL,           -- UUID for hook invocation
    timestamp REAL NOT NULL,         -- Unix epoch (milliseconds precision)

    -- Context
    session_id TEXT NOT NULL,
    hook_event_name TEXT NOT NULL,   -- PreToolUse, PostToolUse, Stop, etc.
    tool_name TEXT,                  -- Bash, Write, etc. (NULL for lifecycle)
    handler_name TEXT,               -- Function name (NULL for hook-level)

    -- Timing
    duration_ms REAL,

    -- Decision
    decision TEXT,                   -- allow, deny, block
    reason TEXT,

    -- Content
    input_preview TEXT,              -- Truncated input JSON

    -- Error
    error_type TEXT,
    error_message TEXT,

    -- Skip
    skip_reason TEXT
);

-- Minimal indexes for common queries
CREATE INDEX idx_events_hook_id ON events(hook_id);
CREATE INDEX idx_events_timestamp ON events(timestamp);
CREATE INDEX idx_events_session ON events(session_id);
CREATE INDEX idx_events_type ON events(event_type);
```

**Why single table?**
- Simplest to implement
- Easy to query with SQLite JSON functions if needed
- Can normalize to `hooks` + `handlers` tables later based on UI needs
- Throwable = no migration cost

**Why Unix epoch REAL?**
- Native SQLite sorting/comparison (no string parsing)
- Milliseconds precision: `round(dt.timestamp(), 3)`
- Convert for display in studio frontend

### Implementation

```python
# src/fasthooks/observability/observers/sqlite.py

"""SQLite observer for studio visualization."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from fasthooks.observability.base import BaseObserver

if TYPE_CHECKING:
    from fasthooks.observability.events import HookObservabilityEvent


class SQLiteObserver(BaseObserver):
    """Write events to SQLite for studio visualization.

    Unlike FileObserver, errors are NOT swallowed - they propagate.
    This is a dev tool; fail-fast helps catch issues immediately.

    Example:
        app.add_observer(SQLiteObserver())  # ~/.fasthooks/studio.db
        app.add_observer(SQLiteObserver("/tmp/debug.db"))  # Custom path
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize observer and create table.

        Args:
            db_path: Path to SQLite DB. Defaults to ~/.fasthooks/studio.db
        """
        if db_path is None:
            db_path = Path.home() / ".fasthooks" / "studio.db"
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Create table and indexes if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    hook_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    session_id TEXT NOT NULL,
                    hook_event_name TEXT NOT NULL,
                    tool_name TEXT,
                    handler_name TEXT,
                    duration_ms REAL,
                    decision TEXT,
                    reason TEXT,
                    input_preview TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    skip_reason TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_hook_id ON events(hook_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")

    def _write(self, event: HookObservabilityEvent) -> None:
        """Insert event into database.

        Note: Errors propagate (not swallowed). Fail-fast for dev tool.
        """
        # Convert datetime to Unix epoch with milliseconds precision
        timestamp = round(event.timestamp.timestamp(), 3)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO events (
                    event_type, hook_id, timestamp, session_id, hook_event_name,
                    tool_name, handler_name, duration_ms, decision, reason,
                    input_preview, error_type, error_message, skip_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_type,
                    event.hook_id,
                    timestamp,
                    event.session_id,
                    event.hook_event_name,
                    event.tool_name,
                    event.handler_name,
                    event.duration_ms,
                    event.decision,
                    event.reason,
                    event.input_preview,
                    event.error_type,
                    event.error_message,
                    event.skip_reason,
                ),
            )

    def on_hook_start(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_hook_end(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_hook_error(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_start(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_end(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_skip(self, event: HookObservabilityEvent) -> None:
        self._write(event)

    def on_handler_error(self, event: HookObservabilityEvent) -> None:
        self._write(event)
```

### Usage

```python
from fasthooks import HookApp
from fasthooks.observability import SQLiteObserver

app = HookApp()
app.add_observer(SQLiteObserver())  # Writes to ~/.fasthooks/studio.db

@app.pre_tool("Bash")
def check(event):
    if "rm -rf" in event.command:
        return deny("Dangerous command")

app.run()
```

### Testing

Tests go in `tests/test_sqlite_observer.py` (separate from `test_observability.py`).

```python
# tests/test_sqlite_observer.py

import sqlite3
from pathlib import Path

import pytest

from fasthooks.observability import SQLiteObserver
from fasthooks.observability.events import HookObservabilityEvent


class TestSQLiteObserver:
    def test_creates_db_and_table(self, tmp_path: Path) -> None:
        """DB and events table created on init."""
        db_path = tmp_path / "test.db"
        SQLiteObserver(db_path)

        assert db_path.exists()
        with sqlite3.connect(db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert ("events",) in tables

    def test_writes_event(self, tmp_path: Path) -> None:
        """Events written to DB."""
        db_path = tmp_path / "test.db"
        observer = SQLiteObserver(db_path)

        event = HookObservabilityEvent(
            event_type="hook_start",
            hook_id="abc-123",
            session_id="session-1",
            hook_event_name="PreToolUse",
            tool_name="Bash",
        )
        observer.on_hook_start(event)

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT * FROM events").fetchall()
            assert len(rows) == 1
            assert rows[0][1] == "hook_start"  # event_type
            assert rows[0][2] == "abc-123"     # hook_id

    def test_timestamp_is_unix_epoch(self, tmp_path: Path) -> None:
        """Timestamp stored as Unix epoch float."""
        db_path = tmp_path / "test.db"
        observer = SQLiteObserver(db_path)

        event = HookObservabilityEvent(
            event_type="hook_start",
            hook_id="abc-123",
            session_id="session-1",
            hook_event_name="PreToolUse",
        )
        observer.on_hook_start(event)

        with sqlite3.connect(db_path) as conn:
            timestamp = conn.execute("SELECT timestamp FROM events").fetchone()[0]
            assert isinstance(timestamp, float)
            assert timestamp > 1700000000  # Sanity check: after 2023

    def test_error_propagates(self, tmp_path: Path) -> None:
        """Errors not swallowed (fail-fast)."""
        db_path = tmp_path / "test.db"
        observer = SQLiteObserver(db_path)

        # Delete the DB to cause error
        db_path.unlink()

        event = HookObservabilityEvent(
            event_type="hook_start",
            hook_id="abc-123",
            session_id="session-1",
            hook_event_name="PreToolUse",
        )

        with pytest.raises(sqlite3.OperationalError):
            observer.on_hook_start(event)
```

---

## Sample Data

Real sample data is available for development and testing:

```
specs/studio/samples/
├── README.md                 # Detailed documentation
├── sample-transcript.jsonl   # Claude Code transcript (11 entries)
└── sample-studio.db          # SQLite DB with hook events (12 rows)
```

See `specs/studio/samples/README.md` for:
- Schema documentation
- Sample queries
- Data correlation examples
- Code snippets for loading/parsing

---

## UI Vision: Conversation View

The studio renders a **conversation view** like Claude Code's TUI, but in a web app. The key insight: **hook events are displayed inline with tool calls**.

### Mockup

```
┌──────────────────────────────────────────────────────────────────────────┐
│ FastHooks Studio                              [Session: 5da894cf...]     │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│ 👤 ! ls ~/.fasthooks/studio.db                                          │
│                                                                          │
│ 🧠 Thinking... ▼                                                        │
│ ┌────────────────────────────────────────────────────────────────────┐  │
│ │ The user wants me to check what's inside a SQLite database file.   │  │
│ │ Let me use sqlite3 to inspect it.                                  │  │
│ └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│ 🔧 Bash(sqlite3 ~/.fasthooks/studio.db ".tables")                       │
│ ┌─ PreToolUse hooks ───────────────────────────────────────────────┐    │
│ │  log_bash  → ✅ allow  0.45ms                                    │    │
│ │  log_all   → ✅ allow  0.19ms                                    │    │
│ │  ────────────────────────────────────────────────                │    │
│ │  Total: 28.1ms                                                   │    │
│ │                                                                  │    │
│ │  [▼ Input Preview]                                               │    │
│ │  {                                                               │    │
│ │    "command": "sqlite3 ~/.fasthooks/studio.db \".tables\"",      │    │
│ │    "tool_use_id": "toolu_0125bgDHg4uhnVskNwrF6xcf"               │    │
│ │  }                                                               │    │
│ └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│ 📥 events                                                               │
│                                                                          │
│ 🧠 Thinking... ▼                                                        │
│ ┌────────────────────────────────────────────────────────────────────┐  │
│ │ There's one table called "events". Let me check its schema and     │  │
│ │ some sample data.                                                  │  │
│ └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│ 🔧 Bash(sqlite3 ~/.fasthooks/studio.db ".schema events" && ...)         │
│ ┌─ PreToolUse hooks ───────────────────────────────────────────────┐    │
│ │  log_bash  → ✅ allow  0.51ms                                    │    │
│ │  log_all   → ✅ allow  0.26ms                                    │    │
│ │  ────────────────────────────────────────────────                │    │
│ │  Total: 35.2ms                                                   │    │
│ └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│ 📥 CREATE TABLE events (...)                                            │
│                                                                          │
│ 💬 **studio.db contents:**                                              │
│    Single table `events` with 12 rows. Tracks FastHooks hook events...  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Deny/Error Highlighting

```
🔧 Bash(rm -rf /tmp/important)
┌─ PreToolUse hooks ───────────────────────────────────────────────┐
│  check_dangerous → ❌ DENY  0.3ms                                │  ← RED
│    reason: "Blocked rm -rf command"                              │
│  log_all         → ⏭️ SKIP (early deny from check_dangerous)    │  ← GRAY
│  ────────────────────────────────────────────────                │
│  Total: 12ms | Final: DENY                                       │
└──────────────────────────────────────────────────────────────────┘
```

### What the UI Shows

| Element | Source | Color |
|---------|--------|-------|
| 👤 User messages | Transcript: `UserMessage` | - |
| 🧠 Thinking blocks | Transcript: `AssistantMessage.content[type=thinking]` | Gray, collapsible |
| 🔧 Tool calls | Transcript: `AssistantMessage.content[type=tool_use]` | - |
| Hook events | SQLite: `events` table (correlated by `tool_use_id`) | Nested under tool |
| ✅ allow | SQLite: `decision='allow'` | Green |
| ❌ deny/block | SQLite: `decision='deny'` or `'block'` | Red |
| ⏭️ skip | SQLite: `event_type='handler_skip'` | Gray |
| 📥 Tool results | Transcript: `UserMessage.content[type=tool_result]` | - |
| 💬 Text responses | Transcript: `AssistantMessage.content[type=text]` | - |

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  SQLite (studio.db)                    Transcript (.jsonl)              │
│  ┌─────────────────────┐               ┌─────────────────────┐          │
│  │ events table        │               │ JSONL entries       │          │
│  │ - hook_id           │               │ - UserMessage       │          │
│  │ - tool_use_id (JSON)│───────────────│ - AssistantMessage  │          │
│  │ - session_id        │               │   - thinking        │          │
│  │ - handler_name      │               │   - tool_use (id)   │          │
│  │ - decision          │               │   - text            │          │
│  │ - duration_ms       │               │ - ToolResult        │          │
│  │ - transcript_path ──┼───────────────│                     │          │
│  └─────────────────────┘               └─────────────────────┘          │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                              CORRELATION                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Get sessions from SQLite (DISTINCT session_id)                      │
│  2. For each session, get transcript_path from input_preview            │
│  3. Load transcript → parse conversation flow                           │
│  4. For each tool_use in transcript:                                    │
│     - Get tool_use_id from ToolUseBlock                                 │
│     - Query SQLite: WHERE json_extract(input_preview, '$.tool_use_id')  │
│     - Get hook_id → fetch all events for that hook                      │
│  5. Render conversation with hook events inline                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Correlation Code

```python
import json
import sqlite3
from fasthooks.transcript import Transcript

def get_session_data(db_path: str, session_id: str) -> dict:
    """Load session with transcript and hook events correlated."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get transcript path
    row = conn.execute(
        "SELECT json_extract(input_preview, '$.transcript_path') as path "
        "FROM events WHERE session_id = ? AND input_preview IS NOT NULL LIMIT 1",
        (session_id,)
    ).fetchone()

    if not row:
        return {"error": "No transcript found"}

    # Load transcript
    transcript = Transcript(row['path'])

    # Build tool_use_id → hook_events map
    tool_hooks = {}
    for tool_use in transcript.tool_uses:
        events = conn.execute(
            "SELECT * FROM events WHERE hook_id = ("
            "  SELECT hook_id FROM events "
            "  WHERE json_extract(input_preview, '$.tool_use_id') = ?"
            ") ORDER BY id",
            (tool_use.id,)
        ).fetchall()
        tool_hooks[tool_use.id] = [dict(e) for e in events]

    return {
        "session_id": session_id,
        "transcript": transcript,
        "tool_hooks": tool_hooks,
        "stats": transcript.stats,
    }
```

---

## Studio Backend

### CLI Command

```bash
fasthooks studio              # Start server on localhost:5555
fasthooks studio --port 8080  # Custom port
fasthooks studio --open       # Open browser automatically
fasthooks studio --db /path/to/studio.db  # Custom DB path
```

### REST API Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /api/sessions` | List all sessions | `[{session_id, tool_count, event_count, first_seen, last_seen}]` |
| `GET /api/sessions/{id}` | Get session detail | `{session_id, transcript_path, stats}` |
| `GET /api/sessions/{id}/conversation` | Full conversation with hooks | `{entries: [...], tool_hooks: {...}}` |
| `GET /api/sessions/{id}/hooks` | All hook events for session | `[{hook_id, events: [...]}]` |
| `GET /api/hooks/{hook_id}` | Single hook detail | `{hook_id, events: [...], input_preview}` |
| `GET /api/stats` | Global statistics | `{total_hooks, deny_rate, avg_latency}` |
| `WS /ws` | WebSocket for real-time | Broadcasts `{type: "db_updated"}` |

### Conversation Endpoint Response

```json
// GET /api/sessions/5da894cf.../conversation
{
  "session_id": "5da894cf-39f2-4285-8dad-323adb2d00ef",
  "entries": [
    {
      "type": "user_message",
      "content": "! ls ~/.fasthooks/studio.db"
    },
    {
      "type": "thinking",
      "content": "The user wants me to check what's inside..."
    },
    {
      "type": "tool_use",
      "id": "toolu_0125bgDHg4uhnVskNwrF6xcf",
      "name": "Bash",
      "input": {"command": "sqlite3 ~/.fasthooks/studio.db \".tables\""},
      "hooks": {
        "hook_id": "f98d4d9d-bb98-4e07-92d9-7d6c0dba3d04",
        "hook_event_name": "PreToolUse",
        "total_duration_ms": 28.1,
        "handlers": [
          {"name": "log_bash", "decision": "allow", "duration_ms": 0.45},
          {"name": "log_all", "decision": "allow", "duration_ms": 0.19}
        ]
      }
    },
    {
      "type": "tool_result",
      "tool_use_id": "toolu_0125bgDHg4uhnVskNwrF6xcf",
      "content": "events"
    },
    {
      "type": "thinking",
      "content": "There's one table called \"events\"..."
    },
    // ... more entries
    {
      "type": "text",
      "content": "**studio.db contents:**\n\nSingle table `events`..."
    }
  ],
  "stats": {
    "tokens_in": 46,
    "tokens_out": 443,
    "messages": 9,
    "turns": 3,
    "tool_calls": 2,
    "hooks_fired": 2,
    "total_hook_time_ms": 63.3
  }
}
```

### Server Structure

```
src/fasthooks/studio/
├── __init__.py
├── __main__.py              # CLI entry point (argparse + uvicorn)
├── server.py                # FastAPI app factory
├── connection_manager.py    # WebSocket broadcast hub
├── config.py                # Server configuration
├── routes/
│   ├── __init__.py
│   ├── sessions.py          # /api/sessions endpoints
│   ├── hooks.py             # /api/hooks endpoints
│   └── stats.py             # /api/stats endpoint
├── services/
│   ├── __init__.py
│   ├── db.py                # SQLite connection + queries
│   └── transcript.py        # Transcript loading + parsing
└── models.py                # Pydantic response models
```

---

## Studio Frontend

React app with conversation view.

### Decision: React + Vite

**Why React (not vanilla JS or HTMX):**
- WebSocket + cache invalidation is natural with React Query
- Collapsible blocks, JSON viewers need component state
- ell-studio uses this pattern and it works well
- Can bundle into `studio/static/` for distribution

**Design inspiration from ell-studio:**
- Will borrow CSS patterns and styling approach later
- Reference: `/tmp/ell/ell-studio/src/` for component patterns
- Dev-friendly dark theme, clean typography

### Tech Stack

| Library | Purpose |
|---------|---------|
| Vite | Build tool (fast, simple) |
| React 18 | UI framework |
| @tanstack/react-query | Data fetching + cache invalidation |
| Tailwind CSS | Utility-first styling |
| WebSocket (native) | Real-time updates |

### Project Structure

```
studio-frontend/
├── package.json
├── vite.config.ts
├── index.html
├── tailwind.config.js
├── src/
│   ├── main.tsx              # Entry point
│   ├── App.tsx               # Layout + routing
│   ├── api.ts                # Fetch helpers for /api/*
│   ├── hooks/
│   │   ├── useWebSocket.ts   # WS connection + query invalidation
│   │   ├── useSessions.ts    # GET /api/sessions
│   │   └── useConversation.ts # GET /api/sessions/{id}/conversation
│   ├── components/
│   │   ├── SessionList.tsx     # Sidebar with sessions
│   │   ├── ConversationView.tsx # Main conversation display
│   │   ├── entries/
│   │   │   ├── UserMessage.tsx
│   │   │   ├── ThinkingBlock.tsx   # Collapsible
│   │   │   ├── ToolUse.tsx         # With nested HookEvents
│   │   │   ├── ToolResult.tsx
│   │   │   └── TextBlock.tsx
│   │   ├── HookEvents.tsx      # Handler list with timing/decision
│   │   ├── InputPreview.tsx    # Expandable JSON viewer
│   │   └── StatsBar.tsx        # Session statistics
│   └── utils/
│       └── formatters.ts       # Duration, timestamp formatting
└── dist/                       # Built output → copy to studio/static/
```

### Build & Distribution

```bash
# Development
cd studio-frontend
npm install
npm run dev          # Vite dev server on :5173, proxies API to :5555

# Production build
npm run build        # Creates dist/
cp -r dist/* ../src/fasthooks/studio/static/
```

The FastAPI server serves `studio/static/` in production mode.

### Key Components

**ConversationView.tsx**
```tsx
function ConversationView({ sessionId }: { sessionId: string }) {
  const { data, isLoading } = useConversation(sessionId);

  if (isLoading) return <Spinner />;

  return (
    <div className="conversation">
      {data.entries.map((entry, i) => {
        switch (entry.type) {
          case 'user_message':
            return <UserMessage key={i} content={entry.content} />;
          case 'thinking':
            return <ThinkingBlock key={i} content={entry.content} />;
          case 'tool_use':
            return (
              <ToolUse key={i} entry={entry}>
                <HookEvents hooks={entry.hooks} />
              </ToolUse>
            );
          case 'tool_result':
            return <ToolResult key={i} content={entry.content} />;
          case 'text':
            return <TextBlock key={i} content={entry.content} />;
        }
      })}
    </div>
  );
}
```

**HookEvents.tsx**
```tsx
function HookEvents({ hooks }: { hooks: HookData }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="hook-events border-l-2 border-blue-500 ml-4 pl-4">
      <div className="hook-header text-sm text-gray-500">
        {hooks.hook_event_name} hooks ({hooks.total_duration_ms.toFixed(1)}ms)
      </div>

      {hooks.handlers.map((h, i) => (
        <div key={i} className="handler flex items-center gap-2">
          <span className="handler-name font-mono">{h.name}</span>
          <span className="arrow">→</span>
          <DecisionBadge decision={h.decision} />
          <span className="duration text-gray-400">{h.duration_ms.toFixed(2)}ms</span>
          {h.reason && <span className="reason text-red-500">"{h.reason}"</span>}
        </div>
      ))}

      <button onClick={() => setExpanded(!expanded)}>
        {expanded ? '▼' : '▶'} Input Preview
      </button>
      {expanded && <JsonViewer data={hooks.input_preview} />}
    </div>
  );
}

function DecisionBadge({ decision }: { decision: string }) {
  const styles = {
    allow: 'bg-green-100 text-green-800',
    deny: 'bg-red-100 text-red-800',
    block: 'bg-red-200 text-red-900',
    skip: 'bg-gray-100 text-gray-500',
  };
  const icons = { allow: '✅', deny: '❌', block: '🚫', skip: '⏭️' };

  return (
    <span className={`badge px-2 py-0.5 rounded ${styles[decision]}`}>
      {icons[decision]} {decision}
    </span>
  );
}
```

---

## Implementation Order

1. ~~**SQLiteObserver**~~ ✅ Implemented
2. ~~**Verify data**~~ ✅ Sample data in `specs/studio/samples/`
3. ~~**Studio server**~~ ✅ FastAPI with conversation endpoint
4. ~~**File watcher**~~ ✅ Poll DB every 500ms, WebSocket broadcast
5. ~~**Studio frontend**~~ ✅ React conversation view in `studio-frontend/`
6. ~~**CLI command**~~ ✅ `fasthooks studio` runs server + serves bundled frontend
7. ~~**Packaging**~~ ✅ `pip install fasthooks[studio]`

---

## Debugging Use Cases

The studio helps developers debug these scenarios:

| Question | How Studio Answers |
|----------|-------------------|
| "Why did my handler deny this?" | See input + decision + reason inline |
| "Is my handler even being called?" | See handler_start/handler_end events |
| "What did the hook receive?" | Expand input_preview JSON |
| "How slow is my handler?" | duration_ms per handler |
| "What order do handlers run?" | Event sequence visible |
| "What was Claude thinking before the tool call?" | Full transcript context |
| "Why was my handler skipped?" | See skip_reason |
| "What happened after the deny?" | See subsequent conversation |

---

## Future Considerations

| Feature | When | Notes |
|---------|------|-------|
| Filter by decision | v1 | "Show only denies" checkbox |
| Search | v1+ | Find by command pattern |
| Real-time updates | v1 | WebSocket + React Query invalidation |
| Multiple sessions | v1 | Session list sidebar |
| Handler timing charts | v2 | Visualize latency over time |
| Export session | v2 | Download as JSON |
| Diff view | v3 | Compare handler behavior |
| Retention policy | If needed | Auto-delete old events |

---

## References

### Sample Data

| File | Purpose |
|------|---------|
| `specs/studio/samples/README.md` | Detailed data documentation |
| `specs/studio/samples/sample-transcript.jsonl` | Real Claude Code transcript |
| `specs/studio/samples/sample-studio.db` | Real hook events |

### ell-studio Files (for implementation reference)

| File | Line Numbers | What to Study |
|------|--------------|---------------|
| `/tmp/ell/src/ell/studio/server.py` | 36-65 | App factory pattern, WebSocket setup |
| `/tmp/ell/src/ell/studio/server.py` | 198-203 | `notify_clients()` attached to app |
| `/tmp/ell/src/ell/studio/__main__.py` | 74-109 | File watcher implementation |
| `/tmp/ell/src/ell/studio/connection_manager.py` | 1-18 | Full WebSocket manager |
| `/tmp/ell/ell-studio/src/hooks/useBackend.js` | 22-59 | WebSocket + React Query invalidation |
| `/tmp/ell/src/ell/stores/sql.py` | 35-50 | SQLModel engine setup |

### fasthooks Files

| File | Relevance |
|------|-----------|
| `specs/observability.md` | BaseObserver, HookObservabilityEvent definitions |
| `src/fasthooks/observability/observers/sqlite.py` | SQLiteObserver implementation |
| `src/fasthooks/transcript/core.py` | Transcript loading and parsing |
