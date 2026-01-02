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


class TestNewFeatures:
    """Test new features: turns, include_archived, logical_parent, etc."""

    @pytest.fixture
    def transcript_with_turns(self, tmp_path):
        """Create transcript with multiple entries per turn (same requestId)."""
        import json

        path = tmp_path / "turns.jsonl"
        entries = [
            {
                "type": "user",
                "uuid": "u1",
                "parentUuid": None,
                "message": {"content": "Hello"},
            },
            {
                "type": "assistant",
                "uuid": "a1",
                "parentUuid": "u1",
                "requestId": "req_001",
                "message": {
                    "content": [{"type": "thinking", "thinking": "Let me think...", "signature": ""}],
                },
            },
            {
                "type": "assistant",
                "uuid": "a2",
                "parentUuid": "a1",
                "requestId": "req_001",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
                    ],
                },
            },
            {
                "type": "user",
                "uuid": "u2",
                "parentUuid": "a2",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "ok", "is_error": False},
                    ],
                },
            },
            {
                "type": "assistant",
                "uuid": "a3",
                "parentUuid": "u2",
                "requestId": "req_001",
                "message": {
                    "content": [{"type": "text", "text": "Done!"}],
                    "stop_reason": "end_turn",
                },
            },
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        t.load()
        return t

    def test_turns_grouping(self, transcript_with_turns):
        """Entries with same requestId should group into a Turn."""
        t = transcript_with_turns
        turns = t.turns
        assert len(turns) == 1
        turn = turns[0]
        assert turn.request_id == "req_001"
        assert len(turn.entries) == 3  # a1, a2, a3

    def test_turn_properties(self, transcript_with_turns):
        """Turn should expose combined properties."""
        t = transcript_with_turns
        turn = t.turns[0]
        assert "Let me think" in turn.thinking
        assert "Done!" in turn.text
        assert len(turn.tool_uses) == 1
        assert turn.is_complete is True
        assert turn.has_tool_use is True

    def test_get_entries_by_request_id(self, transcript_with_turns):
        """Should find all entries with given requestId."""
        t = transcript_with_turns
        entries = t.get_entries_by_request_id("req_001")
        assert len(entries) == 3

    @pytest.fixture
    def transcript_with_compact(self, tmp_path):
        """Create transcript with compaction."""
        import json

        path = tmp_path / "compact.jsonl"
        entries = [
            # Archived entries
            {"type": "user", "uuid": "old1", "parentUuid": None, "message": {"content": "Old message"}},
            {"type": "assistant", "uuid": "old2", "parentUuid": "old1", "message": {"content": []}},
            # Compact boundary
            {
                "type": "system",
                "subtype": "compact_boundary",
                "uuid": "compact1",
                "parentUuid": None,
                "logicalParentUuid": "old2",
                "compactMetadata": {"trigger": "manual"},
            },
            # Current entries
            {"type": "user", "uuid": "new1", "parentUuid": "compact1", "message": {"content": "New message"}},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        t.load()
        return t

    def test_get_logical_parent(self, transcript_with_compact):
        """CompactBoundary should return logical parent."""
        t = transcript_with_compact
        boundary = t.compact_boundaries[0]
        logical_parent = t.get_logical_parent(boundary)
        assert logical_parent is not None
        assert logical_parent.uuid == "old2"

    def test_include_archived_default_false(self, transcript_with_compact):
        """Views should exclude archived by default."""
        t = transcript_with_compact
        assert len(t.user_messages) == 1  # Only new1
        assert t.user_messages[0].uuid == "new1"

    def test_include_archived_true(self, transcript_with_compact):
        """Views should include archived when flag set."""
        t = transcript_with_compact
        t.include_archived = True
        assert len(t.user_messages) == 2  # old1 and new1

    def test_get_user_messages_with_param(self, transcript_with_compact):
        """get_user_messages should accept include_archived param."""
        t = transcript_with_compact
        assert len(t.get_user_messages(include_archived=False)) == 1
        assert len(t.get_user_messages(include_archived=True)) == 2

    def test_get_children_with_archived(self, transcript_with_compact):
        """get_children should optionally search archived."""
        t = transcript_with_compact
        old1 = t.find_by_uuid("old1")
        # Default: only search current
        assert len(t.get_children(old1)) == 0
        # With include_archived
        children = t.get_children(old1, include_archived=True)
        assert len(children) == 1
        assert children[0].uuid == "old2"

    @pytest.fixture
    def transcript_with_snapshots(self, tmp_path):
        """Create transcript with file history snapshots."""
        import json

        path = tmp_path / "snapshots.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "message": {"content": "Create file"}},
            {
                "type": "file-history-snapshot",
                "messageId": "u1",
                "snapshot": {"trackedFileBackups": {"test.py": {"version": 1}}},
                "isSnapshotUpdate": False,
            },
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        t.load()
        return t

    def test_find_snapshot(self, transcript_with_snapshots):
        """Should find snapshot by message_id."""
        t = transcript_with_snapshots
        snapshot = t.find_snapshot("u1")
        assert snapshot is not None
        assert "test.py" in snapshot.snapshot["trackedFileBackups"]

    @pytest.fixture
    def transcript_with_meta(self, tmp_path):
        """Create transcript with meta entries."""
        import json

        path = tmp_path / "meta.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "message": {"content": "Normal"}, "isMeta": False},
            {"type": "user", "uuid": "u2", "message": {"content": "Meta"}, "isMeta": True},
            {"type": "user", "uuid": "u3", "message": {"content": "Visible only"}, "isVisibleInTranscriptOnly": True},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        t.load()
        return t

    def test_meta_filtered_by_default(self, transcript_with_meta):
        """Meta entries should be filtered by default."""
        t = transcript_with_meta
        assert len(t.user_messages) == 1
        assert t.user_messages[0].uuid == "u1"

    def test_include_meta_true(self, transcript_with_meta):
        """Setting include_meta=True should include all entries."""
        t = transcript_with_meta
        t.include_meta = True
        assert len(t.user_messages) == 3


class TestCRUDOperations:
    """Test CRUD operations: save, remove, insert, append, replace."""

    @pytest.fixture
    def transcript_with_chain(self, tmp_path):
        """Create transcript with linked entries."""
        import json

        path = tmp_path / "chain.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "parentUuid": None, "message": {"content": "First"}},
            {"type": "assistant", "uuid": "a1", "parentUuid": "u1", "message": {"content": [{"type": "text", "text": "Response"}]}},
            {"type": "user", "uuid": "u2", "parentUuid": "a1", "message": {"content": "Second"}},
            {"type": "assistant", "uuid": "a2", "parentUuid": "u2", "message": {"content": [{"type": "text", "text": "Response2"}]}},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        t.load()
        return t

    def test_remove_with_relink(self, transcript_with_chain):
        """Remove entry should relink children to parent."""
        t = transcript_with_chain
        a1 = t.find_by_uuid("a1")
        t.remove(a1, relink=True)

        assert len(t.entries) == 3
        assert t.find_by_uuid("a1") is None
        u2 = t.find_by_uuid("u2")
        assert u2.parent_uuid == "u1"  # Relinked to a1's parent

    def test_remove_without_relink(self, transcript_with_chain):
        """Remove without relink leaves orphans."""
        t = transcript_with_chain
        a1 = t.find_by_uuid("a1")
        t.remove(a1, relink=False)

        u2 = t.find_by_uuid("u2")
        assert u2.parent_uuid == "a1"  # Still points to removed entry

    def test_remove_tree(self, transcript_with_chain):
        """Remove tree should remove entry and all descendants."""
        t = transcript_with_chain
        a1 = t.find_by_uuid("a1")
        removed = t.remove_tree(a1)

        assert len(removed) == 3  # a1, u2, a2
        assert len(t.entries) == 1
        assert t.find_by_uuid("u1") is not None
        assert t.find_by_uuid("a1") is None
        assert t.find_by_uuid("u2") is None

    def test_insert_rewires_chain(self, transcript_with_chain):
        """Insert should rewire parent_uuid chain."""
        t = transcript_with_chain
        new_entry = Entry(type="system", uuid="s1")
        t.insert(1, new_entry)

        assert len(t.entries) == 5
        assert new_entry.parent_uuid == "u1"  # Parent is previous entry
        a1 = t.find_by_uuid("a1")
        assert a1.parent_uuid == "s1"  # Next entry relinked

    def test_insert_at_start(self, transcript_with_chain):
        """Insert at index 0 should have no parent."""
        t = transcript_with_chain
        new_entry = Entry(type="system", uuid="s0")
        t.insert(0, new_entry)

        assert new_entry.parent_uuid is None
        u1 = t.find_by_uuid("u1")
        assert u1.parent_uuid == "s0"

    def test_append_sets_parent(self, transcript_with_chain):
        """Append should set parent to last entry."""
        t = transcript_with_chain
        new_entry = Entry(type="user", uuid="u3")
        t.append(new_entry)

        assert len(t.entries) == 5
        assert new_entry.parent_uuid == "a2"

    def test_replace_preserves_chain(self, transcript_with_chain):
        """Replace should preserve chain position."""
        t = transcript_with_chain
        old = t.find_by_uuid("a1")
        new = Entry(type="system", uuid="replacement")
        t.replace(old, new)

        assert t.find_by_uuid("a1") is None
        assert new.parent_uuid == "u1"  # Inherited from old
        u2 = t.find_by_uuid("u2")
        assert u2.parent_uuid == "replacement"  # Relinked

    def test_save_and_reload(self, transcript_with_chain):
        """Save should write entries and reload should preserve them."""
        t = transcript_with_chain
        path = t.path

        # Modify
        new_entry = Entry(type="system", uuid="added")
        t.append(new_entry)
        t.save()

        # Reload
        t2 = Transcript(path)
        t2.load()
        assert len(t2.entries) == 5
        assert t2.find_by_uuid("added") is not None
        added = t2.find_by_uuid("added")
        assert added.parent_uuid == "a2"

    def test_to_dict_preserves_structure(self, transcript_with_chain):
        """to_dict should preserve camelCase and nested structure."""
        t = transcript_with_chain
        a1 = t.find_by_uuid("a1")  # Has parentUuid set
        data = a1.to_dict()

        assert "parentUuid" in data  # camelCase alias
        assert data["parentUuid"] == "u1"
        assert "requestId" in data or "message" in data  # Has nested structure
        assert "_line_number" not in data  # Internal field excluded

    def test_remove_updates_indexes(self, transcript_with_chain):
        """Remove should update lookup indexes."""
        t = transcript_with_chain
        a1 = t.find_by_uuid("a1")
        tool_use_count_before = len(t.tool_uses)

        t.remove(a1)

        assert t.find_by_uuid("a1") is None
        # Index should be updated
        assert a1 not in t.assistant_messages

    def test_insert_at_zero_clears_parent(self, transcript_with_chain):
        """Insert at index 0 should set parent_uuid to None."""
        t = transcript_with_chain
        # Create entry with existing parent_uuid
        new_entry = Entry(type="system", uuid="s0", parent_uuid="stale_parent")
        t.insert(0, new_entry)

        assert new_entry.parent_uuid is None  # Should be cleared
        u1 = t.find_by_uuid("u1")
        assert u1.parent_uuid == "s0"  # First entry relinked

    def test_remove_first_entry(self, transcript_with_chain):
        """Remove first entry should not break chain."""
        t = transcript_with_chain
        u1 = t.find_by_uuid("u1")
        t.remove(u1, relink=True)

        # a1 should now have no parent
        a1 = t.find_by_uuid("a1")
        assert a1.parent_uuid is None

    def test_remove_last_entry(self, transcript_with_chain):
        """Remove last entry should work correctly."""
        t = transcript_with_chain
        a2 = t.find_by_uuid("a2")
        t.remove(a2)

        assert len(t.entries) == 3
        assert t.find_by_uuid("a2") is None


class TestSerializationRoundTrip:
    """Test that modifications are preserved through save/load cycle."""

    def test_assistant_message_content_modification(self, tmp_path):
        """Modified content blocks should be saved correctly."""
        import json

        path = tmp_path / "test.jsonl"
        entry = {
            "type": "assistant",
            "uuid": "a1",
            "parentUuid": None,
            "message": {
                "content": [{"type": "text", "text": "Original"}],
                "model": "claude-3",
            },
        }
        with open(path, "w") as f:
            f.write(json.dumps(entry) + "\n")

        t = Transcript(path)
        t.load()
        e = t.entries[0]

        # Modify content
        e.content[0].text = "MODIFIED"
        t.save()

        # Reload and verify
        t2 = Transcript(path)
        t2.load()
        assert t2.entries[0].text == "MODIFIED"

    def test_user_message_tool_result_modification(self, tmp_path):
        """Modified tool results should be saved correctly."""
        import json

        path = tmp_path / "test.jsonl"
        entry = {
            "type": "user",
            "uuid": "u1",
            "parentUuid": None,
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "Original", "is_error": False}
                ]
            },
        }
        with open(path, "w") as f:
            f.write(json.dumps(entry) + "\n")

        t = Transcript(path)
        t.load()
        e = t.entries[0]

        # Modify tool result
        e.tool_results[0].content = "MODIFIED"
        t.save()

        # Reload and verify
        t2 = Transcript(path)
        t2.load()
        assert t2.entries[0].tool_results[0].content == "MODIFIED"

    def test_assistant_message_preserves_all_fields(self, tmp_path):
        """All AssistantMessage fields should survive round-trip."""
        import json

        path = tmp_path / "test.jsonl"
        entry = {
            "type": "assistant",
            "uuid": "a1",
            "parentUuid": None,
            "requestId": "req_123",
            "message": {
                "id": "msg_456",
                "model": "claude-opus-4",
                "content": [
                    {"type": "thinking", "thinking": "Let me think...", "signature": "abc"},
                    {"type": "text", "text": "Response"},
                    {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "ls"}},
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        }
        with open(path, "w") as f:
            f.write(json.dumps(entry) + "\n")

        t = Transcript(path)
        t.load()
        t.save()

        # Reload and verify all fields
        t2 = Transcript(path)
        t2.load()
        e = t2.entries[0]

        assert e.request_id == "req_123"
        assert e.message_id == "msg_456"
        assert e.model == "claude-opus-4"
        assert e.stop_reason == "tool_use"
        assert e.usage["input_tokens"] == 100
        assert "Let me think" in e.thinking
        assert e.text == "Response"
        assert len(e.tool_uses) == 1
        assert e.tool_uses[0].name == "Bash"
