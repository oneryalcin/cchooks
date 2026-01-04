# Long-Running Agent Strategy

The `LongRunningStrategy` implements Anthropic's two-agent pattern for autonomous agents that work across multiple context windows. It prevents the two common failure modes of long-running agents: **one-shotting** (trying to do everything at once) and **premature victory** (declaring done too early).

> **Live Example**: See a full expense tracker app built autonomously using this strategy:
> [github.com/oneryalcin/fasthooks_example_longrun](https://github.com/oneryalcin/fasthooks_example_longrun)
>
> The repo includes the hooks configuration, Docker setup, and the complete 24-feature app with session history.

## The Problem

Long-running autonomous agents face a fundamental challenge: they work in discrete sessions, and each new session starts with no memory of what came before. This leads to:

1. **One-shotting**: Agent attempts to implement entire project at once, runs out of context mid-implementation, leaves broken state
2. **Premature victory**: Agent sees some progress and declares the project complete despite many features remaining

## The Solution: Two-Agent Pattern

The strategy injects different context for first vs. subsequent sessions:

| Session | Role | Context Injected |
|---------|------|------------------|
| First | **Initializer** | "Create `feature_list.json`, `init.sh`, git repo" |
| Subsequent | **Coding** | "Read progress, work on ONE feature, commit" |

```
Session 1 (Initializer)          Sessions 2+ (Coding)
┌─────────────────────┐          ┌─────────────────────┐
│ Create feature_list │          │ Read progress file  │
│ (30+ features)      │          │ Verify existing     │
│                     │          │ Pick ONE feature    │
│ Create init.sh      │          │ Implement & test    │
│ Initialize git      │          │ Mark passes: true   │
│ First commit        │          │ Commit & update     │
└─────────────────────┘          └─────────────────────┘
```

### Understanding "Two Agents"

**Important:** The "two agents" are NOT two separate systems—they're the same Claude with different context injected based on project state. The term "agent" refers to the *role* Claude plays.

## Architecture: Anthropic vs fasthooks

This strategy implements Anthropic's pattern from their [original article](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), but uses Claude Code hooks instead of a Python script loop.

### Anthropic's Original Approach

```python
# Python script acts as the outer loop
while True:
    client = create_claude_client()  # Fresh context each iteration

    if not feature_list_exists():
        prompt = INITIALIZER_PROMPT
    else:
        prompt = CODING_PROMPT

    await client.query(prompt)
    # Script manages continuation
```

### fasthooks Approach (Hooks-Based)

```python
# Hooks inject context into Claude Code's lifecycle
@app.on_session_start()
def on_session_start(event, state):
    if not feature_list_exists():
        return context(INITIALIZER_PROMPT)
    else:
        return context(CODING_PROMPT)

@app.on_stop()
def on_stop(event, state):
    if not clean_state():
        return block("Commit and update progress first")
```

### Comparison

| Aspect | Anthropic (Script) | fasthooks (Hooks) |
|--------|-------------------|-------------------|
| **Outer loop** | Python `while True` | Claude Code's session lifecycle |
| **Fresh context** | Script creates new client | Claude Code compaction triggers SessionStart |
| **Context injection** | Pass prompt to client | Hook returns `context(...)` |
| **Enforce clean state** | Prompt instructions only | Hook blocks Stop until clean |
| **Browser testing** | Puppeteer MCP | chrome-devtools MCP (headless) |

**Key advantage of hooks**: The `on_stop` hook can *enforce* clean state by blocking, while Anthropic's script relies on prompt instructions alone.

## Quick Start

### 1. Create Your Hooks File

Create `hooks/main.py` (**outside your project workspace**):

```python
#!/usr/bin/env python3
from fasthooks import HookApp
from fasthooks.strategies import LongRunningStrategy

app = HookApp(
    log_dir="/opt/hooks/logs",    # Outside workspace
    state_dir="/opt/hooks/logs",  # Outside workspace
)

strategy = LongRunningStrategy(
    min_features=5,  # Adjust for your project
)

# Optional: Enable observability logging
@strategy.on_observe
def log_events(event):
    with open("/opt/hooks/logs/strategy.log", "a") as f:
        f.write(f"[{event.timestamp}] {event.event_type}: {event.hook_name}\n")

app.include(strategy.get_blueprint())

if __name__ == "__main__":
    app.run()
```

### 2. Configure Claude Code Settings

Add to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [{"type": "command", "command": "python3 /opt/hooks/main.py"}]
      }
    ],
    "Stop": [
      {
        "hooks": [{"type": "command", "command": "python3 /opt/hooks/main.py"}]
      }
    ],
    "PreCompact": [
      {
        "hooks": [{"type": "command", "command": "python3 /opt/hooks/main.py"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [{"type": "command", "command": "python3 /opt/hooks/main.py"}]
      }
    ]
  }
}
```

### 3. Start Claude Code

```bash
cd ~/my-project
claude
```

**First session**: Claude will create `feature_list.json`, `init.sh`, and initialize git.

**Subsequent sessions**: Claude will read progress, verify existing features, and work on one feature at a time.

---

## Critical: Mounting Hooks Correctly

**Claude can modify files in its workspace.** If your hooks are inside the workspace, Claude may delete or modify them to "fix" uncommitted changes errors.

### The Problem

```
workspace/
├── hooks/
│   └── main.py    # ❌ Claude deleted this to fix "uncommitted changes"!
└── src/
```

### The Solution

Mount hooks **outside** the workspace as read-only:

```
/opt/hooks/          # Read-only, Claude can't modify
├── main.py
└── logs/            # Writable for logging

