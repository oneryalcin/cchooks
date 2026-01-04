"""Validation utilities for hooks.py and environment."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

# Introspection script template - runs in isolated subprocess
_INTROSPECT_SCRIPT = '''
import sys
import json

# Add parent directory to sys.path so hooks.py can import local modules
sys.path.insert(0, "PARENT_DIR")

try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("hooks", "HOOKS_PATH")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    from fasthooks import HookApp
    app = None

    # Check common variable names first
    for name in ["app", "hooks", "hook_app", "application"]:
        obj = getattr(module, name, None)
        if isinstance(obj, HookApp):
            app = obj
            break

    # Fallback: scan all module attributes
    if app is None:
        for name in dir(module):
            if not name.startswith("_"):
                obj = getattr(module, name)
                if isinstance(obj, HookApp):
                    app = obj
                    break

    if app is None:
        print(json.dumps({"error": "No HookApp instance found"}))
        sys.exit(1)

    # Extract handlers
    hooks = []
    for tool in app._pre_tool_handlers:
        hooks.append(f"PreToolUse:{tool}")
    for tool in app._post_tool_handlers:
        hooks.append(f"PostToolUse:{tool}")
    for tool in app._permission_handlers:
        hooks.append(f"PermissionRequest:{tool}")
    for event, handlers_list in app._lifecycle_handlers.items():
        if event == "Notification":
            # Notification has matchers like tool events
            for _, matcher in handlers_list:
                if matcher and matcher != "*":
                    hooks.append(f"Notification:{matcher}")
                else:
                    hooks.append("Notification:*")
        else:
            # Other lifecycle events don't have matchers
            hooks.append(event)

    if not hooks:
        print(json.dumps({"error": "No handlers registered"}))
        sys.exit(1)

    print(json.dumps({"hooks": hooks}))

except SyntaxError as e:
    print(json.dumps({"error": f"Syntax error: {e}"}))
    sys.exit(1)
except ImportError as e:
    print(json.dumps({"error": f"Import error: {e}"}))
    sys.exit(1)
except Exception as e:
    print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
    sys.exit(1)
'''


def check_uv_installed() -> bool:
    """Check if uv is in PATH."""
    return shutil.which("uv") is not None


def validate_and_introspect(path: Path) -> tuple[bool, list[str] | None, str | None]:
    """
    Validate hooks.py and extract handlers in isolated subprocess.

    This runs the import in a subprocess to:
    1. Isolate side effects from the CLI process
    2. Catch crashes without killing the CLI
    3. Prevent pollution of the CLI's Python environment

    Args:
        path: Path to hooks.py file

    Returns:
        Tuple of (success, handlers, error_message):
        - success: True if import succeeded and HookApp found with handlers
        - handlers: List of hook identifiers like ["PreToolUse:Bash", "Stop"]
        - error_message: Error description if failed
    """
    if not path.exists():
        return (False, None, f"File not found: {path}")

    # Build script with actual paths
    resolved = path.resolve()
    script = _INTROSPECT_SCRIPT.replace("HOOKS_PATH", str(resolved))
    script = script.replace("PARENT_DIR", str(resolved.parent))

    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=10,  # Prevent hangs from infinite loops
        )
    except subprocess.TimeoutExpired:
        return (False, None, "Timeout: hooks.py took too long to import (>10s)")

    if result.returncode != 0:
        # Try to parse error from stdout
        try:
            data = json.loads(result.stdout)
            return (False, None, data.get("error", "Unknown error"))
        except json.JSONDecodeError:
            # Fall back to stderr
            error = result.stderr.strip() if result.stderr else "Unknown error"
            return (False, None, error)

    try:
        data = json.loads(result.stdout)
        return (True, data["hooks"], None)
    except (json.JSONDecodeError, KeyError) as e:
        return (False, None, f"Failed to parse introspection result: {e}")
