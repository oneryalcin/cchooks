"""Tests for lifecycle decorators."""
import json
from io import StringIO

from fasthooks import HookApp, allow, block, deny


class TestOnStop:
    def test_on_stop_decorator(self):
        """@on_stop registers handler for Stop events."""
        app = HookApp()
        calls = []

        @app.on_stop()
        def handle_stop(event):
            calls.append("stop")
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        assert calls == ["stop"]

    def test_on_stop_block(self):
        """@on_stop can block stopping."""
        app = HookApp()

        @app.on_stop()
        def keep_going(event):
            return block("Not done yet!")

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        stdout.seek(0)
        result = json.loads(stdout.read())
        assert result["decision"] == "block"
        assert "Not done" in result["reason"]


class TestOnSubagentStop:
    def test_on_subagent_stop(self):
        """@on_subagent_stop registers handler."""
        app = HookApp()
        captured_agent_id = []

        @app.on_subagent_stop()
        def handle(event):
            captured_agent_id.append(event.agent_id)
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "SubagentStop",
            "agent_id": "agent-xyz",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        assert captured_agent_id == ["agent-xyz"]


class TestOnSessionStart:
    def test_on_session_start(self):
        """@on_session_start registers handler."""
        app = HookApp()
        sources = []

        @app.on_session_start()
        def handle(event):
            sources.append(event.source)
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "SessionStart",
            "source": "startup",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        assert sources == ["startup"]


class TestOnSessionEnd:
    def test_on_session_end(self):
        """@on_session_end registers handler."""
        app = HookApp()
        reasons = []

        @app.on_session_end()
        def handle(event):
            reasons.append(event.reason)
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "SessionEnd",
            "reason": "logout",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        assert reasons == ["logout"]


class TestOnPreCompact:
    def test_on_pre_compact(self):
        """@on_pre_compact registers handler."""
        app = HookApp()
        triggers = []

        @app.on_pre_compact()
        def handle(event):
            triggers.append(event.trigger)
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreCompact",
            "trigger": "manual",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        assert triggers == ["manual"]


class TestOnPrompt:
    def test_on_prompt(self):
        """@on_prompt registers handler for UserPromptSubmit."""
        app = HookApp()
        prompts = []

        @app.on_prompt()
        def handle(event):
            prompts.append(event.prompt)
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Hello world",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        assert prompts == ["Hello world"]

    def test_on_prompt_deny(self):
        """@on_prompt can deny prompts."""
        app = HookApp()

        @app.on_prompt()
        def block_secrets(event):
            if "password" in event.prompt.lower():
                return deny("No secrets allowed")
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "my password is 123",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        stdout.seek(0)
        result = json.loads(stdout.read())
        assert result["decision"] == "deny"


class TestOnNotification:
    def test_on_notification(self):
        """@on_notification registers handler."""
        app = HookApp()
        types = []

        @app.on_notification()
        def handle(event):
            types.append(event.notification_type)
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Notification",
            "message": "Test",
            "notification_type": "idle_prompt",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)
        assert types == ["idle_prompt"]


class TestTypedEvents:
    def test_pre_tool_receives_typed_bash_event(self):
        """@pre_tool("Bash") receives Bash typed event."""
        app = HookApp()
        commands = []

        @app.pre_tool("Bash")
        def handle(event):
            # Should have .command property from Bash type
            commands.append(event.command)
            return allow()

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
        assert commands == ["ls -la"]
