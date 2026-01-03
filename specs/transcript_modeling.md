# Transcript Modeling Specification

## Overview

The transcript is a JSONL file that represents Claude's memory of the conversation. It is **mutable** - editing the file edits Claude's perceived reality.

> "Claude only knows what's in the transcript. Modify it, and Claude's memory changes."
> — Eternal Sunshine of the Spotless Mind / Memento analogy

## Goals

1. **Model the transcript correctly and completely** - typed, structured, relationships preserved
2. **Enable CRUD operations** - create, read, update, delete entries
3. **Enable querying/filtering** - find entries by criteria
4. **Enable context engineering** - build injectable context from history
5. **Provide great DX** - users work with typed models, not raw dicts

## Design Decisions (from Interview)

### Core Architecture

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Change timing** | Hook decides (`immediate=True/False`) | Flexibility for different use cases |
| **Entry structure** | Flat entries + Turn abstraction (layered) | Both raw access and convenience |
| **Sidechains** | Separate Transcript objects per file | Clean separation, link via session_id |
| **Pre-compact entries** | Separate `.archived` property | Main transcript starts from compact boundary |
| **Concurrency** | Copy-on-write | Safe concurrent access during Claude responses |
| **Transactions** | Context manager (`with transcript.batch():`) | Auto-commit/rollback on success/exception |

### Data Model

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Chain management** | User chooses: `remove(relink=True)` or `remove_tree()` | Different use cases need different behaviors |
| **Raw sync** | Proxy objects | `entry.content = x` auto-updates `_raw` |
| **Tool results** | Typed: `BashResult`, `WriteResult`, etc. | Type-safe access to stdout, stderr, etc. |
| **Turn type** | First-class `Turn` class | Groups thinking+tool_use+text by requestId |
| **Validation** | Modes: `strict`/`warn`/`none` | User controls strictness |
| **Dirty tracking** | No - full rewrite on save | Simplicity over performance |

### Context Engineering (Primary Use Case)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Injection position** | Arbitrary (user specifies) | Full control with chain rewiring |
| **Metadata** | Smart defaults with overrides | Copy from context, allow customization |
| **Synthetic marker** | Visible `isSynthetic` field (if CC allows), else private `_synthetic` | Transparent about what's real |
| **Factories** | Full factories + preset patterns | Power + convenience |
| **Strategies** | 1-2 built-in + cookbook recipes | Examples without over-engineering |
| **Hook timing** | Any hook can inject | Maximum flexibility |

### Memory Editing (Secondary Use Case)

Use cases prioritized:
1. **Injecting background thoughts** - Add context Claude "remembers"
2. **Correcting false memories** - Fix Claude's misunderstandings
3. **Summarizing verbose outputs** - Replace long tool results with summaries (context preservation!)

### API Design

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Query API** | Both fluent + raw iteration | Expressive chaining + Python-native loops |
| **Analytics** | Basic `.stats` property | Essential metrics without bloat |
| **Views** | Pre-built + generic query | `.errors`, `.tool_uses` + `.filter()`, `.where()` |
| **Archived filtering** | `include_archived=False` default | Current window by default, full history on demand |
| **Meta filtering** | `include_meta=False` default | Hide system meta entries, user can override |
| **Export formats** | Multiple: JSONL, Markdown, HTML, JSON | Review, debug, share |
| **Coupling** | Standalone + hook-integrated | Use anywhere, auto-cached in hooks |
| **Existing Transcript** | Replace it (breaking change) | Cleaner than parallel types |
| **Safety** | Configurable: `strict`/`warn`/`none` | Protect against accidental mid-turn edits |

### Out of Scope for v1

- Summarization helpers (user implements)
- Diff capability
- Undo/snapshots (future roadmap)
- FileHistorySnapshot manipulation

### Important Behavior: When Do Changes Take Effect?

When a hook modifies and saves the transcript, the timing of when Claude "sees" the change depends on the hook event:

| Hook Event | When Changes Take Effect |
|------------|--------------------------|
| `on_session_start` | Claude sees changes on first response |
| `on_prompt` (UserPromptSubmit) | Claude sees changes before responding |
| `pre_tool` | Changes affect tool execution and subsequent response |
| `post_tool` | Changes affect subsequent turns only |
| `on_stop` | Changes affect next user turn |

**Key insight**: Transcript changes are read by Claude Code when it loads context for a response. If you modify the transcript *during* a response (e.g., in `pre_tool`), the current streaming response continues with original context. The change affects the *next* turn.

**To affect current turn** (advanced):
- Modify transcript in `on_prompt` before Claude starts responding
- Or return `block()` to restart the turn after modification

**Example - immediate context injection:**
```python
@app.on_prompt()
def inject_context(event, transcript: Transcript):
    # This runs BEFORE Claude sees the prompt
    # Changes here affect the current response
    inject_reminder(transcript, "Use Python 3.11+ features")
    transcript.save()
```

**Example - post-hoc editing (next turn):**
```python
@app.post_tool("Read")
def summarize_read(event, transcript: Transcript):
    # This runs AFTER the tool result is recorded
    # Claude already has the full content in context
    # This change affects future turns
    if len(event.content) > 2000:
        for r in transcript.tool_results:
            if r.tool_use_id == event.tool_use_id:
                r.content = f"[Summarized: {len(event.content)} chars]"
        transcript.save()
```

---

## File Format

```
~/.claude/projects/<project>/sessions/<session_id>/transcript.jsonl
```

Agent sidechains:
```
~/.claude/projects/<project>/sessions/<session_id>/agent-<agent_id>.jsonl
```

---

## Entry Types (Validated Against Real Transcripts)

### High-Level Structure

