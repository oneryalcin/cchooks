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
        """Unknown types should fallback to UnknownBlock and warn."""
        import warnings

        from fasthooks.transcript import UnknownBlock

        data = {"type": "future_block", "text": "some content", "custom": "data"}

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            block = parse_content_block(data, validate="warn")

            # Should warn about unknown type
            assert len(w) == 1
            assert "Unknown content block type" in str(w[0].message)
            assert "future_block" in str(w[0].message)

        # Should be UnknownBlock preserving original type
        assert isinstance(block, UnknownBlock)
        assert block.type == "future_block"
        assert block.text == "some content"
        assert block.model_extra.get("custom") == "data"

    def test_unknown_block_type_strict(self):
        """Unknown types should raise in strict mode."""
        import pytest

        data = {"type": "future_block"}
        with pytest.raises(ValueError, match="Unknown content block type"):
            parse_content_block(data, validate="strict")

    def test_unknown_block_type_none(self):
        """Unknown types should be silent in none mode."""
        import warnings

        from fasthooks.transcript import UnknownBlock

        data = {"type": "future_block"}

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            block = parse_content_block(data, validate="none")

            # Should NOT warn
            assert len(w) == 0

        assert isinstance(block, UnknownBlock)

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


class TestStatsWithArchived:
    """Test that stats include all entries (archived + current)."""

    @pytest.fixture
    def transcript_with_archived_turns(self, tmp_path):
        """Create transcript with turns in both archived and current."""
        import json

        path = tmp_path / "archived_turns.jsonl"
        entries = [
            # Archived entries with a turn
            {
                "type": "assistant",
                "uuid": "old_a1",
                "parentUuid": None,
                "requestId": "old_req_1",
                "timestamp": "2024-01-01T10:00:00Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
            },
            # Compact boundary
            {
                "type": "system",
                "subtype": "compact_boundary",
                "uuid": "compact1",
                "parentUuid": None,
                "logicalParentUuid": "old_a1",
            },
            # Current entries with a turn
            {
                "type": "assistant",
                "uuid": "new_a1",
                "parentUuid": "compact1",
                "requestId": "new_req_1",
                "timestamp": "2024-01-01T10:05:00Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "t2", "name": "Read", "input": {}}],
                    "usage": {"input_tokens": 200, "output_tokens": 100},
                },
            },
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        return Transcript(path)

    def test_stats_turn_count_includes_archived(self, transcript_with_archived_turns):
        """Stats should count turns from both archived and current."""
        t = transcript_with_archived_turns
        stats = t.stats

        # Should count both old_req_1 and new_req_1
        assert stats.turn_count == 2

    def test_stats_tokens_include_archived(self, transcript_with_archived_turns):
        """Stats should sum tokens from both archived and current."""
        t = transcript_with_archived_turns
        stats = t.stats

        assert stats.input_tokens == 300  # 100 + 200
        assert stats.output_tokens == 150  # 50 + 100

    def test_stats_tool_calls_include_archived(self, transcript_with_archived_turns):
        """Stats should count tool calls from both archived and current."""
        t = transcript_with_archived_turns
        stats = t.stats

        assert stats.tool_calls == {"Bash": 1, "Read": 1}


