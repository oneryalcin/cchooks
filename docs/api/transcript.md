# Transcript API Reference

Rich transcript modeling for context engineering.

## Transcript

Main class for loading and manipulating transcripts.

```python
from fasthooks.transcript import Transcript
```

### Constructor

```python
Transcript(
    path: str | Path | None = None,
    auto_load: bool = True,
    validate: Literal["strict", "warn", "none"] = "warn",
    include_archived: bool = False,
    include_meta: bool = False,
)
```

| Parameter | Description |
|-----------|-------------|
| `path` | Path to transcript JSONL file |
| `auto_load` | Load file immediately (default True) |
| `validate` | Unknown block handling: strict=error, warn=warning, none=silent |
| `include_archived` | Include pre-compaction entries in views |
| `include_meta` | Include system meta entries in views |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `entries` | `list[TranscriptEntry]` | Current context window entries |
| `archived` | `list[TranscriptEntry]` | Pre-compaction entries |
| `all_entries` | `list[TranscriptEntry]` | archived + entries |
| `user_messages` | `list[UserMessage]` | User message entries |
| `assistant_messages` | `list[AssistantMessage]` | Assistant message entries |
| `tool_uses` | `list[ToolUseBlock]` | All tool use blocks |
| `tool_results` | `list[ToolResultBlock]` | All tool result blocks |
| `errors` | `list[ToolResultBlock]` | Tool results with is_error=True |
| `turns` | `list[Turn]` | Entries grouped by requestId |
| `compact_boundaries` | `list[CompactBoundary]` | Compaction markers |
| `stats` | `TranscriptStats` | Aggregated statistics |

### CRUD Methods

```python
# Insert
transcript.insert(index: int, entry: Entry) -> None
transcript.append(entry: Entry) -> None

# Remove
transcript.remove(entry: Entry, relink: bool = True) -> None
transcript.remove_tree(entry: Entry) -> list[Entry]

# Replace
transcript.replace(old: Entry, new: Entry) -> None

# Persistence
transcript.load() -> None
transcript.save() -> None

# Batch operations
with transcript.batch():
    # Auto-commit on success, rollback on exception
    ...
```

### Query Methods

```python
transcript.query(
    include_archived: bool | None = None,
    include_meta: bool | None = None,
) -> TranscriptQuery
```

### Lookup Methods

```python
transcript.find_by_uuid(uuid: str) -> Entry | None
transcript.find_tool_use(tool_use_id: str) -> ToolUseBlock | None
transcript.find_tool_result(tool_use_id: str) -> ToolResultBlock | None
transcript.find_snapshot(message_id: str) -> FileHistorySnapshot | None
transcript.get_parent(entry: Entry) -> Entry | None
transcript.get_children(entry: Entry) -> list[Entry]
transcript.get_logical_parent(entry: Entry) -> Entry | None
```

### Export Methods

```python
# To string
transcript.to_markdown(**kwargs) -> str
transcript.to_html(**kwargs) -> str
transcript.to_json(indent: int = 2) -> str
transcript.to_jsonl() -> str

# To file
transcript.to_file(
    path: str | Path,
    format: Literal["md", "html", "json", "jsonl"] = "md",
    **kwargs
) -> None
```

---

## TranscriptQuery

Fluent query builder for filtering entries.

```python
query = transcript.query()
```

### Type Filters

```python
query.users() -> TranscriptQuery
query.assistants() -> TranscriptQuery
query.system() -> TranscriptQuery
query.with_tools() -> TranscriptQuery
query.with_errors() -> TranscriptQuery
query.with_thinking() -> TranscriptQuery
```

### Filtering

```python
query.filter(**kwargs) -> TranscriptQuery
query.where(predicate: Callable) -> TranscriptQuery
query.exclude(**kwargs) -> TranscriptQuery
```

Supported lookups:

| Lookup | Example | Description |
|--------|---------|-------------|
| `exact` | `filter(type="user")` | Exact match (default) |
| `contains` | `filter(text__contains="error")` | Substring |
| `startswith` | `filter(uuid__startswith="abc")` | Prefix |
| `endswith` | `filter(text__endswith="!")` | Suffix |
| `regex` | `filter(text__regex=r"\d+")` | Regex match |
| `in` | `filter(type__in=["user", "assistant"])` | In list |
| `gt` | `filter(timestamp__gt=datetime(...))` | Greater than |
| `gte` | `filter(timestamp__gte=datetime(...))` | Greater or equal |
| `lt` | `filter(timestamp__lt=datetime(...))` | Less than |
| `lte` | `filter(timestamp__lte=datetime(...))` | Less or equal |
| `isnull` | `filter(parent_uuid__isnull=True)` | Is None |