```
Transcript (JSONL file)
│
├── Entry (one line)
│   ├── UserMessage        (type: "user")
│   ├── AssistantMessage   (type: "assistant")
│   ├── SystemEntry        (type: "system")
│   └── FileHistorySnapshot (type: "file-history-snapshot")
│
├── ContentBlocks (embedded in message.content)
│   ├── TextBlock
│   ├── ToolUseBlock
│   ├── ToolResultBlock
│   └── ThinkingBlock
│
├── Abstractions
│   └── Turn (groups entries by requestId)
│
└── Relationships
    ├── parentUuid → uuid (linked list of entries)
    ├── ToolUseBlock.id ↔ ToolResultBlock.tool_use_id
    └── requestId (groups streaming chunks into Turn)
```

### Common Fields (All Message Entries)

```json
{
  "type": "user" | "assistant" | "system",
  "uuid": "unique-id",
  "parentUuid": "previous-entry-uuid" | null,
  "timestamp": "2026-01-02T19:18:31.028Z",
  "sessionId": "c45af7b1-cb7c-4e51-93db-8cbb250a877a",
  "cwd": "/workspace",
  "version": "2.0.76",
  "gitBranch": "",
  "isSidechain": false,
  "userType": "external",
  "slug": "idempotent-sprouting-ocean"
}
```

### Entry: UserMessage

**Text content (human input):**
```json
{
  "type": "user",
  "uuid": "0bdd2740-b6f7-4e7b-b1c9-f159cc83b104",
  "parentUuid": "previous-uuid",
  "timestamp": "2026-01-02T19:18:31.028Z",
  "message": {
    "role": "user",
    "content": "can you run a command ls -la"
  },
  "thinkingMetadata": {"level": "high", "disabled": false, "triggers": []},
  "todos": []
}
```

**Tool result content (system-generated):**
```json
{
  "type": "user",
  "uuid": "855f7359-f4d6-47eb-aad0-3bc49f6d745f",
  "parentUuid": "671cb728-ae54-427e-8933-85527c936c32",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "tool_result",
        "tool_use_id": "toolu_01BYfGNktE4d25hZnxHwFh2s",
        "content": "total 76\ndrwxr-xr-x...",
        "is_error": false
      }
    ]
  },
  "toolUseResult": {
    "stdout": "total 76\ndrwxr-xr-x...",
    "stderr": "",
    "interrupted": false,
    "isImage": false
  }
}
```

### Entry: AssistantMessage

**IMPORTANT**: A single turn produces MULTIPLE assistant entries with same `requestId`.

```json
{
  "type": "assistant",
  "uuid": "671cb728-ae54-427e-8933-85527c936c32",
  "parentUuid": "74329834-862f-46b7-8d29-4cf8f6a36213",
  "timestamp": "2026-01-02T19:18:34.422Z",
  "requestId": "req_011CWj6D8KFP8hnwYdrq7S4C",
  "message": {
    "model": "claude-haiku-4-5-20251001",
    "id": "msg_012yp674BDbdduJCYtTe3GMH",
    "type": "message",
    "role": "assistant",
    "content": [
      {
        "type": "tool_use",
        "id": "toolu_01BYfGNktE4d25hZnxHwFh2s",
        "name": "Bash",
        "input": {"command": "ls -la"}
      }
    ],
    "stop_reason": null,
    "usage": {
      "input_tokens": 9,
      "cache_creation_input_tokens": 5061,
      "cache_read_input_tokens": 12834,
      "output_tokens": 8
    }
  }
}
```

### Entry: SystemEntry

**stop_hook_summary:**
```json
{
  "type": "system",
  "subtype": "stop_hook_summary",
  "hookCount": 1,
  "hookInfos": [{"command": "hooks/run_hook.sh"}],
  "hookErrors": [],
  "preventedContinuation": false
}
```

**compact_boundary:**
```json
{
  "type": "system",
  "subtype": "compact_boundary",
  "parentUuid": null,
  "logicalParentUuid": "a222e3e0-a2be-4b98-a091-da5ee8b3cc7b",
  "content": "Conversation compacted",
  "compactMetadata": {"trigger": "manual", "preTokens": 21558}
}
```

### ThinkingBlock (Read-Only)

```json
{
  "type": "thinking",
  "thinking": "Let me consider...",
  "signature": "EpcDCkYICxgCKkDwuQFKira33iZ2L..."
}
```

**Note**: `signature` is a cryptographic signature (protobuf-encoded Ed25519/ECDSA). Cannot be forged without Anthropic's private key. **Thinking blocks are effectively read-only** - modifications will log a warning.

---

## Content Blocks

### TextBlock
```json
{"type": "text", "text": "Here's what I found..."}
```

### ToolUseBlock
```json
{
  "type": "tool_use",
  "id": "toolu_01BYfGNktE4d25hZnxHwFh2s",
  "name": "Bash",
  "input": {"command": "ls -la", "description": "List files"}
}
```

### ToolResultBlock
```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_01BYfGNktE4d25hZnxHwFh2s",
  "content": "file1.txt\nfile2.txt",
  "is_error": false
}
```

---

## Typed Tool Results

Tool results have rich structured data in `toolUseResult`:

```python
@dataclass
class BashResult:
    stdout: str
    stderr: str
    exit_code: int | None = None
    interrupted: bool = False
    is_image: bool = False

@dataclass
class WriteResult:
    type: Literal["create", "update"]
    file_path: str
    content: str
    structured_patch: list = field(default_factory=list)
    original_file: str | None = None

@dataclass
class ReadResult:
    type: Literal["text"]
    file_path: str
    content: str
    num_lines: int
    start_line: int
    total_lines: int
```

