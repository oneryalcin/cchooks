# fasthooks

<p align="center">
<a href="https://pypi.org/project/fasthooks" target="_blank">
    <img src="https://img.shields.io/pypi/v/fasthooks?color=%2334D058&label=pypi" alt="PyPI version">
</a>
<a href="https://github.com/oneryalcin/fasthooks" target="_blank">
    <img src="https://img.shields.io/github/stars/oneryalcin/fasthooks?style=flat&color=yellow" alt="GitHub stars">
</a>
<a href="https://github.com/oneryalcin/fasthooks/fork" target="_blank">
    <img src="https://img.shields.io/github/forks/oneryalcin/fasthooks?style=flat" alt="GitHub forks">
</a>
</p>

**Delightful Claude Code hooks with a FastAPI-like developer experience.**

```python
from fasthooks import HookApp, deny

app = HookApp()

@app.pre_tool("Bash")
def no_rm_rf(event):
    if "rm -rf" in event.command:
        return deny("Dangerous command blocked")

if __name__ == "__main__":
    app.run()
```

## Features

- **Typed events** - Autocomplete for `event.command`, `event.file_path`, etc.
- **Decorators** - `@app.pre_tool("Bash")`, `@app.on_stop()`, `@app.on_session_start()`
- **Dependency injection** - `def handler(event, transcript: Transcript, state: State)`
- **Blueprints** - Compose handlers from multiple modules
- **Middleware** - Cross-cutting concerns like timing and logging
- **Guards** - `@app.pre_tool("Bash", when=lambda e: "sudo" in e.command)`
- **Testing utilities** - `MockEvent` and `TestClient` for easy testing

## Installation

=== "pip"

    ```bash
    pip install fasthooks
    ```

=== "uv"

    ```bash
    uv add fasthooks
    ```

## Quick Example

```python
from fasthooks import HookApp, allow, deny

app = HookApp()

@app.pre_tool("Bash")
def check_bash(event):
    # event.command has autocomplete!
    if "rm -rf" in event.command:
        return deny("Dangerous command blocked")
    return allow()

@app.pre_tool("Write")
def check_write(event):
    # event.file_path, event.content available
    if event.file_path.endswith(".env"):
        return deny("Cannot modify .env files")
    return allow()

@app.on_stop()
def on_stop(event):
    return allow()

if __name__ == "__main__":
    app.run()
```

## Why fasthooks?

Claude Code hooks are powerful but the raw JSON protocol is tedious:

- No autocomplete for event fields
- Manual JSON parsing and response building
- No reusable patterns for common tasks

fasthooks gives you a **FastAPI-like experience**:

| Raw Hooks | fasthooks |
|-----------|-----------|
| Parse JSON from stdin | Typed `event` objects |
| Build JSON responses | `allow()`, `deny()`, `block()` |
| Manual dispatch | `@app.pre_tool("Bash")` |
| Copy-paste boilerplate | Blueprints & middleware |

## Next Steps

- [Getting Started](getting-started.md) - Set up your first hook project
- [Tutorial](tutorial/index.md) - Learn fasthooks step by step
- [CLI Reference](cli.md) - Command line tools