### Time Filters

```python
query.since(ts: datetime | str) -> TranscriptQuery
query.until(ts: datetime | str) -> TranscriptQuery
```

### Ordering

```python
query.order_by(*fields: str) -> TranscriptQuery
# Prefix with - for descending: order_by("-timestamp")
```

### Pagination

```python
query.limit(n: int) -> TranscriptQuery
query.offset(n: int) -> TranscriptQuery
```

### Terminals

```python
query.all() -> list[TranscriptEntry]
query.first() -> TranscriptEntry | None
query.last() -> TranscriptEntry | None
query.one() -> TranscriptEntry  # Raises if 0 or >1 results
query.count() -> int
query.exists() -> bool
```

---

## Entry Types

### Entry (Base)

```python
class Entry:
    type: str
    uuid: str
    parent_uuid: str | None
    timestamp: datetime | None
    session_id: str
    cwd: str
    version: str
    git_branch: str
    is_sidechain: bool
    is_synthetic: bool
```

### UserMessage

```python
class UserMessage(Entry):
    type: Literal["user"] = "user"

    # Properties
    content: str | list[ToolResultBlock]
    text: str  # Empty if tool result
    is_tool_result: bool
    tool_results: list[ToolResultBlock]

    # Factory
    @classmethod
    def create(
        cls,
        content: str,
        *,
        parent: Entry | None = None,
        context: Entry | None = None,
        **overrides
    ) -> UserMessage
```

### AssistantMessage

```python
class AssistantMessage(Entry):
    type: Literal["assistant"] = "assistant"
    request_id: str

    # Properties
    message_id: str
    model: str
    content: list[ContentBlock]
    stop_reason: str | None
    usage: dict
    text: str
    thinking: str
    tool_uses: list[ToolUseBlock]
    has_tool_use: bool

    # Factory
    @classmethod
    def create(
        cls,
        content: str | list[ContentBlock],
        *,
        parent: Entry | None = None,
        context: Entry | None = None,
        model: str = "synthetic",
        stop_reason: str = "end_turn",
        **overrides
    ) -> AssistantMessage
```

### SystemEntry

```python
class SystemEntry(Entry):
    type: Literal["system"] = "system"
    subtype: str
    content: str
    level: str
```

### CompactBoundary

```python
class CompactBoundary(SystemEntry):
    subtype: Literal["compact_boundary"] = "compact_boundary"
    logical_parent_uuid: str
    compact_metadata: dict
```

---

## Content Blocks

### TextBlock

```python
class TextBlock:
    type: Literal["text"] = "text"
    text: str
```

### ToolUseBlock

```python
class ToolUseBlock:
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict

    # Property - finds matching result
    result: ToolResultBlock | None
```

### ToolResultBlock

```python
class ToolResultBlock:
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str
    is_error: bool

    # Property - finds matching tool use
    tool_use: ToolUseBlock | None
```

### ThinkingBlock

```python
class ThinkingBlock:
    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: str  # Cryptographic signature (read-only)
```

---

## Turn

Groups assistant entries by requestId.

```python
class Turn:
    request_id: str
    entries: list[AssistantMessage]

    # Properties
    thinking: str
    text: str
    tool_uses: list[ToolUseBlock]
    is_complete: bool
    has_error: bool
```

---

## TranscriptStats

```python
class TranscriptStats:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    tool_calls: dict[str, int]
    error_count: int
    message_count: int
    turn_count: int
    compact_count: int
    duration_seconds: float
    slug: str
```

---

## Factory Functions

### inject_tool_result

```python
from fasthooks.transcript import inject_tool_result

inject_tool_result(
    transcript: Transcript,
    tool_name: str,
    tool_input: dict,
    result: str,
    *,
    is_error: bool = False,
    position: int | Literal["start", "end"] = "end",
) -> tuple[AssistantMessage, UserMessage]
```

Creates a matching ToolUseBlock + ToolResultBlock pair and inserts them.
