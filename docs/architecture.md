# Architecture

Low-level internals for contributors and advanced users.

## Claude Code File Layout

```
~/.claude/
├── settings.json              # Global settings
├── settings.local.json        # Local overrides
├── CLAUDE.md                  # Global instructions
├── history.jsonl              # Command history
│
├── projects/                  # Per-project data
│   └── <escaped-cwd>/         # e.g. -Users-john-myproject
│       ├── <session-id>.jsonl     # Main transcript
│       ├── agent-<id>.jsonl       # Subagent sidechains
│       └── <session-id>/          # Session folder (rare)
│
├── session-env/               # Session environment data
├── file-history/              # File change history
├── plans/                     # Plan mode files
└── debug/                     # Debug logs
```

### Path Escaping

Claude Code escapes the working directory path by replacing `/` with `-`:

```
/Users/john/myproject    →  -Users-john-myproject
/tmp/test                →  -tmp-test
/private/tmp/foo         →  -private-tmp-foo
```

### Transcript Files

Each session has a main transcript file:
```
~/.claude/projects/-Users-john-myproject/abc123-def456.jsonl
                   └── escaped cwd ──────┘└─ session id ─┘
```

Subagent sidechains (spawned via Task tool) are stored alongside:
```
~/.claude/projects/-Users-john-myproject/agent-a1b2c3d.jsonl
```

---

## Hook Invocation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Claude Code (parent process)                                    │
│                                                                 │
│  1. User action triggers hook event                             │
│  2. Claude Code spawns hook subprocess                          │
│  3. Writes JSON to stdin:                                       │
│     {                                                           │
│       "session_id": "abc123-...",                               │
│       "hook_event_name": "PreToolUse",                          │
│       "transcript_path": "~/.claude/projects/.../abc.jsonl",    │
│       "cwd": "/Users/john/myproject",                           │
│       "tool_name": "Bash",                                      │
│       "tool_input": {"command": "ls -la"}                       │
│     }                                                           │
│  4. Reads hook's stdout for response                            │
│  5. Applies decision (allow/deny/block)                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ fasthooks (hook subprocess)                                     │
│                                                                 │
│  app.run()                                                      │
│    │                                                            │
│    ├─> _internal/io.py: read_stdin()                            │
│    │     └─> Parse JSON from stdin                              │
│    │                                                            │
│    ├─> _dispatch(data)                                          │
│    │     ├─> Route by hook_event_name                           │
│    │     ├─> Parse into typed Event (Bash, Write, etc.)         │
│    │     └─> Find matching handlers                             │
│    │                                                            │
│    ├─> _run_with_middleware(handlers, event)                    │
│    │     ├─> For each handler:                                  │
│    │     │     ├─> _resolve_deps() → inject Transcript, State   │
│    │     │     └─> Call handler(event, **deps)                  │
│    │     └─> Return first deny/block response                   │
│    │                                                            │
│    └─> _internal/io.py: write_stdout(response)                  │
│          └─> Write JSON response                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Dependency Injection

fasthooks injects dependencies based on type hints:

```python
@app.pre_tool("Bash")
def check(event, transcript: Transcript, state: State):
    #          ↑                 ↑              ↑
    #      auto-passed     DI-injected    DI-injected
```

### How DI Works (app.py:_resolve_deps)

```python
def _resolve_deps(self, handler, event, cache):
    hints = get_type_hints(handler)

    for param_name, hint in hints.items():
        if hint is Transcript:
            # Extract path from event, create Transcript
            transcript_path = getattr(event, "transcript_path", None)
            deps[param_name] = Transcript(transcript_path)

        elif hint is State:
            # Create session-scoped State
            deps[param_name] = State.for_session(
                event.session_id,
                state_dir=self.state_dir
            )
```

### Dependency Caching

Dependencies are cached per-event to avoid redundant work:

```python
# If multiple handlers request Transcript, same instance is reused
cache = {}
for handler in handlers:
    deps = _resolve_deps(handler, event, cache)  # cache shared
    handler(event, **deps)
```

---

## Module Independence

The transcript module is **standalone** - usable without hooks:

```
fasthooks/
├── app.py                    # HookApp - imports transcript
├── depends/
│   └── transcript.py         # Re-exports for DI convenience
└── transcript/               # STANDALONE MODULE
    ├── core.py               # Transcript class
    ├── entries.py            # Entry types
    ├── query.py              # TranscriptQuery
    └── ...
```

### Standalone Usage

```python
# No HookApp, no events - just Transcript
from fasthooks.transcript import Transcript

t = Transcript("/path/to/transcript.jsonl")
t.query().assistants().with_tools().all()
t.stats.input_tokens
```

### Hook-Integrated Usage

```python
# Via DI - path extracted from event automatically
from fasthooks.depends import Transcript

@app.pre_tool("Bash")
def check(event, transcript: Transcript):
    # transcript already loaded with correct session
    pass
```

---

## Event Routing

```python
TOOL_EVENT_MAP = {
    "Bash": Bash,
    "Write": Write,
    "Read": Read,
    "Edit": Edit,
    ...
}

# _dispatch routes by hook_event_name:
# - PreToolUse/PostToolUse → tool handlers + catch-all ("*")
# - Stop/SessionStart/etc. → lifecycle handlers
```

