# Transcript & Context Engineering

The transcript is Claude's memory - a JSONL file containing the entire conversation history. **It's mutable**: edit it, and you edit what Claude remembers.

> "Claude only knows what's in the transcript. Modify it, and Claude's memory changes."

## Quick Start

```python
from fasthooks import HookApp
from fasthooks.depends import Transcript

app = HookApp()

@app.on_prompt()
def inject_context(event, transcript: Transcript):
    """Add context before Claude responds."""
    from fasthooks.transcript import UserMessage

    # Create a "memory" that user mentioned type hints
    reminder = UserMessage.create(
        "Remember: always use type hints in this project",
        context=transcript.entries[-1]  # Copy metadata from last entry
    )
    transcript.insert(0, reminder)  # Insert at start
    transcript.save()
```

## The Transcript Model

### Loading a Transcript

```python
from fasthooks.transcript import Transcript

# From path
t = Transcript("/path/to/transcript.jsonl")

# In hooks - auto-injected via DI
@app.pre_tool("Bash")
def check(event, transcript: Transcript):
    print(f"Entries: {len(transcript.entries)}")
```

### Entry Types

| Type | Description |
|------|-------------|
| `UserMessage` | User input or tool results |
| `AssistantMessage` | Claude's responses |
| `SystemEntry` | System events (compaction, hooks) |
| `FileHistorySnapshot` | File backup for undo |

```python
from fasthooks.transcript import UserMessage, AssistantMessage

for entry in transcript.entries:
    if isinstance(entry, UserMessage):
        print(f"User: {entry.text[:50]}...")
    elif isinstance(entry, AssistantMessage):
        print(f"Claude: {entry.text[:50]}...")
        if entry.has_tool_use:
            for tu in entry.tool_uses:
                print(f"  Tool: {tu.name}")
```

### Content Blocks

Assistant messages contain content blocks:

```python
for entry in transcript.assistant_messages:
    # Text content
    print(entry.text)

    # Thinking (extended thinking mode)
    if entry.thinking:
        print(f"Thinking: {entry.thinking[:100]}...")

    # Tool uses
    for tu in entry.tool_uses:
        print(f"Tool: {tu.name}, Input: {tu.input}")

        # Get the result
        if tu.result:
            print(f"Result: {tu.result.content[:100]}...")
            if tu.result.is_error:
                print("  (error)")
```

## Querying

### Pre-built Views

```python
# Messages by type
transcript.user_messages      # List[UserMessage]
transcript.assistant_messages # List[AssistantMessage]

# Tool interactions
transcript.tool_uses    # All ToolUseBlocks
transcript.tool_results # All ToolResultBlocks
transcript.errors       # Tool results where is_error=True

# Groupings
transcript.turns        # List[Turn] - grouped by requestId
```

### Fluent Query API

Inspired by Django ORM and Tidyverse:

```python
# Type shortcuts
transcript.query().users().all()
transcript.query().assistants().with_tools().all()

# Filtering
transcript.query().filter(type="assistant").all()
transcript.query().filter(text__contains="error").all()
transcript.query().where(lambda e: e.has_tool_use).all()

# Lookups
transcript.query().filter(timestamp__gt=datetime(2024, 1, 1)).all()
transcript.query().filter(type__in=["user", "assistant"]).all()

# Ordering
transcript.query().order_by("-timestamp").limit(10).all()

# Terminals
transcript.query().assistants().count()     # int
transcript.query().with_errors().exists()   # bool
transcript.query().filter(uuid="abc").one() # single entry or ValueError
```

### Time-based Queries

```python
from datetime import datetime

# Entries since timestamp
transcript.query().since(datetime(2024, 1, 1)).all()
transcript.query().since("2024-01-01T00:00:00").all()

# Entries until timestamp
transcript.query().until(datetime.now()).all()
```

## Creating Entries

### Factory Methods

```python
from fasthooks.transcript import UserMessage, AssistantMessage

# Create user message
msg = UserMessage.create(
    "Remember to use Python 3.11+",
    parent=transcript.entries[-1],  # Sets parent_uuid
    context=transcript.entries[0],  # Copies session_id, cwd, etc.
)

# Create assistant message
response = AssistantMessage.create(
    "Understood, I'll use Python 3.11+ features.",
    parent=msg,
    model="synthetic",  # Default
)
```

Created entries are marked with `is_synthetic=True`.

### Injecting Tool Results

For faking tool executions:

```python
from fasthooks.transcript import inject_tool_result

# Claude "remembers" running this command
assistant, user = inject_tool_result(
    transcript,
    tool_name="Read",
    tool_input={"file_path": "/project/config.json"},
    result='{"debug": true, "log_level": "INFO"}',
)

# With error
inject_tool_result(
    transcript,
    "Bash",
    {"command": "rm -rf /"},
    "Permission denied",
    is_error=True,
)

# At specific position
inject_tool_result(transcript, "Bash", {...}, "output", position="start")
inject_tool_result(transcript, "Bash", {...}, "output", position=5)
```

