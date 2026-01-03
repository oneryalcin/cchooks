# Strategies

Strategies are reusable, composable hook patterns that solve common problems. They provide an abstraction layer above raw hooks, enabling users to adopt proven patterns without understanding hook internals.

## What is a Strategy?

A Strategy bundles related hooks with configuration:

```python
from fasthooks import HookApp
from fasthooks.strategies import LongRunningStrategy

app = HookApp()

# Create strategy with configuration
strategy = LongRunningStrategy(
    feature_list="features.json",
    enforce_commits=True,
)

# Include the strategy's hooks in your app
app.include(strategy.get_blueprint())
```

## Available Strategies

| Strategy | Purpose | Status |
|----------|---------|--------|
| [LongRunningStrategy](long-running.md) | Two-agent pattern for autonomous agents | Stable |
| TokenBudgetStrategy | Track and warn on token usage | Planned |
| CleanStateStrategy | Ensure clean state before stopping | Planned |

## Strategy vs Blueprint

| Aspect | Blueprint | Strategy |
|--------|-----------|----------|
| **Purpose** | Group related handlers | Reusable patterns with config |
| **Configuration** | None | Accepts options |
| **Observability** | Manual | Built-in event emission |
| **Lifecycle** | Simple | Setup, teardown, state |

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

    def __init__(self, *, blocked_commands: list[str] = None, **config):
        super().__init__(**config)
        self.blocked_commands = blocked_commands or ["rm -rf"]

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("my-strategy")

        @bp.pre_tool("Bash")
        def check_bash(event):
            for cmd in self.blocked_commands:
                if cmd in event.command:
                    return deny(f"Blocked: {cmd}")

        return bp
```

## Observability

All strategies have built-in observability:

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

## Further Reading

- [Long-Running Strategy Guide](long-running.md)
- [Live Example: Expense Tracker built with LongRunningStrategy](https://github.com/oneryalcin/fasthooks_example_longrun)
