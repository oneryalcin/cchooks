"""Tests for base event model."""
import pytest

from fasthooks.events import BaseEvent


class TestBaseEvent:
    def test_parse_minimal(self):
        """BaseEvent parses with required fields."""
        data = {
            "session_id": "abc123",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
        }
        event = BaseEvent.model_validate(data)
        assert event.session_id == "abc123"
        assert event.cwd == "/workspace"
        assert event.permission_mode == "default"
        assert event.hook_event_name == "PreToolUse"

    def test_parse_with_transcript_path(self):
        """BaseEvent accepts optional transcript_path."""
        data = {
            "session_id": "abc123",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
            "transcript_path": "/root/.claude/projects/session.jsonl",
        }
        event = BaseEvent.model_validate(data)
        assert event.transcript_path == "/root/.claude/projects/session.jsonl"

    def test_parse_missing_required(self):
        """BaseEvent fails without required fields."""
        data = {"session_id": "abc123"}
        with pytest.raises(Exception):  # Pydantic ValidationError
            BaseEvent.model_validate(data)

    def test_extra_fields_ignored(self):
        """BaseEvent ignores extra fields."""
        data = {
            "session_id": "abc123",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "unknown_field": "ignored",
        }
        event = BaseEvent.model_validate(data)
        assert event.session_id == "abc123"
        # Should not raise, extra fields ignored
