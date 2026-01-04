# Strategy System Specification

## Overview

Strategies are reusable, composable hook patterns that solve common problems. They provide
an abstraction layer above raw hooks, enabling users to adopt proven patterns without
understanding hook internals.

### Prerequisites

This spec assumes familiarity with:
- **fasthooks core**: See `CLAUDE.md` for architecture overview
- **Hooks protocol**: Claude Code invokes hooks at lifecycle points (PreToolUse, Stop, SessionStart, etc.)
- **Blueprint**: Composable handler groups via `app.include(blueprint)`
- **Dependency Injection**: `State` (persistent dict) and `Transcript` (conversation history) injected via type hints
- **Responses**: `allow()` continues execution, `deny(reason)` blocks tool, `block(reason)` prevents stopping

### Key Terms

| Term | Definition |
|------|------------|
| **Strategy** | A class that bundles related hooks with configuration, providing a reusable pattern |
| **Blueprint** | Existing fasthooks construct for grouping handlers - strategies produce blueprints |
| **Hook declaration** | String like `on_stop` or `pre_tool:Write` identifying which hook a strategy uses |
| **State namespace** | Isolated section of State dict for a strategy: `state['strategy-name']['key']` |
| **Entry point** | Python packaging mechanism for plugin discovery (`fasthooks.strategies` group) |

```
┌─────────────────────────────────────────────────────────────────┐
│  Community Strategies (PyPI packages)                           │
│  - pip install fasthooks-longrunning                            │
│  - pip install fasthooks-code-review                            │
│  - pip install git+ssh://github.com/mycompany/internal.git      │
├─────────────────────────────────────────────────────────────────┤
│  Built-in Strategies (fasthooks.strategies)                     │
│  - LongRunningStrategy                                          │
│  - TokenBudgetStrategy                                          │
│  - CleanStateStrategy                                           │
├─────────────────────────────────────────────────────────────────┤
│  Strategy Framework (fasthooks.strategies.base)                 │
│  - Strategy base class                                          │
│  - Entry point discovery, conflict detection                    │
├─────────────────────────────────────────────────────────────────┤
│  Primitives (fasthooks core)                                    │
│  - Transcript, State, Tasks                                     │
│  - Hooks: on_stop, on_prompt, etc.                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Design Decisions

### Core Behavior

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Enforcement model** | Binary (allow/block) | Simplicity over graduated escalation |
| **Hook composition** | Append in order | Simple, predictable, registration order matters |
| **State model** | Own namespace per strategy | Clean separation: `state['strategy_name']['key']` |
| **Compaction handling** | Always inject context | Strategy is authoritative on what context matters |
| **Conflict handling** | Error on conflict | Force user to resolve, no silent surprises |
| **Fail mode** | Strategy declares | `fail_mode='open'` or `fail_mode='closed'` per strategy |

### Configuration

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Config format** | Both Python kwargs and YAML | Programmatic for power users, declarative for simple setups |
| **Manifest format** | Python class attrs (`class Meta`) | Pythonic, IDE support, type-safe |
| **Structure** | Opinionated defaults | Works out-of-box, everything overridable |
| **Schema validation** | Configurable per strategy | Strategy accepts schema config, validates against it |

### Ecosystem

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Distribution** | PyPI + entry points | Standard Python ecosystem, zero custom tooling |
| **Primary usage** | Explicit Python imports | Simple, explicit, no magic discovery |
| **YAML config** | Entry point discovery | Optional, enables declarative configuration |
| **Private strategies** | Git URLs or private PyPI | pip already supports this, no custom infrastructure |
| **Built-ins** | Core essentials (2-3) | Quick start without external installs |

### Testing & Debugging

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Dry-run mode** | Global flag | `--dry-run` or env var, all strategies respect it |
| **Testing tools** | CLI validate + dry-run + unit test helpers | Comprehensive testing support |
| **Diagnostics** | Not needed initially | Avoid premature features, add when users need it |
| **Versioning** | No migration | Strategy handles own state compatibility |

---

## Strategy Base Class

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from fasthooks import Blueprint


@dataclass
class StrategyMeta:
    """Strategy metadata and requirements."""

    name: str
    version: str
    description: str

    # Hook declarations for conflict detection
    hooks: list[str] = field(default_factory=list)
    # e.g., ['on_stop', 'on_session_start', 'pre_tool:Write']

    # Behavior on uncaught exception
    fail_mode: Literal['open', 'closed'] = 'open'

    # State namespace (defaults to strategy name)
    state_namespace: str | None = None


class Strategy(ABC):
    """Base class for fasthooks strategies."""

    class Meta:
        name: str = "unnamed"
        version: str = "0.0.0"
        description: str = ""
        hooks: list[str] = []
        fail_mode: Literal['open', 'closed'] = 'open'

    def __init__(self, **config):
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """Override to validate configuration."""
        pass

    @abstractmethod
    def get_blueprint(self) -> Blueprint:
        """Return configured Blueprint with hooks."""
        raise NotImplementedError

    def get_meta(self) -> StrategyMeta:
        """Return strategy metadata."""
        return StrategyMeta(
            name=self.Meta.name,
            version=self.Meta.version,
            description=self.Meta.description,
            hooks=self.Meta.hooks,
            fail_mode=self.Meta.fail_mode,
        )

    @classmethod
    def from_yaml(cls, path: str) -> 'Strategy':
        """Load configuration from YAML file."""
        import yaml
        with open(path) as f:
            config = yaml.safe_load(f)
        return cls(**config.get(cls.Meta.name, {}))
```

---

## Strategy Registration

### Option 1: Python (Programmatic)

```python
from fasthooks import HookApp
from fasthooks.strategies import LongRunningStrategy

app = HookApp()

# Create strategy with configuration
strategy = LongRunningStrategy(
    feature_list="feature_list.json",
    progress_file="claude-progress.txt",
    enforce_commits=True,
)

# Include the strategy's blueprint
app.include(strategy.get_blueprint())
```

### Option 2: YAML (Declarative)

Create `fasthooks-config.yaml`:

```yaml
# fasthooks-config.yaml
strategies:
  long-running:
    feature_list: feature_list.json
    progress_file: claude-progress.txt
    enforce_commits: true

  token-budget:
    warn_threshold: 100000
    critical_threshold: 150000
```

Load in hooks.py:

```python
from fasthooks import HookApp

app = HookApp()
app.load_strategies_from_yaml("fasthooks-config.yaml")
```

### YAML Loading Implementation

```python
# In HookApp class
def load_strategies_from_yaml(self, path: str) -> None:
    """Load and register strategies from YAML config."""
    import yaml
    from fasthooks.strategies import STRATEGY_REGISTRY

    with open(path) as f:
        config = yaml.safe_load(f)

    for strategy_name, strategy_config in config.get("strategies", {}).items():
        # Look up strategy class by name
        if strategy_name not in STRATEGY_REGISTRY:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        strategy_class = STRATEGY_REGISTRY[strategy_name]
        strategy = strategy_class(**strategy_config)
        self.include(strategy.get_blueprint())

# Strategy registry (populated by built-ins and installed strategies)
STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "long-running": LongRunningStrategy,
    "token-budget": TokenBudgetStrategy,
    "clean-state": CleanStateStrategy,
}
```

---

## Hook Declaration Format

Strategies declare which hooks they use in `Meta.hooks`. The format is:

| Format | Example | Meaning |
|--------|---------|---------|
| Lifecycle hook | `on_stop` | The `@app.on_stop()` decorator |
| Tool hook (specific) | `pre_tool:Bash` | The `@app.pre_tool("Bash")` decorator |
| Tool hook (all) | `post_tool:*` | The `@app.post_tool()` catch-all decorator |

