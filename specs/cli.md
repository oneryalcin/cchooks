# fasthooks CLI Specification

## Overview

The fasthooks CLI provides a seamless developer experience for managing Claude Code hooks. It handles installation, configuration generation, and lifecycle management.

**What this solves:** Users write hooks with fasthooks' Python API (`@app.pre_tool("Bash")`), but Claude Code expects JSON configuration in settings.json. The CLI bridges this gap by introspecting the Python code and generating the required JSON configuration.

---

## Background: Claude Code Hooks

Claude Code hooks are shell commands that execute at various points in Claude Code's lifecycle. They're configured in settings files and invoked via stdin/stdout JSON protocol.

### How Claude Code Invokes Hooks

1. Claude Code reads hook configuration from settings.json
2. When a hook event occurs, Claude Code spawns the configured command
3. Claude Code writes JSON to the command's stdin
4. The command processes the event and writes JSON response to stdout
5. Claude Code reads the response and acts accordingly (allow, deny, block, etc.)

### Settings File Locations

Claude Code checks multiple settings files in order of precedence:

| Scope | File Path | Git Tracked | Use Case |
|-------|-----------|-------------|----------|
| User | `~/.claude/settings.json` | No | Personal global hooks |
| Project | `.claude/settings.json` | Yes | Team-shared hooks |
| Local | `.claude/settings.local.json` | No (gitignored) | Personal project hooks |

### Settings.json Hook Schema

```json
{
  "hooks": {
    "<EventName>": [
      {
        "matcher": "<ToolPattern>",
        "hooks": [
          {
            "type": "command",
            "command": "<shell-command>",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

**Fields:**
- `EventName`: Hook event type (see table below)
- `matcher`: Tool name pattern (only for tool events). Supports:
  - Exact match: `"Bash"`, `"Write"`
  - Regex: `"Edit|Write"`, `"Notebook.*"`
  - Catch-all: `"*"` or `""` or omitted
- `type`: Always `"command"` for fasthooks
- `command`: Shell command to execute
- `timeout`: Optional, seconds (default: 60)

### Hook Event Types

| Event | Has Matcher | Description |
|-------|-------------|-------------|
| `PreToolUse` | Yes | Before tool executes. Can block. |
| `PostToolUse` | Yes | After tool completes. Can provide feedback. |
| `PermissionRequest` | Yes | When permission dialog shown. Can auto-allow/deny. |
| `Stop` | No | When Claude finishes. Can force continue. |
| `SubagentStop` | No | When subagent finishes. |
| `SessionStart` | No | Session begins. Can inject context. |
| `SessionEnd` | No | Session ends. Cleanup only. |
| `UserPromptSubmit` | No | User submits prompt. Can validate/block. |
| `PreCompact` | No | Before context compaction. |
| `Notification` | Yes | When Claude sends notifications. |

### Environment Variables

Claude Code provides these environment variables to hook commands:

| Variable | Description |
|----------|-------------|
| `CLAUDE_PROJECT_DIR` | Absolute path to project root (where Claude Code started) |
| `CLAUDE_ENV_FILE` | Path for SessionStart hooks to persist env vars |

### Example: Complete settings.json

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "uv run --with fasthooks \"$CLAUDE_PROJECT_DIR/.claude/hooks.py\""
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "uv run --with fasthooks \"$CLAUDE_PROJECT_DIR/.claude/hooks.py\""
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run --with fasthooks \"$CLAUDE_PROJECT_DIR/.claude/hooks.py\""
          }
        ]
      }
    ]
  }
}
```

**Key insight:** The same hooks.py file handles all events. fasthooks routes internally based on `hook_event_name` in the JSON input.

### Hook Input/Output Protocol

**Input (stdin):** Claude Code sends JSON with event data:
```json
{
  "session_id": "abc123",
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {"command": "ls -la"},
  "cwd": "/path/to/project",
  "transcript_path": "~/.claude/projects/.../session.jsonl"
}
```

**Output (stdout):** Hook responds with decision:
```json
{
  "decision": "deny",
  "reason": "Command blocked by policy"
}
```

