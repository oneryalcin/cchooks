"""Transcript parsing with lazy loading."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class TranscriptStats:
    """Statistics extracted from a transcript."""

    message_counts: dict[str, int] = field(default_factory=dict)
    tool_calls: dict[str, int] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    duration_seconds: float = 0.0
    files_read_count: int = 0
    files_written_count: int = 0
    compact_count: int = 0
    slug: str | None = None


class Transcript:
    """Lazy-loading transcript parser.

    Doesn't parse the transcript until stats/messages/etc are accessed.
    Results are cached after first access.
    """

    def __init__(self, path: str | None):
        self.path = path
        self._stats_cache: TranscriptStats | None = None
        self._entries_cache: list[dict] | None = None

    def _load_entries(self) -> list[dict]:
        """Load and cache transcript entries."""
        if self._entries_cache is not None:
            return self._entries_cache

        self._entries_cache = []
        if not self.path or not Path(self.path).exists():
            return self._entries_cache

        try:
            with open(self.path) as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        self._entries_cache.append(entry)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

        return self._entries_cache

    @property
    def stats(self) -> TranscriptStats:
        """Parse and return transcript statistics (lazy, cached)."""
        if self._stats_cache is not None:
            return self._stats_cache

        self._stats_cache = self._parse_stats()
        return self._stats_cache

    def _parse_stats(self) -> TranscriptStats:
        """Parse transcript and extract statistics."""
        stats = TranscriptStats()
        entries = self._load_entries()

        if not entries:
            return stats

        msg_counts: dict[str, int] = {"user": 0, "assistant": 0, "system": 0}
        tool_calls: dict[str, int] = {}
        files_read: set[str] = set()
        files_written: set[str] = set()
        first_ts: str | None = None
        last_ts: str | None = None

        for entry in entries:
            # Track timestamps
            ts = entry.get("timestamp")
            if ts:
                if not first_ts:
                    first_ts = ts
                last_ts = ts

            # Capture slug
            if entry.get("slug") and not stats.slug:
                stats.slug = entry["slug"]

            # Count message types
            msg_type = entry.get("type")
            if msg_type in msg_counts:
                msg_counts[msg_type] += 1

            # Count compact boundaries
            if entry.get("subtype") == "compact_boundary":
                stats.compact_count += 1

            # Extract from assistant messages
            if msg_type == "assistant":
                message = entry.get("message", {})
                usage = message.get("usage", {})

                stats.input_tokens += usage.get("input_tokens", 0)
                stats.output_tokens += usage.get("output_tokens", 0)
                stats.cache_read_tokens += usage.get("cache_read_input_tokens", 0)
                stats.cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)

                # Count tool calls and track files
                content = message.get("content", [])
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_calls[tool_name] = tool_calls.get(tool_name, 0) + 1

                        tool_input = block.get("input", {})
                        if tool_name == "Read" and tool_input.get("file_path"):
                            files_read.add(tool_input["file_path"])
                        elif tool_name in ("Write", "Edit") and tool_input.get("file_path"):
                            files_written.add(tool_input["file_path"])

        # Calculate duration
        if first_ts and last_ts:
            try:
                first = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                last = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                stats.duration_seconds = (last - first).total_seconds()
            except (ValueError, TypeError):
                pass

        # Only include non-zero message counts
        stats.message_counts = {k: v for k, v in msg_counts.items() if v > 0}
        stats.tool_calls = tool_calls
        stats.files_read_count = len(files_read)
        stats.files_written_count = len(files_written)

        return stats

    @property
    def messages(self) -> list[dict]:
        """Get all user/assistant messages."""
        entries = self._load_entries()
        return [e for e in entries if e.get("type") in ("user", "assistant")]

    @property
    def last_assistant_message(self) -> str:
        """Get text content of last assistant message."""
        entries = self._load_entries()
        last_text = ""

        for entry in entries:
            if entry.get("type") == "assistant":
                message = entry.get("message", {})
                content = message.get("content", [])
                texts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))
                if texts:
                    last_text = "\n".join(texts)

        return last_text

    @property
    def bash_commands(self) -> list[str]:
        """Get all bash commands executed in session."""
        entries = self._load_entries()
        commands = []

        for entry in entries:
            if entry.get("type") == "assistant":
                message = entry.get("message", {})
                content = message.get("content", [])
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        if block.get("name") == "Bash":
                            cmd = block.get("input", {}).get("command", "")
                            if cmd:
                                commands.append(cmd)

        return commands
