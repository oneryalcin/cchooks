"""Tests for rich transcript modeling (fasthooks.transcript)."""
from pathlib import Path

import pytest

from fasthooks.transcript import (
    AssistantMessage,
    CompactBoundary,
    Entry,
    FileHistorySnapshot,
    StopHookSummary,
    SystemEntry,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    Transcript,
    UserMessage,
    parse_content_block,
    parse_entry,
)


# Path to sample data
SAMPLE_DATA_DIR = Path(__file__).parent.parent / "specs" / "data"
SAMPLE_TRANSCRIPT = SAMPLE_DATA_DIR / "sample_main_transcript.jsonl"
SAMPLE_SIDECHAIN = SAMPLE_DATA_DIR / "sample_agent_sidechain.jsonl"


class TestContentBlocks:
    """Test content block parsing."""

    def test_text_block(self):
        data = {"type": "text", "text": "Hello world"}
        block = parse_content_block(data)
        assert isinstance(block, TextBlock)
        assert block.text == "Hello world"
        assert block.type == "text"

    def test_tool_use_block(self):
        data = {
            "type": "tool_use",
            "id": "toolu_123",
            "name": "Bash",
            "input": {"command": "ls -la"},
        }
        block = parse_content_block(data)
        assert isinstance(block, ToolUseBlock)
        assert block.id == "toolu_123"
        assert block.name == "Bash"
        assert block.input == {"command": "ls -la"}

    def test_tool_result_block(self):
        data = {
            "type": "tool_result",
            "tool_use_id": "toolu_123",
            "content": "file1.txt\nfile2.txt",
            "is_error": False,
        }
        block = parse_content_block(data)
        assert isinstance(block, ToolResultBlock)
        assert block.tool_use_id == "toolu_123"
        assert block.content == "file1.txt\nfile2.txt"
        assert block.is_error is False

    def test_tool_result_error(self):
        data = {
            "type": "tool_result",
            "tool_use_id": "toolu_456",
            "content": "Error: command not found",
            "is_error": True,
        }
        block = parse_content_block(data)
        assert isinstance(block, ToolResultBlock)
        assert block.is_error is True

    def test_thinking_block(self):
        data = {
            "type": "thinking",
            "thinking": "Let me consider...",
            "signature": "abc123xyz",
        }
        block = parse_content_block(data)
        assert isinstance(block, ThinkingBlock)
        assert block.thinking == "Let me consider..."
        assert block.signature == "abc123xyz"

    def test_unknown_block_type(self):
        """Unknown types should fallback to TextBlock."""
        data = {"type": "unknown", "text": "fallback"}
        block = parse_content_block(data)
        assert isinstance(block, TextBlock)

    def test_extra_fields_preserved(self):
        """Extra fields should be preserved via model_extra."""
        data = {"type": "text", "text": "Hello", "custom_field": "preserved"}
        block = parse_content_block(data)
        assert block.model_extra.get("custom_field") == "preserved"


