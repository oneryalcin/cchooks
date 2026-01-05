# Studio

Visual debugger for hooks. See exactly what your hooks receive and how they respond.

## What is Studio?

Studio shows Claude's conversation with **hook events inline**:

```
👤 User: "delete the temp files"

🧠 Thinking: "I'll use rm to clean up..."

🔧 Bash(rm -rf /tmp/old-*)
   ┌─ PreToolUse hooks ─────────────────────────────┐
   │  check_dangerous  → ✅ allow   0.8ms          │
   │  log_commands     → ✅ allow   0.2ms          │
   │  Total: 15.2ms                                 │
   └────────────────────────────────────────────────┘

📥 Removed 3 files

💬 Done! Cleaned up the temp files.
```

You see:
- What Claude was thinking
- What tool it called
- **Which handlers ran and what they decided**
- How long each handler took
- The tool output

## Installation

```bash
pip install fasthooks[studio]
# or
uv add fasthooks[studio]
```

## Quick Start

### 1. Add SQLiteObserver to your hooks

```python
from fasthooks import HookApp
from fasthooks.observability import SQLiteObserver

app = HookApp()
app.add_observer(SQLiteObserver())  # Writes to ~/.fasthooks/studio.db

@app.pre_tool("Bash")
def check_bash(event):
    if "rm -rf /" in event.command:
        return deny("Blocked dangerous command")

app.run()
```

### 2. Run your hooks in Claude Code

```bash
fasthooks install .claude/hooks.py
claude  # Run Claude Code with your hooks
```

### 3. Launch Studio

```bash
fasthooks studio --open
```

Opens http://localhost:5555 in your browser.

## Studio UI

### Session List (Sidebar)

Shows all Claude sessions that have hook events:

- Session ID (truncated)
- Number of hooks fired
- Number of events captured
- Last activity time

Click a session to view its conversation.

### Conversation View (Main)

Shows the full conversation with hooks inline:

| Element | What it shows |
|---------|---------------|
| 👤 User | User messages |
| 🧠 Thinking | Claude's reasoning (collapsible) |
| 🔧 Tool | Tool calls with inline hook events |
| 📥 Output | Tool results |
| 💬 Assistant | Claude's responses |

### Hook Events Panel

Under each tool call, you see:

```
┌─ PreToolUse hooks ─────────────────────────────┐
│  handler_name  → ✅ allow   0.45ms            │
│  another_one   → ✅ allow   0.19ms            │
│  ────────────────────────────────────────────  │
│  Total: 28.1ms                                 │
└────────────────────────────────────────────────┘
```

- **Handler name**: Your function name
- **Decision**: ✅ allow, ❌ deny, 🚫 block, ⏭️ skip
- **Duration**: How long the handler took
- **Reason**: Why it denied (if applicable)

Click to expand input preview (the JSON your handler received).

### Real-time Updates

Studio updates automatically when new events arrive:

- WebSocket connection to server
- "Live" indicator in footer
- No need to refresh

## CLI Options

```bash
fasthooks studio [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | `~/.fasthooks/studio.db` | Path to SQLite database |
| `--host` | `127.0.0.1` | Host to bind server to |
| `--port` | `5555` | Port to bind server to |
| `--open` | `false` | Open browser automatically |
| `--verbose` | `false` | Enable debug logging |

**Examples:**

```bash
# Default (localhost:5555)
fasthooks studio

# Auto-open browser
fasthooks studio --open

# Custom port
fasthooks studio --port 8080

# Debug a specific database
fasthooks studio --db /path/to/debug.db --verbose
```

## Debugging Workflows

### "Why did my handler deny this?"

1. Find the tool call in the conversation
2. Expand the hook events panel
3. Look for ❌ deny - shows handler name and reason
4. Click "Input" to see what the handler received

### "Is my handler even running?"

1. Check if events appear in studio
2. If no events: Is SQLiteObserver added to your app?
3. If events but no handler: Check your matcher (`@app.pre_tool("Bash")`)

### "My handler is slow"

1. Look at duration_ms for each handler
2. Find the slow one
3. Optimize or move heavy work to background tasks

### "What did Claude see after my deny?"

1. Find the denied tool call
2. Look at subsequent messages
3. Claude typically explains why it couldn't proceed

## Throwable Database

The studio database is **disposable**:

```bash
rm ~/.fasthooks/studio.db
```

No migrations, no schema versions. Delete it anytime - SQLiteObserver recreates it on next run.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Your Hooks     │────▶│  SQLite DB   │◀────│  File Watcher   │
│  (SQLiteObserver)     │  (studio.db) │     │  (polls changes) │
└─────────────────┘     └──────────────┘     └────────┬────────┘
                                                      │
                                                      ▼
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  React Frontend │◀────│  WebSocket   │◀────│  FastAPI Server │
│  (browser)      │     │  (broadcast) │     │  (REST + WS)    │
└─────────────────┘     └──────────────┘     └─────────────────┘
```

1. Your hooks write events via SQLiteObserver
2. Server polls database for changes
3. Server broadcasts "updated" via WebSocket
4. Frontend refetches data automatically

## API Endpoints

For advanced users / custom integrations:

| Endpoint | Description |
|----------|-------------|
| `GET /api/sessions` | List all sessions |
| `GET /api/sessions/{id}/conversation` | Get conversation with hooks inline |
| `GET /api/sessions/{id}/hooks` | Get all hook events for session |
| `GET /api/hooks/{hook_id}` | Get single hook detail |
| `GET /api/stats` | Global statistics |
| `WS /ws` | WebSocket for real-time updates |

## Troubleshooting

### "No sessions in studio"

1. Did you add `SQLiteObserver()` to your hooks?
2. Did you run Claude Code after adding it?
3. Check the database exists: `ls ~/.fasthooks/studio.db`

### "Events not updating"

1. Check "Live" indicator in footer
2. If "Disconnected": refresh the page
3. Check server console for errors

### "Can't connect to studio"

1. Is the server running? `fasthooks studio`
2. Check port isn't in use: `lsof -i :5555`
3. Try different port: `fasthooks studio --port 8080`

## Next Steps

- [Observability](observability.md) - Learn about observers
- [CLI Reference](cli.md) - All CLI commands
- [Testing](tutorial/testing.md) - Test hooks without studio
