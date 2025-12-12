"""stdin/stdout handling for hook input/output."""
from __future__ import annotations

import json
import sys
from typing import IO, Any

from fasthooks.responses import HookResponse


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
        return json.loads(content)
    except (json.JSONDecodeError, Exception):
        return {}


def write_stdout(response: HookResponse, stdout: IO[str] | None = None) -> None:
    """Write HookResponse JSON to stdout.

    Args:
        response: The response to write
        stdout: Output stream, defaults to sys.stdout
    """
    if stdout is None:
        stdout = sys.stdout

    output = response.to_json()
    if output:
        stdout.write(output)
