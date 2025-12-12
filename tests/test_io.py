"""Tests for stdin/stdout IO handling."""
import json
from io import StringIO

from fasthooks import HookResponse
from fasthooks._internal.io import read_stdin, write_stdout


class TestReadStdin:
    def test_read_valid_json(self):
        """read_stdin parses valid JSON from stdin."""
        stdin = StringIO('{"session_id": "abc", "hook_event_name": "PreToolUse"}')
        data = read_stdin(stdin)
        assert data["session_id"] == "abc"
        assert data["hook_event_name"] == "PreToolUse"

    def test_read_invalid_json(self):
        """read_stdin returns empty dict on invalid JSON."""
        stdin = StringIO("not valid json")
        data = read_stdin(stdin)
        assert data == {}

    def test_read_empty(self):
        """read_stdin returns empty dict on empty input."""
        stdin = StringIO("")
        data = read_stdin(stdin)
        assert data == {}


class TestWriteStdout:
    def test_write_response(self):
        """write_stdout writes HookResponse JSON to stdout."""
        stdout = StringIO()
        response = HookResponse(decision="deny", reason="test")
        write_stdout(response, stdout)
        stdout.seek(0)
        output = stdout.read()
        data = json.loads(output)
        assert data["decision"] == "deny"
        assert data["reason"] == "test"

    def test_write_empty_response(self):
        """write_stdout writes nothing for empty response."""
        stdout = StringIO()
        response = HookResponse(decision="approve")  # allow() response
        write_stdout(response, stdout)
        stdout.seek(0)
        output = stdout.read()
        # Empty or no output for approve-only
        assert output == "" or output == "{}"