Access via:
```python
result = tool_result.as_bash_result()  # Returns BashResult or None
if result:
    print(result.stdout)
```

---

## Relationships

### 1. Entry Linking (parentUuid)

```
Entry[0] (parentUuid: null)
    ↓
Entry[1] (parentUuid: Entry[0].uuid)
    ↓
Entry[2] (parentUuid: Entry[1].uuid)
```

**Compact boundary special case:**
- `parentUuid` is null (breaks chain)
- `logicalParentUuid` links to pre-compact context

### 2. ToolUse ↔ ToolResult

```
ToolUseBlock.id ←→ ToolResultBlock.tool_use_id
```

### 3. Turn Grouping (requestId)

Multiple assistant entries with same `requestId` form one Turn:

```
Turn (requestId: "req_011CWj6D8KFP8hnwYdrq7S4C")
  ├── thinking entry
  ├── tool_use entry
  └── text entry
```

---

## Python API

> **Note**: The spec examples below use dataclass syntax for clarity. The actual implementation uses **Pydantic BaseModel** with field aliases for camelCase→snake_case conversion. See `src/fasthooks/transcript/` for the real code.

### Core Classes

```python
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Callable, Iterator
from uuid import uuid4

# === Content Blocks ===

@dataclass
class TextBlock:
    type: Literal["text"] = "text"
    text: str = ""

@dataclass
class ToolUseBlock:
    type: Literal["tool_use"] = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)

    _transcript: "Transcript | None" = field(default=None, repr=False)

    @property
    def result(self) -> "ToolResultBlock | None":
        """Find matching tool result."""
        if self._transcript:
            return self._transcript.find_tool_result(self.id)
        return None

@dataclass
class ToolResultBlock:
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = ""
    content: str = ""
    is_error: bool = False

    _transcript: "Transcript | None" = field(default=None, repr=False)
    _tool_use_result: dict | str | None = field(default=None, repr=False)

    @property
    def tool_use(self) -> ToolUseBlock | None:
        """Find matching tool use."""
        if self._transcript:
            return self._transcript.find_tool_use(self.tool_use_id)
        return None

    def as_bash_result(self) -> BashResult | None:
        """Get typed Bash result."""
        ...

    def as_write_result(self) -> WriteResult | None:
        """Get typed Write result."""
        ...

    def as_read_result(self) -> ReadResult | None:
        """Get typed Read result."""
        ...

@dataclass
class ThinkingBlock:
    """Read-only - signature cannot be forged."""
    type: Literal["thinking"] = "thinking"
    thinking: str = ""
    signature: str = ""

ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock

# === Entry Base ===

@dataclass
class Entry:
    """Base for all transcript entries. Uses proxy pattern for _raw sync."""
    type: str = ""
    uuid: str = ""
    parent_uuid: str | None = None
    timestamp: datetime | None = None
    session_id: str = ""
    cwd: str = ""
    version: str = ""
    git_branch: str = ""
    is_sidechain: bool = False
    slug: str = ""
    is_synthetic: bool = False  # Visible marker for injected entries

    _raw: dict = field(default_factory=dict, repr=False)
    _line_number: int | None = field(default=None, repr=False)

# === Message Entries ===

@dataclass
class UserMessage(Entry):
    type: Literal["user"] = "user"
    content: str | list[ToolResultBlock] = ""
    thinking_metadata: dict | None = None
    todos: list = field(default_factory=list)
    is_compact_summary: bool = False

    @property
    def is_tool_result(self) -> bool:
        return isinstance(self.content, list)

    @property
    def text(self) -> str:
        return self.content if isinstance(self.content, str) else ""

@dataclass
class AssistantMessage(Entry):
    type: Literal["assistant"] = "assistant"
    request_id: str = ""
    message_id: str = ""
    model: str = ""
    content: list[ContentBlock] = field(default_factory=list)
    stop_reason: str | None = None
    usage: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.content if isinstance(b, TextBlock))

    @property
    def tool_uses(self) -> list[ToolUseBlock]:
        return [b for b in self.content if isinstance(b, ToolUseBlock)]

    @property
    def thinking(self) -> str:
        return "\n".join(b.thinking for b in self.content if isinstance(b, ThinkingBlock))

@dataclass
class SystemEntry(Entry):
    type: Literal["system"] = "system"
    subtype: str = ""
    content: str = ""
    level: str = ""

@dataclass
class CompactBoundary(SystemEntry):
    subtype: Literal["compact_boundary"] = "compact_boundary"
    logical_parent_uuid: str = ""
    compact_metadata: dict = field(default_factory=dict)

# === Turn Abstraction ===

@dataclass
class Turn:
    """Groups entries by requestId into a logical assistant turn."""
    request_id: str
    entries: list[AssistantMessage]

    @property
    def thinking(self) -> str:
        """Combined thinking from all entries."""
        return "\n".join(e.thinking for e in self.entries if e.thinking)

    @property
    def text(self) -> str:
        """Combined text response."""
        return "\n".join(e.text for e in self.entries if e.text)

    @property
    def tool_uses(self) -> list[ToolUseBlock]:
        """All tool uses in this turn."""
        return [tu for e in self.entries for tu in e.tool_uses]

    @property
    def is_complete(self) -> bool:
        """Whether turn finished (has end_turn stop_reason)."""
        return any(e.stop_reason == "end_turn" for e in self.entries)

    @property
    def has_error(self) -> bool:
        """Whether any tool result was an error."""
        for tu in self.tool_uses:
            if tu.result and tu.result.is_error:
                return True
        return False

# === Transcript ===

class Transcript:
    """
    Mutable collection of entries backed by a JSONL file.

    Usage:
        # Standalone
        transcript = Transcript("/path/to/transcript.jsonl")
        transcript.load()

        # In hooks (auto-injected with caching)
        @app.pre_tool("Bash")
        def check(event, transcript: Transcript):
            ...
    """

    def __init__(
        self,
        path: str | Path,
        validate: Literal["strict", "warn", "none"] = "warn",
        safety: Literal["strict", "warn", "none"] = "warn"
    ):
        self.path = Path(path)
        self.validate = validate
        self.safety = safety
        self.entries: list[Entry] = []
        self._archived: list[Entry] = []  # Pre-compact entries

        # Indexes
        self._tool_use_index: dict[str, ToolUseBlock] = {}
        self._tool_result_index: dict[str, ToolResultBlock] = {}
        self._uuid_index: dict[str, Entry] = {}

        # Copy-on-write state
        self._original_content: str | None = None

    # === Persistence ===

    def load(self) -> None:
        """Load entries from JSONL file."""
        ...

    def save(self) -> None:
        """Save entries to JSONL file (atomic write)."""
        ...

    # === Transaction Support ===

    def batch(self) -> "TranscriptBatch":
        """
        Context manager for atomic modifications.

        Usage:
            with transcript.batch():
                transcript.remove(entry1)
                transcript.insert(0, new_entry)
                # Auto-commits on success, rollback on exception
        """
        return TranscriptBatch(self)

    # === CRUD Operations ===

    def remove(self, entry: Entry, relink: bool = True) -> None:
        """
        Remove entry from transcript.

        Args:
            entry: Entry to remove
            relink: If True, child.parent_uuid = entry.parent_uuid
                    If False, leaves orphan (use remove_tree for cascade)
        """
        ...

    def remove_tree(self, entry: Entry) -> list[Entry]:
        """Remove entry and all descendants. Returns removed entries."""
        ...

    def insert(self, index: int, entry: Entry) -> None:
        """
        Insert entry at position, rewiring parent_uuid chain.

        Handles chain management:
        - entry.parent_uuid = entries[index-1].uuid (or None if index=0)
        - entries[index].parent_uuid = entry.uuid
        """
        ...

    def append(self, entry: Entry) -> None:
        """Add entry to end of transcript."""
        ...

    def replace(self, old: Entry, new: Entry) -> None:
        """Replace entry, preserving position in chain."""
        ...

    # === Relationship Lookups ===

    def find_tool_use(self, tool_use_id: str) -> ToolUseBlock | None:
        return self._tool_use_index.get(tool_use_id)

    def find_tool_result(self, tool_use_id: str) -> ToolResultBlock | None:
        return self._tool_result_index.get(tool_use_id)

    def find_by_uuid(self, uuid: str) -> Entry | None:
        return self._uuid_index.get(uuid)

    def get_parent(self, entry: Entry) -> Entry | None:
        if entry.parent_uuid:
            return self.find_by_uuid(entry.parent_uuid)
        return None

    def get_children(self, entry: Entry) -> list[Entry]:
        return [e for e in self.entries if e.parent_uuid == entry.uuid]

    # === Pre-built Views ===

    @property
    def archived(self) -> list[Entry]:
        """Entries before last compact boundary."""
        return self._archived

    @property
    def user_messages(self) -> list[UserMessage]:
        return [e for e in self.entries if isinstance(e, UserMessage)]

    @property
    def assistant_messages(self) -> list[AssistantMessage]:
        return [e for e in self.entries if isinstance(e, AssistantMessage)]

    @property
    def tool_uses(self) -> list[ToolUseBlock]:
        """All tool use blocks across all messages."""
        return list(self._tool_use_index.values())

    @property
    def tool_results(self) -> list[ToolResultBlock]:
        """All tool result blocks."""
        return list(self._tool_result_index.values())

    @property
    def errors(self) -> list[ToolResultBlock]:
        """Tool results where is_error=True."""
        return [r for r in self.tool_results if r.is_error]

    @property
    def turns(self) -> list[Turn]:
        """Group assistant messages by requestId into Turns."""
        ...

    @property
    def compact_boundaries(self) -> list[CompactBoundary]:
        return [e for e in self.entries if isinstance(e, CompactBoundary)]

    # === Query API (Fluent) ===

    def filter(self, predicate: Callable[[Entry], bool]) -> "TranscriptView":
        """Filter entries by predicate."""
        return TranscriptView([e for e in self.entries if predicate(e)])

    def where(self, **criteria) -> "TranscriptView":
        """Filter by attribute equality."""
        def matches(entry):
            return all(getattr(entry, k, None) == v for k, v in criteria.items())
        return self.filter(matches)

    # === Statistics ===

    @property
    def stats(self) -> "TranscriptStats":
        """Basic transcript statistics."""
        return TranscriptStats.from_transcript(self)

    # === Export ===

    def export(self, format: Literal["jsonl", "json", "md", "html"] = "jsonl") -> str:
        """Export transcript to various formats."""
        ...

    def to_markdown(self) -> str:
        """Shorthand for export('md')."""
        return self.export("md")

    # === Iteration ===

    def __iter__(self) -> Iterator[Entry]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)


class TranscriptView:
    """Immutable view for fluent querying."""

    def __init__(self, entries: list[Entry]):
        self._entries = entries

    def filter(self, predicate: Callable[[Entry], bool]) -> "TranscriptView":
        return TranscriptView([e for e in self._entries if predicate(e)])

    def where(self, **criteria) -> "TranscriptView":
        def matches(entry):
            return all(getattr(entry, k, None) == v for k, v in criteria.items())
        return self.filter(matches)

    def has_tool_use(self, name: str | None = None) -> "TranscriptView":
        """Filter to entries with tool use (optionally by tool name)."""
        def check(e):
            if not isinstance(e, AssistantMessage):
                return False
            if name:
                return any(tu.name == name for tu in e.tool_uses)
            return e.has_tool_use
        return self.filter(check)

    def since(self, minutes: int = 0, hours: int = 0) -> "TranscriptView":
        """Entries since time ago."""
        cutoff = datetime.now() - timedelta(minutes=minutes, hours=hours)
        return self.filter(lambda e: e.timestamp and e.timestamp > cutoff)

    def first(self, n: int = 1) -> list[Entry]:
        return self._entries[:n]

    def last(self, n: int = 1) -> list[Entry]:
        return self._entries[-n:]

    def all(self) -> list[Entry]:
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    def __len__(self):
        return len(self._entries)


@dataclass
class TranscriptStats:
    """Basic transcript statistics."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    error_count: int = 0
    message_count: int = 0
    turn_count: int = 0
    compact_count: int = 0

    @classmethod
    def from_transcript(cls, t: Transcript) -> "TranscriptStats":
        ...


class TranscriptBatch:
    """Context manager for atomic transcript modifications."""

    def __init__(self, transcript: Transcript):
        self.transcript = transcript
        self._snapshot: str | None = None

    def __enter__(self):
        # Snapshot current state
        self._snapshot = self.transcript.path.read_text() if self.transcript.path.exists() else ""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            # Rollback on exception
            if self._snapshot is not None:
                self.transcript.path.write_text(self._snapshot)
                self.transcript.load()  # Reload
        else:
            # Commit
            self.transcript.save()
        return False
```

