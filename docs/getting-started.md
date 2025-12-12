# Getting Started

Get your first Claude Code hook running in 5 minutes.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Claude Code CLI

## Create a Hook Project

```bash
fasthooks init my-hooks
cd my-hooks
```

This creates:

```
my-hooks/
├── hooks.py              # Your hook handlers
├── pyproject.toml        # Project dependencies
└── .claude/
    └── settings.json     # Claude Code configuration
```

## Your First Hook

Edit `hooks.py`:

```python
# /// script
# dependencies = ["fasthooks"]
# ///
from fasthooks import HookApp, allow, deny

app = HookApp()

@app.pre_tool("Bash")
def check_bash(event):
    """Block dangerous bash commands."""
    if "rm -rf" in event.command:
        return deny("Dangerous command blocked")
    return allow()

if __name__ == "__main__":
    app.run()
```

## Test Locally

Generate a sample event and test your hook:

```bash
# Generate a dangerous bash event
fasthooks example bash_dangerous > event.json

# Run your hook
fasthooks run hooks.py --input event.json
```

Output:
```json
{"decision": "deny", "reason": "Dangerous command blocked"}
```

Try with a safe command:

```bash
fasthooks example bash > safe.json
fasthooks run hooks.py --input safe.json
```

No output means the command is allowed.

## Configure Claude Code

Copy the generated settings to your project:

```bash
cp .claude/settings.json /path/to/your/project/.claude/
```

Or add to your global Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "uv run /path/to/my-hooks/hooks.py"
          }
        ]
      }
    ]
  }
}
```

## How It Works

1. Claude Code calls your hook via stdin/stdout
2. `app.run()` reads the JSON event from stdin
3. Your handler receives a typed `event` object
4. Return `allow()`, `deny(reason)`, or `None`
5. fasthooks writes the JSON response to stdout

```
Claude Code → stdin (JSON) → fasthooks → handler → response → stdout → Claude Code
```

## Next Steps

- [Events](tutorial/events.md) - Learn about different event types
- [Responses](tutorial/responses.md) - Understand `allow()`, `deny()`, `block()`
- [Testing](tutorial/testing.md) - Write tests for your hooks
