# Responses

Control Claude Code's behavior by returning responses from your handlers.

## Response Types

### allow()

Explicitly allow the action. For PreToolUse, bypasses permission prompts.

```python
from fasthooks import allow

@app.pre_tool("Read")
def allow_docs(event):
    if event.file_path.endswith(".md"):
        return allow()  # Auto-approve reading markdown
```

### deny(reason)

Block the action with a reason shown to Claude.

```python
from fasthooks import deny

@app.pre_tool("Bash")
def no_dangerous(event):
    if "rm -rf" in event.command:
        return deny("Dangerous command blocked")
```

### block(reason)

For Stop/SubagentStop hooks - prevent Claude from stopping.

```python
from fasthooks import block

@app.on_stop()
def ensure_tests(event):
    # Check if tests were run...
    if not tests_passed:
        return block("Please run the tests before stopping")
```

### None (implicit allow)

Return `None` or nothing to allow the action without bypassing permissions.

```python
@app.pre_tool("Bash")
def check(event):
    if is_dangerous(event.command):
        return deny("Blocked")
    # Implicit allow - normal permission flow continues
```

## Response Options

### message

Add a system message shown to the user:

```python
return allow(message="This file is sensitive")
```

### interrupt

Stop Claude entirely (not just block this action):

```python
return deny("Session limit reached", interrupt=True)
```

## Response by Hook Type

| Hook Type | allow() | deny() | block() | None |
|-----------|---------|--------|---------|------|
| PreToolUse | Bypass permission | Block tool | - | Normal flow |
| PostToolUse | - | Feedback to Claude | - | No action |
| PermissionRequest | Auto-approve | Auto-deny | - | Show prompt |
| Stop | Allow stop | - | Prevent stop | Allow stop |

## Examples

### Auto-approve safe commands

```python
@app.pre_tool("Bash")
def auto_approve(event):
    safe_commands = ["ls", "pwd", "echo", "cat"]
    cmd = event.command.split()[0]
    if cmd in safe_commands:
        return allow()
    # Let other commands go through normal permission flow
```

### Block sensitive files

```python
SENSITIVE = [".env", "credentials", "secrets", ".ssh"]

@app.pre_tool("Write")
def protect_sensitive(event):
    for pattern in SENSITIVE:
        if pattern in event.file_path:
            return deny(f"Cannot write to {pattern} files")
```

### Ensure work completion

```python
@app.on_stop()
def check_completion(event):
    if event.stop_hook_active:
        return allow()  # Prevent infinite loop

    # Could check transcript, run tests, etc.
    return block("Please verify all tests pass before stopping")
```
