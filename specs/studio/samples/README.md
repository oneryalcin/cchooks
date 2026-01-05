# Studio Sample Data

Real data from a Claude Code session with FastHooks enabled. Use these files to understand data structures and test studio implementations.

## Files

| File | Description |
|------|-------------|
| `sample-transcript.jsonl` | Claude Code transcript (11 entries) |
| `sample-studio.db` | SQLite DB with hook events (12 rows) |

## Session Context

- **Session ID**: `5da894cf-39f2-4285-8dad-323adb2d00ef`
- **What happened**: User asked Claude to inspect `~/.fasthooks/studio.db`
- **Tools called**: 2x `Bash` (sqlite3 commands)
- **Hooks fired**: 2 hook invocations, each with 2 handlers (`log_bash`, `log_all`)

---

## sample-studio.db

SQLite database with hook events.

### Schema

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,        -- hook_start, handler_start, handler_end, hook_end
    hook_id TEXT NOT NULL,           -- UUID grouping events for one hook invocation
    timestamp REAL NOT NULL,         -- Unix epoch (milliseconds precision)
    session_id TEXT NOT NULL,        -- Claude Code session UUID
    hook_event_name TEXT NOT NULL,   -- PreToolUse, PostToolUse, Stop, etc.
    tool_name TEXT,                  -- Bash, Write, Edit, etc.
    handler_name TEXT,               -- Function name (log_bash, log_all, etc.)
    duration_ms REAL,                -- Execution time (on *_end events)
    decision TEXT,                   -- allow, deny, block (on handler_end)
    reason TEXT,                     -- Denial reason if any
    input_preview TEXT,              -- Full hook input JSON (on hook_start only)
    error_type TEXT,                 -- Exception class name
    error_message TEXT,              -- Exception message
    skip_reason TEXT                 -- Why handler was skipped
);
```

### Event Flow (per tool call)

```
hook_start      ─┐
handler_start    │  handler 1
handler_end     ─┤
handler_start    │  handler 2
handler_end     ─┤
hook_end        ─┘
```

### Sample Data (12 rows)

**Hook invocation 1** (`hook_id: f98d4d9d-bb98-4e07-92d9-7d6c0dba3d04`):

| id | event_type | handler_name | duration_ms | decision |
|----|------------|--------------|-------------|----------|
| 1 | hook_start | - | - | - |
| 2 | handler_start | log_bash | - | - |
| 3 | handler_end | log_bash | 0.45 | allow |
| 4 | handler_start | log_all | - | - |
| 5 | handler_end | log_all | 0.19 | allow |
| 6 | hook_end | - | 28.1 | - |

**Hook invocation 2** (`hook_id: a6217534-7fb4-4c95-932f-268fe6dc70c4`):

| id | event_type | handler_name | duration_ms | decision |
|----|------------|--------------|-------------|----------|
| 7 | hook_start | - | - | - |
| 8 | handler_start | log_bash | - | - |
| 9 | handler_end | log_bash | 0.51 | allow |
| 10 | handler_start | log_all | - | - |
| 11 | handler_end | log_all | 0.26 | allow |
| 12 | hook_end | - | 35.2 | - |

### input_preview JSON (on hook_start)

```json
{
  "session_id": "5da894cf-39f2-4285-8dad-323adb2d00ef",
  "transcript_path": "/Users/.../.claude/projects/.../5da894cf-....jsonl",
  "cwd": "/private/tmp/fh/myell/myhk",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {
    "command": "sqlite3 ~/.fasthooks/studio.db \".tables\"",
    "description": "List tables in studio.db"
  },
  "tool_use_id": "toolu_0125bgDHg4uhnVskNwrF6xcf"
}
```

**Key fields for correlation:**
- `tool_use_id` → matches `ToolUseBlock.id` in transcript
- `transcript_path` → path to load full transcript
- `session_id` → groups all events in a session

### Useful Queries

```bash
# All events for a session
sqlite3 sample-studio.db "SELECT * FROM events WHERE session_id = '5da894cf-39f2-4285-8dad-323adb2d00ef'"

# Events grouped by hook_id
sqlite3 sample-studio.db "SELECT hook_id, GROUP_CONCAT(event_type) FROM events GROUP BY hook_id"

# Handler timing
sqlite3 sample-studio.db "SELECT handler_name, AVG(duration_ms) FROM events WHERE event_type='handler_end' GROUP BY handler_name"

# Get tool_use_id for correlation
sqlite3 sample-studio.db "SELECT json_extract(input_preview, '$.tool_use_id') FROM events WHERE input_preview IS NOT NULL"
```

---

## sample-transcript.jsonl

Claude Code transcript in JSONL format (11 entries).

### Entry Types

| Type | Count | Description |
|------|-------|-------------|
| Entry | 1 | Session metadata |
| FileHistorySnapshot | 1 | File state at session start |
| UserMessage | 3 | User prompts + tool results |
| AssistantMessage | 6 | Claude responses |

### Conversation Flow

```
Entry (session metadata)
FileHistorySnapshot
UserMessage: "! ls ~/.fasthooks/studio.db"
  AssistantMessage:
    - thinking: "The user wants me to check..."
    - tool_use: Bash(sqlite3 ... ".tables")
  AssistantMessage: (continuation)
