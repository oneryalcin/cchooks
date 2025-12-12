"""Tests for HookApp."""
import json
from io import StringIO

from fasthooks import HookApp, allow, deny
from fasthooks.testing import MockEvent, TestClient


class TestHookAppBasic:
    def test_create_app(self):
        """HookApp can be instantiated."""
        app = HookApp()
        assert app is not None

    def test_run_no_handlers(self):
        """App with no handlers returns empty response."""
        app = HookApp()
        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_use_id": "t1",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        # No handlers = allow by default (empty output)
        stdout.seek(0)
        assert stdout.read() == ""


class TestHookAppHandlers:
    def test_pre_tool_handler(self):
        """@pre_tool decorator registers handler."""
        app = HookApp()

        @app.pre_tool("Bash")
        def check_bash(event):
            if "rm" in event.tool_input.get("command", ""):
                return deny("No rm allowed")
            return allow()

        # Test with safe command
        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_use_id": "t1",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        stdout.seek(0)
        assert stdout.read() == ""  # allowed

        # Test with dangerous command
        stdin2 = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "tool_use_id": "t2",
        }))
        stdout2 = StringIO()
        app.run(stdin=stdin2, stdout=stdout2)
        stdout2.seek(0)
        result = json.loads(stdout2.read())
        assert result["decision"] == "deny"
        assert "rm" in result["reason"]

    def test_handler_not_called_for_other_tools(self):
        """Handler only called for matching tool."""
        app = HookApp()
        calls = []

        @app.pre_tool("Bash")
        def bash_only(event):
            calls.append("bash")
            return allow()

        # Send Write event
        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/test.txt"},
            "tool_use_id": "t1",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        assert calls == []  # Handler not called

    def test_multiple_tools_matcher(self):
        """@pre_tool can match multiple tools."""
        app = HookApp()
        calls = []

        @app.pre_tool("Write", "Edit")
        def file_ops(event):
            calls.append(event.tool_name)
            return allow()

        for tool in ["Write", "Edit", "Bash"]:
            stdin = StringIO(json.dumps({
                "session_id": "test",
                "cwd": "/workspace",
                "permission_mode": "default",
                "hook_event_name": "PreToolUse",
                "tool_name": tool,
                "tool_input": {},
                "tool_use_id": "t1",
            }))
            stdout = StringIO()
            app.run(stdin=stdin, stdout=stdout)

        assert calls == ["Write", "Edit"]  # Bash not included


class TestCatchAllHandlers:
    """Tests for catch-all handler support."""

    def test_pre_tool_catch_all(self):
        """Catch-all handler receives all tool events."""
        from fasthooks import HookApp, allow

        app = HookApp()
        calls = []

        @app.pre_tool()  # No args = catch-all
        def catch_all(event):
            calls.append(event.tool_name)
            return allow()

        client = TestClient(app)

        # Send different tool events
        client.send(MockEvent.bash(command="ls"))
        client.send(MockEvent.write(file_path="/test.txt"))
        client.send(MockEvent.read(file_path="/test.txt"))

        assert calls == ["Bash", "Write", "Read"]

    def test_catch_all_with_specific(self):
        """Catch-all runs after specific handlers."""
        from fasthooks import HookApp, allow, deny

        app = HookApp()
        order = []

        @app.pre_tool("Bash")
        def bash_specific(event):
            order.append("bash_specific")
            return allow()

        @app.pre_tool()  # Catch-all
        def catch_all(event):
            order.append("catch_all")
            return allow()

        client = TestClient(app)
        client.send(MockEvent.bash(command="ls"))

        # Specific runs first, then catch-all
        assert order == ["bash_specific", "catch_all"]

    def test_catch_all_deny_stops_chain(self):
        """Catch-all deny stops further processing."""
        from fasthooks import HookApp, deny

        app = HookApp()

        @app.pre_tool()
        def deny_all(event):
            return deny("blocked")

        client = TestClient(app)
        response = client.send(MockEvent.bash(command="ls"))

        assert response is not None
        assert response.decision == "deny"