**Exit codes:**
- 0: Success (stdout parsed as JSON)
- 2: Blocking error (stderr shown to Claude)
- Other: Non-blocking error (logged, execution continues)

### Important Limitation: No Hot Reload

**Claude Code does NOT hot-reload hooks.** After modifying hooks.py or settings.json, the user must restart Claude Code (exit and re-run `claude`) for changes to take effect.

The CLI should remind users of this after install/uninstall.

---

## Design Principles

1. **Explicit over implicit** - Require explicit paths, no magic discovery
2. **Safe by default** - Backup before modify, warn before destructive ops
3. **uv-first** - Embrace modern Python tooling
4. **Minimal v1** - Ship core commands, add more later

### Design Decisions & Rationale

| Decision | Choice | Rationale |
|----------|--------|-----------|
| State tracking | `.fasthooks.lock` file | Enables clean uninstall, status command. Pattern-matching would be fragile. |
| Default scope | Project | Team sharing is common use case. User/local available via flag. |
| Lock follows scope | Yes | Lock should be alongside settings it tracks. |
| Backup strategy | Single .bak file | Simple, covers most recovery cases. Not a full history. |
| Path format | `$CLAUDE_PROJECT_DIR/relative` | Portable across machines, works with team-shared .claude/settings.json. |
| Reinstall behavior | Skip, require --force | Prevents accidental overwrites. Explicit is safer. |
| uv validation | Warn, don't block | User may install uv later. Don't prevent legitimate workflow. |
| CLI deps | Optional `[cli]` extra | Core library stays lightweight. CLI adds typer+rich. |
| Single file composition | Yes | User imports Strategy in hooks.py. Simpler than multi-file merging. |

---

## v1 Command Set

```
fasthooks init              Create hooks.py boilerplate
fasthooks install <path>    Register hooks with Claude Code
fasthooks uninstall         Remove hooks from Claude Code
fasthooks status            Show installation state and validate
```

### Future Commands (v2+)

```
fasthooks show-config       Output settings.json snippet (no write)
fasthooks test              Run hooks with mock events locally
fasthooks update            Re-sync hooks after code changes
```

---

## Commands

### `fasthooks init`

Creates a new hooks.py file with minimal boilerplate.

**Usage:**
```bash
fasthooks init [--path PATH] [--force]
```

**Options:**
- `--path, -p PATH` - Output location (default: `.claude/hooks.py`)
- `--force, -f` - Overwrite existing file

**Behavior:**
1. Check if target file exists, error if so (unless --force)
2. Create parent directories if needed (.claude/)
3. Write boilerplate hooks.py with:
   - PEP 723 script metadata header (for uv run --script)
   - HookApp import and instantiation
   - One example pre_tool handler with comments
   - `if __name__ == "__main__": app.run()` block

**Generated file (.claude/hooks.py):**
```python
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Claude Code hooks for this project.

Usage:
    fasthooks install .claude/hooks.py

After installing, restart Claude Code for hooks to take effect.
"""

from fasthooks import HookApp, deny

app = HookApp()


@app.pre_tool("Bash")
def check_bash(event):
    """Example: block dangerous commands."""
    if "rm -rf /" in event.command:
        return deny("Blocked dangerous command")
    # Return None to allow (default)


# Add more handlers as needed:
# @app.pre_tool("Write")
# @app.post_tool("*")  # catch-all
# @app.on_stop()
# @app.on_session_start()


if __name__ == "__main__":
    app.run()
```

**Why PEP 723:** Enables `uv run --script hooks.py` to automatically install dependencies declared in the header, without requiring a virtual environment or requirements.txt.

---

### `fasthooks install <path>`

Registers hooks with Claude Code by modifying settings.json.

**Usage:**
```bash
fasthooks install <path> [--scope SCOPE] [--force]
```

**Arguments:**
- `<path>` - Path to hooks.py file (required, explicit)

**Options:**
- `--scope, -s SCOPE` - Installation scope: `project` (default), `user`, or `local`
- `--force, -f` - Reinstall even if already installed

