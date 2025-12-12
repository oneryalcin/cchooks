"""Tests for tool-specific event models."""

from fasthooks.events import Bash, Edit, Glob, Grep, Read, Task, Write


class TestBashEvent:
    def test_parse_bash_event(self):
        """Bash event parses with tool_input."""
        data = {
            "session_id": "abc123",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "ls -la",
                "description": "List files",
                "timeout": 5000,
            },
            "tool_use_id": "toolu_123",
        }
        event = Bash.model_validate(data)
        assert event.tool_name == "Bash"
        assert event.command == "ls -la"
        assert event.description == "List files"
        assert event.timeout == 5000

    def test_bash_command_property(self):
        """Bash.command returns command from tool_input."""
        data = {
            "session_id": "abc",
            "cwd": "/",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "pwd"},
            "tool_use_id": "t1",
        }
        event = Bash.model_validate(data)
        assert event.command == "pwd"

    def test_bash_optional_fields(self):
        """Bash handles missing optional fields."""
        data = {
            "session_id": "abc",
            "cwd": "/",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi"},
            "tool_use_id": "t1",
        }
        event = Bash.model_validate(data)
        assert event.description is None
        assert event.timeout is None
        assert event.run_in_background is None


class TestWriteEvent:
    def test_parse_write_event(self):
        """Write event parses file_path and content."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/workspace/test.py",
                "content": "print('hello')",
            },
            "tool_use_id": "t1",
        }
        event = Write.model_validate(data)
        assert event.file_path == "/workspace/test.py"
        assert event.content == "print('hello')"


class TestReadEvent:
    def test_parse_read_event(self):
        """Read event parses file_path and optional offset/limit."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {
                "file_path": "/workspace/main.py",
                "offset": 10,
                "limit": 100,
            },
            "tool_use_id": "t1",
        }
        event = Read.model_validate(data)
        assert event.file_path == "/workspace/main.py"
        assert event.offset == 10
        assert event.limit == 100


class TestEditEvent:
    def test_parse_edit_event(self):
        """Edit event parses file_path and edit params."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/workspace/main.py",
                "old_string": "foo",
                "new_string": "bar",
                "replace_all": True,
            },
            "tool_use_id": "t1",
        }
        event = Edit.model_validate(data)
        assert event.file_path == "/workspace/main.py"
        assert event.old_string == "foo"
        assert event.new_string == "bar"
        assert event.replace_all is True


class TestGrepEvent:
    def test_parse_grep_event(self):
        """Grep event parses pattern and options."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Grep",
            "tool_input": {
                "pattern": "TODO",
                "path": "/workspace",
                "glob": "*.py",
            },
            "tool_use_id": "t1",
        }
        event = Grep.model_validate(data)
        assert event.pattern == "TODO"
        assert event.path == "/workspace"
        assert event.glob == "*.py"


class TestGlobEvent:
    def test_parse_glob_event(self):
        """Glob event parses pattern."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Glob",
            "tool_input": {
                "pattern": "**/*.py",
                "path": "/workspace/src",
            },
            "tool_use_id": "t1",
        }
        event = Glob.model_validate(data)
        assert event.pattern == "**/*.py"
        assert event.path == "/workspace/src"


class TestTaskEvent:
    def test_parse_task_event(self):
        """Task event parses subagent params."""
        data = {
            "session_id": "abc",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Task",
            "tool_input": {
                "description": "Find all tests",
                "prompt": "Search for test files",
                "subagent_type": "Explore",
                "model": "haiku",
            },
            "tool_use_id": "t1",
        }
        event = Task.model_validate(data)
        assert event.description == "Find all tests"
        assert event.prompt == "Search for test files"
        assert event.subagent_type == "Explore"
        assert event.model == "haiku"