Examples:
```python
class Meta:
    hooks = [
        "on_stop",           # Lifecycle: Stop event
        "on_session_start",  # Lifecycle: SessionStart event
        "on_pre_compact",    # Lifecycle: PreCompact event
        "pre_tool:Bash",     # Tool: Before Bash executes
        "post_tool:Write",   # Tool: After Write completes
        "post_tool:*",       # Tool: After any tool completes
    ]
```

---

## Conflict Detection

### When Conflicts Occur

A conflict occurs when two strategies register hooks for the same event.

**All hook overlaps are treated as conflicts.** This is intentionally strict:
- Prevents unpredictable behavior from multiple handlers
- Easier to reason about than "blocking vs non-blocking" distinction
- Forces explicit resolution at configuration time

**Catch-all hooks (`*`) conflict with specific hooks:**
- `post_tool:*` conflicts with `post_tool:Bash`
- `pre_tool:*` conflicts with `pre_tool:Write`

### Detection Mechanism

```python
class StrategyRegistry:
    """Manages strategy registration and conflict detection."""

    def __init__(self):
        self._hook_owners: dict[str, StrategyMeta] = {}
        self._strategies: list[Strategy] = []

    def register(self, strategy: Strategy) -> None:
        meta = strategy.get_meta()

        for hook in meta.hooks:
            # Check exact match
            if hook in self._hook_owners:
                raise StrategyConflictError(hook, self._hook_owners[hook], meta)

            # Check catch-all conflicts
            if hook.endswith(":*"):
                prefix = hook[:-1]  # "post_tool:"
                for existing_hook in self._hook_owners:
                    if existing_hook.startswith(prefix):
                        raise StrategyConflictError(hook, self._hook_owners[existing_hook], meta)
            else:
                # Check if catch-all already registered
                parts = hook.split(":")
                if len(parts) == 2:
                    catch_all = f"{parts[0]}:*"
                    if catch_all in self._hook_owners:
                        raise StrategyConflictError(hook, self._hook_owners[catch_all], meta)

            self._hook_owners[hook] = meta

        self._strategies.append(strategy)
```

### Error Message

```
StrategyConflictError: Conflict detected!

  Hook: on_stop
  Strategy 1: long-running v1.0.0
  Strategy 2: clean-state v1.0.0

Resolution options:
  1. Remove one strategy from configuration
  2. Configure one strategy to use a different hook
  3. Create a combined strategy that handles both concerns
```

### When Detection Happens

- **At registration time** (when `app.include_strategy(strategy)` is called)
- **Not at runtime** - conflicts are detected before any hooks run

---

## Distribution (PyPI + Entry Points)

Strategies are distributed as standard Python packages via PyPI. No custom package management required.

### Installing Strategies

```bash
# Public strategies from PyPI
pip install fasthooks-longrunning
pip install fasthooks-token-budget

# Private/organizational strategies from git
pip install git+ssh://git@github.com/mycompany/internal-strategy.git

# Or via private PyPI index
pip install --index-url https://pypi.mycompany.com fasthooks-internal
```

### Usage: Explicit Python Imports (Primary)

The simplest and most explicit approach—just import and use:

```python
# hooks.py
from fasthooks import HookApp
from fasthooks_longrunning import LongRunningStrategy  # Standard import

app = HookApp()

# Explicit usage - zero magic
strategy = LongRunningStrategy(enforce_commits=True)
app.include(strategy.get_blueprint())
```

**Why this is preferred:**
- User knows exactly what is loaded (explicit imports)
- No discovery edge cases (packages that crash on import)
- Standard Python patterns

### Usage: YAML Configuration (Optional)

For declarative configuration, strategies can register via entry points:

```toml
# In strategy package's pyproject.toml
[project.entry-points."fasthooks.strategies"]
long-running = "fasthooks_longrunning:LongRunningStrategy"
```

This enables YAML-based configuration:

```yaml
# fasthooks-config.yaml
strategies:
  long-running:
    enforce_commits: true
    feature_list: features.json
```

```python
# hooks.py
from fasthooks import HookApp

app = HookApp()
app.load_strategies_from_yaml("fasthooks-config.yaml")  # Auto-discovers via entry points
```

### Entry Point Discovery Implementation

```python
from importlib.metadata import entry_points

# Strategy registry built from entry points
def discover_strategies() -> dict[str, type[Strategy]]:
    """Discover installed strategies via entry points."""
    eps = entry_points(group="fasthooks.strategies")
    registry = {}
    for ep in eps:
        try:
            registry[ep.name] = ep.load()
        except Exception:
            pass  # Skip broken packages
    return registry

STRATEGY_REGISTRY = discover_strategies()
```

### Creating a Strategy Package

Minimal package structure:

```
fasthooks-mystrategy/
├── pyproject.toml
├── src/
│   └── fasthooks_mystrategy/
│       ├── __init__.py
│       └── strategy.py
└── README.md
```

```toml
# pyproject.toml
[project]
name = "fasthooks-mystrategy"
version = "1.0.0"
dependencies = ["fasthooks>=0.5.0"]

[project.entry-points."fasthooks.strategies"]
my-strategy = "fasthooks_mystrategy:MyStrategy"
```

```python
# src/fasthooks_mystrategy/__init__.py
from .strategy import MyStrategy
__all__ = ["MyStrategy"]
```

### Private/Organizational Strategies

For internal strategies, no special infrastructure needed:

```bash
# Install from private git repo
pip install git+ssh://git@github.com/mycompany/fasthooks-internal.git

# Or use private PyPI (Artifactory, AWS CodeArtifact, etc.)
pip install --index-url https://pypi.internal.mycompany.com fasthooks-internal
```

### Discovery for Humans

For community discovery (not programmatic):
- GitHub topic: `fasthooks-strategy`
- PyPI search: `fasthooks-*`
- Community awesome-list: `awesome-fasthooks`

---

## Built-in Strategies

### TokenBudgetStrategy

Tracks token usage via `Transcript.stats` and injects warnings at thresholds.

```python
from fasthooks.strategies import TokenBudgetStrategy

strategy = TokenBudgetStrategy(
    warn_threshold=100_000,     # Inject notice
    critical_threshold=150_000,  # Inject urgent warning
    emergency_threshold=180_000, # Inject CHECKPOINT NOW
)
```

**Implementation details:**

```python
class TokenBudgetStrategy(Strategy):
    class Meta:
        name = "token-budget"
        hooks = ["post_tool:*"]  # Check after every tool
        fail_mode = "open"

    def get_blueprint(self) -> Blueprint:
        bp = Blueprint("token-budget")

        @bp.post_tool()
        def check_tokens(event, transcript: Transcript):
            # Transcript.stats provides token counts from conversation history
            stats = transcript.stats
            total = stats.input_tokens + stats.output_tokens

            if total >= self.emergency_threshold:
                return allow(message=(
                    "🚨 EMERGENCY: Token limit approaching!\n"
                    f"Used: {total:,} tokens\n"
                    "CHECKPOINT IMMEDIATELY: commit and update progress file."
                ))
            elif total >= self.critical_threshold:
                return allow(message=(
                    f"⚠️ CRITICAL: {total:,} tokens used. Checkpoint soon."
                ))
            elif total >= self.warn_threshold:
                return allow(message=(
                    f"📊 Notice: {total:,} tokens used. Consider checkpointing."
                ))

            return None  # No message needed

        return bp
```

**How token counting works:**

`Transcript.stats` is computed from the conversation history:
- `input_tokens`: Sum of all input tokens from assistant messages
- `output_tokens`: Sum of all output tokens from assistant messages
- These are extracted from the `usage` field in each assistant message

### CleanStateStrategy