class TestTurnsFiltering:
    """Test that turns property correctly filters by include_archived."""

    @pytest.fixture
    def transcript_with_archived_turns(self, tmp_path):
        """Create transcript with turns in both archived and current."""
        import json

        path = tmp_path / "turns.jsonl"
        entries = [
            # Archived turn
            {
                "type": "assistant",
                "uuid": "old_a1",
                "requestId": "old_req",
                "message": {"role": "assistant", "content": []},
            },
            # Compact boundary
            {
                "type": "system",
                "subtype": "compact_boundary",
                "uuid": "compact1",
                "parentUuid": None,
            },
            # Current turn
            {
                "type": "assistant",
                "uuid": "new_a1",
                "parentUuid": "compact1",
                "requestId": "new_req",
                "message": {"role": "assistant", "content": []},
            },
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        return Transcript(path)

    def test_turns_excludes_archived_by_default(self, transcript_with_archived_turns):
        """turns property should only show current turns by default."""
        t = transcript_with_archived_turns
        turns = t.turns

        assert len(turns) == 1
        assert turns[0].request_id == "new_req"

    def test_turns_includes_archived_when_set(self, transcript_with_archived_turns):
        """turns property should include archived when include_archived=True."""
        t = transcript_with_archived_turns
        t.include_archived = True
        turns = t.turns

        assert len(turns) == 2
        request_ids = {turn.request_id for turn in turns}
        assert request_ids == {"old_req", "new_req"}

    def test_get_turns_with_param(self, transcript_with_archived_turns):
        """get_turns should accept include_archived param."""
        t = transcript_with_archived_turns

        assert len(t.get_turns(include_archived=False)) == 1
        assert len(t.get_turns(include_archived=True)) == 2


class TestTranscriptQuery:
    """Test the fluent query API."""

    @pytest.fixture
    def transcript_for_query(self, tmp_path):
        """Create transcript with varied entries for query testing."""
        import json
        from datetime import datetime, timezone

        path = tmp_path / "query_test.jsonl"
        entries = [
            {
                "type": "user",
                "uuid": "u1",
                "timestamp": "2024-01-01T10:00:00Z",
                "message": {"role": "user", "content": "Hello"},
            },
            {
                "type": "assistant",
                "uuid": "a1",
                "parentUuid": "u1",
                "requestId": "r1",
                "timestamp": "2024-01-01T10:01:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Hi there!"},
                        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
                    ],
                },
            },
            {
                "type": "user",
                "uuid": "u2",
                "parentUuid": "a1",
                "timestamp": "2024-01-01T10:02:00Z",
                "message": {"role": "user", "content": "Run a command"},
            },
            {
                "type": "assistant",
                "uuid": "a2",
                "parentUuid": "u2",
                "requestId": "r2",
                "timestamp": "2024-01-01T10:03:00Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Error occurred"}],
                },
            },
            {
                "type": "system",
                "uuid": "s1",
                "parentUuid": "a2",
                "timestamp": "2024-01-01T10:04:00Z",
                "subtype": "info",
            },
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        return Transcript(path)

    def test_query_count(self, transcript_for_query):
        """query().count() returns total entries."""
        t = transcript_for_query
        assert t.query().count() == 5

    def test_query_users(self, transcript_for_query):
        """query().users() filters to user messages."""
        t = transcript_for_query
        assert t.query().users().count() == 2

    def test_query_assistants(self, transcript_for_query):
        """query().assistants() filters to assistant messages."""
        t = transcript_for_query
        assert t.query().assistants().count() == 2

    def test_query_system(self, transcript_for_query):
        """query().system() filters to system entries."""
        t = transcript_for_query
        assert t.query().system().count() == 1

    def test_query_with_tools(self, transcript_for_query):
        """query().with_tools() filters to entries with tool use."""
        t = transcript_for_query
        assert t.query().with_tools().count() == 1

    def test_query_filter_exact(self, transcript_for_query):
        """query().filter(field=value) does exact match."""
        t = transcript_for_query
        assert t.query().filter(uuid="u1").count() == 1

    def test_query_filter_contains(self, transcript_for_query):
        """query().filter(field__contains=value) does substring match."""
        t = transcript_for_query
        assert t.query().filter(text__contains="Error").count() == 1

    def test_query_filter_in(self, transcript_for_query):
        """query().filter(field__in=list) checks membership."""
        t = transcript_for_query
        assert t.query().filter(type__in=["user", "system"]).count() == 3

    def test_query_exclude(self, transcript_for_query):
        """query().exclude() inverts filter."""
        t = transcript_for_query
        assert t.query().exclude(type="system").count() == 4

    def test_query_where_lambda(self, transcript_for_query):
        """query().where(lambda) filters by predicate."""
        t = transcript_for_query
        result = t.query().where(lambda e: e.uuid.startswith("a")).count()
        assert result == 2

    def test_query_chaining(self, transcript_for_query):
        """Multiple filters can be chained."""
        t = transcript_for_query
        result = t.query().assistants().with_tools().count()
        assert result == 1

    def test_query_first(self, transcript_for_query):
        """query().first() returns first match or None."""
        t = transcript_for_query
        first = t.query().users().first()
        assert first is not None
        assert first.uuid == "u1"

        no_match = t.query().filter(uuid="nonexistent").first()
        assert no_match is None

    def test_query_last(self, transcript_for_query):
        """query().last() returns last match or None."""
        t = transcript_for_query
        last = t.query().users().last()
        assert last is not None
        assert last.uuid == "u2"

    def test_query_one(self, transcript_for_query):
        """query().one() returns exactly one or raises."""
        t = transcript_for_query

        one = t.query().filter(uuid="u1").one()
        assert one.uuid == "u1"

        with pytest.raises(ValueError, match="no results"):
            t.query().filter(uuid="nonexistent").one()

        with pytest.raises(ValueError, match="2 results"):
            t.query().users().one()

    def test_query_exists(self, transcript_for_query):
        """query().exists() checks for any matches."""
        t = transcript_for_query
        assert t.query().users().exists() is True
        assert t.query().filter(uuid="nonexistent").exists() is False

    def test_query_order_by(self, transcript_for_query):
        """query().order_by() sorts results."""
        t = transcript_for_query

        # Ascending
        asc = t.query().order_by("uuid").all()
        assert asc[0].uuid == "a1"

        # Descending
        desc = t.query().order_by("-uuid").all()
        assert desc[0].uuid == "u2"

    def test_query_limit_offset(self, transcript_for_query):
        """query().limit() and offset() paginate results."""
        t = transcript_for_query

        limited = t.query().limit(2).all()
        assert len(limited) == 2

        offset = t.query().offset(2).limit(2).all()
        assert len(offset) == 2
        assert offset[0].uuid == "u2"

    def test_query_iteration(self, transcript_for_query):
        """Query can be iterated directly."""
        t = transcript_for_query
        uuids = [e.uuid for e in t.query().users()]
        assert uuids == ["u1", "u2"]

    def test_query_len(self, transcript_for_query):
        """len(query) returns count."""
        t = transcript_for_query
        assert len(t.query().users()) == 2

    def test_query_bool(self, transcript_for_query):
        """bool(query) checks exists."""
        t = transcript_for_query
        assert bool(t.query().users()) is True
        assert bool(t.query().filter(uuid="x")) is False

    def test_query_repr(self, transcript_for_query):
        """Query has descriptive repr."""
        t = transcript_for_query
        q = t.query().assistants().with_tools().limit(5)
        repr_str = repr(q)
        assert "assistants()" in repr_str
        assert "with_tools()" in repr_str
        assert "limit(5)" in repr_str

    def test_query_since_until(self, transcript_for_query):
        """query().since() and until() filter by time."""
        t = transcript_for_query

        since = t.query().since("2024-01-01T10:02:00Z").count()
        assert since == 3  # u2, a2, s1

        until = t.query().until("2024-01-01T10:01:00Z").count()
        assert until == 2  # u1, a1

    def test_query_invalid_lookup_raises(self, transcript_for_query):
        """Invalid lookup operator raises ValueError."""
        t = transcript_for_query
        with pytest.raises(ValueError, match="Unknown lookup"):
            t.query().filter(uuid__invalid="x").all()

    def test_query_order_by_multiple_fields(self, transcript_for_query):
        """order_by with multiple fields should sort correctly (closure fix)."""
        t = transcript_for_query
        # Sort by type ascending, then uuid descending within each type
        result = t.query().order_by("type", "-uuid").all()

        # Group by type and verify order within groups
        assistants = [e for e in result if e.type == "assistant"]
        users = [e for e in result if e.type == "user"]

        # Assistants should come before users (alphabetically)
        assert result.index(assistants[0]) < result.index(users[0])

        # Within assistants, should be descending by uuid (a2 before a1)
        assert assistants[0].uuid == "a2"
        assert assistants[1].uuid == "a1"

        # Within users, should be descending by uuid (u2 before u1)
        assert users[0].uuid == "u2"
        assert users[1].uuid == "u1"

    def test_query_include_meta_filtering(self, tmp_path):
        """query() should respect include_meta setting."""
        import json

        path = tmp_path / "meta_test.jsonl"
        entries = [
            {
                "type": "user",
                "uuid": "u1",
                "message": {"role": "user", "content": "Normal message"},
            },
            {
                "type": "user",
                "uuid": "u2",
                "isMeta": True,
                "message": {"role": "user", "content": "Meta message"},
            },
            {
                "type": "user",
                "uuid": "u3",
                "message": {"role": "user", "content": "Another normal"},
            },
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)

        # Default: meta entries excluded
        assert t.query().users().count() == 2

        # With include_meta=True: all entries included
        assert t.query(include_meta=True).users().count() == 3

        # Setting on transcript instance
        t.include_meta = True
        assert t.query().users().count() == 3