**Scopes:**
| Scope | Settings File | Lock File | Use Case |
|-------|--------------|-----------|----------|
| `project` | `.claude/settings.json` | `.claude/.fasthooks.lock` | Team-shared hooks (git tracked) |
| `user` | `~/.claude/settings.json` | `~/.claude/.fasthooks.lock` | Personal global hooks |
| `local` | `.claude/settings.local.json` | `.claude/.fasthooks.local.lock` | Personal project hooks (gitignored) |

**Behavior:**

1. **Validate uv:** Check if `uv` is in PATH. Warn if not (but proceed).
   ```
   ⚠ uv not found in PATH. Hooks may fail at runtime.
     Install: https://docs.astral.sh/uv/getting-started/installation/
   ```

2. **Validate hooks.py exists:** Error if file not found.

3. **Validate hooks.py is importable:**
   - Import the module in a subprocess to avoid polluting current process
   - Catch ImportError, SyntaxError, etc.
   - Error with helpful message if import fails

4. **Introspect registered handlers:**
   - Import hooks.py
   - Find the HookApp instance (look for module-level `app` variable)
   - Extract registered handlers from internal data structures
   - Error if no handlers registered

5. **Check lock file:**
   - If lock exists for this scope and --force not set, skip with message
   - If --force, proceed to reinstall

6. **Backup settings.json:**
   - If settings.json exists, copy to settings.json.bak
   - Overwrite existing .bak (only keep one backup)

7. **Generate hook configuration:**
   - Build command string: `uv run --with fasthooks "$CLAUDE_PROJECT_DIR/<relative-path>"`
   - Group handlers by event type
   - Generate settings.json structure

8. **Merge with existing settings:**
   - Read existing settings.json (or start with `{}`)
   - Merge hook entries (see Merge Strategy below)
   - Write updated settings.json

9. **Write lock file:**
   - Record installation metadata for uninstall/status

10. **Print success message with reminder:**
    ```
    ✓ Hooks installed to .claude/settings.json

    Restart Claude Code to activate hooks.
    ```

**Generated Command Format:**
```
uv run --with fasthooks "$CLAUDE_PROJECT_DIR/.claude/hooks.py"
```

**Why `--with fasthooks`:** Ensures fasthooks package is available even if not in the script's PEP 723 dependencies. Users don't need to add fasthooks to their dependencies list.

**Lock File Format (.fasthooks.lock):**
```json
{
  "version": 1,
  "installed_at": "2024-01-15T10:30:00Z",
  "hooks_path": ".claude/hooks.py",
  "hooks_registered": ["PreToolUse:Bash", "PreToolUse:*", "PostToolUse:*", "Stop"],
  "settings_file": ".claude/settings.json",
  "command": "uv run --with fasthooks \"$CLAUDE_PROJECT_DIR/.claude/hooks.py\""
}
```

**Example session:**
```bash
$ fasthooks install .claude/hooks.py
✓ Validated .claude/hooks.py
✓ Found 4 handlers:
    PreToolUse:Bash
    PreToolUse:*
    PostToolUse:*
    Stop
✓ Backed up .claude/settings.json → .claude/settings.json.bak
✓ Updated .claude/settings.json
✓ Created .claude/.fasthooks.lock

┌────────────────────────────────────────┐
│  Restart Claude Code to activate.      │
└────────────────────────────────────────┘
```

---

### `fasthooks uninstall`

Removes hooks from Claude Code settings.

**Usage:**
```bash
fasthooks uninstall [--scope SCOPE]
```

**Options:**
- `--scope, -s SCOPE` - Scope to uninstall from (default: `project`)

**Behavior:**

1. **Read lock file:** Find lock for specified scope. Error if not found.
   ```
   ✗ No hooks installed in project scope.
     Nothing to uninstall.
   ```

2. **Backup settings.json:** Copy to settings.json.bak

3. **Remove hook entries:**
   - Read settings.json
   - Find and remove entries matching the command from lock file
   - Write updated settings.json

4. **Delete lock file**

5. **Print success message:**
   ```
   ✓ Removed 4 hook entries from .claude/settings.json
   ✓ Deleted .claude/.fasthooks.lock

   Restart Claude Code to deactivate.
   ```