Ensures clean state before session ends.

```python
from fasthooks.strategies import CleanStateStrategy

strategy = CleanStateStrategy(
    require_files=["README.md"],  # Block stop if missing
    check_uncommitted=True,        # Block stop if git dirty
)
```

**Implementation details:**

```python
class CleanStateStrategy(Strategy):
    class Meta:
        name = "clean-state"
        hooks = ["on_stop"]
        fail_mode = "closed"  # Fail closed = block if strategy errors

    def get_blueprint(self) -> Blueprint:
        bp = Blueprint("clean-state")

        @bp.on_stop()
        def enforce_clean(event):
            issues = []
            project_dir = Path(event.cwd)

            # Check required files
            for f in self.require_files:
                if not (project_dir / f).exists():
                    issues.append(f"Missing required file: {f}")

            # Check uncommitted changes
            if self.check_uncommitted:
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True, text=True, cwd=project_dir
                )
                if result.returncode == 0 and result.stdout.strip():
                    issues.append("Uncommitted changes exist")

            if issues:
                return block(
                    "Cannot stop - clean state required:\n" +
                    "\n".join(f"- {i}" for i in issues)
                )

            return allow()

        return bp
```

---

## Long-Running Agent Strategy

### Background: The Problem

Long-running autonomous agents face challenges when working across multiple context windows:

1. **One-shotting**: Agent tries to implement entire project at once, runs out of context mid-implementation, leaves broken state
2. **Premature victory**: Agent sees some progress and declares the project complete
3. **Context loss**: After compaction or new session, agent doesn't know what happened before
4. **Dirty state**: Agent stops with uncommitted changes, broken tests, or undocumented progress

### The Two-Agent Pattern (from Anthropic)

Anthropic's solution uses two specialized prompts:

1. **Initializer Agent** (first session only):
   - Creates `feature_list.json` with 200+ features, all marked `passes: false`
   - Creates `init.sh` script to set up development environment
   - Creates `claude-progress.txt` for session summaries
   - Initializes git repository

2. **Coding Agent** (all subsequent sessions):
   - Reads progress file and git log to understand current state
   - Works on ONE feature at a time
   - Tests thoroughly before marking feature as passing
   - Commits progress with descriptive messages
   - Updates progress file before stopping

This strategy implements this pattern via fasthooks hooks, running inside standard Claude Code
rather than a custom agent harness.

### Hook Events Used

| Hook | Purpose | When Fired by Claude Code |
|------|---------|---------------------------|
| `on_session_start` | Inject context (initializer or coding instructions) | Session starts or resumes after compact |
| `on_stop` | Enforce clean state before stopping | Claude attempts to stop |
| `on_pre_compact` | Preserve critical state before context compaction | Before Claude Code compacts context |
| `post_tool("Write")` | Track file modifications | After any Write tool completes |
| `post_tool("Bash")` | Track git commits | After any Bash tool completes |

### SessionStart Event Details

The `event.source` field indicates why session started:
- `"startup"`: Fresh session start (user ran Claude Code)
- `"compact"`: Session resumed after context compaction
- `"resume"`: Session resumed from previous (less common)

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Session boundary** | Claude Code session_id | Natural boundary, user may resume |
| **Context limit** | Inject urgent warning | Advise but don't force action |
| **Git integration** | Deep integration | Check status, suggest commits |
| **Feature list rules** | Post-hoc warning | Allow changes but discourage structural modifications |
| **Context verbosity** | Summary (10-20 lines) | Key info: status, recent commits, current task |
| **Project structure** | Opinionated defaults | Works out-of-box, all paths configurable |

### Implementation

```python
class LongRunningStrategy(Strategy):
    """
    Harness for long-running autonomous agents.

    Implements the two-agent pattern:
    - Initializer: First run sets up feature_list.json, init.sh, git
    - Coding: Subsequent runs make incremental progress
    """

    class Meta:
        name = "long-running"
        version = "1.0.0"
        description = "Harness for long-running autonomous agents"
        hooks = [
            "on_session_start",
            "on_stop",
            "on_pre_compact",
            "post_tool:Write",
            "post_tool:Bash",
        ]
        fail_mode = "open"  # Don't break user workflow on strategy errors

    # Default file paths (all configurable)
    DEFAULT_FEATURE_LIST = "feature_list.json"
    DEFAULT_PROGRESS_FILE = "claude-progress.txt"
    DEFAULT_INIT_SCRIPT = "init.sh"

    def __init__(
        self,
        *,
        feature_list: str = DEFAULT_FEATURE_LIST,
        progress_file: str = DEFAULT_PROGRESS_FILE,
        init_script: str = DEFAULT_INIT_SCRIPT,
        enforce_commits: bool = True,
        warn_uncommitted: bool = True,
        feature_schema: dict | None = None,
        token_warn_threshold: int = 150_000,
    ):
        self.feature_list = feature_list
        self.progress_file = progress_file
        self.init_script = init_script
        self.enforce_commits = enforce_commits
        self.warn_uncommitted = warn_uncommitted
        self.feature_schema = feature_schema or self.DEFAULT_SCHEMA
        self.token_warn_threshold = token_warn_threshold

    DEFAULT_SCHEMA = {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["description", "passes"],
            "properties": {
                "category": {"type": "string"},
                "description": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
                "passes": {"type": "boolean"},
            }
        }
    }

    def get_blueprint(self) -> Blueprint:
        bp = Blueprint("long-running")

        @bp.on_session_start()
        def on_session_start(event, state: State):
            return self._handle_session_start(event, state)

        @bp.on_stop()
        def on_stop(event, state: State):
            return self._handle_stop(event, state)

        @bp.on_pre_compact()
        def on_pre_compact(event, state: State, transcript: Transcript):
            return self._handle_pre_compact(event, state, transcript)

        @bp.post_tool("Write")
        def post_write(event, state: State):
            return self._track_write(event, state)

        @bp.post_tool("Bash")
        def post_bash(event, state: State):
            return self._track_bash(event, state)

        return bp
```

### Session Start Handler

```python
def _handle_session_start(self, event, state: State) -> HookResponse:
    """Route to initializer or coding agent context."""
    project_dir = Path(event.cwd)
    feature_list = project_dir / self.feature_list

    # Initialize strategy state namespace
    ns = state.setdefault(self.Meta.name, {})
    ns["session_count"] = ns.get("session_count", 0) + 1
    ns["files_modified"] = []
    ns["commits_made"] = []
    ns["progress_updated"] = False
    state.save()

    if event.source == "startup":
        if not feature_list.exists():
            return allow(message=self._get_initializer_context())
        else:
            return allow(message=self._get_coding_context(project_dir, ns))
    else:  # compact
        return allow(message=self._get_compact_context(project_dir, ns))

def _get_coding_context(self, project_dir: Path, ns: dict) -> str:
    """Build 10-20 line summary for coding agent."""
    lines = ["## Session Context (Long-Running Agent)"]

    # Feature status
    passing, total = self._count_features(project_dir)
    lines.append(f"- Features: {passing}/{total} passing")

    # Recent git commits
    commits = self._get_recent_commits(project_dir, limit=5)
    if commits:
        lines.append(f"- Recent commits:")
        for c in commits[:3]:
            lines.append(f"  - {c}")

    # Progress file summary
    progress = self._read_progress(project_dir)
    if progress:
        lines.append(f"- Last session: {progress[:100]}...")

    # Current task (if tracked)
    if current := ns.get("current_feature"):
        lines.append(f"- In progress: {current}")

    lines.append("")
    lines.append("Remember: Work on ONE feature at a time. Commit before stopping.")

    return "\n".join(lines)
```

### Stop Handler