## CRUD Operations

### Insert

```python
# At position (rewires parent_uuid chain)
transcript.insert(0, entry)      # At start
transcript.insert(5, entry)      # At index 5

# At end
transcript.append(entry)
```

### Remove

```python
# Remove single entry, relink children
transcript.remove(entry, relink=True)  # Default

# Remove entry and all descendants
removed = transcript.remove_tree(entry)
print(f"Removed {len(removed)} entries")
```

### Replace

```python
# Swap entry, preserve position in chain
transcript.replace(old_entry, new_entry)
```

### Save

```python
# Atomic write (temp file + rename)
transcript.save()

# Batch operations with auto-commit/rollback
with transcript.batch():
    transcript.remove(entry1)
    transcript.insert(0, new_entry)
    # Auto-saves on success, rollback on exception
```

## Statistics

```python
stats = transcript.stats

# Token usage
print(f"Input: {stats.input_tokens}")
print(f"Output: {stats.output_tokens}")
print(f"Cache read: {stats.cache_read_tokens}")

# Tool calls
print(f"Tools: {stats.tool_calls}")  # {"Bash": 5, "Read": 3}
print(f"Errors: {stats.error_count}")

# Session info
print(f"Messages: {stats.message_count}")
print(f"Turns: {stats.turn_count}")
print(f"Duration: {stats.duration_seconds}s")
```

## Exporting

### To String

```python
# Markdown - nice for reading
md = transcript.to_markdown()
md = transcript.to_markdown(
    include_thinking=True,      # Show thinking blocks (collapsed)
    include_tool_input=True,    # Show tool input JSON
    max_content_length=500,     # Truncate long content
)

# HTML - for sharing
html = transcript.to_html(title="Debug Session")

# JSON - for processing
json_str = transcript.to_json(indent=2)

# JSONL - original format
jsonl = transcript.to_jsonl()
```

### To File

```python
transcript.to_file("session.md")
transcript.to_file("session.html", format="html")
transcript.to_file("session.json", format="json")
```

## Use Cases

### Inject Project Context

```python
@app.on_session_start()
def add_context(event, transcript: Transcript):
    """Inject project guidelines at session start."""
    reminder = UserMessage.create(
        "Project rules: Use Black formatting, type hints required, pytest for tests",
        context=transcript.entries[0] if transcript.entries else None,
    )
    transcript.insert(0, reminder)
    transcript.save()
```

### Redact Sensitive Data

```python
@app.on_stop()
def redact_secrets(event, transcript: Transcript):
    """Remove API keys from transcript."""
    import re
    pattern = re.compile(r'sk-[a-zA-Z0-9]{32,}')

    with transcript.batch():
        for result in transcript.tool_results:
            if pattern.search(result.content):
                result.content = pattern.sub('[REDACTED]', result.content)
```

### Summarize Large Outputs

```python
@app.post_tool("Read")
def summarize_large_files(event, transcript: Transcript):
    """Replace large file contents with summary."""
    if len(event.content or "") > 5000:
        for result in transcript.tool_results:
            if result.tool_use_id == event.tool_use_id:
                lines = result.content.count('\n')
                result.content = f"[File: {event.file_path}, {lines} lines]"
        transcript.save()
```

### Analyze Session

```python
@app.on_stop()
def analyze(event, transcript: Transcript):
    """Log session analytics."""
    stats = transcript.stats

    # Check for issues
    if stats.error_count > 5:
        print(f"Warning: {stats.error_count} errors in session")

    # Export for review
    if stats.output_tokens > 50000:
        transcript.to_file(f"/tmp/large_session_{stats.slug}.md")
```

### Fake Tool Results for Context

```python
@app.on_prompt()
def inject_fake_config(event, transcript: Transcript):
    """Make Claude 'remember' reading a config file."""
    inject_tool_result(
        transcript,
        "Read",
        {"file_path": "/project/.claude-config"},
        "prefer_typescript=true\nmax_file_size=1000",
        position="start",
    )
    transcript.save()
```

## Advanced: Archived Entries

Entries before the last context compaction are in `transcript.archived`:

```python
# Current context window only (default)
transcript.entries

# Pre-compaction entries
transcript.archived

# Both
transcript.all_entries

# Query with archived
transcript.query(include_archived=True).count()
```

## When Do Changes Take Effect?

| Hook | When Changes Apply |
|------|-------------------|
| `on_session_start` | First response |
| `on_prompt` | Current response |
| `pre_tool` | Next turn (current continues) |
| `post_tool` | Next turn |
| `on_stop` | Next user turn |

To affect the **current** response, modify in `on_prompt` before Claude starts.
