"""Tests for dependency injection."""
import json
from io import StringIO

from fasthooks import HookApp, allow
from fasthooks.depends import State, Transcript


class TestDITranscript:
    def test_transcript_injected(self, tmp_path):
        """Transcript is auto-injected when type-hinted."""
        # Create sample transcript with proper structure
        transcript_file = tmp_path / "transcript.jsonl"
        entries = [
            {
                "type": "user",
                "uuid": "u1",
                "timestamp": "2024-01-01T10:00:00Z",
                "message": {"role": "user", "content": "test"},
            },
            {
                "type": "assistant",
                "uuid": "a1",
                "parentUuid": "u1",
                "requestId": "r1",
                "timestamp": "2024-01-01T10:00:05Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}},
                    ],
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
            },
        ]
        transcript_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        app = HookApp()
        captured_stats = []

        @app.on_stop()
        def handler(event, transcript: Transcript):
            captured_stats.append(transcript.stats.tool_calls)
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
            "transcript_path": str(transcript_file),
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)

        assert captured_stats == [{"Bash": 1}]

    def test_transcript_none_when_no_path(self):
        """Transcript works even without transcript_path."""
        app = HookApp()
        captured = []

        @app.on_stop()
        def handler(event, transcript: Transcript):
            # New API uses message_count (int) not message_counts (dict)
            captured.append(transcript.stats.message_count)
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)

        assert captured == [0]  # Empty stats, no crash


class TestDIState:
    def test_state_injected(self, tmp_path):
        """State is auto-injected when type-hinted."""
        app = HookApp(state_dir=str(tmp_path))
        captured = []

        @app.on_stop()
        def handler(event, state: State):
            state["count"] = state.get("count", 0) + 1
            state.save()
            captured.append(state["count"])
            return allow()

        # First call
        stdin = StringIO(json.dumps({
            "session_id": "session-1",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        # Second call (same session)
        stdin2 = StringIO(json.dumps({
            "session_id": "session-1",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin2, stdout=StringIO())

        assert captured == [1, 2]

    def test_state_session_isolation(self, tmp_path):
        """Different sessions have isolated state."""
        app = HookApp(state_dir=str(tmp_path))
        captured = {}

        @app.on_stop()
        def handler(event, state: State):
            state["count"] = state.get("count", 0) + 1
            state.save()
            captured[event.session_id] = state["count"]
            return allow()

        # Session A
        stdin_a = StringIO(json.dumps({
            "session_id": "session-a",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin_a, stdout=StringIO())

        # Session B
        stdin_b = StringIO(json.dumps({
            "session_id": "session-b",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin_b, stdout=StringIO())

        # Session A again
        stdin_a2 = StringIO(json.dumps({
            "session_id": "session-a",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin_a2, stdout=StringIO())

        assert captured == {"session-a": 2, "session-b": 1}


class TestDICombined:
    def test_multiple_deps_injected(self, tmp_path):
        """Multiple dependencies can be injected."""
        transcript_file = tmp_path / "transcript.jsonl"
        transcript_file.write_text('{"type": "user", "uuid": "u1", "message": {"role": "user", "content": "hi"}}\n')

        app = HookApp(state_dir=str(tmp_path))
        captured = []

        @app.on_stop()
        def handler(event, transcript: Transcript, state: State):
            captured.append({
                "has_transcript": transcript is not None,
                "has_state": state is not None,
            })
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
            "transcript_path": str(transcript_file),
        }))
        app.run(stdin=stdin, stdout=StringIO())

        assert captured == [{"has_transcript": True, "has_state": True}]


class TestDIEventOnly:
    def test_no_injection_when_not_requested(self):
        """Handlers without DI hints still work."""
        app = HookApp()
        calls = []

        @app.on_stop()
        def simple_handler(event):
            calls.append("called")
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        assert calls == ["called"]


class TestDIPreTool:
    def test_di_works_with_pre_tool(self, tmp_path):
        """DI works with pre_tool decorators too."""
        app = HookApp(state_dir=str(tmp_path))
        captured = []

        @app.pre_tool("Bash")
        def handler(event, state: State):
            state["bash_count"] = state.get("bash_count", 0) + 1
            state.save()
            captured.append(state["bash_count"])
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_use_id": "t1",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        assert captured == [1]


class TestDITranscriptCaching:
    def test_transcript_cached_across_handlers(self, tmp_path):
        """Same Transcript instance should be shared across handlers."""
        transcript_file = tmp_path / "transcript.jsonl"
        transcript_file.write_text(
            '{"type": "user", "uuid": "u1", "message": {"role": "user", "content": "hi"}}\n'
        )

        app = HookApp()
        transcript_ids = []

        @app.on_stop()
        def handler1(event, transcript: Transcript):
            transcript_ids.append(id(transcript))

        @app.on_stop()
        def handler2(event, transcript: Transcript):
            transcript_ids.append(id(transcript))

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
            "transcript_path": str(transcript_file),
        }))
        app.run(stdin=stdin, stdout=StringIO())

        # Both handlers should get the same Transcript instance
        assert len(transcript_ids) == 2
        assert transcript_ids[0] == transcript_ids[1]
