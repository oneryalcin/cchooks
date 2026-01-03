"""Tests for Transcript dependency (DI integration)."""
import json
from pathlib import Path

import pytest

from fasthooks.depends import Transcript, TranscriptStats


class TestTranscriptBasic:
    def test_create_transcript(self):
        """Transcript can be instantiated with path."""
        t = Transcript("/some/path.jsonl", auto_load=False)
        assert t.path == Path("/some/path.jsonl")

    def test_transcript_none_path(self):
        """Transcript handles None path gracefully."""
        t = Transcript(None)
        assert t.path is None
        assert t.stats.message_count == 0

    def test_transcript_missing_file(self):
        """Transcript handles missing file gracefully."""
        t = Transcript("/nonexistent/path.jsonl")
        assert t.stats.message_count == 0


class TestTranscriptStats:
    @pytest.fixture
    def sample_transcript(self, tmp_path):
        """Create a sample transcript file."""
        transcript_file = tmp_path / "transcript.jsonl"
        entries = [
            {
                "type": "system",
                "uuid": "sys-1",
                "timestamp": "2024-01-01T10:00:00Z",
                "slug": "test-session",
            },
            {
                "type": "user",
                "uuid": "user-1",
                "parentUuid": "sys-1",
                "timestamp": "2024-01-01T10:00:01Z",
                "message": {"role": "user", "content": "Hello"},
            },
            {
                "type": "assistant",
                "uuid": "asst-1",
                "parentUuid": "user-1",
                "requestId": "req-1",
                "timestamp": "2024-01-01T10:00:05Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Hi there!"},
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "Bash",
                            "input": {"command": "ls"},
                        },
                        {
                            "type": "tool_use",
                            "id": "tool-2",
                            "name": "Bash",
                            "input": {"command": "pwd"},
                        },
                        {
                            "type": "tool_use",
                            "id": "tool-3",
                            "name": "Read",
                            "input": {"file_path": "/test.py"},
                        },
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
                "uuid": "user-2",
                "parentUuid": "asst-1",
                "timestamp": "2024-01-01T10:00:10Z",
                "message": {"role": "user", "content": "Thanks"},
            },
            {
                "type": "assistant",
                "uuid": "asst-2",
                "parentUuid": "user-2",
                "requestId": "req-2",
                "timestamp": "2024-01-01T10:00:15Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "You're welcome!"},
                        {
                            "type": "tool_use",
                            "id": "tool-4",
                            "name": "Write",
                            "input": {"file_path": "/out.txt"},
                        },
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

    def test_message_count(self, sample_transcript):
        """Stats includes message count."""
        t = Transcript(str(sample_transcript))
        # 2 user + 2 assistant = 4 messages
        assert t.stats.message_count == 4

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
        assert t.stats.duration_seconds == 15.0  # 10:00:00 (system) to 10:00:15

    def test_slug(self, sample_transcript):
        """Stats includes session slug."""
        t = Transcript(str(sample_transcript))
        assert t.stats.slug == "test-session"

    def test_turn_count(self, sample_transcript):
        """Stats includes turn count."""
        t = Transcript(str(sample_transcript))
        assert t.stats.turn_count == 2  # 2 request IDs


class TestTranscriptAutoLoad:
    def test_auto_load_enabled_by_default(self, tmp_path):
        """Transcript auto-loads when path provided."""
        transcript_file = tmp_path / "transcript.jsonl"
        transcript_file.write_text('{"type": "user", "uuid": "u1", "message": {"role": "user", "content": "hi"}}\n')

        t = Transcript(str(transcript_file))
        # Should be loaded already
        assert t._loaded is True
        assert len(t.entries) == 1

    def test_auto_load_disabled(self, tmp_path):
        """Transcript doesn't load when auto_load=False."""
        transcript_file = tmp_path / "transcript.jsonl"
        transcript_file.write_text('{"type": "user", "uuid": "u1", "message": {"role": "user", "content": "hi"}}\n')

        t = Transcript(str(transcript_file), auto_load=False)
        # Should not be loaded yet
        assert t._loaded is False
        assert len(t.entries) == 0

        # Explicit load
        t.load()
        assert t._loaded is True
        assert len(t.entries) == 1


class TestTranscriptMessages:
    @pytest.fixture
    def transcript_with_messages(self, tmp_path):
        """Create transcript with message content."""
        transcript_file = tmp_path / "transcript.jsonl"
        entries = [
            {
                "type": "user",
                "uuid": "u1",
                "message": {"role": "user", "content": "First question"},
            },
            {
                "type": "assistant",
                "uuid": "a1",
                "parentUuid": "u1",
                "requestId": "r1",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "First answer"},
                    ],
                },
            },
            {
                "type": "user",
                "uuid": "u2",
                "parentUuid": "a1",
                "message": {"role": "user", "content": "Second question"},
            },
            {
                "type": "assistant",
                "uuid": "a2",
                "parentUuid": "u2",
                "requestId": "r2",
                "message": {
                    "role": "assistant",
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

    def test_user_messages(self, transcript_with_messages):
        """Can access user messages."""
        t = Transcript(str(transcript_with_messages))
        assert len(t.user_messages) == 2
        assert t.user_messages[0].text == "First question"
        assert t.user_messages[1].text == "Second question"

    def test_assistant_messages(self, transcript_with_messages):
        """Can access assistant messages."""
        t = Transcript(str(transcript_with_messages))
        assert len(t.assistant_messages) == 2
        assert t.assistant_messages[0].text == "First answer"
        assert t.assistant_messages[1].text == "Second answer"


class TestTranscriptToolUses:
    @pytest.fixture
    def transcript_with_tools(self, tmp_path):
        """Create transcript with tool uses."""
        transcript_file = tmp_path / "transcript.jsonl"
        entries = [
            {
                "type": "assistant",
                "uuid": "a1",
                "requestId": "r1",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t1",
                            "name": "Bash",
                            "input": {"command": "ls -la"},
                        },
                        {
                            "type": "tool_use",
                            "id": "t2",
                            "name": "Bash",
                            "input": {"command": "pwd"},
                        },
                    ],
                },
            },
            {
                "type": "assistant",
                "uuid": "a2",
                "parentUuid": "a1",
                "requestId": "r2",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "t3",
                            "name": "Read",
                            "input": {"file_path": "/test"},
                        },
                        {
                            "type": "tool_use",
                            "id": "t4",
                            "name": "Bash",
                            "input": {"command": "git status"},
                        },
                    ],
                },
            },
        ]
        with open(transcript_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return transcript_file

    def test_tool_uses(self, transcript_with_tools):
        """Can extract all tool uses."""
        t = Transcript(str(transcript_with_tools))
        tool_uses = t.tool_uses
        assert len(tool_uses) == 4

        # Check Bash commands
        bash_uses = [tu for tu in tool_uses if tu.name == "Bash"]
        assert len(bash_uses) == 3
        commands = [tu.input.get("command") for tu in bash_uses]
        assert "ls -la" in commands
        assert "pwd" in commands
        assert "git status" in commands


class TestDIIntegration:
    """Test that Transcript works correctly when injected via DI."""

    def test_transcript_from_depends_import(self):
        """Can import Transcript from fasthooks.depends."""
        from fasthooks.depends import Transcript as DepTranscript
        from fasthooks.transcript import Transcript as CoreTranscript

        # They should be the same class
        assert DepTranscript is CoreTranscript

    def test_transcript_stats_from_depends_import(self):
        """Can import TranscriptStats from fasthooks.depends."""
        from fasthooks.depends import TranscriptStats as DepStats
        from fasthooks.transcript import TranscriptStats as CoreStats

        # They should be the same class
        assert DepStats is CoreStats