```python
def _handle_stop(self, event, state: State) -> HookResponse:
    """Enforce clean state before stopping."""
    project_dir = Path(event.cwd)
    ns = state.get(self.Meta.name, {})
    issues = []

    # Check uncommitted changes
    if self.enforce_commits:
        if uncommitted := self._check_uncommitted(project_dir):
            issues.append(f"Uncommitted changes in: {', '.join(uncommitted[:5])}")

    # Check progress file updated
    if not ns.get("progress_updated"):
        issues.append(f"Please update {self.progress_file} with session summary")

    if issues:
        return block(
            "Cannot stop - please address:\n" +
            "\n".join(f"- {i}" for i in issues)
        )

    return allow()
```

### Feature List Validation

```python
def _track_write(self, event, state: State) -> HookResponse | None:
    """Track writes, warn on feature_list.json structural changes."""
    ns = state.get(self.Meta.name, {})
    ns.setdefault("files_modified", []).append(event.file_path)

    # Use pathlib for reliable path comparison
    if Path(event.file_path).name == Path(self.feature_list).name:
        # Check if structural change (not just passes field)
        if self._is_structural_change(event):
            return allow(message=(
                "WARNING: You modified the structure of feature_list.json.\n"
                "Only the 'passes' field should be changed. "
                "Consider reverting structural changes."
            ))

    if Path(event.file_path).name == Path(self.progress_file).name:
        ns["progress_updated"] = True

    state.save()
    return None
```

### Initializer Context (First Session)

When no `feature_list.json` exists, inject instructions to set up the project:

```python
INITIALIZER_PROMPT = """
## YOUR ROLE - INITIALIZER AGENT (First Session)

You are setting up a long-running autonomous project. Create these artifacts:

### 1. feature_list.json
Create a comprehensive list of features with this structure:
```json
[
  {
    "category": "functional",
    "description": "User can create new chat",
    "steps": ["Navigate to app", "Click new chat", "Verify empty state"],
    "passes": false
  }
]
```
- Minimum 50 features (more for complex projects)
- All features start with `"passes": false`
- Order by priority (foundational features first)

### 2. init.sh
Script to set up and run the development environment.

### 3. claude-progress.txt
Empty file for session summaries.

### 4. Git Repository
Initialize git and make first commit with all artifacts.

After setup, you may begin implementing the first feature.
"""

def _get_initializer_context(self) -> str:
    return INITIALIZER_PROMPT
```

### Compact Context (After Compaction)

When session resumes after compaction, inject minimal recovery context:

```python
def _get_compact_context(self, project_dir: Path, ns: dict) -> str:
    """Minimal context after compaction."""
    passing, total = self._count_features(project_dir)

    return f"""
## Context Restored After Compaction

- Features: {passing}/{total} passing
- Session #{ns.get('session_count', '?')}
- Files modified this session: {len(ns.get('files_modified', []))}

Read `claude-progress.txt` and `git log` for full context.
Continue with current task or pick next feature from feature_list.json.
"""
```

### Helper Methods (Complete Implementation)

```python
import subprocess
import json
from pathlib import Path

def _count_features(self, project_dir: Path) -> tuple[int, int]:
    """Count passing/total features in feature_list.json."""
    feature_file = project_dir / self.feature_list
    if not feature_file.exists():
        return 0, 0

    try:
        features = json.loads(feature_file.read_text())
        total = len(features)
        passing = sum(1 for f in features if f.get("passes", False))
        return passing, total
    except (json.JSONDecodeError, IOError):
        return 0, 0

def _get_recent_commits(self, project_dir: Path, limit: int = 5) -> list[str]:
    """Get recent git commit messages."""
    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-{limit}"],
            capture_output=True, text=True, cwd=project_dir
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")
    except Exception:
        pass
    return []

def _read_progress(self, project_dir: Path) -> str:
    """Read last entry from progress file."""
    progress_file = project_dir / self.progress_file
    if not progress_file.exists():
        return ""

    try:
        content = progress_file.read_text()
        # Return last paragraph (most recent session)
        paragraphs = content.strip().split("\n\n")
        return paragraphs[-1] if paragraphs else ""
    except IOError:
        return ""

def _check_uncommitted(self, project_dir: Path) -> list[str]:
    """Return list of uncommitted files, empty if clean."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=project_dir
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse "M  file.py" format, return file names
            lines = result.stdout.strip().split("\n")
            return [line[3:].strip() for line in lines if line]
    except Exception:
        pass
    return []

def _is_structural_change(self, event) -> bool:
    """Check if feature_list.json change modified structure (not just passes)."""
    # Compare old vs new content
    # This requires reading the file before and after, or analyzing the diff
    # Simplified: check if any key other than 'passes' was in the written content
    try:
        new_content = event.content  # The content written
        features = json.loads(new_content)

        # Load previous version from git
        project_dir = Path(event.cwd)
        result = subprocess.run(
            ["git", "show", f"HEAD:{self.feature_list}"],
            capture_output=True, text=True, cwd=project_dir
        )
        if result.returncode != 0:
            return False  # No previous version, can't compare

        old_features = json.loads(result.stdout)

        # Compare: same count, same descriptions, only passes changed
        if len(features) != len(old_features):
            return True  # Count changed = structural

        for new, old in zip(features, old_features):
            # Check if anything other than 'passes' changed
            for key in set(new.keys()) | set(old.keys()):
                if key == "passes":
                    continue
                if new.get(key) != old.get(key):
                    return True  # Structural change

        return False  # Only passes changed
    except Exception:
        return False  # Can't determine, assume ok

def _track_bash(self, event, state: State) -> HookResponse | None:
    """Track git commits."""
    ns = state.get(self.Meta.name, {})

    # Check if this was a git commit
    if event.command.startswith("git commit"):
        ns.setdefault("commits_made", []).append(event.command)
        state.save()

    return None

def _handle_pre_compact(self, event, state: State, transcript: Transcript) -> HookResponse:
    """Inject state summary before compaction."""
    ns = state.get(self.Meta.name, {})
    project_dir = Path(event.cwd)
    passing, total = self._count_features(project_dir)

    summary = f"""
## COMPACTION CHECKPOINT

Before context is compacted, note:
- Features: {passing}/{total} passing
- Files modified: {ns.get('files_modified', [])}
- Commits made: {len(ns.get('commits_made', []))}

If you have uncommitted work, commit NOW before compaction.
Update {self.progress_file} with current status.
"""
    return allow(message=summary)
```

---

## CLI Commands

### Strategy Management

```bash
# Validate strategy configuration
fasthooks validate-strategy long-running --config fasthooks-config.yaml

# Dry-run against sample transcript
fasthooks dry-run --strategy long-running --sample samples/coding-session.jsonl

# Run with dry-run mode (global)
fasthooks run hooks.py --dry-run
```

---

## Testing Support

### Unit Test Helpers

```python
from fasthooks.testing import StrategyTestClient
from fasthooks.strategies import LongRunningStrategy

def test_long_running_blocks_without_commit():
    strategy = LongRunningStrategy(enforce_commits=True)
    client = StrategyTestClient(strategy)

    # Simulate session with uncommitted changes
    client.setup_git_state(uncommitted=["file.py"])

    response = client.trigger_stop()

    assert response.decision == "block"
    assert "uncommitted" in response.reason.lower()


def test_long_running_injects_context():
    strategy = LongRunningStrategy()
    client = StrategyTestClient(strategy)

    # Setup project with feature list
    client.setup_file("feature_list.json", '[{"passes": false}]')

    response = client.trigger_session_start(source="startup")

    assert "0/1 passing" in response.message
```

### Dry-Run Mode

When `--dry-run` is active:

```python
class Strategy:
    def _execute_hook(self, hook_name: str, *args, **kwargs):
        result = self._hooks[hook_name](*args, **kwargs)

        if os.environ.get("FASTHOOKS_DRY_RUN"):
            # Log what would happen, but return allow()
            logger.info(f"[DRY-RUN] {hook_name} would return: {result}")
            return allow()

        return result
```

---

## Migration Path

### Phase 1: Framework + Long-Running ✅

1. Implement `Strategy` base class ✅
2. Implement `LongRunningStrategy` as first concrete strategy ✅
3. Add `fasthooks.strategies` module with both ✅
4. Add observability module ✅

### Phase 2: Testing & Built-ins ✅

1. Add tests for Strategy base class and LongRunningStrategy ✅
2. Add tests for observability module ✅
3. Implement `TokenBudgetStrategy` built-in ✅
4. Implement `CleanStateStrategy` built-in ✅
5. Add conflict detection at registration time ✅

### Phase 3: YAML Config & Entry Points ❌ DEFERRED

Not implementing - Python API is sufficient. The complexity of YAML config
and entry point discovery is not justified by the minimal benefit.

### Phase 4: Documentation & Community ✅

1. Strategy docs in `docs/strategies/index.md` ✅
2. Creating strategies guide in `docs/strategies/index.md` ✅
3. LongRunningStrategy guide in `docs/strategies/long-running.md` ✅

### Future Work

- **App-level observability** (`@app.on_observe`) - central callback for all strategies
- **fail_mode enforcement** - currently metadata-only, errors raise exceptions

---

## Observability System

### Overview

Strategies emit observable events that enable debugging, analysis, and improvement.
The system is designed for both human debugging and LLM analysis.

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Granularity** | Hook + decisions | Log hook entry, exit, and decision. Good balance. |
| **Data format** | Dual format | Structured JSON for LLMs, human-readable views on top |
| **Backend pattern** | Callback-based | Simple `on_event(callback)`. Users wire to anything. |
| **Data location** | Per-session files | `~/.fasthooks/observability/<session-id>.jsonl` |
| **Data richness** | Configurable verbosity | minimal/standard/verbose levels |
| **Correlation** | Request-scoped | `session_id` + `request_id` per hook invocation |
| **Error handling** | Log error event | Emit error with exception details |
| **Write mode** | Async with flush | Queue events, flush on session end |
| **Custom events** | Typed in Meta | Strategies declare custom event types |
| **Activation** | Default on, opt-out | Good defaults, respects choice |
| **File format** | Append-only JSONL | Simple, streamable |
| **Timing** | Hook duration | Track ms per hook invocation |
| **Terminal output** | Configurable levels | quiet/normal/verbose |
| **Registration** | Both scopes | App-level + per-strategy callbacks |
| **Default backend** | Auto with override | File logging works out-of-box |
| **Retention** | User manages | No auto-cleanup |

---

### Event Model (Pydantic v2)

```python
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field
import uuid


class ObservabilityEvent(BaseModel):
    """Base event emitted by observability system."""

    # Correlation
    session_id: str
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Timing
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: float | None = None  # Set on hook_exit

    # Event type
    event_type: Literal[
        "hook_enter",
        "hook_exit",
        "decision",
        "error",
        "custom",
    ]

    # Context
    strategy_name: str
    hook_name: str  # e.g., "on_stop", "pre_tool:Bash"

    # Payload (verbosity-dependent)
    payload: dict[str, Any] = Field(default_factory=dict)

    # For custom events
    custom_event_type: str | None = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class DecisionEvent(ObservabilityEvent):
    """Emitted when strategy returns a decision."""

    event_type: Literal["decision"] = "decision"
    decision: Literal["allow", "deny", "block"]
    reason: str | None = None
    message: str | None = None  # Injected message


class ErrorEvent(ObservabilityEvent):
    """Emitted when strategy throws an exception."""

    event_type: Literal["error"] = "error"
    error_type: str  # Exception class name
    error_message: str
    traceback: str | None = None  # Only in verbose mode
```

---

### Verbosity Levels

```python
from enum import Enum

class Verbosity(Enum):
    MINIMAL = "minimal"    # Just decisions and errors
    STANDARD = "standard"  # Hook enter/exit + decisions + errors
    VERBOSE = "verbose"    # Full payload, tracebacks, timing details
```

**What each level includes:**

| Event | Minimal | Standard | Verbose |
|-------|---------|----------|---------|
| `hook_enter` | ❌ | ✅ | ✅ + full event payload |
| `hook_exit` | ❌ | ✅ | ✅ + duration_ms |
| `decision` | ✅ | ✅ | ✅ + relevant transcript context |
| `error` | ✅ | ✅ | ✅ + full traceback |
| `custom` | ❌ | ✅ | ✅ + full payload |

---

### Callback Registration

```python
from fasthooks import HookApp
from fasthooks.strategies import LongRunningStrategy
from fasthooks.observability import ObservabilityEvent

app = HookApp()

# App-level callback: receives ALL strategy events
@app.on_observe
def log_to_external(event: ObservabilityEvent):
    # Send to DataDog, Sentry, custom backend, etc.
    requests.post("https://my-backend.com/events", json=event.model_dump())

# Strategy-level callback: receives only this strategy's events
strategy = LongRunningStrategy()

@strategy.on_observe
def log_long_running(event: ObservabilityEvent):
    print(f"[{strategy.Meta.name}] {event.event_type}: {event.hook_name}")

app.include(strategy.get_blueprint())
```

---

### Default File Backend

Automatically writes to `~/.fasthooks/observability/<session-id>.jsonl`:

```python
class FileObservabilityBackend:
    """Default backend that writes JSONL per session."""

    def __init__(
        self,
        base_dir: Path = Path.home() / ".fasthooks" / "observability",
        verbosity: Verbosity = Verbosity.STANDARD,
    ):
        self.base_dir = base_dir
        self.verbosity = verbosity
        self._queue: list[ObservabilityEvent] = []
        self._current_session: str | None = None
        self._file: IO | None = None

    def handle_event(self, event: ObservabilityEvent) -> None:
        """Queue event for async write."""
        if self._should_include(event):
            self._queue.append(event)

    def _should_include(self, event: ObservabilityEvent) -> bool:
        """Filter based on verbosity level."""
        if self.verbosity == Verbosity.MINIMAL:
            return event.event_type in ("decision", "error")
        elif self.verbosity == Verbosity.STANDARD:
            return True  # All events
        else:  # VERBOSE
            return True

    def flush(self) -> None:
        """Write queued events to file."""
        if not self._queue:
            return

        session_id = self._queue[0].session_id
        file_path = self.base_dir / f"{session_id}.jsonl"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "a") as f:
            for event in self._queue:
                f.write(event.model_dump_json() + "\n")

        self._queue.clear()
```

---

### Disabling/Overriding Default Backend

```python
from fasthooks import HookApp
from fasthooks.observability import Verbosity

# Disable file backend entirely
app = HookApp(observability=False)

# Override verbosity
app = HookApp(observability_verbosity=Verbosity.VERBOSE)

# Replace with custom backend only
app = HookApp(observability=False)

@app.on_observe
def my_custom_backend(event):
    ...  # Your implementation
```

---

### Custom Events from Strategies

Strategies can emit custom events by declaring them in Meta:

```python
class LongRunningStrategy(Strategy):
    class Meta:
        name = "long-running"
        hooks = ["on_stop", "on_session_start"]
        custom_events = [
            "feature_started",   # When work begins on a feature
            "feature_completed", # When feature marked as passing
            "checkpoint_needed", # When strategy detects checkpoint needed
        ]

    def _handle_session_start(self, event, state):
        # Emit custom event
        self.emit_event("feature_started", {
            "feature_id": 42,
            "feature_name": "user-login",
        })
```