**Example session:**
```bash
$ fasthooks uninstall
✓ Found installation in .claude/.fasthooks.lock
✓ Backed up .claude/settings.json → .claude/settings.json.bak
✓ Removed 4 hook entries
✓ Deleted .claude/.fasthooks.lock

┌────────────────────────────────────────┐
│  Restart Claude Code to deactivate.    │
└────────────────────────────────────────┘
```

---

### `fasthooks status`

Shows installation state and validates hooks.

**Usage:**
```bash
fasthooks status [--scope SCOPE]
```

**Options:**
- `--scope, -s SCOPE` - Specific scope to check (default: checks all scopes)

**Behavior:**

1. For each scope (or specified scope):
   - Check if lock file exists
   - If installed:
     - Show hooks path and installation time
     - Validate hooks.py is still importable
     - List registered handlers
     - Check settings.json contains expected entries
     - Report any discrepancies

**Example output (all scopes):**
```
┌─────────────────────────────────────────────────────────┐
│  Hook Status                                            │
├─────────────────────────────────────────────────────────┤
│  Project scope (.claude/settings.json)                  │
│    ✓ Installed: .claude/hooks.py                        │
│    ✓ Installed at: 2024-01-15 10:30:00                  │
│    ✓ Handlers: PreToolUse:Bash, PostToolUse:*, Stop     │
│    ✓ Settings in sync                                   │
│                                                         │
│  User scope (~/.claude/settings.json)                   │
│    ✗ Not installed                                      │
│                                                         │
│  Local scope (.claude/settings.local.json)              │
│    ✗ Not installed                                      │
└─────────────────────────────────────────────────────────┘
```

**Validation errors:**
```
Project scope (.claude/settings.json):
  ✓ Installed: .claude/hooks.py
  ✗ Import error: ModuleNotFoundError: No module named 'requests'
  ⚠ Settings mismatch: Stop handler not in settings.json
    Run `fasthooks install .claude/hooks.py --force` to resync
```

---

## Configuration Introspection

The install command works by importing hooks.py and examining the HookApp instance to discover registered handlers.

### Finding the HookApp Instance

```python
import importlib.util
import sys
from pathlib import Path

def load_hooks_module(hooks_path: Path):
    """Load hooks.py and return the module."""
    spec = importlib.util.spec_from_file_location("hooks", hooks_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["hooks"] = module
    spec.loader.exec_module(module)
    return module

def find_hookapp(module) -> HookApp | None:
    """Find HookApp instance in module."""
    from fasthooks import HookApp

    # Look for common variable names
    for name in ["app", "hooks", "hook_app", "application"]:
        obj = getattr(module, name, None)
        if isinstance(obj, HookApp):
            return obj

    # Fallback: scan all module attributes
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, HookApp):
            return obj

    return None
```

### Extracting Registered Handlers

```python
def get_registered_hooks(app: HookApp) -> list[str]:
    """
    Returns list of hook identifiers.

    Format:
      - Tool events: "PreToolUse:Bash", "PostToolUse:*"
      - Lifecycle events: "Stop", "SessionStart"
    """
    hooks = []
    bp = app._blueprint

    # Pre-tool handlers
    for tool_name in bp._pre_tool_handlers:
        hooks.append(f"PreToolUse:{tool_name}")

    # Post-tool handlers
    for tool_name in bp._post_tool_handlers:
        hooks.append(f"PostToolUse:{tool_name}")

    # Permission handlers
    for tool_name in bp._permission_handlers:
        hooks.append(f"PermissionRequest:{tool_name}")

    # Lifecycle handlers (Stop, SessionStart, etc.)
    for event_name in bp._lifecycle_handlers:
        # event_name is like "STOP", "SESSION_START"
        # Convert to Claude Code format
        hooks.append(event_name_to_claude_format(event_name))

    return hooks

def event_name_to_claude_format(event_name: str) -> str:
    """Convert internal event name to Claude Code hook event name."""
    mapping = {
        "STOP": "Stop",
        "SESSION_START": "SessionStart",
        "SESSION_END": "SessionEnd",
        "USER_PROMPT_SUBMIT": "UserPromptSubmit",
        "PRE_COMPACT": "PreCompact",
        "NOTIFICATION": "Notification",
        "SUBAGENT_STOP": "SubagentStop",
    }
    return mapping.get(event_name, event_name)
```

