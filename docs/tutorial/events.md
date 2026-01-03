# Events

Claude Code sends different events to your hooks. fasthooks provides typed classes for each.

## Hook Event Types

### PreToolUse

Runs **before** a tool executes. Can allow, deny, or modify the tool call.

```python
@app.pre_tool("Bash")
def check_bash(event):
    if "rm -rf" in event.command:
        return deny("Blocked dangerous command")
```

### PostToolUse

Runs **after** a tool executes successfully. Can provide feedback to Claude.

```python
@app.post_tool("Write")
def after_write(event):
    # event.tool_response contains the result
    if event.tool_response.get("success"):
        print(f"Wrote to {event.file_path}")
```

### PermissionRequest

Runs when Claude asks for permission. Can auto-allow or auto-deny.

```python
@app.on_permission("Bash")
def auto_allow_safe(event):
    if event.command.startswith("ls"):
        return allow()  # Auto-approve ls commands
```

### Stop / SubagentStop

Runs when Claude (or a subagent) is about to stop.

```python
@app.on_stop()
def on_stop(event):
    if event.stop_hook_active:
        return allow()  # Prevent infinite loops
    # Check if work is complete...
    return block("Please run the tests first")
```

### SessionStart / SessionEnd

Runs at session lifecycle events.

```python
@app.on_session_start()
def on_start(event):
    print(f"Session started: {event.source}")  # startup, resume, clear
```

## Tool Events

Each tool has a typed event class with specific properties.

### Bash

```python
@app.pre_tool("Bash")
def check(event):
    event.command      # str - the command to run
    event.description  # str | None - optional description
    event.timeout      # int | None - timeout in ms
```

### Write

```python
@app.pre_tool("Write")
def check(event):
    event.file_path  # str - path to write
    event.content    # str - file content
```

### Edit

```python
@app.pre_tool("Edit")
def check(event):
    event.file_path   # str - path to edit
    event.old_string  # str - text to find
    event.new_string  # str - replacement text
```

### Read

```python
@app.pre_tool("Read")
def check(event):
    event.file_path  # str - path to read
    event.offset     # int | None - line offset
    event.limit      # int | None - line limit
```

### Grep / Glob

```python
@app.pre_tool("Grep")
def check(event):
    event.pattern  # str - search pattern
    event.path     # str | None - search path
```

## Catch-All Handlers

Use `"*"` or omit the tool name to match all tools:

```python
@app.pre_tool("*")
def log_all(event):
    print(f"Tool: {event.tool_name}")

# Or without argument
@app.pre_tool()
def log_all(event):
    print(f"Tool: {event.tool_name}")
```

## Common Fields

All events have these fields:

```python
event.session_id       # str - session identifier
event.cwd              # str - current working directory
event.permission_mode  # str - default, plan, acceptEdits, bypassPermissions
event.transcript_path  # str | None - path to conversation JSON
```

Tool events also have:

```python
event.tool_name     # str - Bash, Write, Edit, etc.
event.tool_input    # dict - raw input parameters
event.tool_use_id   # str - unique tool call ID
```