Implementation:

```python
class Strategy:
    def emit_event(self, event_type: str, payload: dict) -> None:
        """Emit a custom observability event."""
        if event_type not in self.Meta.custom_events:
            raise ValueError(f"Undeclared custom event: {event_type}")

        event = ObservabilityEvent(
            session_id=self._current_session_id,
            request_id=self._current_request_id,
            event_type="custom",
            custom_event_type=event_type,
            strategy_name=self.Meta.name,
            hook_name=self._current_hook,
            payload=payload,
        )
        self._emit_to_callbacks(event)
```

---

### Terminal Output

Real-time terminal output with configurable levels:

```python
class TerminalOutput(Enum):
    QUIET = "quiet"    # No output
    NORMAL = "normal"  # Show blocks/denies only
    VERBOSE = "verbose"  # Show all decisions
```

Example output (NORMAL level):
```
[long-running] BLOCK on_stop: Uncommitted changes in: file.py
[token-budget] ALLOW post_tool:Write: ⚠️ 150K tokens used
```

Example output (VERBOSE level):
```
[long-running] ENTER on_session_start (source=startup)
[long-running] ALLOW on_session_start: Injected coding context (45/200 features)
[long-running] EXIT on_session_start (12ms)
...
```

Configuration:
```python
app = HookApp(terminal_output=TerminalOutput.NORMAL)
```

---

### Markdown Summary Generation

Generate human-readable session summary for post-session review:

```python
from fasthooks.observability import generate_session_summary

# After session ends
summary = generate_session_summary(session_id="abc123")
print(summary)
```

Output (`~/.fasthooks/observability/abc123.md`):
```markdown
# Session Summary: abc123

**Duration**: 45 minutes
**Strategies**: long-running, token-budget

## Timeline

| Time | Strategy | Event | Details |
|------|----------|-------|---------|
| 10:00:00 | long-running | ALLOW | Injected coding context |
| 10:15:32 | token-budget | ALLOW | Notice: 100K tokens |
| 10:30:45 | long-running | BLOCK | Uncommitted changes |
| 10:31:02 | long-running | ALLOW | Clean state confirmed |

## Decisions

- **Allows**: 12
- **Blocks**: 1
- **Denies**: 0
- **Errors**: 0

## Errors

None

## Custom Events

- `feature_completed`: 3 times
```

---

### Integration with Strategy Base Class

```python
class Strategy(ABC):
    """Base class with observability built-in."""

    def __init__(self, **config):
        self.config = config
        self._observers: list[Callable] = []
        self._current_session_id: str | None = None
        self._current_request_id: str | None = None
        self._current_hook: str | None = None

    def on_observe(self, callback: Callable[[ObservabilityEvent], None]):
        """Register strategy-level observer."""
        self._observers.append(callback)
        return callback

    def _emit_to_callbacks(self, event: ObservabilityEvent) -> None:
        """Emit event to strategy callbacks + global callbacks."""
        for callback in self._observers:
            try:
                callback(event)
            except Exception:
                pass  # Don't let callback errors break strategy

    def _wrap_hook(self, hook_fn: Callable, hook_name: str) -> Callable:
        """Wrap hook function with observability."""
        def wrapped(event, *args, **kwargs):
            self._current_session_id = event.session_id
            self._current_request_id = str(uuid.uuid4())
            self._current_hook = hook_name

            # Emit hook_enter
            self._emit_to_callbacks(ObservabilityEvent(
                session_id=self._current_session_id,
                request_id=self._current_request_id,
                event_type="hook_enter",
                strategy_name=self.Meta.name,
                hook_name=hook_name,
            ))

            start_time = time.perf_counter()
            try:
                result = hook_fn(event, *args, **kwargs)

                # Emit decision if result returned
                if result is not None:
                    self._emit_to_callbacks(DecisionEvent(
                        session_id=self._current_session_id,
                        request_id=self._current_request_id,
                        strategy_name=self.Meta.name,
                        hook_name=hook_name,
                        decision=result.decision,
                        reason=result.reason,
                        message=result.message,
                    ))

                return result

            except Exception as e:
                # Emit error
                self._emit_to_callbacks(ErrorEvent(
                    session_id=self._current_session_id,
                    request_id=self._current_request_id,
                    strategy_name=self.Meta.name,
                    hook_name=hook_name,
                    error_type=type(e).__name__,
                    error_message=str(e),
                ))
                raise

            finally:
                # Emit hook_exit with duration
                duration_ms = (time.perf_counter() - start_time) * 1000
                self._emit_to_callbacks(ObservabilityEvent(
                    session_id=self._current_session_id,
                    request_id=self._current_request_id,
                    event_type="hook_exit",
                    strategy_name=self.Meta.name,
                    hook_name=hook_name,
                    duration_ms=duration_ms,
                ))

        return wrapped
```

---

### File Structure

```
~/.fasthooks/
├── observability/
│   ├── abc123-def456.jsonl      # Raw events (JSONL)
│   ├── abc123-def456.md         # Human summary (generated on demand)
│   └── xyz789-...jsonl
└── ...
```

---

### Event Flow (Complete Picture)

This section explains exactly how events flow through the system.

#### 1. Event Emission Order

When a hook runs, events are emitted in this order:

```
1. hook_enter (start of hook execution)
2. [custom events, if any, emitted by strategy code]
3. decision (if hook returns allow/deny/block)
   OR error (if hook throws exception)
4. hook_exit (end of hook, includes duration_ms)
```

#### 2. Callback Invocation Order

When an event is emitted, callbacks are invoked in this order:

```python
def _emit_event(self, event: ObservabilityEvent) -> None:
    # 1. Strategy-level callbacks (registered on specific strategy)
    for callback in self._strategy_observers:
        callback(event)

    # 2. App-level callbacks (registered on HookApp)
    for callback in self._app_observers:
        callback(event)

    # 3. Default file backend (if enabled)
    if self._file_backend:
        self._file_backend.handle_event(event)

    # 4. Terminal output (if enabled)
    if self._terminal_output != TerminalOutput.QUIET:
        self._print_to_terminal(event)
```

#### 3. When flush() is Called

The file backend's `flush()` is called:

1. **After each hook invocation** (not after each event)
2. **On HookApp shutdown** (via `atexit` handler)
3. **Manually** via `app.flush_observability()`

```python
class HookApp:
    def __init__(self, ...):
        ...
        if self._observability_enabled:
            self._file_backend = FileObservabilityBackend(
                verbosity=self._observability_verbosity
            )
            atexit.register(self._file_backend.flush)

    def _run_hook(self, hook_fn, event):
        try:
            result = hook_fn(event)
            return result
        finally:
            # Flush after each hook completes
            if self._file_backend:
                self._file_backend.flush()
```

#### 4. How Default Backend is Auto-Registered

```python
class HookApp:
    def __init__(
        self,
        *,
        observability: bool = True,  # Default ON
        observability_verbosity: Verbosity = Verbosity.STANDARD,
        observability_dir: Path | None = None,
        terminal_output: TerminalOutput = TerminalOutput.NORMAL,
        **kwargs,
    ):
        self._observability_enabled = observability
        self._observability_verbosity = observability_verbosity
        self._terminal_output = terminal_output

        # App-level observers (user-registered)
        self._app_observers: list[Callable] = []

        # Default file backend (auto-registered if enabled)
        if observability:
            base_dir = observability_dir or (Path.home() / ".fasthooks" / "observability")
            self._file_backend = FileObservabilityBackend(
                base_dir=base_dir,
                verbosity=observability_verbosity,
            )
        else:
            self._file_backend = None

    def on_observe(self, callback: Callable[[ObservabilityEvent], None]):
        """Register app-level observer."""
        self._app_observers.append(callback)
        return callback
```