### Generating Settings Configuration

```python
def generate_settings(hooks: list[str], command: str) -> dict:
    """
    Generate settings.json hooks configuration.

    Args:
        hooks: List of hook identifiers like "PreToolUse:Bash", "Stop"
        command: Shell command to execute

    Returns:
        Dict ready to merge into settings.json
    """
    settings = {"hooks": {}}

    # Group hooks by event type
    events: dict[str, set[str]] = {}
    for hook in hooks:
        if ":" in hook:
            event, matcher = hook.split(":", 1)
        else:
            event, matcher = hook, None

        if event not in events:
            events[event] = set()
        if matcher:
            events[event].add(matcher)

    # Generate configuration for each event type
    for event, matchers in events.items():
        hook_entry = {
            "type": "command",
            "command": command
        }

        if matchers:
            # Tool event with matchers
            if "*" in matchers:
                # Catch-all: use "*" as matcher
                matcher_str = "*"
            else:
                # Combine with regex OR
                matcher_str = "|".join(sorted(matchers))

            settings["hooks"][event] = [{
                "matcher": matcher_str,
                "hooks": [hook_entry]
            }]
        else:
            # Lifecycle event (no matcher)
            settings["hooks"][event] = [{
                "hooks": [hook_entry]
            }]

    return settings
```

### Merge Strategy

When installing, we need to merge generated hooks with existing settings.json:

```python
def merge_hooks_config(existing: dict, new: dict, our_command: str) -> dict:
    """
    Merge new hooks into existing settings.

    Strategy:
    1. For each event type in new config:
       - Remove any existing entries with our_command (updating)
       - Add our new entries
    2. Preserve entries from other sources (different commands)

    Args:
        existing: Current settings.json content
        new: Generated hooks configuration
        our_command: The command we're installing (for identification)

    Returns:
        Merged settings dict
    """
    result = existing.copy()
    if "hooks" not in result:
        result["hooks"] = {}

    for event_type, new_entries in new.get("hooks", {}).items():
        if event_type not in result["hooks"]:
            result["hooks"][event_type] = []

        # Remove our old entries (if reinstalling)
        result["hooks"][event_type] = [
            entry for entry in result["hooks"][event_type]
            if not any(
                hook.get("command") == our_command
                for hook in entry.get("hooks", [])
            )
        ]

        # Add new entries
        result["hooks"][event_type].extend(new_entries)

        # Clean up empty lists
        if not result["hooks"][event_type]:
            del result["hooks"][event_type]

    # Clean up empty hooks dict
    if not result["hooks"]:
        del result["hooks"]

    return result
```

---

## Path Handling

### Project Root Detection

The project root is the directory where the user runs fasthooks commands. We detect it by looking for common project markers:

```python
def find_project_root(start_path: Path) -> Path:
    """
    Find project root by looking for markers.

    Checks for (in order):
    1. .claude/ directory
    2. .git/ directory
    3. pyproject.toml
    4. package.json

    Falls back to start_path if no marker found.
    """
    current = start_path.resolve()

    while current != current.parent:
        if (current / ".claude").is_dir():
            return current
        if (current / ".git").is_dir():
            return current
        if (current / "pyproject.toml").is_file():
            return current
        if (current / "package.json").is_file():
            return current
        current = current.parent

    return start_path.resolve()
```

### Relative Path Calculation

```python
def make_relative_command(hooks_path: Path, project_root: Path) -> str:
    """
    Generate the hook command with $CLAUDE_PROJECT_DIR.

    Args:
        hooks_path: Absolute path to hooks.py
        project_root: Project root directory

    Returns:
        Command string like: uv run --with fasthooks "$CLAUDE_PROJECT_DIR/.claude/hooks.py"
    """
    relative = hooks_path.relative_to(project_root)
    return f'uv run --with fasthooks "$CLAUDE_PROJECT_DIR/{relative}"'
```

---

## Error Handling

