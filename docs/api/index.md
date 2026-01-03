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
