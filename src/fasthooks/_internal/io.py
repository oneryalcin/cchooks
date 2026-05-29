"""stdin/stdout handling for hook input/output."""
from __future__ import annotations

import inspect
import json
import sys
from typing import IO, Any, cast

from fasthooks.responses import BaseHookResponse


def serialize_response(
    response: BaseHookResponse, hook_event_name: str | None = None
) -> str:
    """Serialize a response, tolerating legacy no-arg ``to_json`` overrides.

    ``to_json`` gained a ``hook_event_name`` parameter; a custom
    ``BaseHookResponse`` subclass written against the old ``to_json(self)`` API
    would raise ``TypeError`` if called with the argument. Detect that case and
    fall back, so upgrading doesn't break third-party response classes.
    """
    try:
        params = inspect.signature(response.to_json).parameters
    except (TypeError, ValueError):
        params = None  # builtins / unintrospectable — assume new signature
    if params is not None and len(params) == 0:
        return response.to_json()  # legacy no-arg override
    return response.to_json(hook_event_name)


def read_stdin(stdin: IO[str] | None = None) -> dict[str, Any]:
    """Read and parse JSON from stdin.

    Args:
        stdin: Input stream, defaults to sys.stdin

    Returns:
        Parsed JSON dict, or empty dict on error
    """
    if stdin is None:
        stdin = sys.stdin

    try:
        content = stdin.read()
        if not content.strip():
            return {}
        return cast(dict[str, Any], json.loads(content))
    except (json.JSONDecodeError, Exception):
        return {}


def write_stdout(
    response: BaseHookResponse,
    stdout: IO[str] | None = None,
    hook_event_name: str | None = None,
) -> None:
    """Write hook response JSON to stdout.

    Args:
        response: The response to write
        stdout: Output stream, defaults to sys.stdout
        hook_event_name: Event being responded to (for event-specific output)
    """
    if stdout is None:
        stdout = sys.stdout

    output = serialize_response(response, hook_event_name)
    if output:
        stdout.write(output)
