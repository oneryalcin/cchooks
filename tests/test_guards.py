"""Tests for guards (when= parameter)."""
import json
from io import StringIO

from fasthooks import HookApp, allow, deny


class TestGuardsPreTool:
    def test_when_lambda_filters(self):
        """@pre_tool with when= only calls handler if condition matches."""
        app = HookApp()
        calls = []

        @app.pre_tool("Write", when=lambda e: e.file_path.endswith(".py"))
        def python_only(event):
            calls.append(event.file_path)
            return allow()

        # Python file - should match
        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/test.py", "content": "x=1"},
            "tool_use_id": "t1",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        # Non-python file - should not match
        stdin2 = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/test.txt", "content": "hello"},
            "tool_use_id": "t2",
        }))
        app.run(stdin=stdin2, stdout=StringIO())

        assert calls == ["/test.py"]  # Only .py file triggered handler

    def test_when_with_bash(self):
        """Guard works with Bash events."""
        app = HookApp()
        calls = []

        @app.pre_tool("Bash", when=lambda e: "sudo" in e.command)
        def check_sudo(event):
            calls.append("sudo_check")
            return deny("No sudo allowed")

        # Without sudo - guard doesn't match, handler not called
        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_use_id": "t1",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        stdout.seek(0)
        assert stdout.read() == ""  # allowed (no output)

        # With sudo - guard matches, handler called
        stdin2 = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "sudo rm -rf /"},
            "tool_use_id": "t2",
        }))
        stdout2 = StringIO()
        app.run(stdin=stdin2, stdout=stdout2)

        assert calls == ["sudo_check"]
        stdout2.seek(0)
        result = json.loads(stdout2.read())
        assert result["decision"] == "deny"


class TestGuardsLifecycle:
    def test_session_start_source_guard(self):
        """Lifecycle events can have guards."""
        app = HookApp()
        calls = []

        @app.on_session_start(when=lambda e: e.source == "startup")
        def startup_only(event):
            calls.append("startup")
            return allow()

        # startup source - matches
        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "SessionStart",
            "source": "startup",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        # resume source - doesn't match
        stdin2 = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "SessionStart",
            "source": "resume",
        }))
        app.run(stdin=stdin2, stdout=StringIO())

        assert calls == ["startup"]

    def test_pre_compact_trigger_guard(self):
        """PreCompact can filter by trigger."""
        app = HookApp()
        calls = []

        @app.on_pre_compact(when=lambda e: e.trigger == "auto")
        def auto_compact_only(event):
            calls.append("auto")
            return allow()

        # auto trigger - matches
        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreCompact",
            "trigger": "auto",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        # manual trigger - doesn't match
        stdin2 = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreCompact",
            "trigger": "manual",
        }))
        app.run(stdin=stdin2, stdout=StringIO())

        assert calls == ["auto"]


class TestGuardsCombined:
    def test_guard_with_di(self):
        """Guards work together with DI."""
        app = HookApp()
        calls = []

        from fasthooks.depends import Transcript

        @app.on_stop(when=lambda e: e.stop_hook_active)
        def handle_active_stop(event, transcript: Transcript):
            calls.append(f"active_stop:{transcript is not None}")
            return allow()

        # stop_hook_active=True - matches
        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
            "stop_hook_active": True,
        }))
        app.run(stdin=stdin, stdout=StringIO())

        # stop_hook_active=False - doesn't match
        stdin2 = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
            "stop_hook_active": False,
        }))
        app.run(stdin=stdin2, stdout=StringIO())

        assert calls == ["active_stop:True"]
