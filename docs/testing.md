# Testing Guide

Practical patterns for testing fasthooks. Carmack rules: simple, fast, no bloat.

## Philosophy

- **Audience**: Contributors who don't know the codebase. Error messages should provide context.
- **Coverage**: No target. Cover what matters, ignore the number.
- **Speed**: Unit tests are fast (mocked I/O). Integration tests can be slower (real git, real files).
- **Isolation**: `tmp_path` handles cleanup. Every test gets fresh state.

## Directory Structure

```
tests/
├── conftest.py              # Common fixtures (MockEvent, tmp dirs)
├── test_app.py              # Core HookApp tests
├── test_blueprint.py        # Blueprint tests
├── test_*.py                # Other unit tests
├── strategies/
│   ├── conftest.py          # Strategy-specific fixtures
│   ├── test_base.py         # Strategy base class tests
│   ├── test_long_running.py # LongRunningStrategy tests
│   └── test_observability.py # Observability tests
└── integration/
    ├── conftest.py          # Real git, real files fixtures
    └── test_long_running_integration.py
```

## Existing Patterns

### MockEvent Factory

Create typed events for testing handlers:

```python
from fasthooks.testing import MockEvent

# Tool events
event = MockEvent.bash(command="ls -la")
event = MockEvent.write(file_path="/test.txt", content="hello")
event = MockEvent.edit(file_path="/test.txt", old_string="a", new_string="b")

# Lifecycle events
event = MockEvent.stop()
event = MockEvent.session_start(source="startup")
event = MockEvent.pre_compact(trigger="manual")

# All events accept session_id and cwd overrides
event = MockEvent.bash(command="ls", cwd="/my/project", session_id="sess-123")
```

### TestClient

Send events to a HookApp without stdin/stdout plumbing:

```python
from fasthooks import HookApp, allow, deny
from fasthooks.testing import TestClient, MockEvent

app = HookApp()

@app.pre_tool("Bash")
def check_bash(event):
    if "rm -rf" in event.command:
        return deny("Dangerous command")
    return allow()

client = TestClient(app)

# Returns None if allowed (no response needed)
assert client.send(MockEvent.bash(command="ls")) is None

# Returns HookResponse if denied/blocked
response = client.send(MockEvent.bash(command="rm -rf /"))
assert response.decision == "deny"
```

### Test Organization

Use classes to group related tests:

```python
class TestBashHandler:
    def test_allows_safe_commands(self):
        ...

    def test_denies_dangerous_commands(self):
        ...
```

## Strategy Testing Patterns

### StrategyTestClient

Full-featured client for strategy testing (in `fasthooks.testing`):

```python
from fasthooks.testing import StrategyTestClient
from fasthooks.strategies import LongRunningStrategy

strategy = LongRunningStrategy(enforce_commits=True)
client = StrategyTestClient(strategy)

# Project setup helpers
client.setup_project(files={
    "feature_list.json": '[{"description": "test", "passes": false}]',
    "claude-progress.txt": "Session 1: started",
})

# Git setup (creates real git repo in tmp_path)
client.setup_git()
client.add_uncommitted("dirty.py")

# Trigger hooks and get responses
response = client.trigger_session_start(source="startup")
assert response.decision == "approve"
assert "1/1" not in response.message  # 0/1 passing

response = client.trigger_stop()
assert response.decision == "block"  # uncommitted changes

# Assertions
client.assert_blocked("uncommitted")
client.assert_event_emitted("session_type", type="coding")
```

### Unit Tests (Mocked I/O)

Fast tests that mock subprocess and filesystem:

```python
# tests/strategies/test_long_running.py
import pytest
from unittest.mock import patch, MagicMock

class TestLongRunningSessionStart:
    """SessionStart handler behavior."""

    @pytest.mark.parametrize("has_feature_list,expected_type", [
        (False, "initializer"),
        (True, "coding"),
    ])
    def test_detects_session_type(self, strategy_client, has_feature_list, expected_type):
        if has_feature_list:
            strategy_client.setup_project(files={"feature_list.json": "[]"})

        response = strategy_client.trigger_session_start()
        strategy_client.assert_event_emitted("session_type", type=expected_type)
```

### Integration Tests (Real I/O)

Slower tests with real git repos:

```python
# tests/integration/test_long_running_integration.py

class TestLongRunningRealGit:
    """Integration tests with real git operations."""

    def test_stop_blocked_with_uncommitted_changes(self, real_git_project):
        """Stop is blocked when git has uncommitted changes."""
        # real_git_project is a fixture that creates actual git repo
        real_git_project.write_file("new.py", "# new file")
        # Don't commit - leave as uncommitted

        client = StrategyTestClient(
            LongRunningStrategy(enforce_commits=True),
            project_dir=real_git_project.path,
        )

        response = client.trigger_stop()
        assert response.decision == "block"
        assert "uncommitted" in response.reason.lower()
```

