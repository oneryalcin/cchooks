# CLI Reference

fasthooks provides command-line tools for creating and testing hooks.

## Commands

### fasthooks init

Create a new hooks project:

```bash
fasthooks init my-hooks
```

Creates:

```
my-hooks/
├── hooks.py              # Your hook handlers
├── pyproject.toml        # Project dependencies
└── .claude/
    └── settings.json     # Claude Code configuration
```

The generated `hooks.py` includes inline script dependencies for use with `uv run`:

```python
# /// script
# dependencies = ["fasthooks"]
# ///
from fasthooks import HookApp, allow, deny
...
```

### fasthooks run

Run a hooks file:

```bash
# Normal mode (reads from stdin, writes to stdout)
fasthooks run hooks.py

# Test mode with input file
fasthooks run hooks.py --input event.json
```

Options:

| Option | Short | Description |
|--------|-------|-------------|
| `--input` | `-i` | JSON file to use as input instead of stdin |

### fasthooks example

Generate sample event JSON for testing:

```bash
# List available event types
fasthooks example --help

# Generate specific events
fasthooks example bash
fasthooks example bash_dangerous
fasthooks example write
fasthooks example stop
```

Available event types:

| Type | Description |
|------|-------------|
| `bash` | Safe bash command (`echo hello`) |
| `bash_dangerous` | Dangerous command (`rm -rf /`) |
| `write` | Write file event |
| `read` | Read file event |
| `edit` | Edit file event |
| `stop` | Stop event |
| `session_start` | Session start event |
| `pre_compact` | Pre-compact event |
| `permission_bash` | Permission request for bash |
| `permission_write` | Permission request for write |
| `permission_edit` | Permission request for edit |

### fasthooks --help

Show help and available commands:

```bash
fasthooks --help
fasthooks init --help
fasthooks run --help
fasthooks example --help
```

### fasthooks --version

Show version:

```bash
fasthooks --version
```

## Workflow Example

Complete local testing workflow:

```bash
# 1. Create project
fasthooks init my-hooks
cd my-hooks

# 2. Edit hooks.py with your handlers
# ...

# 3. Generate test event
fasthooks example bash_dangerous > event.json

# 4. Test your hook
fasthooks run hooks.py --input event.json
# Output: {"decision": "deny", "reason": "..."}

# 5. Test with safe event
fasthooks example bash > safe.json
fasthooks run hooks.py --input safe.json
# No output = allowed
```