| Scenario | Exit Code | Message |
|----------|-----------|---------|
| hooks.py not found | 1 | `✗ File not found: {path}` |
| hooks.py import error | 1 | `✗ Cannot import {path}: {error}` |
| No HookApp found | 1 | `✗ No HookApp instance found in {path}` |
| No handlers registered | 2 | `✗ No hooks registered in {path}. Add handlers with @app.pre_tool(), @app.on_stop(), etc.` |
| settings.json parse error | 1 | `✗ Invalid JSON in {file}: {error}` |
| Lock file corrupt | - | Warn, proceed as if not installed |
| Already installed | 0 | `Already installed. Use --force to reinstall.` (skip, not error) |
| uv not found | - | Warn only: `⚠ uv not found in PATH` |
| Permission denied | 1 | `✗ Permission denied: {path}` |

---

## Backup Strategy

Before any modification to settings.json:

```python
def backup_settings(settings_path: Path) -> Path | None:
    """
    Create backup of settings file.

    Returns:
        Path to backup file, or None if original didn't exist
    """
    if not settings_path.exists():
        return None

    backup_path = settings_path.with_suffix(".json.bak")
    shutil.copy2(settings_path, backup_path)
    return backup_path
```

Only one backup is kept (the most recent). This is intentional - we're not providing full version history, just a safety net for the last operation.

---

## PEP 723 Integration