## Observability Testing

### Callback Collector Pattern

Capture emitted events with a simple list:

```python
def test_observability_events_in_order(self):
    """Events emitted in correct order: hook_enter, decision, hook_exit."""
    strategy = LongRunningStrategy()
    events = []

    @strategy.on_observe
    def collect(event):
        events.append(event)

    client = StrategyTestClient(strategy)
    client.trigger_session_start()

    # Verify order
    event_types = [e.event_type for e in events]
    assert event_types == ["hook_enter", "decision", "hook_exit"]

    # Verify decision content
    decision_event = events[1]
    assert decision_event.decision == "approve"
```

### Testing Custom Events

```python
def test_custom_event_emitted(self):
    """Strategy emits custom session_type event."""
    strategy = LongRunningStrategy()
    events = []

    @strategy.on_observe
    def collect(event):
        if event.event_type == "custom":
            events.append(event)

    client = StrategyTestClient(strategy)
    client.trigger_session_start()

    assert len(events) == 1
    assert events[0].custom_event_type == "session_type"
    assert events[0].payload["type"] == "initializer"
```

## Fixtures

### Root conftest.py

```python
# tests/conftest.py
import pytest
from pathlib import Path
from fasthooks.testing import MockEvent

@pytest.fixture
def tmp_project(tmp_path):
    """Empty project directory."""
    return tmp_path

@pytest.fixture
def mock_event():
    """MockEvent factory."""
    return MockEvent
```

### Strategy conftest.py

```python
# tests/strategies/conftest.py
import pytest
from fasthooks.strategies import LongRunningStrategy
from fasthooks.testing import StrategyTestClient

@pytest.fixture
def strategy():
    """Default LongRunningStrategy."""
    return LongRunningStrategy()

@pytest.fixture
def strategy_client(strategy, tmp_path):
    """StrategyTestClient with tmp project directory."""
    return StrategyTestClient(strategy, project_dir=tmp_path)
```

### Integration conftest.py

```python
# tests/integration/conftest.py
import pytest
import subprocess
from pathlib import Path

class RealGitProject:
    """Helper for creating real git repos in tests."""

    def __init__(self, path: Path):
        self.path = path
        subprocess.run(["git", "init"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path)

    def write_file(self, name: str, content: str):
        (self.path / name).write_text(content)

    def commit(self, message: str = "commit"):
        subprocess.run(["git", "add", "."], cwd=self.path)
        subprocess.run(["git", "commit", "-m", message], cwd=self.path)

@pytest.fixture
def real_git_project(tmp_path):
    """Real git repository in tmp_path."""
    return RealGitProject(tmp_path)
```

## Error Handling Tests

### Testing fail_mode

```python
@pytest.mark.parametrize("fail_mode,expected_decision", [
    ("open", "approve"),    # Exception → allow (fail open)
    ("closed", "block"),    # Exception → block (fail closed)
])
def test_fail_mode_behavior(self, fail_mode, expected_decision):
    """Strategy respects fail_mode when handler throws."""
    # Create strategy with custom fail_mode
    # Trigger handler that throws
    # Verify decision matches expected
```

## Malformed Input Tests

```python
def test_malformed_feature_list_logs_warning(self, strategy_client, caplog):
    """Invalid JSON in feature_list.json logs warning, doesn't crash."""
    strategy_client.setup_project(files={
        "feature_list.json": "not valid json {{{",
    })

    response = strategy_client.trigger_session_start()

    # Should still work (graceful degradation)
    assert response.decision == "approve"
    # Should log warning
    assert "warning" in caplog.text.lower() or "error" in caplog.text.lower()
```

## Best Practices

### DO

- Use `tmp_path` for all file operations
- Use parametrize for mode/variant testing
- Keep unit tests fast (no real subprocess/git)
- Use descriptive test names: `test_stop_blocked_when_uncommitted`
- Add docstrings only for complex tests

### DON'T

- Don't set coverage targets
- Don't test library internals (trust filelock, etc.)
- Don't mock what you don't own (mock your boundaries, not third-party libs)
- Don't write integration tests for every unit test case

### Test Naming

```python
# Good: describes behavior
def test_stop_blocked_when_uncommitted_changes_exist(self):

# Good: describes input/output
def test_session_start_returns_initializer_context_when_no_feature_list(self):

# Bad: too vague
def test_stop(self):
def test_handler(self):
```

## Running Tests

```bash
# All tests
make test

# Unit tests only (fast)
uv run pytest tests/ --ignore=tests/integration/

# Integration tests only
uv run pytest tests/integration/

# Single test file
uv run pytest tests/strategies/test_long_running.py -v

# Single test
uv run pytest tests/strategies/test_long_running.py::TestSessionStart::test_detects_mode -v

# With coverage (informational, no target)
uv run pytest --cov=fasthooks tests/
```
