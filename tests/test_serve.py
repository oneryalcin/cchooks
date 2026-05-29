"""HTTP server transport (Claude Code 'http' hooks).

Drives HookApp._asgi_app directly with a mock ASGI scope/receive/send so the
tests need no running uvicorn — they verify the transport contract: the same
dispatch + JSON output as the stdin path, and fail-open on bad input.
"""
from __future__ import annotations

import json
import warnings

import anyio

from fasthooks import HookApp, deny


def _drive(
    app: HookApp, body: bytes, *, headers: list | None = None
) -> tuple[int, bytes]:
    """Send one HTTP request body through the ASGI app; return (status, body)."""
    scope = {"type": "http", "method": "POST", "path": "/", "headers": headers or []}
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    anyio.run(app._asgi_app, scope, receive, send)

    start = next(m for m in sent if m["type"] == "http.response.start")
    out = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], out


def _payload(**extra) -> bytes:
    data = {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/",
            "tool_name": "Bash", "tool_use_id": "t"}
    data.update(extra)
    return json.dumps(data).encode()


def test_serve_denies_and_returns_json():
    app = HookApp()

    @app.pre_tool("Bash")
    def guard(event):
        if "rm -rf /" in event.command:
            return deny("blocked")

    status, body = _drive(app, _payload(tool_input={"command": "rm -rf /"}))
    assert status == 200
    hso = json.loads(body)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert hso["permissionDecisionReason"] == "blocked"


def test_serve_allow_returns_empty_body():
    app = HookApp()

    @app.pre_tool("Bash")
    def guard(event):
        if "rm -rf /" in event.command:
            return deny("blocked")

    status, body = _drive(app, _payload(tool_input={"command": "ls"}))
    assert status == 200
    assert body == b""  # no decision -> empty 200 -> Claude Code proceeds


def test_serve_generic_event_over_http():
    app = HookApp()
    seen = {}

    @app.on("FileChanged")
    def on_change(event):
        seen["path"] = event.file_path

    body = json.dumps(
        {"hook_event_name": "FileChanged", "session_id": "s", "cwd": "/",
         "file_path": "/x.py"}
    ).encode()
    status, out = _drive(app, body)
    assert status == 200
    assert out == b""
    assert seen["path"] == "/x.py"


def test_serve_fails_open_on_malformed_json():
    """Bad input must not 500 — CC treats errors as non-blocking, so we return
    an empty 200 rather than risk stalling the agent loop."""
    app = HookApp()

    @app.pre_tool("Bash")
    def guard(event):
        return deny("should not run")

    status, body = _drive(app, b"{not valid json")
    assert status == 200
    assert body == b""


def test_serve_rejects_non_post():
    """Only POST is a valid hook delivery; other methods get 405."""
    app = HookApp()
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    anyio.run(app._asgi_app, scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 405


def test_serve_preserves_log_dir_audit_trail(tmp_path):
    """Server mode must log the raw event like the stdin path does."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # log_dir is deprecated
        app = HookApp(log_dir=str(tmp_path))

    @app.pre_tool("Bash")
    def noop(event):
        return None

    _drive(app, _payload(session_id="abc", tool_input={"command": "ls"}))

    log_file = tmp_path / "hooks-abc.jsonl"
    assert log_file.exists()
    logged = json.loads(log_file.read_text().strip())
    assert logged["event"] == "PreToolUse"


def test_serve_token_required_when_set():
    """With a token configured, only requests bearing it are dispatched."""
    app = HookApp()
    app._auth_token = "s3cret"

    @app.pre_tool("Bash")
    def guard(event):
        if "rm -rf /" in event.command:
            return deny("blocked")

    body = _payload(tool_input={"command": "rm -rf /"})

    # No header -> 401, handler never runs
    assert _drive(app, body)[0] == 401
    # Wrong token -> 401
    assert _drive(app, body, headers=[(b"authorization", b"Bearer nope")])[0] == 401
    # Correct token -> dispatched
    status, out = _drive(app, body, headers=[(b"authorization", b"Bearer s3cret")])
    assert status == 200
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_serve_no_token_means_open():
    """Without a token, requests are dispatched (current default)."""
    app = HookApp()

    @app.pre_tool("Bash")
    def guard(event):
        if "rm -rf /" in event.command:
            return deny("blocked")

    status, out = _drive(app, _payload(tool_input={"command": "rm -rf /"}))
    assert status == 200
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_serve_rejects_oversized_body():
    """A body over the cap is rejected with 413 (no memory exhaustion)."""
    app = HookApp()
    status, body = _drive(app, b"x" * (4 * 1024 * 1024 + 1))
    assert status == 413
    assert body == b""


def test_serve_refuses_non_loopback_without_token(monkeypatch):
    import pytest

    monkeypatch.delenv("FASTHOOKS_TOKEN", raising=False)
    app = HookApp()
    with pytest.raises(RuntimeError, match="non-loopback"):
        app.serve(host="0.0.0.0")


def test_reload_factory_rebuilds_app_from_env(tmp_path, monkeypatch):
    """The reload factory loads the hooks file fresh and applies the token —
    this is what lets uvicorn --reload pick up edits without a restart."""
    hooks = tmp_path / "h.py"
    hooks.write_text(
        "from fasthooks import HookApp\n"
        "app = HookApp()\n"
        "@app.pre_tool('Bash')\n"
        "def c(event):\n"
        "    return None\n"
    )
    monkeypatch.setenv("FASTHOOKS_HOOKS_PATH", str(hooks))
    monkeypatch.setenv("FASTHOOKS_TOKEN", "abc")

    from fasthooks.cli.commands.serve import _reload_asgi_factory

    asgi = _reload_asgi_factory()
    rebuilt_app = asgi.__self__  # bound method -> the HookApp
    assert rebuilt_app._auth_token == "abc"
    assert "Bash" in rebuilt_app._pre_tool_handlers


def test_serve_handles_lifespan():
    app = HookApp()
    events = iter(["lifespan.startup", "lifespan.shutdown"])
    sent: list[dict] = []

    async def receive():
        return {"type": next(events)}

    async def send(message):
        sent.append(message)

    anyio.run(app._asgi_app, {"type": "lifespan"}, receive, send)
    assert [m["type"] for m in sent] == [
        "lifespan.startup.complete",
        "lifespan.shutdown.complete",
    ]
