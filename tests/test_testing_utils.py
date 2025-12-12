"""Tests for testing utilities."""

from fasthooks import HookApp, allow, deny
from fasthooks.testing import MockEvent, TestClient


class TestMockEvent:
    def test_mock_bash(self):
        """MockEvent.bash() creates Bash event."""
        event = MockEvent.bash(command="ls -la")
        assert event.command == "ls -la"
        assert event.tool_name == "Bash"
        assert event.hook_event_name == "PreToolUse"

    def test_mock_bash_with_extras(self):
        """MockEvent.bash() accepts extra params."""
        event = MockEvent.bash(
            command="npm install",
            description="Install dependencies",
            timeout=60000,
        )
        assert event.command == "npm install"
        assert event.description == "Install dependencies"
        assert event.timeout == 60000

    def test_mock_write(self):
        """MockEvent.write() creates Write event."""
        event = MockEvent.write(file_path="/test.py", content="x=1")
        assert event.file_path == "/test.py"
        assert event.content == "x=1"
        assert event.tool_name == "Write"

    def test_mock_read(self):
        """MockEvent.read() creates Read event."""
        event = MockEvent.read(file_path="/test.py")
        assert event.file_path == "/test.py"
        assert event.tool_name == "Read"

    def test_mock_edit(self):
        """MockEvent.edit() creates Edit event."""
        event = MockEvent.edit(
            file_path="/test.py",
            old_string="foo",
            new_string="bar",
        )
        assert event.file_path == "/test.py"
        assert event.old_string == "foo"
        assert event.new_string == "bar"

    def test_mock_stop(self):
        """MockEvent.stop() creates Stop event."""
        event = MockEvent.stop()
        assert event.hook_event_name == "Stop"

    def test_mock_stop_with_hook_active(self):
        """MockEvent.stop() can set stop_hook_active."""
        event = MockEvent.stop(stop_hook_active=True)
        assert event.stop_hook_active is True

    def test_mock_session_start(self):
        """MockEvent.session_start() creates SessionStart event."""
        event = MockEvent.session_start(source="startup")
        assert event.source == "startup"
        assert event.hook_event_name == "SessionStart"

    def test_mock_pre_compact(self):
        """MockEvent.pre_compact() creates PreCompact event."""
        event = MockEvent.pre_compact(trigger="auto")
        assert event.trigger == "auto"
        assert event.hook_event_name == "PreCompact"

    def test_mock_custom_session(self):
        """MockEvent allows custom session_id."""
        event = MockEvent.bash(command="ls", session_id="custom-123")
        assert event.session_id == "custom-123"


class TestTestClient:
    def test_client_send_pre_tool(self):
        """TestClient.send() invokes PreToolUse handlers."""
        app = HookApp()
        calls = []

        @app.pre_tool("Bash")
        def handler(event):
            calls.append(event.command)
            return allow()

        client = TestClient(app)
        response = client.send(MockEvent.bash(command="ls -la"))

        assert calls == ["ls -la"]
        assert response is None  # allow returns None

    def test_client_send_deny(self):
        """TestClient returns deny responses."""
        app = HookApp()

        @app.pre_tool("Bash")
        def handler(event):
            if "rm" in event.command:
                return deny("No rm allowed")
            return allow()

        client = TestClient(app)
        response = client.send(MockEvent.bash(command="rm -rf /"))

        assert response is not None
        assert response.decision == "deny"
        assert "rm" in response.reason

    def test_client_send_lifecycle(self):
        """TestClient works with lifecycle events."""
        app = HookApp()
        calls = []

        @app.on_stop()
        def handler(event):
            calls.append("stop")
            return allow()

        client = TestClient(app)
        client.send(MockEvent.stop())

        assert calls == ["stop"]

    def test_client_with_di(self, tmp_path):
        """TestClient works with DI."""
        app = HookApp(state_dir=str(tmp_path))
        captured = []

        from fasthooks.depends import State

        @app.on_stop()
        def handler(event, state: State):
            state["called"] = True
            state.save()
            captured.append(True)
            return allow()

        client = TestClient(app)
        client.send(MockEvent.stop())

        assert captured == [True]


class TestTestClientRaw:
    def test_client_send_raw(self):
        """TestClient.send_raw() sends raw dict."""
        app = HookApp()
        calls = []

        @app.pre_tool("Bash")
        def handler(event):
            calls.append(event.command)
            return allow()

        client = TestClient(app)
        client.send_raw({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "pwd"},
            "tool_use_id": "t1",
        })

        assert calls == ["pwd"]
