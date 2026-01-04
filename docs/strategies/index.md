# Strategies

## Raw Hooks vs Strategy: When to Use Which

**Raw fasthooks** and **Strategy** can both accomplish the same things. The difference is in packaging and reuse.

### Use Raw Hooks When:

- Building project-specific hooks
- Simple logic (1-2 hooks, minimal state)
- You want maximum transparency
- Learning how fasthooks works

```python
# Raw fasthooks - simple, transparent, project-specific
from fasthooks import HookApp, deny
from fasthooks.depends import State

app = HookApp(state_dir="/tmp/hook-state")

@app.pre_tool("Bash")
def rate_limit(event, state: State):
    count = state.get("bash_count", 0) + 1
    state["bash_count"] = count
    state.save()
    if count > 100:
        return deny(f"Rate limit: {count}/100 commands")
```

### Use Strategy When:

- **Reusing a proven pattern** - don't reinvent complex logic
- **Distributing hooks** - share via PyPI packages
- **Multiple strategies coexisting** - namespace isolation prevents state collisions
- **Debugging complex behavior** - built-in observability

```python
# Strategy - packaged, configurable, reusable
from fasthooks import HookApp
from fasthooks.strategies import LongRunningStrategy

app = HookApp()

strategy = LongRunningStrategy(
    feature_list="features.json",
    enforce_commits=True,
)
app.include(strategy.get_blueprint())
```

---

## What Strategy Adds

Raw fasthooks already provides state, multiple hooks, and complex logic. Strategy adds a **packaging layer**:

| Feature | Raw Hooks | Strategy |
|---------|-----------|----------|
| State persistence | `state: State` DI | Same, plus auto-namespacing |
| Multiple hooks | Register each manually | Bundle as single unit |
| Configuration | Hardcoded or manual | Kwargs with validation |
| Observability | Manual logging | Built-in events |
| Distribution | Copy-paste code | PyPI packages |
| Conflict detection | None | Meta.hooks declaration |
| Testing | TestClient | StrategyTestClient with helpers |

### State Namespace Isolation

When multiple strategies run together, each gets isolated state:

```python
# Strategy A writes to state['strategy-a']['key']
# Strategy B writes to state['strategy-b']['key']
# No collision possible
```

With raw hooks, you'd manage this manually.

---

## When Strategy Truly Shines

Consider `LongRunningStrategy` - Anthropic's two-agent pattern for autonomous agents:

- **5 hooks coordinating**: session_start, stop, pre_compact, post_tool:Write, post_tool:Bash
- **State tracked across hooks**: session count, files modified, commits made, progress updated
- **Complex logic**: mode detection (initializer vs coding), feature list validation, git status checks
- **Hard to get right**: timing, edge cases, state management

You *could* build this with raw fasthooks. But you'd be reimplementing 500+ lines of tested logic.

```python
# Without Strategy - you write and maintain all this yourself
@app.on_session_start()
def handle_session_start(event, state: State):
    # 50 lines of mode detection, context injection...

@app.on_stop()
def handle_stop(event, state: State):
    # 40 lines of commit enforcement, progress checks...

@app.on_pre_compact()
def handle_pre_compact(event, state: State, transcript: Transcript):
    # 20 lines of checkpoint warnings...

@app.post_tool("Write")
def track_write(event, state: State):
    # 30 lines of file tracking, feature list validation...

@app.post_tool("Bash")
def track_bash(event, state: State):
    # 15 lines of commit tracking...

# Plus helper functions, error handling, edge cases...
```

```python
# With Strategy - use proven implementation
strategy = LongRunningStrategy(enforce_commits=True)
app.include(strategy.get_blueprint())
```

**Strategy packages complex patterns so you don't reinvent them.**

---

## Built-in Strategies

| Strategy | Purpose | Complexity |
|----------|---------|------------|
| [LongRunningStrategy](long-running.md) | Two-agent pattern for autonomous agents | High (5 hooks, state, modes) |
| TokenBudgetStrategy | Warn on token usage thresholds | Low (1 hook) |
| CleanStateStrategy | Enforce clean state before stopping | Low (1 hook) |

### Simple Strategies: Educational Value

`TokenBudgetStrategy` and `CleanStateStrategy` are simple enough to implement with raw hooks:

```python
# TokenBudgetStrategy as raw hooks (~10 lines)
@app.post_tool()
def check_tokens(event, transcript: Transcript):
    total = transcript.stats.input_tokens + transcript.stats.output_tokens
    if total >= 150_000:
        return allow(message="⚠️ Token limit approaching!")
```

```python
# CleanStateStrategy as raw hooks (~15 lines)
@app.on_stop()
def enforce_clean(event):
    result = subprocess.run(["git", "status", "--porcelain"],
                            capture_output=True, text=True, cwd=event.cwd)
    if result.stdout.strip():
        return block("Uncommitted changes exist")
```

We provide them as built-in strategies to:

1. **Demonstrate the pattern** - see how Strategy wraps simple logic
2. **Provide starting points** - extend them for your needs
3. **Show the spectrum** - from simple (1 hook) to complex (5 hooks)