#### 5. If No Callbacks Registered

Events still flow to:
- Default file backend (if `observability=True`, the default)
- Terminal output (if `terminal_output != QUIET`)

If user sets `observability=False` AND doesn't register callbacks, events are discarded.

#### 6. Multiple Strategies in Same File

Events from all strategies are interleaved in chronological order:

```jsonl
{"session_id":"abc","strategy_name":"long-running","event_type":"hook_enter","hook_name":"on_session_start",...}
{"session_id":"abc","strategy_name":"token-budget","event_type":"hook_enter","hook_name":"post_tool:Write",...}
{"session_id":"abc","strategy_name":"token-budget","event_type":"decision","decision":"allow",...}
{"session_id":"abc","strategy_name":"token-budget","event_type":"hook_exit","duration_ms":2.3,...}
{"session_id":"abc","strategy_name":"long-running","event_type":"decision","decision":"allow",...}
{"session_id":"abc","strategy_name":"long-running","event_type":"hook_exit","duration_ms":15.7,...}
```

The `strategy_name` field allows filtering by strategy when analyzing.

---

### JSONL Format Example

Each line is a complete JSON object:

**hook_enter event:**
```json
{
  "session_id": "abc123-def456",
  "request_id": "req-789",
  "timestamp": "2024-01-15T10:30:00.123456",
  "duration_ms": null,
  "event_type": "hook_enter",
  "strategy_name": "long-running",
  "hook_name": "on_session_start",
  "payload": {},
  "custom_event_type": null
}
```

**decision event:**
```json
{
  "session_id": "abc123-def456",
  "request_id": "req-789",
  "timestamp": "2024-01-15T10:30:00.135000",
  "duration_ms": null,
  "event_type": "decision",
  "strategy_name": "long-running",
  "hook_name": "on_session_start",
  "payload": {},
  "custom_event_type": null,
  "decision": "allow",
  "reason": null,
  "message": "## Session Context...(injected content)"
}
```

**hook_exit event:**
```json
{
  "session_id": "abc123-def456",
  "request_id": "req-789",
  "timestamp": "2024-01-15T10:30:00.145000",
  "duration_ms": 22.5,
  "event_type": "hook_exit",
  "strategy_name": "long-running",
  "hook_name": "on_session_start",
  "payload": {},
  "custom_event_type": null
}
```

**error event:**
```json
{
  "session_id": "abc123-def456",
  "request_id": "req-790",
  "timestamp": "2024-01-15T10:31:00.000000",
  "duration_ms": null,
  "event_type": "error",
  "strategy_name": "long-running",
  "hook_name": "on_stop",
  "payload": {},
  "custom_event_type": null,
  "error_type": "FileNotFoundError",
  "error_message": "feature_list.json not found",
  "traceback": "Traceback (most recent call last):..."
}
```

**custom event:**
```json
{
  "session_id": "abc123-def456",
  "request_id": "req-789",
  "timestamp": "2024-01-15T10:30:00.140000",
  "duration_ms": null,
  "event_type": "custom",
  "strategy_name": "long-running",
  "hook_name": "on_session_start",
  "payload": {"feature_id": 42, "feature_name": "user-login"},
  "custom_event_type": "feature_started"
}
```

---

### Payload Contents by Verbosity

**MINIMAL verbosity:**
- `hook_enter`: NOT emitted
- `hook_exit`: NOT emitted
- `decision`: `payload = {}` (empty)
- `error`: `traceback = null`
- `custom`: NOT emitted

**STANDARD verbosity:**
- `hook_enter`: `payload = {}` (empty)
- `hook_exit`: `payload = {}`, `duration_ms` included
- `decision`: `payload = {}` (empty)
- `error`: `traceback = null`
- `custom`: `payload` as provided by strategy

**VERBOSE verbosity:**
- `hook_enter`: `payload = {"tool_name": "Bash", "tool_input": {...}}` (full event data)
- `hook_exit`: `payload = {}`, `duration_ms` included
- `decision`: `payload = {"transcript_context": "last 3 messages..."}` (relevant context)
- `error`: `traceback = "full traceback string"`
- `custom`: `payload` as provided by strategy

---

### Terminal Output Implementation

Terminal output is a separate system from file logging:

```python
class HookApp:
    def _print_to_terminal(self, event: ObservabilityEvent) -> None:
        """Print event to terminal based on terminal_output level."""
        if self._terminal_output == TerminalOutput.QUIET:
            return

        # Color codes
        COLORS = {
            "allow": "\033[32m",  # Green
            "deny": "\033[31m",   # Red
            "block": "\033[33m",  # Yellow
            "error": "\033[31m",  # Red
            "reset": "\033[0m",
        }

        if self._terminal_output == TerminalOutput.NORMAL:
            # Only show blocks, denies, and errors
            if event.event_type == "decision" and event.decision in ("deny", "block"):
                color = COLORS[event.decision]
                print(f"{color}[{event.strategy_name}] {event.decision.upper()} "
                      f"{event.hook_name}: {event.reason or event.message}{COLORS['reset']}")
            elif event.event_type == "error":
                print(f"{COLORS['error']}[{event.strategy_name}] ERROR "
                      f"{event.hook_name}: {event.error_message}{COLORS['reset']}")

        elif self._terminal_output == TerminalOutput.VERBOSE:
            # Show all events
            if event.event_type == "hook_enter":
                print(f"[{event.strategy_name}] ENTER {event.hook_name}")
            elif event.event_type == "hook_exit":
                print(f"[{event.strategy_name}] EXIT {event.hook_name} ({event.duration_ms:.1f}ms)")
            elif event.event_type == "decision":
                color = COLORS.get(event.decision, "")
                msg = event.reason or event.message or ""
                if len(msg) > 50:
                    msg = msg[:50] + "..."
                print(f"{color}[{event.strategy_name}] {event.decision.upper()} "
                      f"{event.hook_name}: {msg}{COLORS['reset']}")
            elif event.event_type == "error":
                print(f"{COLORS['error']}[{event.strategy_name}] ERROR "
                      f"{event.hook_name}: {event.error_message}{COLORS['reset']}")
            elif event.event_type == "custom":
                print(f"[{event.strategy_name}] CUSTOM {event.custom_event_type}")
```

---

### Markdown Generation

Markdown summaries are generated **on demand**, not automatically:

```python
# CLI command
# fasthooks observability summary <session-id>

# Or programmatically
from fasthooks.observability import generate_session_summary

summary_md = generate_session_summary("abc123-def456")
# Returns markdown string

# Optionally write to file
generate_session_summary("abc123-def456", write_file=True)
# Writes to ~/.fasthooks/observability/abc123-def456.md
```

**Implementation:**

