"""Tests for Transcript dependency."""
import json
import tempfile
from pathlib import Path

import pytest

from fasthooks.depends import Transcript


class TestTranscriptBasic:
    def test_create_transcript(self):
        """Transcript can be instantiated with path."""
        t = Transcript("/some/path.jsonl")
        assert t.path == "/some/path.jsonl"

    def test_transcript_none_path(self):
        """Transcript handles None path gracefully."""
        t = Transcript(None)
        assert t.path is None
        assert t.stats.message_counts == {}

    def test_transcript_missing_file(self):
        """Transcript handles missing file gracefully."""
        t = Transcript("/nonexistent/path.jsonl")
        assert t.stats.message_counts == {}


class TestTranscriptStats:
    @pytest.fixture
    def sample_transcript(self, tmp_path):
        """Create a sample transcript file."""
        transcript_file = tmp_path / "transcript.jsonl"
        entries = [
            {
                "type": "system",
                "timestamp": "2024-01-01T10:00:00Z",
                "slug": "test-session",
            },
            {
                "type": "user",
                "timestamp": "2024-01-01T10:00:01Z",
                "message": {"content": "Hello"},
            },
            {
                "type": "assistant",
                "timestamp": "2024-01-01T10:00:05Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "Hi there!"},
                        {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                        {"type": "tool_use", "name": "Bash", "input": {"command": "pwd"}},
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "/test.py"}},
                    ],
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_read_input_tokens": 20,
                        "cache_creation_input_tokens": 10,
                    },
                },
            },
            {
                "type": "user",
                "timestamp": "2024-01-01T10:00:10Z",
                "message": {"content": "Thanks"},
            },
            {
                "type": "assistant",
                "timestamp": "2024-01-01T10:00:15Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "You're welcome!"},
                        {"type": "tool_use", "name": "Write", "input": {"file_path": "/out.txt"}},
                    ],
                    "usage": {
                        "input_tokens": 150,
                        "output_tokens": 30,
                    },
                },
            },
        ]
        with open(transcript_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return transcript_file

    def test_message_counts(self, sample_transcript):
        """Stats includes message counts by type."""
        t = Transcript(str(sample_transcript))
        assert t.stats.message_counts == {"user": 2, "assistant": 2, "system": 1}

    def test_tool_calls(self, sample_transcript):
        """Stats includes tool call counts."""
        t = Transcript(str(sample_transcript))
        assert t.stats.tool_calls == {"Bash": 2, "Read": 1, "Write": 1}

    def test_token_usage(self, sample_transcript):
        """Stats includes token usage."""
        t = Transcript(str(sample_transcript))
        assert t.stats.input_tokens == 250
        assert t.stats.output_tokens == 80
        assert t.stats.cache_read_tokens == 20
        assert t.stats.cache_creation_tokens == 10

    def test_duration(self, sample_transcript):
        """Stats includes session duration."""
        t = Transcript(str(sample_transcript))
        assert t.stats.duration_seconds == 15.0

    def test_file_counts(self, sample_transcript):
        """Stats includes file read/write counts."""
        t = Transcript(str(sample_transcript))
        assert t.stats.files_read_count == 1
        assert t.stats.files_written_count == 1

    def test_slug(self, sample_transcript):
        """Stats includes session slug."""
        t = Transcript(str(sample_transcript))
        assert t.stats.slug == "test-session"


class TestTranscriptLazyLoading:
    def test_stats_not_parsed_until_accessed(self, tmp_path):
        """Transcript doesn't parse until stats accessed."""
        transcript_file = tmp_path / "transcript.jsonl"
        transcript_file.write_text('{"type": "user"}\n')

        t = Transcript(str(transcript_file))
        # Cache should be None before access
        assert t._stats_cache is None

        # Access stats triggers parsing
        _ = t.stats
        assert t._stats_cache is not None

    def test_stats_cached(self, tmp_path):
        """Stats are cached after first access."""
        transcript_file = tmp_path / "transcript.jsonl"
        transcript_file.write_text('{"type": "user"}\n')

        t = Transcript(str(transcript_file))
        stats1 = t.stats
        stats2 = t.stats
        assert stats1 is stats2  # Same object


class TestTranscriptMessages:
    @pytest.fixture
    def transcript_with_messages(self, tmp_path):
        """Create transcript with message content."""
        transcript_file = tmp_path / "transcript.jsonl"
        entries = [
            {
                "type": "user",
                "message": {"content": "First question"},
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "First answer"},
                    ],
                },
            },
            {
                "type": "user",
                "message": {"content": "Second question"},
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Second answer"},
                    ],
                },
            },
        ]
        with open(transcript_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return transcript_file

    def test_messages_property(self, transcript_with_messages):
        """Can access all messages."""
        t = Transcript(str(transcript_with_messages))
        assert len(t.messages) == 4

    def test_last_assistant_message(self, transcript_with_messages):
        """Can get last assistant message."""
        t = Transcript(str(transcript_with_messages))
        assert t.last_assistant_message == "Second answer"


class TestTranscriptBashCommands:
    @pytest.fixture
    def transcript_with_bash(self, tmp_path):
        """Create transcript with bash commands."""
        transcript_file = tmp_path / "transcript.jsonl"
        entries = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}},
                        {"type": "tool_use", "name": "Bash", "input": {"command": "pwd"}},
                    ],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "/test"}},
                        {"type": "tool_use", "name": "Bash", "input": {"command": "git status"}},
                    ],
                },
            },
        ]
        with open(transcript_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return transcript_file

    def test_bash_commands(self, transcript_with_bash):
        """Can extract all bash commands."""
        t = Transcript(str(transcript_with_bash))
        assert t.bash_commands == ["ls -la", "pwd", "git status"]