/workspace/          # Claude's workspace
├── src/
└── feature_list.json
```

---

## Docker Deployment (Recommended)

The most reliable way to run LongRunningStrategy is in a Docker container with proper isolation.

### Directory Structure

```
my-strategy-test/
├── Dockerfile
├── docker-compose.yml
├── settings.json          # Claude Code hook settings
├── claude.json            # Claude Code config (onboarding bypass)
├── hooks/
│   ├── main.py            # Your hook script
│   └── logs/              # Generated logs
├── workspace/             # Claude's project directory
└── claude-sessions/       # Persisted Claude transcripts
```

### Dockerfile

```dockerfile
FROM debian:bookworm-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    ripgrep \
    jq \
    python3 \
    python3-pip \
    python3-venv \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Create python alias
RUN ln -s /usr/bin/python3 /usr/bin/python

# Install Node.js 20.x (for frontend projects)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI (for docker compose)
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install Claude Code
RUN curl -fsSL https://claude.ai/install.sh | bash

# Install fasthooks
RUN uv pip install --system --break-system-packages fasthooks

WORKDIR /workspace
RUN mkdir -p /root/.claude

CMD ["/bin/bash"]
```

### docker-compose.yml

```yaml
services:
  claude:
    build: .
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      # Project workspace
      - ./workspace:/workspace

      # Hooks OUTSIDE workspace (read-only, except logs)
      - ./hooks:/opt/hooks:ro
      - ./hooks/logs:/opt/hooks/logs

      # Claude Code configuration
      - ./claude.json:/root/.claude.json
      - ./settings.json:/root/.claude/settings.json

      # Persist session transcripts for analysis
      - ./claude-sessions:/root/.claude/projects

      # Docker socket for docker/docker-compose commands
      - /var/run/docker.sock:/var/run/docker.sock
    stdin_open: true
    tty: true
```

### settings.json

```json
{
  "env": {
    "DISABLE_AUTOUPDATER": "1"
  },
  "permissions": {
    "allow": ["Bash", "Read", "Write", "Edit"]
  },
  "model": "sonnet",
  "hooks": {
    "SessionStart": [
      {
        "hooks": [{"type": "command", "command": "python3 /opt/hooks/main.py"}]
      }
    ],
    "Stop": [
      {
        "hooks": [{"type": "command", "command": "python3 /opt/hooks/main.py"}]
      }
    ],
    "PreCompact": [
      {
        "hooks": [{"type": "command", "command": "python3 /opt/hooks/main.py"}]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [{"type": "command", "command": "python3 /opt/hooks/main.py"}]
      }
    ]
  }
}
```

### hooks/main.py

```python
#!/usr/bin/env python3
"""Long-running agent hooks."""
from fasthooks import HookApp
from fasthooks.strategies import LongRunningStrategy

app = HookApp(
    log_dir="/opt/hooks/logs",
    state_dir="/opt/hooks/logs",
)

strategy = LongRunningStrategy(
    feature_list="feature_list.json",
    progress_file="claude-progress.txt",
    init_script="init.sh",
    min_features=30,
    enforce_commits=True,
    require_progress_update=True,
    exclude_paths=["hooks/", ".claude/"],  # Ignore these in uncommitted check
)

# Log strategy events to file
STRATEGY_LOG = "/opt/hooks/logs/strategy.log"

@strategy.on_observe
def log_events(event):
    with open(STRATEGY_LOG, "a") as f:
        f.write(f"[{event.timestamp}] {event.event_type}: {event.hook_name}\n")
        if hasattr(event, "decision"):
            f.write(f"  decision={event.decision}\n")