### Handler Resolution Order

1. Tool-specific handlers: `@app.pre_tool("Bash")`
2. Catch-all handlers: `@app.pre_tool()` (matches all tools)
3. First deny/block response wins

---

## Transcript Internals

### Lazy Loading

Transcript data is loaded on first access:

```python
class Transcript:
    def __init__(self, path):
        self.path = Path(path) if path else None
        self._loaded = False
        self.entries = []

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()  # Parse JSONL file
            self._loaded = True

    @property
    def stats(self):
        self._ensure_loaded()  # Triggers load if needed
        return self._stats
```

### Entry Types

```
TranscriptEntry (union type)
├── UserMessage         # User input
├── AssistantMessage    # Claude response (may contain tool_use blocks)
├── SystemEntry         # System messages, summaries
└── FileHistorySnapshot # File state snapshots (not an Entry subclass)
```

### Indexing

Transcript maintains indexes for fast lookups:

```python
self._by_uuid: dict[str, Entry] = {}           # UUID → Entry
self._children: dict[str, list[Entry]] = {}    # parent_uuid → children
```

---

## Response Protocol

Hooks respond via stdout JSON:

```python
# Allow (continue execution)
{"decision": "allow"}

# Allow with message to user
{"decision": "allow", "hookSpecificOutput": {"message": "Approved"}}

# Deny (block this action, continue session)
{"decision": "deny", "reason": "Not allowed"}

# Block (show error to Claude, may retry)
{"decision": "block", "reason": "Rate limited"}
```

Exit codes:
- `0`: Success (response parsed)
- `2`: Blocking error (stderr shown to Claude)

---

## State Persistence

State is session-scoped and persisted to JSON:

```
<state_dir>/<session_id>.json
```

```python
state = State.for_session("abc123", state_dir="/tmp/state")
state["count"] = 1
state.save()  # Writes to /tmp/state/abc123.json
```

---

## Background Tasks

Tasks run in separate processes, results retrieved later:

```python
@app.pre_tool("Write")
def on_write(event, tasks: Tasks):
    tasks.add(analyze, event.content)  # Enqueue

@app.on_prompt()
def check(event, tasks: Tasks):
    if result := tasks.pop(analyze):   # Retrieve
        return allow(message=result)
```

Backend options:
- `InMemoryBackend`: Default, single-process
- Custom backends for distributed execution

---

## CLI Architecture

The fasthooks CLI (`fasthooks init`, `install`, `uninstall`, `status`) bridges user's Python hooks with Claude Code's JSON configuration.

### Install Flow

```
fasthooks install .claude/hooks.py
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Validate hooks.py                                        │
│    - Run in subprocess (isolated from CLI process)          │
│    - Catches syntax errors, import errors                   │
│    - 10-second timeout prevents hangs                       │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Introspect HookApp                                       │
│    - Find `app` variable (HookApp instance)                 │
│    - Extract registered handlers from internal structures   │
│    - Build list: ["PreToolUse:Bash", "PostToolUse:*", ...]  │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Generate settings.json configuration                     │
│    - Build command: uv run --with fasthooks "$CLAUDE_..."   │
│    - Group handlers by event type                           │
│    - Combine matchers with | (e.g., "Bash|Write")           │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Merge with existing settings                             │
│    - Read existing settings.json (supports JSONC/comments)  │
│    - Remove our old entries (by command match)              │
│    - Add new entries                                        │
│    - Preserve other hooks (different commands)              │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Write lock file                                          │
│    - Records: hooks_path, handlers, command, timestamp      │
│    - Enables clean uninstall and status checking            │
└─────────────────────────────────────────────────────────────┘
```

### Lock File Format

```json
{
  "version": 1,
  "installed_at": "2024-01-15T10:30:00Z",
  "hooks_path": ".claude/hooks.py",
  "hooks_registered": ["PreToolUse:Bash", "PostToolUse:*", "Stop"],
  "settings_file": ".claude/settings.json",
  "command": "uv run --with fasthooks \"$CLAUDE_PROJECT_DIR/.claude/hooks.py\""
}
```

### Path Handling

The CLI uses `$CLAUDE_PROJECT_DIR` for portable paths:

```python
# Generated command in settings.json
"uv run --with fasthooks \"$CLAUDE_PROJECT_DIR/.claude/hooks.py\""
#                          └── Claude Code provides this at runtime
```

This allows settings.json to be committed to git and work across machines.

### Scope Resolution

```
get_settings_path(scope, project_root):
    project → project_root/.claude/settings.json
    user    → ~/.claude/settings.json
    local   → project_root/.claude/settings.local.json

get_lock_path(scope, project_root):
    project → project_root/.claude/.fasthooks.lock
    user    → ~/.claude/.fasthooks.lock
    local   → project_root/.claude/.fasthooks.local.lock
```

### Introspection Safety

User hooks.py may have side effects at import time (db connections, prints, etc.). The CLI runs introspection in a **subprocess** to:

1. Isolate side effects from CLI process
2. Catch crashes without killing CLI
3. Enforce 10-second timeout
4. Prevent environment pollution
