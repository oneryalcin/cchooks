# CLI Reference

The fasthooks CLI helps you create, install, and manage Claude Code hooks.

## Installation

The CLI is included when you install fasthooks:

```bash
pip install fasthooks
# or
uv add fasthooks
```

## Commands

### fasthooks init

Create a new hooks file with boilerplate code.

```bash
fasthooks init [--path PATH] [--force]
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--path` | `-p` | `.claude/hooks.py` | Where to create the hooks file |
| `--force` | `-f` | `false` | Overwrite if file exists |

**Example:**

```bash
# Create default .claude/hooks.py
fasthooks init

# Create in custom location
fasthooks init --path my-hooks.py

# Overwrite existing file
fasthooks init --force
```

**Generated file:**

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


if __name__ == "__main__":
    app.run()
```

---

### fasthooks install

Register your hooks with Claude Code by updating `settings.json`.

```bash
fasthooks install <path> [--scope SCOPE] [--force]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `path` | Yes | Path to your hooks.py file |

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--scope` | `-s` | `project` | Where to install: `project`, `user`, or `local` |
| `--force` | `-f` | `false` | Reinstall even if already installed |

**Example:**

```bash
# Install to project scope (recommended for teams)
fasthooks install .claude/hooks.py

# Install to user scope (personal global hooks)
fasthooks install ~/.my-hooks/hooks.py --scope user

# Install to local scope (personal, not git-tracked)
fasthooks install .claude/hooks.py --scope local

# Reinstall after modifying hooks.py
fasthooks install .claude/hooks.py --force
```

**What it does:**

1. Validates your hooks.py is importable (catches syntax errors)
2. Discovers registered handlers (`@app.pre_tool`, `@app.on_stop`, etc.)
3. Backs up existing settings.json
4. Generates and merges hook configuration
5. Creates a lock file to track the installation

**Output:**

```
✓ Validated .claude/hooks.py
✓ Found 3 handlers:
    PreToolUse:Bash
    PostToolUse:*
    Stop
✓ Backed up .claude/settings.json → .claude/settings.json.bak
✓ Updated .claude/settings.json
✓ Created .claude/.fasthooks.lock

┌──────────────────────────────────────────────────────────────┐
│ Restart Claude Code to activate hooks.                       │
└──────────────────────────────────────────────────────────────┘
```

!!! warning "Restart Required"
    Claude Code does **not** hot-reload hooks. After installing or modifying hooks, you must restart Claude Code (exit and re-run `claude`) for changes to take effect.

---

### fasthooks uninstall

Remove hooks from Claude Code.

```bash
fasthooks uninstall [--scope SCOPE]
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--scope` | `-s` | `project` | Scope to uninstall from |

**Example:**

```bash
# Uninstall from project scope
fasthooks uninstall

# Uninstall from user scope
fasthooks uninstall --scope user
```

**Output:**

```
✓ Found installation in .claude/.fasthooks.lock
✓ Backed up .claude/settings.json → .claude/settings.json.bak
✓ Removed 3 hook entries
✓ Deleted .claude/.fasthooks.lock

┌──────────────────────────────────────────────────────────────┐
│ Restart Claude Code to deactivate hooks.                     │
└──────────────────────────────────────────────────────────────┘
```

---

### fasthooks status

Show installation state and validate hooks.

```bash
fasthooks status [--scope SCOPE]
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--scope` | `-s` | all | Check specific scope, or all if not specified |

**Example:**

```bash
# Check all scopes
fasthooks status