UserMessage: tool_result for toolu_0125...
  AssistantMessage:
    - thinking: "There's one table called events..."
    - tool_use: Bash(sqlite3 ... ".schema")
  AssistantMessage: (continuation)
UserMessage: tool_result for toolu_01TQ...
  AssistantMessage:
    - thinking: "The database contains..."
    - text: "**studio.db contents:**..."
  AssistantMessage: (continuation)
```

### Loading with FastHooks

```python
from fasthooks.transcript import Transcript

t = Transcript("specs/studio/samples/sample-transcript.jsonl")

# Basic info
print(f"Entries: {len(t.entries)}")
print(f"Stats: {t.stats}")  # TranscriptStats(tokens=46in/443out, messages=9, turns=3)

# Tool uses
for tu in t.tool_uses:
    print(f"{tu.name}: {tu.id}")
    # Bash: toolu_0125bgDHg4uhnVskNwrF6xcf
    # Bash: toolu_01TQCzJs43dPKWhXKrqaL5ju

# Find specific tool use
tool = t.find_tool_use("toolu_0125bgDHg4uhnVskNwrF6xcf")
print(tool.input)  # {'command': 'sqlite3 ...', 'description': '...'}
```

### AssistantMessage Content Blocks

```python
for entry in t.all_entries:
    if type(entry).__name__ == 'AssistantMessage':
        for block in entry.content:
            if block.type == 'thinking':
                print(f"🧠 {block.thinking[:50]}...")
            elif block.type == 'text':
                print(f"💬 {block.text[:50]}...")
            elif block.type == 'tool_use':
                print(f"🔧 {block.name}({block.id})")
```

---

## Correlating Data

The key to the studio UI is correlating hook events with transcript entries.

### Flow

```
┌─────────────────────┐
│ SQLite: events      │
│   tool_use_id ──────┼──────┐
│   transcript_path ──┼────┐ │
└─────────────────────┘    │ │
                           │ │
┌─────────────────────┐    │ │
│ Transcript.jsonl    │◄───┘ │
│   ToolUseBlock.id ◄─┼──────┘
└─────────────────────┘
```

### Code Example

```python
import json
import sqlite3
from fasthooks.transcript import Transcript

# 1. Get session data from SQLite
conn = sqlite3.connect("specs/studio/samples/sample-studio.db")
conn.row_factory = sqlite3.Row

# 2. Get unique sessions
sessions = conn.execute(
    "SELECT DISTINCT session_id, json_extract(input_preview, '$.transcript_path') as path "
    "FROM events WHERE input_preview IS NOT NULL"
).fetchall()

for session in sessions:
    session_id = session['session_id']
    transcript_path = session['path']

    # 3. Load transcript
    # Note: In sample, path points to original location. Update for your setup.
    t = Transcript("specs/studio/samples/sample-transcript.jsonl")

    # 4. For each tool use in transcript, find hook events
    for tool_use in t.tool_uses:
        tool_use_id = tool_use.id

        # 5. Get hook events for this tool use
        events = conn.execute(
            "SELECT * FROM events WHERE json_extract(input_preview, '$.tool_use_id') = ?",
            (tool_use_id,)
        ).fetchall()

        if events:
            hook_id = events[0]['hook_id']
            all_hook_events = conn.execute(
                "SELECT event_type, handler_name, duration_ms, decision "
                "FROM events WHERE hook_id = ? ORDER BY id",
                (hook_id,)
            ).fetchall()

            print(f"\n🔧 {tool_use.name}: {tool_use.input.get('command', '')[:40]}...")
            for e in all_hook_events:
                if e['handler_name']:
                    print(f"   {e['event_type']}: {e['handler_name']} → {e['decision']} ({e['duration_ms']:.2f}ms)" if e['duration_ms'] else f"   {e['event_type']}: {e['handler_name']}")
                else:
                    print(f"   {e['event_type']}: total {e['duration_ms']:.1f}ms" if e['duration_ms'] else f"   {e['event_type']}")
```

### Expected Output

```
🔧 Bash: sqlite3 ~/.fasthooks/studio.db ".tables"...
   hook_start
   handler_start: log_bash
   handler_end: log_bash → allow (0.45ms)
   handler_start: log_all
   handler_end: log_all → allow (0.19ms)
   hook_end: total 28.1ms

🔧 Bash: sqlite3 ~/.fasthooks/studio.db ".schema ev...
   hook_start
   handler_start: log_bash
   handler_end: log_bash → allow (0.51ms)
   handler_start: log_all
   handler_end: log_all → allow (0.26ms)
   hook_end: total 35.2ms
```

---

## Notes

- Sample data was generated on 2026-01-04
- Both handlers (`log_bash`, `log_all`) always return `allow` (no blocking)
- The transcript path in `input_preview` points to the original location; update for your setup
- Session has 2 tool calls, each generating 6 hook events (12 total)
