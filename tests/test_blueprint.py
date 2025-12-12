"""Tests for Blueprint composition."""
import json
from io import StringIO

from fasthooks import HookApp, allow, deny
from fasthooks.blueprint import Blueprint


class TestBlueprintBasic:
    def test_create_blueprint(self):
        """Blueprint can be created with a name."""
        bp = Blueprint("security")
        assert bp.name == "security"

    def test_blueprint_pre_tool(self):
        """Blueprint supports @pre_tool decorator."""
        bp = Blueprint("test")

        @bp.pre_tool("Bash")
        def check_bash(event):
            return allow()

        assert len(bp._pre_tool_handlers["Bash"]) == 1

    def test_blueprint_on_stop(self):
        """Blueprint supports lifecycle decorators."""
        bp = Blueprint("test")

        @bp.on_stop()
        def handle_stop(event):
            return allow()

        assert len(bp._lifecycle_handlers["Stop"]) == 1


class TestBlueprintInclude:
    def test_include_blueprint(self):
        """App includes blueprint handlers."""
        app = HookApp()
        bp = Blueprint("security")
        calls = []

        @bp.pre_tool("Bash")
        def check_bash(event):
            calls.append("bash_check")
            return allow()

        app.include(bp)

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

        assert calls == ["bash_check"]

    def test_multiple_blueprints(self):
        """Multiple blueprints can be included."""
        app = HookApp()
        calls = []

        security = Blueprint("security")
        logging = Blueprint("logging")

        @security.pre_tool("Bash")
        def security_check(event):
            calls.append("security")
            return allow()

        @logging.pre_tool("Bash")
        def log_command(event):
            calls.append("logging")
            return allow()

        app.include(security)
        app.include(logging)

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

        assert calls == ["security", "logging"]

    def test_blueprint_deny_stops_chain(self):
        """Blueprint handler deny stops processing."""
        app = HookApp()
        calls = []

        security = Blueprint("security")

        @security.pre_tool("Bash")
        def block_rm(event):
            calls.append("checked")
            if "rm" in event.command:
                return deny("No rm allowed")
            return allow()

        # Include blueprint first, then add app handler
        # This ensures security checks run before other handlers
        app.include(security)

        @app.pre_tool("Bash")
        def should_not_run(event):
            calls.append("app_handler")
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "tool_use_id": "t1",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)

        assert calls == ["checked"]  # app_handler never ran
        stdout.seek(0)
        result = json.loads(stdout.read())
        assert result["decision"] == "deny"


class TestBlueprintLifecycle:
    def test_blueprint_lifecycle_handlers(self):
        """Blueprint lifecycle handlers are included."""
        app = HookApp()
        calls = []

        hooks = Blueprint("hooks")

        @hooks.on_stop()
        def handle_stop(event):
            calls.append("stop")
            return allow()

        @hooks.on_session_start()
        def handle_start(event):
            calls.append("start")
            return allow()

        app.include(hooks)

        # Test stop
        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        # Test session start
        stdin2 = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "SessionStart",
            "source": "startup",
        }))
        app.run(stdin=stdin2, stdout=StringIO())

        assert calls == ["stop", "start"]