# Check only project scope
fasthooks status --scope project
```

**Output:**

```
╭──────────────────────────────── Hook Status ─────────────────────────────────╮
│ Project scope (.claude/settings.json)                                        │
│   ✓ Installed: .claude/hooks.py                                              │
│   ✓ Installed at: 2024-01-15 10:30:00                                        │
│   ✓ Handlers: PreToolUse:Bash, PostToolUse:*, Stop                           │
│   ✓ Hooks valid                                                              │
│   ✓ Settings in sync                                                         │
│                                                                              │
│ User scope (~/.claude/settings.json)                                         │
│   ✗ Not installed                                                            │
│                                                                              │
│ Local scope (.claude/settings.local.json)                                    │
│   ✗ Not installed                                                            │
╰──────────────────────────────────────────────────────────────────────────────╯
```

**Detects issues:**

- Import errors in hooks.py
- Handlers added/removed since install
- Settings.json out of sync
- Multiple scopes with hooks (warns about conflicts)

---

## Scopes

fasthooks supports three installation scopes:

| Scope | Settings File | Lock File | Use Case |
|-------|--------------|-----------|----------|
| `project` | `.claude/settings.json` | `.claude/.fasthooks.lock` | Team-shared hooks (git-tracked) |
| `user` | `~/.claude/settings.json` | `~/.claude/.fasthooks.lock` | Personal global hooks |
| `local` | `.claude/settings.local.json` | `.claude/.fasthooks.local.lock` | Personal project hooks (gitignored) |

**Choosing a scope:**

- **project** (default): Best for team projects. The settings.json is committed to git, so everyone on the team gets the same hooks.

- **user**: Best for personal productivity hooks you want everywhere. Applied to all projects.

- **local**: Best for personal overrides on a specific project. Not git-tracked, won't affect teammates.

!!! note "Multiple Scopes"
    If hooks are installed in multiple scopes, **all of them run** for each event. Use `fasthooks status` to check which scopes have hooks installed.

---

## Common Workflows

### Setting up hooks for a team project

```bash
# 1. Create hooks file
fasthooks init

# 2. Edit .claude/hooks.py with your handlers
# ...

# 3. Install to project scope (default)
fasthooks install .claude/hooks.py

# 4. Commit to git
git add .claude/hooks.py .claude/settings.json
git commit -m "Add project hooks"

# 5. Restart Claude Code
```

### Adding personal global hooks

```bash
# 1. Create hooks file in your home directory
mkdir -p ~/.my-hooks
fasthooks init --path ~/.my-hooks/hooks.py

# 2. Edit with your personal handlers
# ...

# 3. Install to user scope
fasthooks install ~/.my-hooks/hooks.py --scope user

# 4. Restart Claude Code
```

### Updating hooks after changes

```bash
# 1. Edit your hooks.py
# ...

# 2. Reinstall to update settings.json
fasthooks install .claude/hooks.py --force

# 3. Restart Claude Code
```

### Checking installation status

```bash
# See what's installed across all scopes
fasthooks status

# If handlers changed, resync:
fasthooks install .claude/hooks.py --force
```

---

## Troubleshooting

### "Hooks not running"

1. Did you restart Claude Code after installing?
2. Run `fasthooks status` to check installation
3. Verify handlers are registered: `fasthooks install .claude/hooks.py --force`

### "Import error" during install

Your hooks.py has a syntax error or missing dependency. Fix it and try again:

```bash
# Test your hooks.py directly
python .claude/hooks.py
```

### "Already installed"

Use `--force` to reinstall:

```bash
fasthooks install .claude/hooks.py --force
```

### "Multiple scopes" warning

You have hooks in multiple scopes. This is usually fine, but if you're seeing unexpected behavior:

```bash
# Check what's installed
fasthooks status

# Uninstall from scopes you don't need
fasthooks uninstall --scope local
```

---

## Roadmap

Future CLI commands planned for v2:

| Command | Description |
|---------|-------------|
| `fasthooks show-config` | Output settings.json snippet without writing (for CI/CD, debugging) |
| `fasthooks test` | Run hooks locally with mock events (quick smoke tests) |

**show-config** - Preview what `install` would write:
```bash
fasthooks show-config .claude/hooks.py
# Outputs JSON to stdout, doesn't modify any files
```

**test** - Test handlers without Claude Code:
```bash
fasthooks test .claude/hooks.py --event PreToolUse:Bash --input '{"command": "rm -rf /"}'
# Output: {"decision": "deny", "reason": "Dangerous command blocked"}
```

Have a feature request? [Open an issue](https://github.com/oneryalcin/fasthooks/issues).

---

## Help

```bash
# Show all commands
fasthooks --help

# Show help for a specific command
fasthooks init --help
fasthooks install --help
fasthooks uninstall --help
fasthooks status --help

# Show version
fasthooks --version
```
