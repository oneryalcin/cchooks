"""Tests for HookApp."""
import json
from io import StringIO

from fasthooks import HookApp, allow, approve_permission, deny, deny_permission
from fasthooks.responses import PermissionHookResponse
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


class TestAsyncHandlers:
    """Tests for async handler support."""

    def test_async_handler_allow(self):
        """Async handler can return allow."""
        app = HookApp()

        @app.pre_tool("Bash")
        async def async_check(event):
            return allow()

        client = TestClient(app)
        response = client.send(MockEvent.bash(command="ls"))
        assert response is None  # allowed

    def test_async_handler_deny(self):
        """Async handler can return deny."""
        app = HookApp()

        @app.pre_tool("Bash")
        async def async_check(event):
            return deny("async blocked")

        client = TestClient(app)
        response = client.send(MockEvent.bash(command="ls"))
        assert response is not None
        assert response.decision == "deny"
        assert "async" in response.reason

    def test_mixed_sync_async_handlers(self):
        """Sync and async handlers work together."""
        app = HookApp()
        calls = []

        @app.pre_tool("Bash")
        def sync_handler(event):
            calls.append("sync")
            return allow()

        @app.pre_tool("Bash")
        async def async_handler(event):
            calls.append("async")
            return allow()

        client = TestClient(app)
        client.send(MockEvent.bash(command="ls"))
        assert calls == ["sync", "async"]

    def test_async_handler_with_await(self):
        """Async handler can use await."""
        import anyio

        app = HookApp()
        awaited = []

        @app.pre_tool("Bash")
        async def async_check(event):
            await anyio.sleep(0.001)  # Small async operation
            awaited.append(True)
            return allow()

        client = TestClient(app)
        client.send(MockEvent.bash(command="ls"))
        assert awaited == [True]

    def test_async_guard(self):
        """Async guard function works."""
        app = HookApp()

        async def is_dangerous(event):
            return "rm" in event.command

        @app.pre_tool("Bash", when=is_dangerous)
        async def block_dangerous(event):
            return deny("dangerous command")

        client = TestClient(app)

        # Safe command - guard returns False, handler not called
        response = client.send(MockEvent.bash(command="ls"))
        assert response is None

        # Dangerous command - guard returns True, handler called
        response = client.send(MockEvent.bash(command="rm -rf"))
        assert response is not None
        assert response.decision == "deny"


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
        from fasthooks import HookApp, allow

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


class TestPermissionRequestHandlers:
    """Tests for PermissionRequest handlers."""

    def test_on_permission_approve(self):
        """on_permission handler can approve permission request."""
        app = HookApp()

        @app.on_permission("Bash")
        def auto_approve(event):
            return approve_permission()

        client = TestClient(app)
        response = client.send(MockEvent.permission_bash(command="ls"))

        assert response is not None
        assert isinstance(response, PermissionHookResponse)
        assert response.behavior == "allow"

    def test_on_permission_deny(self):
        """on_permission handler can deny permission request."""
        app = HookApp()

        @app.on_permission("Bash")
        def deny_rm(event):
            if "rm" in event.command:
                return deny_permission("rm not allowed")
            return approve_permission()

        client = TestClient(app)

        # Safe command
        response = client.send(MockEvent.permission_bash(command="ls"))
        assert response.behavior == "allow"

        # Dangerous command
        response = client.send(MockEvent.permission_bash(command="rm -rf /"))
        assert response.behavior == "deny"
        assert response.message == "rm not allowed"

    def test_on_permission_with_modify(self):
        """on_permission handler can modify tool input."""
        app = HookApp()

        @app.on_permission("Bash")
        def sanitize(event):
            # Always replace command with safe version
            return approve_permission(modify={"command": "echo safe"})

        client = TestClient(app)
        response = client.send(MockEvent.permission_bash(command="dangerous"))

        assert response.behavior == "allow"
        assert response.modify == {"command": "echo safe"}

    def test_on_permission_catch_all(self):
        """on_permission() with no args matches all tools."""
        app = HookApp()
        calls = []

        @app.on_permission()  # catch-all
        def log_all(event):
            calls.append(event.tool_name)
            return approve_permission()

        client = TestClient(app)
        client.send(MockEvent.permission_bash(command="ls"))
        client.send(MockEvent.permission_write(file_path="/test.txt"))

        assert calls == ["Bash", "Write"]

    def test_on_permission_tool_specific_plus_catch_all(self):
        """Tool-specific and catch-all handlers both run."""
        app = HookApp()
        order = []

        @app.on_permission("Bash")
        def bash_specific(event):
            order.append("bash_specific")
            return None  # Continue to next handler

        @app.on_permission()
        def catch_all(event):
            order.append("catch_all")
            return approve_permission()

        client = TestClient(app)
        client.send(MockEvent.permission_bash(command="ls"))

        # Specific runs first, then catch-all
        assert order == ["bash_specific", "catch_all"]

    def test_on_permission_not_called_for_pre_tool(self):
        """on_permission handler not called for PreToolUse events."""
        app = HookApp()
        permission_calls = []
        pretool_calls = []

        @app.on_permission("Bash")
        def permission_handler(event):
            permission_calls.append("permission")
            return approve_permission()

        @app.pre_tool("Bash")
        def pretool_handler(event):
            pretool_calls.append("pretool")
            return allow()

        client = TestClient(app)

        # Send PreToolUse
        client.send(MockEvent.bash(command="ls"))
        assert pretool_calls == ["pretool"]
        assert permission_calls == []

        # Send PermissionRequest
        client.send(MockEvent.permission_bash(command="ls"))
        assert permission_calls == ["permission"]

    def test_on_permission_multiple_tools(self):
        """on_permission can match multiple tools."""
        app = HookApp()
        calls = []

        @app.on_permission("Write", "Edit")
        def file_ops(event):
            calls.append(event.tool_name)
            return approve_permission()

        client = TestClient(app)
        client.send(MockEvent.permission_write(file_path="/test.txt"))
        client.send(MockEvent.permission_edit("/test.txt", "old", "new"))
        client.send(MockEvent.permission_bash(command="ls"))

        assert calls == ["Write", "Edit"]

    def test_on_permission_async(self):
        """Async on_permission handler works."""
        app = HookApp()

        @app.on_permission("Bash")
        async def async_handler(event):
            return approve_permission()

        client = TestClient(app)
        response = client.send(MockEvent.permission_bash(command="ls"))

        assert response.behavior == "allow"

    def test_on_permission_with_guard(self):
        """on_permission handler with guard function."""
        app = HookApp()

        def is_dangerous(event):
            return "rm" in event.command

        @app.on_permission("Bash", when=is_dangerous)
        def block_dangerous(event):
            return deny_permission("dangerous command blocked")

        @app.on_permission("Bash")
        def allow_safe(event):
            return approve_permission()

        client = TestClient(app)

        # Safe - guard fails, first handler skipped, second runs
        response = client.send(MockEvent.permission_bash(command="ls"))
        assert response.behavior == "allow"

        # Dangerous - guard passes, first handler runs
        response = client.send(MockEvent.permission_bash(command="rm -rf"))
        assert response.behavior == "deny"

    def test_permission_request_typed_event(self):
        """PermissionRequest events get typed tool properties."""
        app = HookApp()
        captured = []

        @app.on_permission("Bash")
        def capture_command(event):
            captured.append(event.command)  # Uses typed Bash.command property
            return approve_permission()

        client = TestClient(app)
        client.send(MockEvent.permission_bash(command="ls -la"))

        assert captured == ["ls -la"]