class TestFactories:
    """Test factory methods for creating entries."""

    def test_user_message_create_basic(self):
        """UserMessage.create() should generate uuid, timestamp, and mark synthetic."""
        msg = UserMessage.create("Hello world")
        assert msg.text == "Hello world"
        assert msg.uuid  # Generated
        assert msg.timestamp is not None
        assert msg.is_synthetic is True
        assert msg.type == "user"

    def test_user_message_create_with_parent(self):
        """UserMessage.create() should set parent_uuid from parent."""
        parent = UserMessage.create("Parent message")
        child = UserMessage.create("Child message", parent=parent)
        assert child.parent_uuid == parent.uuid

    def test_user_message_create_with_context(self):
        """UserMessage.create() should copy metadata from context."""
        ctx = UserMessage.create("Context", cwd="/test", session_id="sess-123")
        msg = UserMessage.create("New message", context=ctx)
        assert msg.cwd == "/test"
        assert msg.session_id == "sess-123"

    def test_user_message_create_overrides(self):
        """UserMessage.create() should allow field overrides."""
        ctx = UserMessage.create("Context", cwd="/original")
        msg = UserMessage.create("New", context=ctx, cwd="/override")
        assert msg.cwd == "/override"

    def test_user_message_create_serialization(self):
        """Created UserMessage should serialize correctly."""
        msg = UserMessage.create("Test content")
        data = msg.to_dict()
        assert data["message"]["role"] == "user"
        assert data["message"]["content"] == "Test content"
        assert data["isSynthetic"] is True

    def test_assistant_message_create_basic(self):
        """AssistantMessage.create() should generate all required fields."""
        msg = AssistantMessage.create("Hello from Claude")
        assert msg.text == "Hello from Claude"
        assert msg.uuid  # Generated
        assert msg.timestamp is not None
        assert msg.is_synthetic is True
        assert msg.model == "synthetic"
        assert msg.stop_reason == "end_turn"
        assert msg.request_id.startswith("req_")
        assert msg.message_id.startswith("msg_")

    def test_assistant_message_create_with_content_blocks(self):
        """AssistantMessage.create() should accept ContentBlock list."""
        blocks = [
            TextBlock(text="I'll run a command"),
            ToolUseBlock(id="toolu_123", name="Bash", input={"command": "ls"}),
        ]
        msg = AssistantMessage.create(blocks)
        assert len(msg.content) == 2
        assert msg.text == "I'll run a command"
        assert msg.has_tool_use is True
        assert msg.tool_uses[0].name == "Bash"

    def test_assistant_message_create_with_parent(self):
        """AssistantMessage.create() should set parent_uuid from parent."""
        parent = UserMessage.create("Question")
        response = AssistantMessage.create("Answer", parent=parent)
        assert response.parent_uuid == parent.uuid

    def test_assistant_message_create_custom_model(self):
        """AssistantMessage.create() should allow custom model name."""
        msg = AssistantMessage.create("Test", model="claude-3-opus")
        assert msg.model == "claude-3-opus"

    def test_assistant_message_create_serialization(self):
        """Created AssistantMessage should serialize correctly."""
        msg = AssistantMessage.create("Test response")
        data = msg.to_dict()
        assert data["message"]["role"] == "assistant"
        assert data["message"]["content"][0]["type"] == "text"
        assert data["message"]["content"][0]["text"] == "Test response"
        assert data["message"]["model"] == "synthetic"
        assert data["isSynthetic"] is True


