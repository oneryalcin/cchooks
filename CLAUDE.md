# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
make help        # Show all commands
make install     # uv sync
make test        # Run tests with coverage
make lint        # Run ruff linter
make typecheck   # Run mypy
make format      # Format code
make check       # Run all checks (lint, typecheck, test)

# Run single test
uv run pytest tests/test_app.py::test_function_name -v
```

## Architecture

fasthooks is a library for building Claude Code hooks with a FastAPI-like API. Claude Code invokes hooks via stdin/stdout JSON protocol.

### Core Flow
1. `HookApp.run()` reads JSON from stdin via `_internal/io.py`
2. `_dispatch()` routes by `hook_event_name` field (PreToolUse, PostToolUse, Stop, etc.)
3. For tool events, combines tool-specific handlers with catch-all ("*") handlers
4. Runs handler chain through middleware, returns first deny/block response
5. Writes JSON response to stdout

### Key Components

**app.py:HookApp** - Main class. Registers handlers via decorators (`@app.pre_tool()`, `@app.on_stop()`). Resolves DI based on type hints. `TOOL_EVENT_MAP` maps tool names to typed event classes.

**events/** - Pydantic models for hook events:
- `base.py:BaseEvent` - Common fields (session_id, cwd, transcript_path)
- `tools.py` - Typed tool events (Bash, Write, Edit, etc.) with property accessors
- `lifecycle.py` - Stop, SessionStart, etc.

**responses.py** - `allow()`, `deny()`, `block()` builders. `HookResponse.to_json()` serializes to Claude Code format.

**depends/** - Injectable dependencies:
- `Transcript` - Lazy-parsed session transcript with `.stats` (token counts, tool calls)
- `State` - Session-scoped persistent dict backed by JSON file

**blueprint.py** - Composable handler groups via `app.include(blueprint)`

**testing/** - `MockEvent` factory and `TestClient` for unit tests

### Handler Pattern
Handlers receive typed event + optional DI deps. Return `None` to allow, `deny(reason)` to block.

```python
@app.pre_tool("Bash")
def check(event, state: State):  # DI via type hint
    if "rm -rf" in event.command:
        return deny("Blocked")
```

Guards filter via `when=` lambda. Catch-all handlers use `@app.pre_tool()` (no args).

## Claude Code Hooks Protocol

See `docs/refs/hooks-refs.md` for the complete Claude Code hooks reference:
- Hook events: PreToolUse, PostToolUse, Stop, SubagentStop, SessionStart, SessionEnd, UserPromptSubmit, Notification, PreCompact
- Input JSON schema per event type (tool_name, tool_input, tool_response, etc.)
- Output JSON schema: `decision`, `reason`, `hookSpecificOutput`, `continue`, `systemMessage`
- Exit codes: 0=success, 2=blocking error (stderr shown to Claude)
- Matchers: exact match, regex (`Edit|Write`), catch-all (`*`)
