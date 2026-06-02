"""Recipes: engine behavior, scaffolding, and fail-open discovery."""
from __future__ import annotations

from rich.console import Console

from fasthooks import HookApp
from fasthooks.recipes import (
    evidence_gate,
    include_recipes,
    kill_switch,
    scaffold_for,
    steer,
)
from fasthooks.testing import MockEvent, TestClient


def _pre_tool(cwd: str) -> dict:
    return {
        "hook_event_name": "PreToolUse", "session_id": "s", "cwd": cwd,
        "tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_use_id": "t",
    }


# ── Engines ──────────────────────────────────────────────────────────────────


def test_kill_switch_denies_only_while_sentinel_present(tmp_path):
    app = HookApp()
    app.include(kill_switch(sentinel="AGENT_STOP"))
    client = TestClient(app)

    assert client.send_raw(_pre_tool(str(tmp_path))) is None  # absent -> allow

    (tmp_path / "AGENT_STOP").write_text("")
    response = client.send_raw(_pre_tool(str(tmp_path)))
    assert response is not None and response.decision == "deny"

    (tmp_path / "AGENT_STOP").unlink()
    assert client.send_raw(_pre_tool(str(tmp_path))) is None  # resumes


def test_steer_injects_then_clears(tmp_path):
    app = HookApp()
    app.include(steer(sentinel="STEER.md"))
    client = TestClient(app)
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s",
               "cwd": str(tmp_path), "prompt": "hi"}

    assert client.send_raw(payload) is None  # no file -> no-op

    steer_file = tmp_path / "STEER.md"
    steer_file.write_text("focus on the failing test")
    response = client.send_raw(payload)
    assert response is not None
    assert "focus on the failing test" in response.to_json()
    assert not steer_file.exists()  # delivered exactly once


def test_evidence_gate_requires_evidence_read_before_results_write(tmp_path):
    """Default-FAIL: the results file can't be written until evidence is Read.

    Needs a real state_dir — the read tracked in one hook invocation must be
    visible to the write gate in the next (separate process in production).
    """
    app = HookApp(state_dir=str(tmp_path))
    app.include(evidence_gate(results_file="test-results.json"))
    c = TestClient(app)

    # 1. write without evidence -> denied
    r = c.send(MockEvent.write("test-results.json", "{}"))
    assert r is not None and r.decision == "deny"

    # 2. read a screenshot (evidence) -> the next write is allowed
    c.send(MockEvent.read("screenshots/feature-1.png"))
    assert c.send(MockEvent.write("test-results.json", "{}")) is None

    # 3. evidence consumed -> the following write is denied again
    assert c.send(MockEvent.write("test-results.json", "{}")).decision == "deny"

    # 4. a non-results write is never gated
    assert c.send(MockEvent.write("src/app.py", "x = 1")) is None

    # 5. a non-evidence read (no screenshot/console marker) does not unlock
    c.send(MockEvent.read("README.md"))
    assert c.send(MockEvent.write("test-results.json", "{}")).decision == "deny"


# ── Scaffolding ──────────────────────────────────────────────────────────────


def test_scaffold_default_is_derived_from_engine(tmp_path):
    # Guards against the scaffold's default (and knob name) drifting from the
    # factory signature.
    assert 'kill_switch(sentinel="AGENT_STOP")' in scaffold_for("kill-switch")
    assert 'steer(sentinel="STEER.md")' in scaffold_for("steer")
    assert 'evidence_gate(results_file="test-results.json")' in scaffold_for("evidence-gate")


# ── Discovery ────────────────────────────────────────────────────────────────


def test_include_recipes_loads_scaffolded_files(tmp_path):
    rdir = tmp_path / "recipes"
    rdir.mkdir()
    (rdir / "kill_switch.py").write_text(scaffold_for("kill-switch"))
    (rdir / "steer.py").write_text(scaffold_for("steer"))

    app = HookApp()
    loaded = include_recipes(app, str(rdir))
    assert set(loaded) == {"kill_switch", "steer"}

    # And the loaded kill-switch actually works
    client = TestClient(app)
    (tmp_path / "AGENT_STOP").write_text("")
    assert client.send_raw(_pre_tool(str(tmp_path))).decision == "deny"


def test_include_recipes_missing_dir_is_empty(tmp_path):
    assert include_recipes(HookApp(), str(tmp_path / "nope")) == []


def test_include_recipes_fails_open_on_broken_recipe(tmp_path, capsys):
    """A broken recipe file must be skipped, not crash discovery — the good
    recipes (and the server) must still load."""
    rdir = tmp_path / "recipes"
    rdir.mkdir()
    (rdir / "kill_switch.py").write_text(scaffold_for("kill-switch"))
    (rdir / "broken.py").write_text("this is not valid python !!!\n")
    (rdir / "no_recipe.py").write_text("x = 1  # no `recipe` defined\n")

    app = HookApp()
    loaded = include_recipes(app, str(rdir))

    assert loaded == ["kill_switch"]  # good one survived
    err = capsys.readouterr().err
    assert "broken.py" in err
    assert "no_recipe.py" in err


# ── `fasthooks add` ──────────────────────────────────────────────────────────


def test_add_scaffolds_recipe_and_never_touches_settings(tmp_path):
    """The acceptance property: adding recipes (even a 2nd) never writes
    settings.json — so it needs no Claude Code restart."""
    from fasthooks.cli.commands.add import run_add

    rdir = tmp_path / ".claude" / "hooks" / "recipes"
    console = Console()

    assert run_add("kill-switch", str(rdir), False, console) == 0
    assert (rdir / "kill_switch.py").exists()

    # Adding a SECOND recipe
    assert run_add("steer", str(rdir), False, console) == 0
    assert (rdir / "steer.py").exists()

    # No settings file was created anywhere — add is settings-neutral.
    assert list(tmp_path.rglob("settings*.json")) == []


def test_add_unknown_recipe_errors(tmp_path):
    from fasthooks.cli.commands.add import run_add

    code = run_add("does-not-exist", str(tmp_path), False, Console())
    assert code == 1


def test_add_is_idempotent_without_force(tmp_path):
    from fasthooks.cli.commands.add import run_add

    rdir = tmp_path / "recipes"
    console = Console()
    assert run_add("kill-switch", str(rdir), False, console) == 0
    edited = rdir / "kill_switch.py"
    edited.write_text("# user edits\nrecipe = None\n")

    # Re-adding without --force must not clobber the user's edits
    assert run_add("kill-switch", str(rdir), False, console) == 0
    assert edited.read_text() == "# user edits\nrecipe = None\n"