app.include(strategy.get_blueprint())

if __name__ == "__main__":
    app.run()
```

### claude.json (Bypass Onboarding)

```json
{
  "numStartups": 5,
  "hasCompletedOnboarding": true,
  "hasSeenStashHint": true,
  "projects": {
    "/workspace": {
      "allowedTools": [],
      "hasTrustDialogAccepted": true,
      "projectOnboardingSeenCount": 3
    }
  }
}
```

### Makefile

```makefile
.PHONY: build run debug shell logs clean

build:
	docker compose build

run:
	docker compose run --rm claude claude

debug:
	docker compose run --rm claude claude --debug

shell:
	docker compose run --rm claude bash

logs:
	tail -f hooks/logs/strategy.log

clean:
	rm -rf workspace/* hooks/logs/*.jsonl hooks/logs/*.log
```

### Running

```bash
# Set your API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# Build the image
make build

# Run Claude Code
make run

# Watch strategy events in another terminal
make logs
```

---

## Browser Testing with Headless Chrome

For frontend projects, Claude can use the `chrome-devtools-mcp` server to interact with a real browser. Running headless Chrome inside the container ensures all network requests stay local (no CORS issues).

### Updated Dockerfile (with Chromium)

```dockerfile
FROM debian:bookworm-slim

# Install system dependencies + Chromium
RUN apt-get update && apt-get install -y \
    curl git ripgrep jq \
    python3 python3-pip python3-venv \
    ca-certificates gnupg \
    chromium chromium-sandbox \
    fonts-liberation libnss3 libatk-bridge2.0-0 \
    libdrm2 libxkbcommon0 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# ... rest of Dockerfile ...

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/bash"]
```

### entrypoint.sh

```bash
#!/bin/bash
# Start headless Chromium with remote debugging
chromium \
  --headless \
  --disable-gpu \
  --no-sandbox \
  --disable-dev-shm-usage \
  --remote-debugging-port=9222 \
  --remote-debugging-address=0.0.0.0 \
  --user-data-dir=/tmp/chrome-profile \
  &

sleep 2
exec "$@"
```

### MCP Configuration (in ~/.claude.json)

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--browser-url=http://localhost:9222"]
    }
  }
}
```

### Port Forwarding for Manual Testing

Expose frontend/backend ports so you can test in your host browser while Claude works:

```yaml
# docker-compose.yml
services:
  claude:
    # ...
    ports:
      - "3000:3000"   # Frontend (Vite/React)
      - "8000:8000"   # Backend (FastAPI)
```

Now you can:
- Claude uses headless Chrome via MCP for automated testing
- You access `http://localhost:3000` in your browser for manual testing

---

## Configuration Options

```python
strategy = LongRunningStrategy(
    # File paths (relative to project root)
    feature_list="feature_list.json",    # Feature tracking file
    progress_file="claude-progress.txt", # Session notes
    init_script="init.sh",               # Environment setup script

    # Requirements
    min_features=30,                     # Minimum features to create

    # Enforcement (blocking behavior)
    enforce_commits=True,                # Block stop if uncommitted changes
    warn_uncommitted=True,               # Warn (not block) if enforce_commits=False
    require_progress_update=True,        # Block stop if progress not updated

    # Paths to exclude from uncommitted changes check
    exclude_paths=["hooks/", ".claude/", ".fasthooks-state/"],
)
```

### Configuration Reference

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `feature_list` | `str` | `"feature_list.json"` | Path to feature tracking file |
| `progress_file` | `str` | `"claude-progress.txt"` | Path to session notes file |
| `init_script` | `str` | `"init.sh"` | Path to environment setup script |
| `min_features` | `int` | `30` | Minimum features agent must create |
| `enforce_commits` | `bool` | `True` | Block stop if uncommitted changes exist |
| `warn_uncommitted` | `bool` | `True` | Warn on uncommitted (when enforce_commits=False) |
| `require_progress_update` | `bool` | `True` | Block stop if progress file not updated |
| `exclude_paths` | `list[str]` | `["hooks/", ".claude/", ...]` | Paths to exclude from uncommitted check |

---

## How It Works

### Hook Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                    Session Lifecycle                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  SessionStart                                               │
│      │                                                      │
│      ▼                                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ on_session_start handler                            │   │
│  │   - Check if feature_list.json exists               │   │
│  │   - If NO: inject INITIALIZER context               │   │
│  │   - If YES: inject CODING context with status       │   │
│  └─────────────────────────────────────────────────────┘   │
│      │                                                      │
│      ▼                                                      │
│  [Claude works on tasks...]                                 │
│      │                                                      │
│      ▼                                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ post_tool:Write handler (on each file write)        │   │
│  │   - Track modified files                            │   │
│  │   - Detect progress_file updates                    │   │
│  │   - Warn on feature_list.json structural changes    │   │
│  └─────────────────────────────────────────────────────┘   │
│      │                                                      │
│      ▼                                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ post_tool:Bash handler (on each bash command)       │   │
│  │   - Track git commits                               │   │
│  └─────────────────────────────────────────────────────┘   │
│      │                                                      │
│      ▼                                                      │
│  [Context fills up OR user stops...]                        │
│      │                                                      │
│      ├──── PreCompact ────────────────────────────────────┐│
│      │  ┌──────────────────────────────────────────────┐  ││
│      │  │ on_pre_compact handler                       │  ││
│      │  │   - Inject checkpoint reminder               │  ││
│      │  │   - Show current status                      │  ││
│      │  └──────────────────────────────────────────────┘  ││
│      │                                                    ││
│      └──── Stop ──────────────────────────────────────────┘│
│         ┌──────────────────────────────────────────────┐   │
│         │ on_stop handler                              │   │
│         │   - Check uncommitted changes → BLOCK        │   │
│         │   - Check progress updated → BLOCK           │   │
│         │   - If clean → ALLOW                         │   │
│         └──────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Key Artifacts

The strategy manages three critical files:

#### 1. `feature_list.json`

Source of truth for what needs to be built:

```json
[
  {
    "category": "functional",
    "description": "User can create new account",
    "steps": [
      "Navigate to signup page",
      "Fill in email and password",
      "Click submit",
      "Verify account created"
    ],
    "passes": false
  },
  {
    "category": "style",
    "description": "Login button has correct styling",
    "steps": [
      "Navigate to login page",
      "Verify button color is primary",
      "Verify button has hover state"
    ],
    "passes": true
  }
]
```

**Rules:**
- Only the `passes` field can be changed
- Never remove or edit features
- Never modify descriptions or steps

#### 2. `claude-progress.txt`

Session-by-session notes for context recovery:

```
## Session 3 - 2024-01-15

Completed:
- Implemented user signup (feature #1)
- Fixed validation bug in email field

In Progress:
- Working on login flow (feature #2)

Status: 5/30 features passing

Next session should:
- Complete login flow
- Start on password reset
```

#### 3. `init.sh`

Environment setup script:

```bash
#!/bin/bash
# Install dependencies
npm install

# Start development server
npm run dev &

echo "Server running at http://localhost:3000"
```

---

## Observability

The strategy emits events for debugging and analysis.

### Enabling Observability

```python
from fasthooks import HookApp
from fasthooks.strategies import LongRunningStrategy

app = HookApp()
strategy = LongRunningStrategy()

# Register observer callback - LOG TO FILE, NOT STDERR
@strategy.on_observe
def log_events(event):
    # WARNING: Do NOT print to stderr - it causes "hook error" in Claude Code
    with open("/opt/hooks/logs/strategy.log", "a") as f:
        f.write(f"[{event.event_type}] {event.hook_name}\n")
        if hasattr(event, 'decision'):
            f.write(f"  Decision: {event.decision}\n")

app.include(strategy.get_blueprint())
```

### Event Types

| Event Type | When Emitted | Payload |
|------------|--------------|---------|
| `hook_enter` | Handler starts | `hook_name` |
| `hook_exit` | Handler ends | `hook_name`, `duration_ms` |
| `decision` | Handler returns allow/deny/block | `decision`, `reason`, `message` |
| `error` | Handler throws exception | `error_type`, `error_message` |
| `custom` | Strategy emits custom event | `custom_event_type`, `payload` |

### Custom Events

The strategy emits these custom events:

| Event | When | Payload |
|-------|------|---------|
| `session_type` | Session start | `{"type": "initializer" \| "coding" \| "compact_resume"}` |
| `feature_progress` | Session start | `{"passing": 5, "total": 30}` |
| `checkpoint_needed` | Pre-compact | `{"reason": "compaction"}` |

---

## Troubleshooting

### "SessionStart:startup hook error"

**Cause:** Usually stderr output from the hook.

**Fix:** Log to file instead of stderr:
```python
# BAD - causes "hook error"
print(f"Debug: {event}", file=sys.stderr)

# GOOD - log to file
with open("/opt/hooks/logs/debug.log", "a") as f:
    f.write(f"Debug: {event}\n")
```

### "Cannot stop - uncommitted changes in: hooks/..."

**Cause:** Hook files are in the workspace and detected as uncommitted.

**Fix:**
1. Mount hooks outside workspace (see Docker Deployment)
2. Or add to `exclude_paths`:
```python
strategy = LongRunningStrategy(
    exclude_paths=["hooks/", ".claude/"]
)
```

### Claude deleted hooks/main.py

**Cause:** Hooks were in the workspace. Claude "fixed" uncommitted changes by deleting them.

**Fix:** Mount hooks as read-only outside workspace:
```yaml
volumes:
  - ./hooks:/opt/hooks:ro          # Read-only!
  - ./hooks/logs:/opt/hooks/logs   # Logs writable
```

### "Cannot stop - please update progress file"

**Fix:** Write to `claude-progress.txt` with your session summary.

**Or disable enforcement:**
```python
strategy = LongRunningStrategy(require_progress_update=False)
```

### Initializer runs every session

The strategy checks for `feature_list.json` existence. If it keeps running initializer:

1. Check that `feature_list.json` exists in the project root
2. Check the file path matches your configuration
3. Check the file is valid JSON

### Context not injected

If hooks aren't being called:

1. Verify settings.json is in the right location
2. Check the command path is correct and executable
3. Run the hook manually to test:
   ```bash
   echo '{"hook_event_name":"SessionStart","session_id":"test","cwd":"/workspace","source":"startup"}' | python3 /opt/hooks/main.py
   ```

---

## Testing the Strategy

### Local Testing with TestClient

```python
from fasthooks import HookApp
from fasthooks.strategies import LongRunningStrategy
from fasthooks.testing import MockEvent, TestClient
import tempfile
import json
from pathlib import Path

# Create temp directory for test
tmpdir = Path(tempfile.mkdtemp())

# Create strategy
strategy = LongRunningStrategy(
    min_features=5,  # Lower for testing
    enforce_commits=False,  # Disable for testing
    require_progress_update=False,
)

# Collect events for verification
events = []
strategy.on_observe(lambda e: events.append(e))

# Create app and client
app = HookApp(state_dir=str(tmpdir))
app.include(strategy.get_blueprint())
client = TestClient(app)

# Test 1: First session (no feature_list.json)
print("Test 1: Initializer mode")
result = client.send(MockEvent.session_start(cwd=str(tmpdir)))
decision_events = [e for e in events if e.event_type == "decision"]
assert any("INITIALIZER" in (e.message or "") for e in decision_events)
print("  ✓ Initializer context injected")

# Test 2: Create feature_list.json and test coding mode
events.clear()
(tmpdir / "feature_list.json").write_text(json.dumps([
    {"description": "Test feature", "passes": False}
]))

print("Test 2: Coding mode")
result = client.send(MockEvent.session_start(cwd=str(tmpdir)))
decision_events = [e for e in events if e.event_type == "decision"]
assert any("0/1 passing" in (e.message or "") for e in decision_events)
print("  ✓ Coding context with status injected")

print("\nAll tests passed!")
```

---

## Reference

### API

```python
class LongRunningStrategy(Strategy):
    """Harness for long-running autonomous agents."""

    def __init__(
        self,
        *,
        feature_list: str = "feature_list.json",
        progress_file: str = "claude-progress.txt",
        init_script: str = "init.sh",
        min_features: int = 30,
        enforce_commits: bool = True,
        warn_uncommitted: bool = True,
        require_progress_update: bool = True,
        exclude_paths: list[str] | None = None,
    ): ...

    def get_blueprint(self) -> Blueprint:
        """Return configured Blueprint with hooks."""
        ...

    def on_observe(self, callback: Callable[[ObservabilityEvent], None]):
        """Register observer callback."""
        ...
```

### Hooks Registered

| Hook | Event | Purpose |
|------|-------|---------|
| `on_session_start` | `SessionStart` | Inject initializer or coding context |
| `on_stop` | `Stop` | Enforce clean state before stopping |
| `on_pre_compact` | `PreCompact` | Inject checkpoint reminder |
| `post_tool("Write")` | `PostToolUse` | Track file creations |
| `post_tool("Edit")` | `PostToolUse` | Track file modifications (Claude uses Edit for updates) |
| `post_tool("Bash")` | `PostToolUse` | Track git commits |

> **Important**: Claude uses the `Edit` tool (shown as "Update" in UI) for file modifications, not `Write`. Make sure your PostToolUse matcher includes `Edit`!

---

## Further Reading

- [Live Example: Expense Tracker built with LongRunningStrategy](https://github.com/oneryalcin/fasthooks_example_longrun) - Full app with hooks config and session history
- [Anthropic: Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) - Original article this strategy implements