class TestInjectToolResult:
    """Test inject_tool_result factory function."""

    def test_inject_tool_result_basic(self, tmp_path):
        """inject_tool_result should create matching tool use + result pair."""
        import json

        from fasthooks.transcript import inject_tool_result

        path = tmp_path / "transcript.jsonl"
        path.write_text(
            json.dumps({
                "type": "user",
                "uuid": "u1",
                "sessionId": "sess-1",
                "cwd": "/test",
                "message": {"role": "user", "content": "Run ls"},
            })
            + "\n"
        )

        t = Transcript(path)
        assert len(t.entries) == 1

        assistant, user = inject_tool_result(
            t, "Bash", {"command": "ls -la"}, "file1.txt\nfile2.txt"
        )

        assert len(t.entries) == 3

        # Check assistant message
        assert assistant.type == "assistant"
        assert len(assistant.tool_uses) == 1
        assert assistant.tool_uses[0].name == "Bash"
        assert assistant.tool_uses[0].input == {"command": "ls -la"}

        # Check user message (tool result)
        assert user.type == "user"
        assert user.is_tool_result is True
        assert len(user.tool_results) == 1
        assert user.tool_results[0].content == "file1.txt\nfile2.txt"
        assert user.tool_results[0].is_error is False

        # Check IDs match
        assert user.tool_results[0].tool_use_id == assistant.tool_uses[0].id

        # Check chain
        assert assistant.parent_uuid == "u1"
        assert user.parent_uuid == assistant.uuid

    def test_inject_tool_result_with_error(self, tmp_path):
        """inject_tool_result should support is_error flag."""
        import json

        from fasthooks.transcript import inject_tool_result

        path = tmp_path / "transcript.jsonl"
        path.write_text(
            json.dumps({
                "type": "user",
                "uuid": "u1",
                "message": {"role": "user", "content": "Run bad command"},
            })
            + "\n"
        )

        t = Transcript(path)
        assistant, user = inject_tool_result(
            t, "Bash", {"command": "bad-cmd"}, "command not found", is_error=True
        )

        assert user.tool_results[0].is_error is True

    def test_inject_tool_result_at_start(self, tmp_path):
        """inject_tool_result should support position='start'."""
        import json

        from fasthooks.transcript import inject_tool_result

        path = tmp_path / "transcript.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "msg1"}},
            {"type": "user", "uuid": "u2", "parentUuid": "u1", "message": {"role": "user", "content": "msg2"}},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        assistant, user = inject_tool_result(
            t, "Read", {"file_path": "/config.json"}, "{}", position="start"
        )

        # Should be at the beginning
        assert t.entries[0] == assistant
        assert t.entries[1] == user
        assert t.entries[2].uuid == "u1"

    def test_inject_tool_result_synthetic_marker(self, tmp_path):
        """Injected entries should be marked as synthetic."""
        import json

        from fasthooks.transcript import inject_tool_result

        path = tmp_path / "transcript.jsonl"
        path.write_text(
            json.dumps({
                "type": "user",
                "uuid": "u1",
                "message": {"role": "user", "content": "test"},
            })
            + "\n"
        )

        t = Transcript(path)
        assistant, user = inject_tool_result(t, "Bash", {"command": "echo"}, "output")

        assert assistant.is_synthetic is True
        assert user.is_synthetic is True

    def test_inject_tool_result_copies_metadata(self, tmp_path):
        """inject_tool_result should copy metadata from context entry."""
        import json

        from fasthooks.transcript import inject_tool_result

        path = tmp_path / "transcript.jsonl"
        path.write_text(
            json.dumps({
                "type": "user",
                "uuid": "u1",
                "sessionId": "session-xyz",
                "cwd": "/workspace",
                "version": "2.0.76",
                "gitBranch": "main",
                "slug": "test-slug",
                "message": {"role": "user", "content": "test"},
            })
            + "\n"
        )

        t = Transcript(path)
        assistant, user = inject_tool_result(t, "Bash", {"command": "ls"}, "out")

        assert assistant.session_id == "session-xyz"
        assert assistant.cwd == "/workspace"
        assert assistant.version == "2.0.76"
        assert assistant.git_branch == "main"
        assert assistant.slug == "test-slug"


