# Python API Reference

Auto-generated API documentation from source code docstrings.

## Modules

| Module | Description |
|--------|-------------|
| [HookApp](app.md) | Main application class |
| [Responses](responses.md) | Response builders (`allow`, `deny`, `block`) |
| [Events](events.md) | Event types for tools and lifecycle |
| [Dependencies](depends.md) | Injectable dependencies (`Transcript`, `State`) |
| [Transcript](transcript.md) | Rich transcript modeling and context engineering |
| [Tasks](tasks.md) | Background task system |
| [Claude Integration](contrib-claude.md) | Claude Agent SDK wrapper |
| [Testing](testing.md) | Testing utilities |

## CLI Utilities

Internal modules used by the `fasthooks` CLI. These are not part of the public API but documented for contributors.

| Module | Description |
|--------|-------------|
| `fasthooks.cli_utils.validation` | Hooks.py validation and introspection |
| `fasthooks.cli_utils.settings` | Settings.json read/write/merge |
| `fasthooks.cli_utils.lock` | Lock file management |
| `fasthooks.cli_utils.paths` | Project root detection, path handling |
| `fasthooks.cli_utils.introspect` | Handler extraction and config generation |

## Quick Links

```python
# Core
from fasthooks import HookApp, Blueprint
from fasthooks import allow, deny, block

# Dependencies
from fasthooks.depends import Transcript, State

# Transcript (context engineering)
from fasthooks.transcript import (
    Transcript,
    UserMessage,
    AssistantMessage,
    inject_tool_result,
)

# Background Tasks
from fasthooks.tasks import task, Tasks

# Claude Integration (optional)
from fasthooks.contrib.claude import ClaudeAgent, agent_task

# Testing
from fasthooks.testing import MockEvent, TestClient
```
