# Middleware

Middleware wraps ALL handler calls, letting you add cross-cutting behavior like timing, logging, or error handling.

## Why Middleware?

Some behaviors should apply to **every** handler:

- Timing how long handlers take
- Logging all events
- Error handling and recovery
- Authentication/authorization

Without middleware, you'd duplicate this in every handler:

```python
@app.pre_tool("Bash")
def check_bash(event):
    start = time.time()
    try:
        result = do_check(event)
        logger.info(f"Bash check took {time.time() - start:.3f}s")
        return result
    except Exception as e:
        logger.error(f"Error: {e}")
        raise

# Repeat for every handler... 😩
```

With middleware:

```python
@app.middleware
def timing(event, call_next):
    start = time.time()
    result = call_next(event)
    print(f"Handlers took {time.time() - start:.3f}s")
    return result

# Automatically wraps ALL handlers ✨
```

## Basic Usage

```python
from fasthooks import HookApp

app = HookApp()

@app.middleware
def my_middleware(event, call_next):
    # Before handlers
    print(f"Processing {event.hook_event_name}")

    # Call the handler chain
    result = call_next(event)

    # After handlers
    print(f"Result: {result}")

    return result
```

## How It Works

```
Event → Middleware 1 → Middleware 2 → ... → Handlers → Response
              ↓              ↓                  ↓
          call_next      call_next          execute
```

1. Event enters the middleware chain
2. Each middleware calls `call_next(event)` to continue
3. Handlers execute and return a response
4. Response bubbles back through middleware
5. Final response returned

## Common Patterns

### Timing

```python
import time

@app.middleware
def timing(event, call_next):
    start = time.time()
    result = call_next(event)
    elapsed = time.time() - start
    print(f"[{event.hook_event_name}] {elapsed:.3f}s")
    return result
```

### Logging

```python
import logging

logger = logging.getLogger("hooks")

@app.middleware
def log_events(event, call_next):
    logger.info(f"Event: {event.hook_event_name}")
    if hasattr(event, "tool_name"):
        logger.info(f"Tool: {event.tool_name}")

    result = call_next(event)

    if result:
        logger.info(f"Decision: {result.decision}")

    return result
```

### Error Handling

```python
@app.middleware
def error_handler(event, call_next):
    try:
        return call_next(event)
    except Exception as e:
        print(f"Handler error: {e}")
        # Return None to allow (fail-open)
        # Or return deny("Internal error") to fail-closed
        return None
```

### Conditional Processing

```python
@app.middleware
def skip_in_plan_mode(event, call_next):
    # Skip all checks in plan mode
    if event.permission_mode == "plan":
        return None

    return call_next(event)
```

### Response Modification

```python
@app.middleware
def add_warnings(event, call_next):
    result = call_next(event)

    # Add warning to all denials
    if result and result.decision == "deny":
        result.message = f"⚠️ Blocked: {result.reason}"

    return result
```

## Async Middleware

Middleware can be async:

```python
@app.middleware
async def async_middleware(event, call_next):
    # Async operations allowed
    await some_async_check()

    result = await call_next(event)

    return result
```

## Multiple Middleware

Middleware executes in **registration order**:

```python
@app.middleware
def first(event, call_next):
    print("1. First - before")
    result = call_next(event)
    print("4. First - after")
    return result

@app.middleware
def second(event, call_next):
    print("2. Second - before")
    result = call_next(event)
    print("3. Second - after")
    return result

# Output:
# 1. First - before
# 2. Second - before
# (handlers run)
# 3. Second - after
# 4. First - after
```

## Short-Circuiting

Return early to skip handlers:

```python
from fasthooks import deny

@app.middleware
def auth_check(event, call_next):
    # Block everything if not authorized
    if not is_authorized():
        return deny("Not authorized")

    # Otherwise continue to handlers
    return call_next(event)
```

## Real-World Example

```python
import time
import logging
from fasthooks import HookApp, deny

app = HookApp()
logger = logging.getLogger("hooks")

@app.middleware
def comprehensive_middleware(event, call_next):
    # 1. Log incoming event
    start = time.time()
    event_info = f"{event.hook_event_name}"
    if hasattr(event, "tool_name"):
        event_info += f":{event.tool_name}"
    logger.info(f"→ {event_info}")

    # 2. Skip processing in certain modes
    if event.permission_mode == "bypassPermissions":
        logger.info("  Skipping (bypass mode)")
        return None

    # 3. Execute handlers with error handling
    try:
        result = call_next(event)
    except Exception as e:
        logger.error(f"  Error: {e}")
        return deny(f"Internal error: {e}")

    # 4. Log result
    elapsed = time.time() - start
    decision = result.decision if result else "allow"
    logger.info(f"← {event_info} [{decision}] ({elapsed:.3f}s)")

    return result
```

## Middleware vs Blueprints vs Guards

| Feature | Use Case |
|---------|----------|
| **Middleware** | Universal behavior (timing, logging, auth) |
| **Blueprints** | Organizing handlers by feature |
| **Guards** | Filtering which events trigger a handler |

```python
# Middleware: runs for EVERY event
@app.middleware
def timing(event, call_next): ...

# Blueprint: groups related handlers
security = Blueprint("security")

# Guard: filters specific handler
@app.pre_tool("Bash", when=lambda e: "sudo" in e.command)
def check_sudo(event): ...
```