---

## Factory Methods & Presets

### Entry Factories

```python
class UserMessage(Entry):
    @classmethod
    def create(
        cls,
        content: str,
        *,
        parent: Entry | None = None,
        context: Entry | None = None,  # Copy metadata from this entry
        cwd: str | None = None,
        session_id: str | None = None,
        **overrides
    ) -> "UserMessage":
        """
        Create a valid UserMessage with proper UUID/timestamp.

        Args:
            content: Message text
            parent: Entry this should follow (sets parent_uuid)
            context: Entry to copy metadata from (cwd, session_id, etc.)
            cwd: Override working directory
            session_id: Override session ID
            **overrides: Any other field overrides
        """
        ...

class AssistantMessage(Entry):
    @classmethod
    def create(
        cls,
        content: str | list[ContentBlock],
        *,
        parent: Entry | None = None,
        context: Entry | None = None,
        model: str = "synthetic",
        **overrides
    ) -> "AssistantMessage":
        """Create a valid AssistantMessage."""
        ...
```

### Preset Patterns

```python
# In fasthooks.context_engineering or fasthooks.presets

def inject_reminder(
    transcript: Transcript,
    message: str,
    *,
    position: int | Entry | Literal["start", "before_current"] = "start"
) -> UserMessage:
    """
    Inject a reminder that appears as if user said it earlier.

    Usage:
        inject_reminder(transcript, "Remember to always use type hints")
    """
    ...

def inject_tool_result(
    transcript: Transcript,
    tool_name: str,
    tool_input: dict,
    result: str,
    *,
    is_error: bool = False,
    position: int | Entry | Literal["start", "before_current"] = "before_current"
) -> tuple[AssistantMessage, UserMessage]:
    """
    Inject fake tool use + result pair.

    Usage:
        inject_tool_result(
            transcript,
            "Read",
            {"file_path": "/fake/config.json"},
            '{"setting": "value"}'
        )
    """
    ...

def inject_exchange(
    transcript: Transcript,
    user_content: str,
    assistant_content: str,
    *,
    position: int | Entry | Literal["start", "before_current"] = "start"
) -> tuple[UserMessage, AssistantMessage]:
    """
    Inject a fake user-assistant exchange.

    Usage:
        inject_exchange(
            transcript,
            "What's the coding style for this project?",
            "This project uses Black formatting, type hints required, ..."
        )
    """
    ...

def summarize_tool_result(
    entry: UserMessage,
    summary: str
) -> None:
    """
    Replace verbose tool result content with a summary.
    Preserves context while reducing token usage.

    Usage:
        for result in transcript.tool_results:
            if len(result.content) > 1000:
                summarize_tool_result(result._entry, f"[File contents: {len(result.content)} chars]")
    """
    ...
```