class TestExports:
    """Test export functionality."""

    def test_to_markdown_basic(self, tmp_path):
        """to_markdown() should produce markdown string."""
        import json

        path = tmp_path / "transcript.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "Hello"}},
            {
                "type": "assistant",
                "uuid": "a1",
                "parentUuid": "u1",
                "requestId": "req1",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hi there!"}],
                },
            },
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        md = t.to_markdown()

        assert "# Transcript" in md
        assert "## User" in md
        assert "Hello" in md
        assert "## Assistant" in md
        assert "Hi there!" in md

    def test_to_markdown_with_tool_use(self, tmp_path):
        """to_markdown() should format tool uses."""
        import json

        path = tmp_path / "transcript.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "Run ls"}},
            {
                "type": "assistant",
                "uuid": "a1",
                "requestId": "req1",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "ls"}},
                    ],
                },
            },
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        md = t.to_markdown()

        assert "Tool: Bash" in md
        assert '"command"' in md

    def test_to_markdown_truncation(self, tmp_path):
        """to_markdown() should truncate long content."""
        import json

        path = tmp_path / "transcript.jsonl"
        long_text = "x" * 1000
        entries = [
            {"type": "user", "uuid": "u1", "message": {"role": "user", "content": long_text}},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        md = t.to_markdown(max_content_length=100)

        assert "..." in md
        assert len(md) < 500  # Much shorter than 1000

    def test_to_html_basic(self, tmp_path):
        """to_html() should produce valid HTML."""
        import json

        path = tmp_path / "transcript.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "Hello"}},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        html = t.to_html(title="Test Session")

        assert "<!DOCTYPE html>" in html
        assert "<title>Test Session</title>" in html
        assert "Hello" in html

    def test_to_json_basic(self, tmp_path):
        """to_json() should produce valid JSON array."""
        import json

        path = tmp_path / "transcript.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "Hello"}},
            {"type": "user", "uuid": "u2", "message": {"role": "user", "content": "World"}},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        json_str = t.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["uuid"] == "u1"

    def test_to_jsonl_basic(self, tmp_path):
        """to_jsonl() should produce JSONL string."""
        import json

        path = tmp_path / "transcript.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "Hello"}},
            {"type": "user", "uuid": "u2", "message": {"role": "user", "content": "World"}},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        jsonl = t.to_jsonl()

        lines = jsonl.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["uuid"] == "u1"
        assert json.loads(lines[1])["uuid"] == "u2"

    def test_to_file_markdown(self, tmp_path):
        """to_file() should write markdown to disk."""
        import json

        path = tmp_path / "transcript.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "Hello"}},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)
        out_path = tmp_path / "output.md"
        t.to_file(out_path)

        assert out_path.exists()
        content = out_path.read_text()
        assert "# Transcript" in content
        assert "Hello" in content

    def test_to_file_formats(self, tmp_path):
        """to_file() should support all formats."""
        import json

        path = tmp_path / "transcript.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "Hello"}},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)

        # All formats should work
        for fmt, ext in [("md", ".md"), ("html", ".html"), ("json", ".json"), ("jsonl", ".jsonl")]:
            out_path = tmp_path / f"output{ext}"
            t.to_file(out_path, format=fmt)
            assert out_path.exists()
            assert out_path.stat().st_size > 0

    def test_to_file_invalid_format(self, tmp_path):
        """to_file() should raise on invalid format."""
        import json

        path = tmp_path / "transcript.jsonl"
        entries = [
            {"type": "user", "uuid": "u1", "message": {"role": "user", "content": "Hello"}},
        ]
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        t = Transcript(path)

        with pytest.raises(ValueError, match="Unknown format"):
            t.to_file(tmp_path / "out.txt", format="txt")

class TestCriticalEdgeCases:
    """Critical tests for data integrity and complex queries."""

    def test_batch_rollback_on_error(self, tmp_path):
        """Test that transcript state is rolled back if an exception occurs in batch."""
        f = tmp_path / "transcript.jsonl"
        f.touch()
        
        transcript = Transcript(f)
        
        # Setup initial state
        msg1 = UserMessage.create("Message 1")
        msg2 = AssistantMessage.create("Message 2")
        transcript.append(msg1)
        transcript.append(msg2)
        transcript.save()
        
        initial_count = len(transcript.entries)
        initial_ids = [e.uuid for e in transcript.entries]
        
        # Attempt batch with error
        with pytest.raises(ValueError, match="Boom"):
            with transcript.batch():
                # Make some destructive changes
                transcript.remove(msg1)
                transcript.append(UserMessage.create("New Message"))
                
                # Verify changes happened in memory
                assert len(transcript.entries) == initial_count  # removed 1, added 1
                assert transcript.entries[0].uuid != initial_ids[0] # msg1 removed
                
                # Trigger error
                raise ValueError("Boom")
                
        # Verify rollback
        assert len(transcript.entries) == initial_count
        assert [e.uuid for e in transcript.entries] == initial_ids
        assert msg1 in transcript.entries
        assert msg2 in transcript.entries

    def test_batch_commit_on_success(self, tmp_path):
        """Test that batch commits and saves on success."""
        f = tmp_path / "transcript.jsonl"
        f.touch()
        
        transcript = Transcript(f)
        msg1 = UserMessage.create("Message 1")
        transcript.append(msg1)
        transcript.save()
        
        with transcript.batch():
            transcript.append(AssistantMessage.create("Message 2"))
            
        # Verify in memory
        assert len(transcript.entries) == 2
        
        # Verify on disk (reload)
        t2 = Transcript(f)
        t2.load()
        assert len(t2.entries) == 2

    def test_query_operators(self):
        """Test gt, gte, lt, lte, isnull operators."""
        from datetime import datetime, timedelta, timezone
        from fasthooks.transcript.query import TranscriptQuery
        
        entries = []
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        # Create entries with different timestamps/values
        for i in range(5):
            msg = UserMessage.create(f"msg {i}")
            msg.timestamp = base_time + timedelta(hours=i)
            entries.append(msg)
            
        # Add one with no timestamp
        no_ts_msg = UserMessage.create("no ts")
        no_ts_msg.timestamp = None
        entries.append(no_ts_msg)
        
        q = TranscriptQuery(entries)
        
        # gt
        res = q.filter(timestamp__gt=base_time).all()
        assert len(res) == 4 # 1, 2, 3, 4
        
        # gte
        res = q.filter(timestamp__gte=base_time).all()
        assert len(res) == 5 # 0, 1, 2, 3, 4
        
        # lt
        res = q.filter(timestamp__lt=base_time + timedelta(hours=2)).all()
        assert len(res) == 2 # 0, 1
        
        # lte
        res = q.filter(timestamp__lte=base_time + timedelta(hours=2)).all()
        assert len(res) == 3 # 0, 1, 2
        
        # isnull=True
        res = q.filter(timestamp__isnull=True).all()
        assert len(res) == 1
        assert res[0].text == "no ts"
        
        # isnull=False
        res = q.filter(timestamp__isnull=False).all()
        assert len(res) == 5

    def test_export_html_basic(self, tmp_path):
        """Basic test for HTML export."""
        f = tmp_path / "transcript.jsonl"
        transcript = Transcript(f, auto_load=False)
        
        transcript.append(UserMessage.create("Hello"))
        transcript.append(AssistantMessage.create("Hi there"))
        
        html = transcript.to_html(title="My Test Session")
        
        assert "<!DOCTYPE html>" in html
        assert "My Test Session" in html
        assert "Hello" in html
        assert "Hi there" in html