[PEP 723](https://peps.python.org/pep-0723/) allows declaring script metadata inline:

```python
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests>=2.28",
#     "pydantic>=2.0",
# ]
# ///
```

**How it works with uv:**
- `uv run --script hooks.py` reads the header and installs deps automatically
- No virtual environment or requirements.txt needed
- Dependencies are cached by uv

**Why we use `--with fasthooks` anyway:**
- Users don't need to add fasthooks to their PEP 723 deps
- Command always works regardless of script header content
- Simpler documentation and fewer user errors

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (or "already installed" skip) |
| 1 | General error (file not found, import error, permission denied) |
| 2 | Validation error (no handlers, invalid config) |

---

## Future Considerations

### show-config (v2)
```bash
fasthooks show-config .claude/hooks.py
```
Outputs the JSON that would be added to settings.json, without modifying anything. Useful for:
- Manual installation
- Debugging configuration issues
- CI/CD pipelines where direct modification isn't wanted

### test (v2)
```bash
fasthooks test .claude/hooks.py --event PreToolUse:Bash --input '{"command": "ls"}'
```
Runs hooks locally with mock event data. Features:
- Simulates Claude Code's stdin/stdout protocol
- Shows response (allow/deny/block) and any messages
- Useful for quick smoke tests without starting Claude Code

### Plugin Generation (future)
```bash
fasthooks plugin init my-hooks-plugin
```
Creates Claude Code plugin structure:
```
my-hooks-plugin/
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   └── hooks.json      # Generated from hooks.py
└── scripts/
    └── hooks.py        # User's fasthooks code
```

For users who want to distribute hooks as shareable plugins.

---

## Implementation Notes

### CLI Framework

**typer + rich** for modern, type-hint based CLI with beautiful output.

```toml
# pyproject.toml
[project.optional-dependencies]
cli = [
    "typer>=0.9.0",
    "rich>=13.0.0",
]
```

Install with CLI support:
```bash
pip install fasthooks[cli]
# or
uv add fasthooks[cli]
```

### Entry Point

```toml
# pyproject.toml
[project.scripts]
fasthooks = "fasthooks.cli:main"
```

**Note:** The entry point requires `fasthooks[cli]` to be installed. If user runs `fasthooks` without CLI deps, show helpful error:

```python
def main():
    try:
        from fasthooks.cli.app import app
        app()
    except ImportError:
        print("CLI dependencies not installed.")
        print("Run: pip install fasthooks[cli]")
        sys.exit(1)
```

### Example Command Implementation

```python
# src/fasthooks/cli/app.py
import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="fasthooks",
    help="Manage Claude Code hooks with ease.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def init(
    path: str = typer.Option(
        ".claude/hooks.py",
        "--path", "-p",
        help="Output path for hooks.py",
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Overwrite existing file",
    ),
):
    """Create a new hooks.py with boilerplate."""
    from fasthooks.cli.commands.init import run_init
    raise SystemExit(run_init(path, force, console))


@app.command()
def install(
    path: str = typer.Argument(..., help="Path to hooks.py"),
    scope: str = typer.Option(
        "project",
        "--scope", "-s",
        help="Installation scope: project, user, or local",
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Reinstall even if already installed",
    ),
):
    """Register hooks with Claude Code."""
    from fasthooks.cli.commands.install import run_install
    raise SystemExit(run_install(path, scope, force, console))


@app.command()
def uninstall(
    scope: str = typer.Option(
        "project",
        "--scope", "-s",
        help="Scope to uninstall from",
    ),
):
    """Remove hooks from Claude Code."""
    from fasthooks.cli.commands.uninstall import run_uninstall
    raise SystemExit(run_uninstall(scope, console))


@app.command()
def status(
    scope: str = typer.Option(
        None,
        "--scope", "-s",
        help="Specific scope to check (default: all)",
    ),
):
    """Show installation state and validate."""
    from fasthooks.cli.commands.status import run_status
    raise SystemExit(run_status(scope, console))


def main():
    app()
```

### Rich Output Patterns

```python
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Success
console.print("[green]✓[/green] Installed hooks to .claude/settings.json")

# Warning
console.print("[yellow]⚠[/yellow] uv not found in PATH")

# Error
console.print("[red]✗[/red] Cannot import hooks.py: ModuleNotFoundError")

# Status table
table = Table(title="Hook Status")
table.add_column("Scope", style="cyan")
table.add_column("Status")
table.add_column("Path")
table.add_row("project", "[green]✓ Installed[/green]", ".claude/hooks.py")
table.add_row("user", "[dim]✗ Not installed[/dim]", "-")
console.print(table)

# Important reminder
console.print(Panel(
    "Restart Claude Code to activate hooks.",
    border_style="blue",
))
```

### Module Structure

```
src/fasthooks/
├── cli/
│   ├── __init__.py       # Exports main()
│   ├── app.py            # typer app definition
│   └── commands/
│       ├── __init__.py
│       ├── init.py       # fasthooks init
│       ├── install.py    # fasthooks install
│       ├── uninstall.py  # fasthooks uninstall
│       └── status.py     # fasthooks status
├── cli_utils/
│   ├── __init__.py
│   ├── introspect.py     # HookApp discovery and handler extraction
│   ├── settings.py       # settings.json read/write/merge
│   ├── lock.py           # Lock file management
│   ├── paths.py          # Project root detection, path handling
│   └── validation.py     # Import validation, uv check
```

---

## Testing the CLI

### Unit Tests

```python
# tests/cli/test_introspect.py
def test_get_registered_hooks():
    """Test handler extraction from HookApp."""
    from fasthooks import HookApp

    app = HookApp()

    @app.pre_tool("Bash")
    def check_bash(event):
        pass

    @app.on_stop()
    def handle_stop(event):
        pass

    hooks = get_registered_hooks(app)
    assert "PreToolUse:Bash" in hooks
    assert "Stop" in hooks
```

### Integration Tests

```python
# tests/cli/test_install.py
def test_install_creates_settings(tmp_path):
    """Test full install flow."""
    # Create hooks.py
    hooks_py = tmp_path / ".claude" / "hooks.py"
    hooks_py.parent.mkdir()
    hooks_py.write_text('''
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass

if __name__ == "__main__":
    app.run()
''')

    # Run install
    result = runner.invoke(app, ["install", str(hooks_py)])
    assert result.exit_code == 0

    # Check settings.json created
    settings = tmp_path / ".claude" / "settings.json"
    assert settings.exists()

    data = json.loads(settings.read_text())
    assert "PreToolUse" in data["hooks"]
```

---

## References

- **Claude Code Hooks Documentation:** See `/private/tmp/strategy-test/hooks.md` and `/private/tmp/strategy-test/hooks-guide.md` for complete Claude Code hooks reference
- **PEP 723 (Inline Script Metadata):** https://peps.python.org/pep-0723/
- **uv Documentation:** https://docs.astral.sh/uv/
- **typer Documentation:** https://typer.tiangolo.com/
- **rich Documentation:** https://rich.readthedocs.io/
