"""Tests for lifecycle event models."""
from fasthooks.events import (
    Notification,
    PreCompact,
    SessionEnd,
    SessionStart,
    Stop,
    SubagentStop,
    UserPromptSubmit,
)


class TestStopEvent:
    def test_parse_stop_event(self):
        """Stop event parses correctly."""
        data = {
            "session_id": "abc123",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "transcript_path": "/root/.claude/session.jsonl",
        }
        event = Stop.model_validate(data)
        assert event.hook_event_name == "Stop"
        assert event.stop_hook_active is False
        assert event.transcript_path == "/root/.claude/session.jsonl"

    def test_stop_hook_active_default(self):
        """stop_hook_active defaults to False."""
        data = {
            "session_id": "abc",
            "cwd": "/",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }
        event = Stop.model_validate(data)
        assert event.stop_hook_active is False


class TestSubagentStopEvent:
    def test_parse_subagent_stop(self):
        """SubagentStop parses with agent_id."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "SubagentStop",
            "agent_id": "agent-123",
            "stop_hook_active": True,
        }
        event = SubagentStop.model_validate(data)
        assert event.agent_id == "agent-123"
        assert event.stop_hook_active is True


class TestSessionStartEvent:
    def test_parse_session_start(self):
        """SessionStart parses with source."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "SessionStart",
            "source": "startup",
        }
        event = SessionStart.model_validate(data)
        assert event.source == "startup"

    def test_session_start_compact_source(self):
        """SessionStart handles compact source."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "SessionStart",
            "source": "compact",
            "transcript_path": "/root/.claude/session.jsonl",
        }
        event = SessionStart.model_validate(data)
        assert event.source == "compact"


class TestSessionEndEvent:
    def test_parse_session_end(self):
        """SessionEnd parses with reason."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "SessionEnd",
            "reason": "prompt_input_exit",
        }
        event = SessionEnd.model_validate(data)
        assert event.reason == "prompt_input_exit"


class TestPreCompactEvent:
    def test_parse_pre_compact(self):
        """PreCompact parses with trigger and instructions."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreCompact",
            "trigger": "manual",
            "custom_instructions": "Keep it short",
            "transcript_path": "/root/.claude/session.jsonl",
        }
        event = PreCompact.model_validate(data)
        assert event.trigger == "manual"
        assert event.custom_instructions == "Keep it short"

    def test_pre_compact_auto(self):
        """PreCompact handles auto trigger."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreCompact",
            "trigger": "auto",
        }
        event = PreCompact.model_validate(data)
        assert event.trigger == "auto"
        assert event.custom_instructions is None


class TestUserPromptSubmitEvent:
    def test_parse_user_prompt(self):
        """UserPromptSubmit parses with prompt."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "What is the weather?",
        }
        event = UserPromptSubmit.model_validate(data)
        assert event.prompt == "What is the weather?"


class TestNotificationEvent:
    def test_parse_notification(self):
        """Notification parses with message and type."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Notification",
            "message": "Claude needs permission",
            "notification_type": "permission_prompt",
        }
        event = Notification.model_validate(data)
        assert event.message == "Claude needs permission"
        assert event.notification_type == "permission_prompt"