class TestEntries:
    """Test entry parsing."""

    def test_user_message_text(self):
        data = {
            "type": "user",
            "uuid": "abc-123",
            "parentUuid": "parent-456",
            "timestamp": "2026-01-02T10:30:00Z",
            "sessionId": "session-789",
            "cwd": "/workspace",
            "message": {"role": "user", "content": "Hello Claude"},
        }
        entry = parse_entry(data)
        assert isinstance(entry, UserMessage)
        assert entry.uuid == "abc-123"
        assert entry.parent_uuid == "parent-456"
        assert entry.session_id == "session-789"
        assert entry.text == "Hello Claude"
        assert entry.is_tool_result is False

    def test_user_message_tool_result(self):
        data = {
            "type": "user",
            "uuid": "abc-123",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_123",
                        "content": "output here",
                        "is_error": False,
                    }
                ],
            },
            "toolUseResult": {"stdout": "output here", "stderr": ""},
        }
        entry = parse_entry(data)
        assert isinstance(entry, UserMessage)
        assert entry.is_tool_result is True
        assert len(entry.content) == 1
        assert isinstance(entry.content[0], ToolResultBlock)

    def test_assistant_message(self):
        data = {
            "type": "assistant",
            "uuid": "asst-123",
            "requestId": "req-456",
            "message": {
                "model": "claude-haiku-4-5-20251001",
                "id": "msg_789",
                "content": [
                    {"type": "text", "text": "Here's the output"},
                    {"type": "tool_use", "id": "toolu_abc", "name": "Bash", "input": {}},
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        }
        entry = parse_entry(data)
        assert isinstance(entry, AssistantMessage)
        assert entry.request_id == "req-456"
        assert entry.message_id == "msg_789"
        assert entry.model == "claude-haiku-4-5-20251001"
        assert entry.stop_reason == "tool_use"
        assert entry.text == "Here's the output"
        assert len(entry.tool_uses) == 1
        assert entry.has_tool_use is True

    def test_assistant_message_with_thinking(self):
        data = {
            "type": "assistant",
            "uuid": "asst-123",
            "message": {
                "content": [
                    {"type": "thinking", "thinking": "Let me think...", "signature": ""},
                    {"type": "text", "text": "I'll help you"},
                ],
            },
        }
        entry = parse_entry(data)
        assert isinstance(entry, AssistantMessage)
        assert entry.thinking == "Let me think..."
        assert entry.text == "I'll help you"

    def test_system_entry(self):
        data = {
            "type": "system",
            "subtype": "custom",
            "uuid": "sys-123",
            "content": "System message",
            "level": "info",
        }
        entry = parse_entry(data)
        assert isinstance(entry, SystemEntry)
        assert entry.subtype == "custom"
        assert entry.content == "System message"

    def test_compact_boundary(self):
        data = {
            "type": "system",
            "subtype": "compact_boundary",
            "uuid": "compact-123",
            "parentUuid": None,
            "logicalParentUuid": "logical-parent-456",
            "compactMetadata": {"trigger": "manual", "preTokens": 10000},
        }
        entry = parse_entry(data)
        assert isinstance(entry, CompactBoundary)
        assert entry.logical_parent_uuid == "logical-parent-456"
        assert entry.compact_metadata["trigger"] == "manual"
        assert entry.parent_uuid is None

    def test_stop_hook_summary(self):
        data = {
            "type": "system",
            "subtype": "stop_hook_summary",
            "uuid": "hook-123",
            "hookCount": 2,
            "hookInfos": [{"command": "hook1"}, {"command": "hook2"}],
            "preventedContinuation": False,
        }
        entry = parse_entry(data)
        assert isinstance(entry, StopHookSummary)
        assert entry.hook_count == 2
        assert len(entry.hook_infos) == 2
        assert entry.prevented_continuation is False

    def test_file_history_snapshot(self):
        data = {
            "type": "file-history-snapshot",
            "messageId": "msg-123",
            "snapshot": {"trackedFileBackups": {}},
            "isSnapshotUpdate": True,
        }
        entry = parse_entry(data)
        assert isinstance(entry, FileHistorySnapshot)
        assert entry.message_id == "msg-123"
        assert entry.is_snapshot_update is True

    def test_field_aliases(self):
        """Field aliases (camelCase -> snake_case) should work."""
        data = {
            "type": "user",
            "uuid": "test",
            "parentUuid": "parent",
            "sessionId": "session",
            "gitBranch": "main",
            "isSidechain": True,
            "userType": "external",
            "message": {"content": "test"},
        }
        entry = parse_entry(data)
        assert entry.parent_uuid == "parent"
        assert entry.session_id == "session"
        assert entry.git_branch == "main"
        assert entry.is_sidechain is True
        assert entry.user_type == "external"


@pytest.mark.skipif(
    not SAMPLE_TRANSCRIPT.exists(), reason="Sample transcript not found"
)
class TestTranscriptLoading:
    """Test loading real transcript data."""

    def test_load_sample_transcript(self):
        t = Transcript(SAMPLE_TRANSCRIPT)
        t.load()

        # Should have entries
        assert len(t.entries) > 0 or len(t.archived) > 0

        # Should have compact boundary
        assert len(t.compact_boundaries) == 1

        # Should have tool uses and results
        assert len(t.tool_uses) > 0
        assert len(t.tool_results) > 0

    def test_archived_vs_current(self):
        """Entries before compact boundary should be archived."""
        t = Transcript(SAMPLE_TRANSCRIPT)
        t.load()

        # Most entries are before compact boundary
        assert len(t.archived) > len(t.entries)

        # Compact boundary should be in archived
        assert any(isinstance(e, CompactBoundary) for e in t.archived)

    def test_tool_use_result_relationship(self):
        """Tool use should link to its result."""
        t = Transcript(SAMPLE_TRANSCRIPT)
        t.load()

        # Find a tool use and verify its result
        linked_count = 0
        for tu in t.tool_uses:
            result = tu.result
            if result:
                assert result.tool_use_id == tu.id
                # Verify reverse lookup
                assert result.tool_use == tu
                linked_count += 1

        # Should have at least some linked pairs
        assert linked_count > 0

    def test_error_detection(self):
        """Should detect tool errors."""
        t = Transcript(SAMPLE_TRANSCRIPT)
        t.load()

        # Sample has at least one error (cat nonexistent.txt)
        assert len(t.errors) > 0
        for err in t.errors:
            assert err.is_error is True

    def test_uuid_index(self):
        """Should be able to find entries by UUID."""
        t = Transcript(SAMPLE_TRANSCRIPT)
        t.load()

        # Find any entry with UUID
        all_entries = list(t.entries) + list(t.archived)
        for entry in all_entries:
            if isinstance(entry, Entry) and entry.uuid:
                found = t.find_by_uuid(entry.uuid)
                assert found is not None
                assert found.uuid == entry.uuid
                break

    def test_iteration(self):
        """Can iterate over transcript entries."""
        t = Transcript(SAMPLE_TRANSCRIPT)
        t.load()

        count = 0
        for entry in t:
            count += 1
        assert count == len(t)
        assert count == len(t.entries)


@pytest.mark.skipif(not SAMPLE_SIDECHAIN.exists(), reason="Sample sidechain not found")
class TestSidechainLoading:
    """Test loading agent sidechain transcript."""

    def test_load_sidechain(self):
        t = Transcript(SAMPLE_SIDECHAIN)
        t.load()

        # Should have entries
        assert len(t.entries) > 0

        # Should have is_sidechain=True
        for entry in t.entries:
            if isinstance(entry, Entry):
                assert entry.is_sidechain is True


class TestTranscriptEmpty:
    """Test empty/missing transcript handling."""

    def test_nonexistent_file(self, tmp_path):
        t = Transcript(tmp_path / "nonexistent.jsonl")
        t.load()
        assert len(t.entries) == 0
        assert len(t.archived) == 0

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        t = Transcript(path)
        t.load()
        assert len(t.entries) == 0


class TestTranscriptViews:
    """Test pre-built views."""

    @pytest.fixture
    def transcript_with_entries(self, tmp_path):
        """Create transcript with various entry types."""
        import json

        path = tmp_path / "test.jsonl"
        entries = [
            {
                "type": "user",
                "uuid": "u1",
                "message": {"content": "Hello"},
            },
            {
                "type": "assistant",
                "uuid": "a1",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
                    ],
                },
            },
            {
                "type": "user",
                "uuid": "u2",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "ok", "is_error": False},
                    ],
                },
            },
            {
                "type": "assistant",
                "uuid": "a2",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {}},
                    ],
                },
            },
            {
                "type": "user",
                "uuid": "u3",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t2", "content": "error", "is_error": True},
                    ],
                },
            },
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        t.load()
        return t

    def test_user_messages(self, transcript_with_entries):
        t = transcript_with_entries
        assert len(t.user_messages) == 3

    def test_assistant_messages(self, transcript_with_entries):
        t = transcript_with_entries
        assert len(t.assistant_messages) == 2

    def test_tool_uses(self, transcript_with_entries):
        t = transcript_with_entries
        assert len(t.tool_uses) == 2

    def test_tool_results(self, transcript_with_entries):
        t = transcript_with_entries
        assert len(t.tool_results) == 2

    def test_errors(self, transcript_with_entries):
        t = transcript_with_entries
        assert len(t.errors) == 1
        assert t.errors[0].tool_use_id == "t2"