### Context Strategies (Cookbook Examples)

```python
class ContextStrategy:
    """Base class for context injection strategies."""

    def apply(self, transcript: Transcript) -> None:
        """Apply strategy to transcript."""
        raise NotImplementedError


class ProjectContextStrategy(ContextStrategy):
    """
    Inject project-specific context at session start.

    Example usage in hook:
        @app.on_session_start()
        def inject_context(event, transcript: Transcript):
            strategy = ProjectContextStrategy(
                style_guide="Use Black, type hints required",
                architecture="FastAPI backend, React frontend"
            )
            strategy.apply(transcript)
    """

    def __init__(self, **context):
        self.context = context

    def apply(self, transcript: Transcript) -> None:
        content = "\n".join(f"- {k}: {v}" for k, v in self.context.items())
        inject_reminder(transcript, f"Project context:\n{content}", position="start")


class MemoryPruningStrategy(ContextStrategy):
    """
    Summarize verbose tool results to preserve context.

    Example:
        @app.post_tool("Read")
        def prune_large_reads(event, transcript: Transcript):
            strategy = MemoryPruningStrategy(max_content_length=500)
            strategy.apply(transcript)
    """

    def __init__(self, max_content_length: int = 1000):
        self.max_length = max_content_length

    def apply(self, transcript: Transcript) -> None:
        for result in transcript.tool_results:
            if len(result.content) > self.max_length:
                summary = f"[Content truncated: {len(result.content)} chars]"
                summarize_tool_result(result._entry, summary)
```

