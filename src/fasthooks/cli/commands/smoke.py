"""``fasthooks test`` — run a hook file against a synthetic event (smoke test).

This drives the hook the *same way Claude Code does*: it builds a hook-event
stdin envelope and runs the file in a subprocess, then reports the three signals
a hook can produce — stdout JSON decision, stderr, and exit code (2 = block).
That's the differentiated value over a programmatic ``TestClient`` test: it
exercises the real stdin → dispatch → stdout/exit path end to end.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from rich.console import Console

_TIMEOUT_S = 10


def _parse_event_spec(spec: str) -> tuple[str, str | None]:
    """``'PreToolUse:Bash'`` -> ``('PreToolUse', 'Bash')``; ``'Stop'`` -> ``('Stop', None)``."""
    name, _, tool = spec.partition(":")
    return name, (tool or None)


def build_event(
    event_name: str,
    tool_name: str | None,
    tool_input: dict[str, Any],
    *,
    cwd: str,
    transcript_path: str,
) -> dict[str, Any]:
    """Build a Claude Code hook stdin envelope.

    Field placement mirrors :class:`MockEvent` (the programmatic test factory) so
    the smoke-test path and the test path can't drift — pinned by
    ``test_cli_smoke.test_envelope_matches_mockevent``.
    """
    event: dict[str, Any] = {
        "session_id": "smoke-test",
        "transcript_path": transcript_path,
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": event_name,
    }
    if tool_name:
        event["tool_name"] = tool_name
        event["tool_input"] = tool_input
        event["tool_use_id"] = "smoke-test-tool-use"
        if event_name == "PostToolUse":
            event["tool_response"] = {}
    elif event_name == "UserPromptSubmit":
        event["prompt"] = tool_input.get("prompt", "") if isinstance(tool_input, dict) else ""
    elif event_name in ("Stop", "SubagentStop"):
        event["stop_hook_active"] = False
    return event


def _load_input(raw: str | None, console: Console) -> dict[str, Any] | None:
    """Parse ``--input`` (inline JSON or ``@file.json``). Returns None on error."""
    if not raw:
        return {}
    text = Path(raw[1:]).read_text() if raw.startswith("@") else raw
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]--input is not valid JSON:[/red] {e}")
        return None
    if not isinstance(parsed, dict):
        console.print("[red]--input must be a JSON object[/red]")
        return None
    return parsed


def _render(proc: subprocess.CompletedProcess[str], console: Console) -> int:
    """Interpret the hook's three signals; return the CLI's own exit code.

    The CLI exits 0 whenever the hook *ran* (allow OR block are both valid hook
    outcomes); non-zero only when the harness or the hook itself failed.
    """
    out, err, code = proc.stdout.strip(), proc.stderr.strip(), proc.returncode

    if code == 2:  # block: reason goes to stderr, shown to Claude
        console.print("[red]● blocked[/red] [dim](exit 2)[/dim]")
        if err:
            console.print(err)
        return 0
    if code != 0:
        console.print(f"[red]✗ hook errored (exit {code})[/red]")
        if err:
            console.print(err)
        return code
    if not out:
        console.print("[green]● allowed[/green] [dim](no output)[/dim]")
        if err:
            console.print(f"[dim]stderr: {err}[/dim]")
        return 0
    try:
        console.print_json(json.dumps(json.loads(out)))
    except json.JSONDecodeError:
        console.print(out)  # hook printed something non-JSON; show it raw
    if err:
        console.print(f"[dim]stderr: {err}[/dim]")
    return 0


def run_smoke(
    hook_file: str, event_spec: str, input_raw: str | None, console: Console
) -> int:
    """Run ``hook_file`` against a synthetic ``event_spec`` event."""
    hook_path = Path(hook_file)
    if not hook_path.is_file():
        console.print(f"[red]Hook file not found:[/red] {hook_file}")
        return 1

    tool_input = _load_input(input_raw, console)
    if tool_input is None:
        return 1

    event_name, tool_name = _parse_event_spec(event_spec)

    # An empty transcript file so handlers that take `transcript: Transcript`
    # don't error on a bogus path — they just see an empty session.
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as tf:
        transcript_path = tf.name
    try:
        event = build_event(
            event_name, tool_name, tool_input,
            cwd=str(Path.cwd()), transcript_path=transcript_path,
        )
        label = event_name + (f":{tool_name}" if tool_name else "")
        console.print(f"[dim]→ {label} → {hook_path}[/dim]")
        try:
            proc = subprocess.run(
                [sys.executable, str(hook_path)],
                input=json.dumps(event),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            console.print(f"[red]✗ hook timed out after {_TIMEOUT_S}s[/red]")
            return 1
    finally:
        Path(transcript_path).unlink(missing_ok=True)

    return _render(proc, console)