For simple cases, raw hooks are often cleaner. As complexity grows, Strategy pays off.

---

## Quick Comparison

```
┌─────────────────────────────────────────────────────────────┐
│  Your Decision Tree                                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Is this a one-off, project-specific hook?                   │
│    YES → Use raw fasthooks                                   │
│                                                              │
│  Are you implementing a complex, multi-hook pattern?         │
│    YES → Check if a Strategy exists first                    │
│                                                              │
│  Do you want to share/distribute this pattern?               │
│    YES → Create a Strategy, publish to PyPI                  │
│                                                              │
│  Do you need observability/debugging?                        │
│    YES → Strategy has it built-in                            │
│                                                              │
│  Are multiple patterns running together?                     │
│    YES → Strategy namespacing prevents collisions            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Creating a Strategy

Extend the `Strategy` base class:

```python
from fasthooks import Blueprint, deny
from fasthooks.strategies import Strategy

class MyStrategy(Strategy):
    class Meta:
        name = "my-strategy"
        version = "1.0.0"
        description = "Does something useful"
        hooks = ["pre_tool:Bash"]

    def __init__(self, *, blocked_commands: list[str] | None = None):
        # IMPORTANT: Set attributes BEFORE super().__init__()
        # super().__init__() calls _validate_config() which may need these
        self.blocked_commands = blocked_commands or ["rm -rf"]
        super().__init__()

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("my-strategy")

        @bp.pre_tool("Bash")
        def check_bash(event):
            for cmd in self.blocked_commands:
                if cmd in event.command:
                    return deny(f"Blocked: {cmd}")

        return bp
```

### Meta Class Options

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier (used for state namespace, conflict detection) |
| `version` | Yes | Semantic version string |
| `hooks` | Yes | List of hooks this strategy uses (for conflict detection) |
| `description` | No | Human-readable description |
| `fail_mode` | No | `"open"` or `"closed"` - metadata only (errors currently raise) |
| `custom_events` | No | List of custom event types this strategy emits |
| `state_namespace` | No | Override state namespace (defaults to strategy name) |

Hook format: `"on_stop"`, `"pre_tool:Bash"`, `"post_tool:*"` (catch-all).

### Validation

Override `_validate_config()` for custom validation:

```python
def _validate_config(self) -> None:
    if self.max_retries < 0:
        raise ValueError("max_retries must be non-negative")
```

Called automatically by `super().__init__()`.

### Using Dependencies

Handlers can use DI just like raw hooks:

```python
from fasthooks.depends import State, Transcript

def _build_blueprint(self) -> Blueprint:
    bp = Blueprint("my-strategy")

    @bp.post_tool()
    def track_usage(event, state: State, transcript: Transcript):
        # State is auto-namespaced to strategy name
        state["call_count"] = state.get("call_count", 0) + 1
        state.save()

        # Transcript provides token stats
        total = transcript.stats.input_tokens + transcript.stats.output_tokens
        if total > 100_000:
            return allow(message="Token warning!")

    return bp
```

### Testing

Use `StrategyTestClient`:

```python
from fasthooks.testing import StrategyTestClient
from fasthooks.strategies import LongRunningStrategy

def test_blocks_on_uncommitted_changes():
    strategy = LongRunningStrategy(enforce_commits=True)
    client = StrategyTestClient(strategy)

    # Set up git with uncommitted changes
    client.setup_git()
    client.add_uncommitted("dirty.py")

    # Trigger stop hook
    client.trigger_session_start()  # Initialize state
    response = client.trigger_stop()

    assert response is not None
    client.assert_blocked("uncommitted")
```

For strategies using `Transcript`:

```python
from unittest.mock import Mock

def test_with_transcript():
    client = StrategyTestClient(strategy)

    # Mock transcript with token counts
    mock_transcript = Mock()
    mock_transcript.stats.input_tokens = 100_000
    mock_transcript.stats.output_tokens = 50_000
    client.set_transcript(mock_transcript)

    response = client.trigger_post_bash(command="echo test")
    # ...
```

---

## Observability

All strategies emit events automatically:

```python
strategy = LongRunningStrategy()

@strategy.on_observe
def log_events(event):
    print(f"[{event.event_type}] {event.hook_name}")

app.include(strategy.get_blueprint())
```

Events emitted:
- `hook_enter` - Handler starts
- `hook_exit` - Handler ends (with duration)
- `decision` - Handler returns allow/deny/block
- `error` - Handler throws exception
- `custom` - Strategy-specific events

---

## Future Work

The following features are planned but not yet implemented:

- **App-level observability** (`@app.on_observe`) - Single callback for all strategy events
- **fail_mode enforcement** - Currently metadata-only; handler errors raise exceptions

---

## Further Reading

- [Long-Running Strategy Guide](long-running.md)
- [Live Example: Expense Tracker built with LongRunningStrategy](https://github.com/oneryalcin/fasthooks_example_longrun)
- [Testing Strategies](../testing.md)
