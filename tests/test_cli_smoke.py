"""Tests for `fasthooks test` — the one-shot hook smoke-test command (#3)."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from fasthooks.cli.app import app
from fasthooks.cli.commands.smoke import build_event
from fasthooks.testing import MockEvent

runner = CliRunner()

_DENY_HOOK = '''\
from fasthooks import HookApp, deny
app = HookApp()

@app.pre_tool("Bash")
def block_rm(event):
    if "rm -rf" in event.command:
        return deny("Dangerous command blocked")

if __name__ == "__main__":
    app.run()
'''

_EXIT2_HOOK = '''\
import sys
sys.stderr.write("blocked via exit 2\\n")
sys.exit(2)
'''

_STOP_HOOK = '''\
from fasthooks import HookApp, block
app = HookApp()

@app.on_stop()
def s(event):
    return block("not yet")

if __name__ == "__main__":
    app.run()
'''

_POST_HOOK = '''\
from fasthooks import HookApp
app = HookApp()

@app.post_tool("Edit")
def p(event):
    return None

if __name__ == "__main__":
    app.run()
'''

# A handler that takes `transcript: Transcript` must not crash on the empty
# temp transcript the smoke runner provides.
_TRANSCRIPT_HOOK = '''\
from fasthooks import HookApp
from fasthooks.depends import Transcript
app = HookApp()

@app.pre_tool("Bash")
def t(event, transcript: Transcript):
    _ = transcript.stats.input_tokens
    return None

if __name__ == "__main__":
    app.run()
'''


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


def test_envelope_matches_mockevent():
    """Drift guard: the CLI envelope must carry every field MockEvent emits.

    Keeps the smoke-test path and the programmatic test factory from diverging on
    hook-event field placement.
    """
    env = build_event(
        "PreToolUse", "Bash", {"command": "x"},
        cwd="/w", transcript_path="/t.jsonl",
    )
    mock_keys = set(MockEvent.bash("x").model_dump(by_alias=True, exclude_none=True))
    assert mock_keys <= set(env), f"envelope missing MockEvent keys: {mock_keys - set(env)}"


def test_deny_via_stdout_json(tmp_path):
    """A hook that denies via deny() surfaces the decision JSON; CLI exits 0."""
    hook = _write(tmp_path, "hooks.py", _DENY_HOOK)
    result = runner.invoke(
        app, ["test", str(hook), "-e", "PreToolUse:Bash", "-i", '{"command":"rm -rf /"}']
    )
    assert result.exit_code == 0, result.output
    assert "deny" in result.output
    assert "Dangerous command blocked" in result.output


def test_allowed_when_safe(tmp_path):
    """A non-matching command produces no output -> reported as allowed."""
    hook = _write(tmp_path, "hooks.py", _DENY_HOOK)
    result = runner.invoke(
        app, ["test", str(hook), "-i", '{"command":"ls -la"}']  # default event PreToolUse:Bash
    )
    assert result.exit_code == 0, result.output
    assert "allowed" in result.output


def test_block_via_exit_2(tmp_path):
    """The exit-2 protocol path (block + stderr) is interpreted, not dropped."""
    hook = _write(tmp_path, "exit2.py", _EXIT2_HOOK)
    result = runner.invoke(app, ["test", str(hook), "-i", '{"command":"x"}'])
    assert result.exit_code == 0, result.output  # smoke test ran; hook blocked as designed
    assert "blocked" in result.output
    assert "blocked via exit 2" in result.output


def test_stop_event_blocks(tmp_path):
    """A Stop hook returning block() round-trips through the Stop envelope."""
    hook = _write(tmp_path, "stop.py", _STOP_HOOK)
    result = runner.invoke(app, ["test", str(hook), "-e", "Stop"])
    assert result.exit_code == 0, result.output
    assert "block" in result.output
    assert "not yet" in result.output


def test_post_tool_use_event_runs(tmp_path):
    """The documented PostToolUse:Edit envelope parses and runs."""
    hook = _write(tmp_path, "post.py", _POST_HOOK)
    result = runner.invoke(
        app, ["test", str(hook), "-e", "PostToolUse:Edit", "-i", '{"file_path":"x.py"}']
    )
    assert result.exit_code == 0, result.output
    assert "allowed" in result.output


def test_transcript_di_handler_does_not_crash(tmp_path):
    """A handler taking `transcript: Transcript` runs against the empty transcript."""
    hook = _write(tmp_path, "trans.py", _TRANSCRIPT_HOOK)
    result = runner.invoke(app, ["test", str(hook), "-i", '{"command":"ls"}'])
    assert result.exit_code == 0, result.output
    assert "allowed" in result.output


def test_missing_file_errors(tmp_path):
    result = runner.invoke(app, ["test", str(tmp_path / "nope.py")])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_bad_input_json_errors(tmp_path):
    hook = _write(tmp_path, "hooks.py", _DENY_HOOK)
    result = runner.invoke(app, ["test", str(hook), "-i", "{not json"])
    assert result.exit_code == 1
    assert "not valid JSON" in result.output