---

## Usage Examples

### Context Injection in Hooks

```python
from fasthooks import HookApp, allow
from fasthooks.depends import Transcript
from fasthooks.presets import inject_reminder, inject_exchange

app = HookApp()

@app.on_session_start()
def add_project_context(event, transcript: Transcript):
    """Inject project guidelines at session start."""
    inject_reminder(
        transcript,
        "Project guidelines: Use type hints, Black formatting, pytest for tests"
    )
    transcript.save()

@app.pre_tool("Bash")
def check_dangerous_commands(event, transcript: Transcript):
    """Block dangerous commands, inject correction if needed."""
    if "rm -rf /" in event.command:
        # Inject a "memory" that user doesn't want destructive commands
        inject_exchange(
            transcript,
            "Be careful with destructive commands",
            "Understood, I'll always ask before running rm -rf or similar."
        )
        transcript.save()
        return deny("Blocked: destructive command")
```

### Memory Editing

```python
@app.on_stop()
def cleanup_sensitive_data(event, transcript: Transcript):
    """Redact any API keys that slipped through."""
    import re
    api_key_pattern = re.compile(r'sk-[a-zA-Z0-9]{32,}')

    with transcript.batch():
        for entry in transcript.user_messages:
            if isinstance(entry.content, str):
                if api_key_pattern.search(entry.content):
                    entry.content = api_key_pattern.sub('[REDACTED]', entry.content)

        for result in transcript.tool_results:
            if api_key_pattern.search(result.content):
                result.content = api_key_pattern.sub('[REDACTED]', result.content)
```

### Summarizing Verbose Tool Outputs

```python
@app.post_tool("Read")
def summarize_large_files(event, transcript: Transcript):
    """Replace large file reads with summaries to preserve context."""
    if len(event.content or "") > 2000:
        # Find the tool result entry
        for result in transcript.tool_results:
            if result.tool_use_id == event.tool_use_id:
                lines = result.content.count('\n')
                result.content = f"[File: {event.file_path}, {lines} lines, content summarized]"
                break
        transcript.save()
```

### Querying Transcript

```python
@app.on_stop()
def analyze_session(event, transcript: Transcript):
    """Log session analytics."""
    stats = transcript.stats

    # Basic stats
    print(f"Tokens: {stats.input_tokens} in, {stats.output_tokens} out")
    print(f"Tool calls: {stats.tool_calls}")
    print(f"Errors: {stats.error_count}")

    # Query for patterns
    bash_errors = (
        transcript.filter(lambda e: isinstance(e, UserMessage) and e.is_tool_result)
        .filter(lambda e: any(r.is_error for r in e.content))
        .count()
    )
    print(f"Bash errors: {bash_errors}")

    # Recent activity
    recent = transcript.where(type="assistant").since(minutes=5).count()
    print(f"Responses in last 5 min: {recent}")
```

---

## Appendix A: Sample Data Files

Real transcript samples are provided in `specs/data/` for reference:

| File | Description |
|------|-------------|
| `sample_main_transcript.jsonl` | Full session with tool use, errors, compaction |
| `sample_agent_sidechain.jsonl` | Subagent transcript (Explore agent) |
| `sample_hook_logs.jsonl` | Hook execution logs (separate from transcript) |

Use these to validate parsing and understand edge cases.

---

## Appendix B: Complete Field Reference

### UserMessage Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"user"` | Yes | Entry type discriminator |
| `uuid` | `string` | Yes | Unique identifier for this entry |
| `parentUuid` | `string \| null` | Yes | Links to previous entry (null for first) |
| `timestamp` | `ISO8601` | Yes | When entry was created |
| `sessionId` | `string` | Yes | Session UUID |
| `cwd` | `string` | Yes | Working directory |
| `version` | `string` | Yes | Claude Code version (e.g., "2.0.76") |
| `gitBranch` | `string` | Yes | Current git branch (empty if not in repo) |
| `isSidechain` | `boolean` | Yes | True for subagent transcripts |
| `userType` | `string` | Yes | Always "external" |
| `slug` | `string` | No | Session slug (appears after first interaction) |
| `message.role` | `"user"` | Yes | Message role |
| `message.content` | `string \| ToolResultBlock[]` | Yes | Text or tool results |
| `thinkingMetadata` | `object` | No | `{level, disabled, triggers}` |
| `todos` | `array` | No | Todo items from TodoWrite |
| `toolUseResult` | `object \| string` | No | Structured tool result (richer than message.content) |
| `isMeta` | `boolean` | No | True for system-generated meta messages |
| `isCompactSummary` | `boolean` | No | True for compaction summary |
| `isVisibleInTranscriptOnly` | `boolean` | No | True if only shown in transcript (not to Claude) |

### AssistantMessage Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"assistant"` | Yes | Entry type discriminator |
| `uuid` | `string` | Yes | Unique identifier for this entry |
| `parentUuid` | `string \| null` | Yes | Links to previous entry |
| `timestamp` | `ISO8601` | Yes | When entry was created |
| `requestId` | `string` | Yes | Groups entries from same API request |
| `sessionId` | `string` | Yes | Session UUID |
| `cwd` | `string` | Yes | Working directory |
| `version` | `string` | Yes | Claude Code version |
| `gitBranch` | `string` | Yes | Current git branch |
| `isSidechain` | `boolean` | Yes | True for subagent transcripts |
| `userType` | `string` | Yes | Always "external" |
| `slug` | `string` | No | Session slug |
| `message.model` | `string` | Yes | Model used (e.g., "claude-haiku-4-5-20251001") |
| `message.id` | `string` | Yes | Anthropic message ID (same across streaming chunks) |
| `message.type` | `"message"` | Yes | Always "message" |
| `message.role` | `"assistant"` | Yes | Message role |
| `message.content` | `ContentBlock[]` | Yes | Array of content blocks |
| `message.stop_reason` | `string \| null` | Yes | "end_turn", "tool_use", or null (streaming) |
| `message.stop_sequence` | `string \| null` | Yes | Usually null |
| `message.usage` | `object` | Yes | Token usage statistics |

