# Getting Started

Get your first Claude Code hook running in 5 minutes.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Claude Code CLI

## Step 1: Install fasthooks

=== "uv"

    ```bash
    uv add fasthooks
    ```

=== "pip"

    ```bash
    pip install fasthooks
    ```

!!! tip "Want visual debugging?"
    Install with the studio extra to get `fasthooks studio`:
    ```bash
    pip install fasthooks[studio]
    # or
    uv add fasthooks[studio]
    ```

## Step 2: Create a hooks file

```bash
fasthooks init
```

This creates `.claude/hooks.py` with example code:

```python
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
from fasthooks import HookApp, deny

app = HookApp()


@app.pre_tool("Bash")
def check_bash(event):
    """Block dangerous bash commands."""
    if "rm -rf /" in event.command:
        return deny("Blocked dangerous command")


if __name__ == "__main__":
    app.run()
```

## Step 3: Customize your hooks

Edit `.claude/hooks.py` with your own handlers:

```python
from fasthooks import HookApp, deny

app = HookApp()


@app.pre_tool("Bash")
def check_bash(event):
    """Block dangerous bash commands."""
    dangerous = ["rm -rf", "mkfs", "> /dev/"]
    if any(d in event.command for d in dangerous):
        return deny(f"Blocked dangerous command")


@app.pre_tool("Write")
def check_write(event):
    """Protect sensitive files."""
    protected = [".env", "credentials", "secrets"]
    if any(p in event.file_path for p in protected):
        return deny(f"Cannot modify {event.file_path}")


@app.on_stop()
def on_stop(event):
    """Called when Claude finishes."""
    pass  # Add logging, cleanup, etc.


if __name__ == "__main__":
    app.run()
```

## Step 4: Install to Claude Code

```bash
fasthooks install .claude/hooks.py
```

Output:
```
✓ Validated .claude/hooks.py
✓ Found 3 handlers:
    PreToolUse:Bash
    PreToolUse:Write
    Stop
✓ Updated .claude/settings.json
✓ Created .claude/.fasthooks.lock

┌──────────────────────────────────────────────────────────────┐
│ Restart Claude Code to activate hooks.                       │
└──────────────────────────────────────────────────────────────┘
```

## Step 5: Restart Claude Code

**Important:** Claude Code doesn't hot-reload hooks. You must restart it:

```bash
# Exit Claude Code (Ctrl+C or type /exit)
# Then restart
claude
```

Your hooks are now active!

## Verify it's working

Run `fasthooks status` to check:

```
╭──────────────────────────────── Hook Status ─────────────────────────────────╮
│ Project scope (.claude/settings.json)                                        │
│   ✓ Installed: .claude/hooks.py                                              │
│   ✓ Handlers: PreToolUse:Bash, PreToolUse:Write, Stop                        │
│   ✓ Hooks valid                                                              │
│   ✓ Settings in sync                                                         │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## How it works

```
Claude Code → spawns hook → stdin (JSON event) → fasthooks → your handler → response → stdout → Claude Code
```

1. Claude Code triggers an event (e.g., about to run a bash command)
2. It spawns your hooks.py as a subprocess
3. Sends a JSON event to stdin
4. fasthooks routes to your handler based on `@app.pre_tool("Bash")`
5. Your handler returns `deny(reason)` or `None` (allow)
6. fasthooks sends the response to stdout
7. Claude Code applies the decision

## Updating hooks

When you modify `.claude/hooks.py`:

```bash
# Reinstall to pick up new handlers
fasthooks install .claude/hooks.py --force

# Restart Claude Code
```

## Team setup

For team projects, commit your hooks to git:

```bash
git add .claude/hooks.py .claude/settings.json
git commit -m "Add project hooks"
```

Teammates will get the hooks automatically when they pull.

## Next steps

- [Events](tutorial/events.md) - Learn about different event types (`Bash`, `Write`, `Edit`, etc.)
- [Responses](tutorial/responses.md) - Understand `allow()`, `deny()`, `block()`
- [Dependency Injection](tutorial/dependencies.md) - Access `Transcript` and `State`
- [Observability](observability.md) - Trace hook events for debugging
- [Studio](studio.md) - Visual debugger with conversation view
- [CLI Reference](cli.md) - All CLI commands and options
- [Testing](tutorial/testing.md) - Write tests for your hooks
