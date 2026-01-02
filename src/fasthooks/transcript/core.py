"""Core Transcript class for loading and querying transcript data."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Literal

from fasthooks.transcript.blocks import ToolResultBlock, ToolUseBlock
from fasthooks.transcript.entries import (
    AssistantMessage,
    CompactBoundary,
    Entry,
    FileHistorySnapshot,
    StopHookSummary,
    SystemEntry,
    TranscriptEntry,
    UserMessage,
    parse_entry,
)


class Transcript:
    """
    Mutable collection of entries backed by a JSONL file.

    Usage:
        # Standalone
        transcript = Transcript("/path/to/transcript.jsonl")
        transcript.load()

        # Query
        for msg in transcript.user_messages:
            print(msg.text)
    """

    def __init__(
        self,
        path: str | Path,
        validate: Literal["strict", "warn", "none"] = "warn",
        safety: Literal["strict", "warn", "none"] = "warn",
    ):
        self.path = Path(path)
        self.validate = validate
        self.safety = safety

        # All entries in order
        self.entries: list[TranscriptEntry] = []

        # Pre-compact entries (archived)
        self._archived: list[TranscriptEntry] = []

        # Indexes for fast lookups
        self._tool_use_index: dict[str, ToolUseBlock] = {}
        self._tool_result_index: dict[str, ToolResultBlock] = {}
        self._uuid_index: dict[str, Entry] = {}

        # Track if loaded
        self._loaded = False

    def load(self) -> None:
        """Load entries from JSONL file."""
        if not self.path.exists():
            self._loaded = True
            return

        self.entries = []
        self._archived = []
        self._tool_use_index = {}
        self._tool_result_index = {}
        self._uuid_index = {}

        # Find last compact boundary to split archived vs current
        raw_entries: list[dict[str, Any]] = []
        last_compact_idx = -1

        with open(self.path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    data["_line_number"] = line_num
                    raw_entries.append(data)

                    if data.get("subtype") == "compact_boundary":
                        last_compact_idx = len(raw_entries) - 1
                except json.JSONDecodeError:
                    if self.validate == "strict":
                        raise
                    continue

        # Parse entries and split archived vs current
        for i, data in enumerate(raw_entries):
            entry = parse_entry(data, self)

            # Set line number
            if hasattr(entry, "_line_number"):
                object.__setattr__(entry, "_line_number", data.get("_line_number"))

            if i <= last_compact_idx:
                self._archived.append(entry)
            else:
                self.entries.append(entry)

            # Build indexes
            self._index_entry(entry)

        self._loaded = True

    def _index_entry(self, entry: TranscriptEntry) -> None:
        """Add entry to lookup indexes."""
        # UUID index (only for Entry subclasses)
        if isinstance(entry, Entry) and entry.uuid:
            self._uuid_index[entry.uuid] = entry

        # Tool use/result indexes
        if isinstance(entry, AssistantMessage):
            for block in entry.content:
                if isinstance(block, ToolUseBlock):
                    self._tool_use_index[block.id] = block
                    block.set_transcript(self)
        elif isinstance(entry, UserMessage) and entry.is_tool_result:
            for block in entry.content:
                if isinstance(block, ToolResultBlock):
                    self._tool_result_index[block.tool_use_id] = block
                    block.set_transcript(self)

    # === Relationship Lookups ===

    def find_tool_use(self, tool_use_id: str) -> ToolUseBlock | None:
        """Find ToolUseBlock by id."""
        return self._tool_use_index.get(tool_use_id)

    def find_tool_result(self, tool_use_id: str) -> ToolResultBlock | None:
        """Find ToolResultBlock by tool_use_id."""
        return self._tool_result_index.get(tool_use_id)

    def find_by_uuid(self, uuid: str) -> Entry | None:
        """Find entry by UUID."""
        return self._uuid_index.get(uuid)

    def get_parent(self, entry: Entry) -> Entry | None:
        """Get parent entry via parent_uuid."""
        if entry.parent_uuid:
            return self.find_by_uuid(entry.parent_uuid)
        return None

    def get_children(self, entry: Entry) -> list[Entry]:
        """Get all entries with this entry as parent."""
        return [
            e
            for e in self.entries
            if isinstance(e, Entry) and e.parent_uuid == entry.uuid
        ]

    # === Pre-built Views ===

    @property
    def archived(self) -> list[TranscriptEntry]:
        """Entries before last compact boundary."""
        return self._archived

    @property
    def user_messages(self) -> list[UserMessage]:
        """All user messages (excludes archived)."""
        return [e for e in self.entries if isinstance(e, UserMessage)]

    @property
    def assistant_messages(self) -> list[AssistantMessage]:
        """All assistant messages (excludes archived)."""
        return [e for e in self.entries if isinstance(e, AssistantMessage)]

    @property
    def system_entries(self) -> list[SystemEntry]:
        """All system entries (excludes archived)."""
        return [e for e in self.entries if isinstance(e, SystemEntry)]

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
    def compact_boundaries(self) -> list[CompactBoundary]:
        """All compaction markers (including archived)."""
        all_entries = self._archived + self.entries
        return [e for e in all_entries if isinstance(e, CompactBoundary)]

    @property
    def file_snapshots(self) -> list[FileHistorySnapshot]:
        """All file history snapshots."""
        return [e for e in self.entries if isinstance(e, FileHistorySnapshot)]

    # === Iteration ===

    def __iter__(self) -> Iterator[TranscriptEntry]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def __repr__(self) -> str:
        return f"Transcript({self.path}, entries={len(self.entries)}, archived={len(self._archived)})"