```python
def generate_session_summary(
    session_id: str,
    observability_dir: Path | None = None,
    write_file: bool = False,
) -> str:
    """Generate markdown summary from JSONL events."""
    base_dir = observability_dir or (Path.home() / ".fasthooks" / "observability")
    jsonl_path = base_dir / f"{session_id}.jsonl"

    if not jsonl_path.exists():
        raise FileNotFoundError(f"No observability data for session: {session_id}")

    # Parse events
    events = []
    with open(jsonl_path) as f:
        for line in f:
            events.append(ObservabilityEvent.model_validate_json(line))

    # Build summary
    strategies = set(e.strategy_name for e in events)
    decisions = [e for e in events if e.event_type == "decision"]
    errors = [e for e in events if e.event_type == "error"]

    # Calculate duration
    first_ts = min(e.timestamp for e in events)
    last_ts = max(e.timestamp for e in events)
    duration = last_ts - first_ts

    # Format markdown
    md = f"""# Session Summary: {session_id}

**Duration**: {duration}
**Strategies**: {', '.join(sorted(strategies))}

## Decisions

- **Allows**: {sum(1 for d in decisions if d.decision == 'allow')}
- **Blocks**: {sum(1 for d in decisions if d.decision == 'block')}
- **Denies**: {sum(1 for d in decisions if d.decision == 'deny')}
- **Errors**: {len(errors)}

## Timeline

| Time | Strategy | Event | Details |
|------|----------|-------|---------|
"""
    for e in events:
        if e.event_type == "decision":
            details = e.reason or e.message or ""
            if len(details) > 50:
                details = details[:50] + "..."
            md += f"| {e.timestamp.strftime('%H:%M:%S')} | {e.strategy_name} | {e.decision.upper()} | {details} |\n"
        elif e.event_type == "error":
            md += f"| {e.timestamp.strftime('%H:%M:%S')} | {e.strategy_name} | ERROR | {e.error_message} |\n"

    if errors:
        md += "\n## Errors\n\n"
        for e in errors:
            md += f"### {e.error_type} in {e.hook_name}\n\n"
            md += f"```\n{e.error_message}\n```\n\n"
            if e.traceback:
                md += f"<details><summary>Traceback</summary>\n\n```\n{e.traceback}\n```\n\n</details>\n\n"
    else:
        md += "\n## Errors\n\nNone\n"

    if write_file:
        md_path = base_dir / f"{session_id}.md"
        md_path.write_text(md)

    return md
```

---

### Dry-Run Mode Interaction

When `--dry-run` is active:

1. **Decisions are logged as normal** (what WOULD have happened)
2. **An additional field is added** to decision events:

```python
class DecisionEvent(ObservabilityEvent):
    ...
    dry_run: bool = False  # True if this was a dry-run
```

This allows analysis to distinguish real decisions from dry-run decisions.

```python
# In Strategy._wrap_hook when dry-run is active:
if os.environ.get("FASTHOOKS_DRY_RUN"):
    decision_event.dry_run = True
    decision_event.message = f"[DRY-RUN] {decision_event.message}"
```

---

### Complete Module Structure

```
src/fasthooks/
├── observability/
│   ├── __init__.py          # Exports: ObservabilityEvent, Verbosity, etc.
│   ├── events.py             # Event models (Pydantic)
│   ├── backend.py            # FileObservabilityBackend
│   ├── terminal.py           # Terminal output implementation
│   ├── summary.py            # Markdown generation
│   └── enums.py              # Verbosity, TerminalOutput enums
└── strategies/
    └── base.py               # Strategy base class with _wrap_hook
```

---

## Implementation Notes (Robustness)

Two implementation details require attention to avoid performance/concurrency issues:

### 1. Observability Blocking

**Risk**: In `Strategy._emit()`, user callbacks are called synchronously:

```python
def _emit(self, event: ObservabilityEvent) -> None:
    for callback in self._observers:
        callback(event)  # ⚠️ Blocks if callback is slow (e.g., HTTP POST)
```

If a user attaches a slow callback (e.g., synchronous HTTP POST to Datadog), it blocks the main hook execution, adding latency.

**Fix**: User callbacks MUST be fire-and-forget:

```python
import threading

def _emit(self, event: ObservabilityEvent) -> None:
    for callback in self._observers:
        try:
            # Fire-and-forget: don't block hook execution
            threading.Thread(target=callback, args=(event,), daemon=True).start()
        except Exception:
            pass
```

Or use a queue-based approach for batching.

### 2. State Race Conditions

**Risk**: `State.save()` writes without file locking:

```python
def save(self) -> None:
    self._file.write_text(json.dumps(dict(self), indent=2))  # ⚠️ No lock
```

If multiple processes access the same state file, writes can corrupt data.

**Mitigating factor**: Claude Code's hook protocol is synchronous (stdin→process→stdout), so hooks don't run concurrently within a session.

**Fix**: Add file locking for robustness:

```python
import filelock  # or fasteners

def save(self) -> None:
    self._file.parent.mkdir(parents=True, exist_ok=True)
    lock = filelock.FileLock(f"{self._file}.lock")
    with lock:
        # Atomic write: write to temp, then rename
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(self), indent=2))
        tmp.rename(self._file)
```

---

## Open Questions (Deferred)

1. **Cost estimation**: Should strategies have access to token pricing for cost estimates?
2. **Remote state**: Should strategies be able to store state remotely (for team sharing)?
3. **Strategy composition**: Should strategies be able to wrap/extend other strategies?
4. **Events/webhooks**: Should strategies be able to emit events for external systems?
5. **Observability aggregation**: Should we provide cross-session analytics?

---

## End-to-End Example

### User Workflow: Setting Up Long-Running Agent

1. **Install fasthooks** (if not already):
   ```bash
   pip install fasthooks
   ```

2. **Create hooks.py**:
   ```python
   from fasthooks import HookApp
   from fasthooks.strategies import LongRunningStrategy

   app = HookApp(state_dir="/tmp/fasthooks-state")

   strategy = LongRunningStrategy(
       feature_list="feature_list.json",
       progress_file="claude-progress.txt",
       enforce_commits=True,
   )
   app.include(strategy.get_blueprint())

   if __name__ == "__main__":
       app.run()
   ```

3. **Configure Claude Code** (`~/.claude/settings.json`):
   ```json
   {
     "hooks": {
       "SessionStart": [{"command": "python /path/to/hooks.py"}],
       "Stop": [{"command": "python /path/to/hooks.py"}],
       "PreCompact": [{"command": "python /path/to/hooks.py"}],
       "PostToolUse": [{"command": "python /path/to/hooks.py"}]
     }
   }
   ```

4. **Start Claude Code** in your project:
   ```bash
   cd ~/myproject
   claude
   ```

5. **First session** (no feature_list.json exists):
   - Strategy injects initializer context
   - Claude creates feature_list.json, init.sh, claude-progress.txt
   - Claude initializes git

6. **Subsequent sessions**:
   - Strategy injects coding context (feature status, recent commits)
   - Claude works on one feature at a time
   - On stop, strategy blocks if uncommitted changes or progress not updated

---

## Event Reference

### SessionStart Event

```python
class SessionStart(BaseEvent):
    source: str  # "startup", "compact", or "resume"
```

### Stop Event

```python
class Stop(BaseEvent):
    stop_hook_active: bool  # Whether stop hook is currently running
```

### PreCompact Event

```python
class PreCompact(BaseEvent):
    trigger: str  # What triggered compaction
```

### Write Event (PostToolUse)

```python
class Write(ToolEvent):
    @property
    def file_path(self) -> str: ...
    @property
    def content(self) -> str: ...
```

### Bash Event (PostToolUse)

```python
class Bash(ToolEvent):
    @property
    def command(self) -> str: ...
    @property
    def description(self) -> str | None: ...
```

---

## Appendix: File Locations

| Path | Purpose |
|------|---------|
| `~/.fasthooks/` | Global fasthooks directory |
| `~/.fasthooks/observability/` | Observability event logs (JSONL) |
| `~/.claude/settings.json` | Claude Code hook configuration |
| `<project>/fasthooks-config.yaml` | Project-level strategy config (optional) |
| `<state_dir>/<session>.json` | Strategy state files |

---

## References

- [Anthropic: Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Quickstart Code](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding)
- [GitHub Issue #15](https://github.com/oneryalcin/fasthooks/issues/15)
- [fasthooks CLAUDE.md](../CLAUDE.md) - Architecture overview
- [fasthooks docs/architecture.md](../docs/architecture.md) - Detailed internals
