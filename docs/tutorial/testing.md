# Testing

fasthooks provides utilities for testing your hooks without Claude Code.

## MockEvent

Create typed test events:

```python
from fasthooks.testing import MockEvent

# Create a Bash event
event = MockEvent.bash(command="ls -la")
print(event.command)  # "ls -la"

# Create a Write event
event = MockEvent.write(
    file_path="/tmp/test.txt",
    content="Hello world"
)
print(event.file_path)  # "/tmp/test.txt"
```

## Available Mock Events

### Tool Events (PreToolUse)

```python
MockEvent.bash(command="echo hello")
MockEvent.write(file_path="/tmp/f.txt", content="...")
MockEvent.read(file_path="/tmp/f.txt")
MockEvent.edit(file_path="/tmp/f.txt", old_string="a", new_string="b")
```

### Permission Events

```python
MockEvent.permission_bash(command="rm -rf /")
MockEvent.permission_write(file_path="/etc/passwd", content="...")
MockEvent.permission_edit(file_path="/etc/hosts", old_string="a", new_string="b")
```

### Lifecycle Events

```python
MockEvent.stop()
MockEvent.stop(stop_hook_active=True)
MockEvent.session_start(source="startup")
MockEvent.pre_compact(trigger="manual")
```

## TestClient

Test your handlers end-to-end:

```python
from fasthooks.testing import TestClient, MockEvent
from my_hooks import app

client = TestClient(app)

def test_allows_safe_commands():
    response = client.send(MockEvent.bash(command="ls -la"))
    assert response is None  # Allowed

def test_blocks_dangerous_commands():
    response = client.send(MockEvent.bash(command="rm -rf /"))
    assert response.decision == "deny"
    assert "dangerous" in response.reason.lower()
```

## Example Test File

```python
# test_hooks.py
import pytest
from fasthooks.testing import TestClient, MockEvent
from hooks import app

@pytest.fixture
def client():
    return TestClient(app)

class TestBashHooks:
    def test_allows_ls(self, client):
        response = client.send(MockEvent.bash(command="ls"))
        assert response is None

    def test_blocks_rm_rf(self, client):
        response = client.send(MockEvent.bash(command="rm -rf /"))
        assert response is not None
        assert response.decision == "deny"

class TestWriteHooks:
    def test_blocks_env_files(self, client):
        response = client.send(MockEvent.write(
            file_path=".env",
            content="SECRET=123"
        ))
        assert response.decision == "deny"

    def test_allows_normal_files(self, client):
        response = client.send(MockEvent.write(
            file_path="readme.md",
            content="# Hello"
        ))
        assert response is None
```

Run tests:

```bash
pytest test_hooks.py -v
```

## CLI Smoke Test

For a quick manual check (no test file needed), run a hook against a synthetic
event with `fasthooks test`:

```bash
fasthooks test .claude/hooks.py --event PreToolUse:Bash --input '{"command": "rm -rf /"}'
```

It builds a valid hook-event envelope, runs the hook the way Claude Code does
(stdin → hook → stdout/exit code), and reports the outcome — the decision JSON, a
block (exit 2), or "allowed". `--event` accepts `Name` or `Name:Tool` (e.g.
`Stop`, `PostToolUse:Edit`); `--input` is the `tool_input` JSON (or `@file.json`).

This is a smoke test, not your test suite — for thorough tests use `TestClient`
and `MockEvent` as shown above.