### SystemEntry Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"system"` | Yes | Entry type discriminator |
| `subtype` | `string` | Yes | "stop_hook_summary", "compact_boundary", etc. |
| `uuid` | `string` | Yes | Unique identifier |
| `parentUuid` | `string \| null` | Yes | Links to previous entry |
| `timestamp` | `ISO8601` | Yes | When entry was created |
| `level` | `string` | No | "info", "suggestion", etc. |

**stop_hook_summary additional fields:**
- `hookCount`: Number of hooks executed
- `hookInfos`: Array of `{command: string}`
- `hookErrors`: Array of errors
- `preventedContinuation`: Whether hook blocked continuation
- `stopReason`: Stop reason string
- `hasOutput`: Whether hook produced output
- `toolUseID`: Associated tool use ID

**compact_boundary additional fields:**
- `logicalParentUuid`: Links to pre-compact context (parentUuid is null)
- `compactMetadata`: `{trigger: "manual"|"auto", preTokens: number}`
- `content`: "Conversation compacted"
- `isMeta`: Usually false

### Agent Sidechain Additional Field

| Field | Type | Description |
|-------|------|-------------|
| `agentId` | `string` | Short agent ID (e.g., "af1ff21") |

---

## Appendix C: Hook Logs Format (Related Reference)

Hook logs are **separate from transcripts** but useful context. They record hook executions.

**Location:** `hooks/logs/hooks-<session_id>.jsonl`

### Hook Log Entry Types

**SessionStart:**
```json
{
  "ts": "2026-01-02T19:11:26Z",
  "session_id": "c45af7b1-cb7c-4e51-93db-8cbb250a877a",
  "event": "SessionStart",
  "cwd": "/workspace",
  "source": "startup",
  "transcript_path": "/root/.claude/projects/-workspace/c45af7b1.jsonl"
}
```

**UserPromptSubmit:**
```json
{
  "ts": "2026-01-02T19:18:31Z",
  "session_id": "...",
  "event": "UserPromptSubmit",
  "cwd": "/workspace",
  "permission_mode": "default",
  "prompt": "can you run a command ls -la"
}
```

**PreToolUse:**
```json
{
  "ts": "2026-01-02T19:18:34Z",
  "session_id": "...",
  "event": "PreToolUse",
  "cwd": "/workspace",
  "permission_mode": "default",
  "tool_name": "Bash",
  "tool_input": {"command": "ls -la", "description": "List files"},
  "bash_command": "ls -la",
  "bash_description": "List files"
}
```

**PostToolUse:**
```json
{
  "ts": "2026-01-02T19:18:34Z",
  "session_id": "...",
  "event": "PostToolUse",
  "cwd": "/workspace",
  "permission_mode": "default",
  "tool_name": "Bash",
  "tool_input": {"command": "ls -la"},
  "tool_response": {"stdout": "...", "stderr": "", "interrupted": false}
}
```

**Stop:**
```json
{
  "ts": "2026-01-02T19:18:38Z",
  "session_id": "...",
  "event": "Stop",
  "cwd": "/workspace",
  "permission_mode": "default",
  "stop_hook_active": false
}
```

**SubagentStop:**
```json
{
  "ts": "2026-01-02T19:11:26Z",
  "session_id": "...",
  "event": "SubagentStop",
  "cwd": "/workspace",
  "permission_mode": "default",
  "agent_id": "af1ff21",
  "stop_hook_active": false
}
```

**PreCompact:**
```json
{
  "ts": "2026-01-02T19:20:44Z",
  "session_id": "...",
  "event": "PreCompact",
  "cwd": "/workspace",
  "trigger": "manual"
}
```

**Notification:**
```json
{
  "ts": "2026-01-02T19:22:03Z",
  "session_id": "...",
  "event": "Notification",
  "cwd": "/workspace",
  "message": "Claude is waiting for your input",
  "notification_type": "idle_prompt"
}
```

### Hook Log Event Types Summary

| Event | When | Key Fields |
|-------|------|------------|
| `SessionStart` | Session begins or resumes after compact | `source`, `transcript_path` |
| `UserPromptSubmit` | User sends message | `prompt` |
| `PreToolUse` | Before tool executes | `tool_name`, `tool_input` |
| `PostToolUse` | After tool executes | `tool_name`, `tool_response` |
| `Stop` | Claude finishes responding | `stop_hook_active` |
| `SubagentStop` | Subagent finishes | `agent_id` |
| `PreCompact` | Before context compaction | `trigger` |
| `Notification` | System notification | `message`, `notification_type` |

---

## Appendix D: Token Usage Structure

The `message.usage` field in AssistantMessage contains detailed token metrics:

```json
{
  "input_tokens": 9,
  "output_tokens": 8,
  "cache_creation_input_tokens": 5061,
  "cache_read_input_tokens": 12834,
  "cache_creation": {
    "ephemeral_5m_input_tokens": 5061,
    "ephemeral_1h_input_tokens": 0
  },
  "service_tier": "standard"
}
```

