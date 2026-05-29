"""HTTP server transport (Claude Code 'http' hooks).

Drives HookApp._asgi_app directly with a mock ASGI scope/receive/send so the
tests need no running uvicorn — they verify the transport contract: the same
dispatch + JSON output as the stdin path, and fail-open on bad input.
"""
from __future__ import annotations

import json

import anyio

from fasthooks import HookApp, deny


def _drive(app: HookApp, body: bytes) -> tuple[int, bytes]:
    """Send one HTTP request body through the ASGI app; return (status, body)."""
    scope = {"type": "http", "method": "POST", "path": "/", "headers": []}
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
    assert json.loads(body) == {"decision": "deny", "reason": "blocked"}


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