| Field | Description |
|-------|-------------|
| `input_tokens` | Tokens in this request's prompt |
| `output_tokens` | Tokens in this response |
| `cache_creation_input_tokens` | Tokens added to cache |
| `cache_read_input_tokens` | Tokens read from cache (saved cost) |
| `cache_creation.ephemeral_5m_input_tokens` | 5-minute cache tokens |
| `cache_creation.ephemeral_1h_input_tokens` | 1-hour cache tokens |
| `service_tier` | "standard" or other tier |

---

## Open Questions (Future Roadmap)

1. **Snapshot/undo support** - Named checkpoints for rollback
2. **Lazy loading** - Stream large transcripts without full memory load
3. **Sidechain federation** - Unified view across main + agent transcripts
4. **LLM summarization helpers** - Built-in Claude calls for smart summarization
5. **Diff/changelog** - Track what changed between load and save
6. **Visible synthetic marker** - Test if Claude Code accepts `isSynthetic` field

---

## Next Steps

1. [x] Examine real transcript files to validate model
2. [x] Interview stakeholder on design decisions
3. [x] Implement Entry parsing (JSONL → Pydantic models)
4. [-] Implement proxy pattern for _raw sync (not needed - model_dump preserves structure via model_extra)
5. [x] Implement relationship indexing (tool_use, tool_result, uuid, request_id, snapshot)
6. [x] Implement CRUD with chain management (remove, remove_tree, insert, append, replace, save)
7. [x] Implement Turn grouping (by requestId)
8. [x] Implement TranscriptQuery fluent API
9. [x] Implement factories (create() + inject_tool_result)
10. [x] Implement export formats (md, html, json, jsonl)
11. [x] Add to fasthooks DI system (replace depends.Transcript)
12. [x] Write tests (351 tests)
13. [x] Write documentation (tutorial + API reference)

### Implementation Notes (v1)

- **Pydantic over dataclasses**: All models use Pydantic BaseModel for validation, field aliases (camelCase→snake_case), and `extra="allow"` to preserve unknown fields
- **DI integration**: `depends/transcript.py` re-exports from `fasthooks.transcript`, making rich Transcript available via `from fasthooks.depends import Transcript`. Constructor accepts `path: str | Path | None` with `auto_load=True` by default.
- **`include_archived` setting**: Transcript has instance-level `include_archived=False` default; views respect this, methods accept override param
- **`include_meta` setting**: Filters out `isMeta=True` and `isVisibleInTranscriptOnly=True` entries by default
- **`tool_results` property**: Added to UserMessage for type-safe access (returns `list[ToolResultBlock]`)
- **`get_logical_parent()`**: For CompactBoundary, returns entry via `logicalParentUuid` (preserves chain across compaction)
- **`find_snapshot()`**: Finds FileHistorySnapshot by message_id
- **Turn forward reference**: Uses `list[Any]` to avoid Pydantic forward reference issues with AssistantMessage
- **CRUD operations**: `remove(relink=True)`, `remove_tree()`, `insert()`, `append()`, `replace()` all manage parentUuid chain
- **`save()`**: Atomic write via temp file + rename; uses `to_dict()` which serializes with camelCase aliases
- **No proxy pattern needed**: `model_dump(by_alias=True)` includes `model_extra`, preserving original nested structure
- **TranscriptStats consistency**: Calculates all metrics (turn_count, error_count, tokens) from archived+current entries for full session stats
- **DI caching**: Transcript is cached per-event in `_run_handlers`, so multiple handlers share same instance
- **turns filtering**: `get_turns(include_archived=...)` filters entries by UUID membership to respect include_archived setting
- **UnknownBlock**: Forward-compatible fallback for unrecognized content block types; preserves original type string and all data
- **validate setting**: Flows from Transcript to `parse_content_block()` - "strict" raises, "warn" logs warning (default), "none" silent
- **TranscriptQuery**: Fluent query API inspired by Django ORM and Tidyverse. Immutable chaining, lazy evaluation on terminals. Supports:
  - Type shortcuts: `.users()`, `.assistants()`, `.system()`, `.with_tools()`, `.with_errors()`, `.with_thinking()`
  - Filtering: `.filter(field=val)`, `.where(lambda)`, `.exclude()`
  - Lookups: `exact`, `contains`, `startswith`, `endswith`, `regex`, `in`, `gt/gte/lt/lte`, `isnull`
  - Time: `.since(ts)`, `.until(ts)`
  - Ordering: `.order_by("field")`, `.order_by("-field")` for descending
  - Pagination: `.limit(n)`, `.offset(n)`
  - Terminals: `.all()`, `.first()`, `.last()`, `.one()`, `.count()`, `.exists()`
  - Iteration: `for e in query`, `len(query)`, `bool(query)`
- **Factories**: Ruthlessly minimal - only what adds real value:
  - `UserMessage.create(content, parent=, context=, **overrides)` - generates uuid, timestamp, copies metadata, marks `is_synthetic=True`
  - `AssistantMessage.create(content, parent=, context=, model="synthetic", **overrides)` - same + generates request_id, message_id
  - `inject_tool_result(transcript, tool_name, tool_input, result, is_error=, position=)` - creates matching ToolUseBlock + ToolResultBlock pair with correct ID wiring
  - Skipped: `inject_reminder`, `inject_exchange`, `summarize_tool_result` - too thin, 2 lines with create() + insert()
- **Exports**: Multiple format support, string or file output:
  - `to_markdown()` -> str - formatted with User/Assistant headers, tool uses, thinking (collapsed)
  - `to_html()` -> str - markdown wrapped in HTML with basic CSS
  - `to_json()` -> str - pretty-printed JSON array
  - `to_jsonl()` -> str - one JSON per line
  - `to_file(path, format="md")` -> writes to disk, supports all formats
  - Options: `include_thinking`, `include_tool_input`, `max_content_length` for truncation
