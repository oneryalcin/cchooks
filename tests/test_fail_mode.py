"""Fail-mode behavior: what happens to the action when a handler *crashes*.

These test BEHAVIOR (the synthesized response), not declaration. The prior gap
was that fail_mode="closed" was declared on strategies but never enforced — a
crashed guard always failed open. For a guardrail library that's the scariest
default, so it's a first-class test target.
"""
from __future__ import annotations

from fasthooks import HookApp
from fasthooks.blueprint import Blueprint
from fasthooks.strategies.base import Strategy
from fasthooks.testing import MockEvent, TestClient


def _raiser():
    """Return a *fresh* crashing handler.

    Each test uses its own function object: fail_mode is stashed as a function
    attribute, so reusing one shared function across registrations would let one
    test's tag leak into another (and mirrors a real gotcha — registering the
    same function with two fail_modes, last one wins).
    """

    def boom(event):
        raise RuntimeError("kaboom")

    return boom


# ── app-level default ────────────────────────────────────────────────────────

def test_open_is_default_crash_allows():
    """Default fail_mode is open: a crashed pre_tool handler lets the tool run."""
    app = HookApp()
    app.pre_tool("Bash")(_raiser())
    assert TestClient(app).send(MockEvent.bash(command="ls")) is None


def test_app_closed_crash_denies_pre_tool():
    """fail_mode='closed' turns a crashed PreToolUse handler into a deny."""
    app = HookApp(fail_mode="closed")
    app.pre_tool("Bash")(_raiser())
    response = TestClient(app).send(MockEvent.bash(command="ls"))
    assert response is not None
    assert response.decision == "deny"


# ── per-handler override (both directions) ───────────────────────────────────

def test_per_handler_closed_overrides_app_open():
    app = HookApp()  # open
    app.pre_tool("Bash", fail_mode="closed")(_raiser())
    response = TestClient(app).send(MockEvent.bash(command="ls"))
    assert response is not None and response.decision == "deny"


def test_per_handler_open_overrides_app_closed():
    app = HookApp(fail_mode="closed")
    app.pre_tool("Bash", fail_mode="open")(_raiser())
    assert TestClient(app).send(MockEvent.bash(command="ls")) is None


# ── event-appropriate blocking response ──────────────────────────────────────

def test_closed_stop_blocks():
    """Stop has no deny; closed must emit block (force-continue), not deny."""
    app = HookApp(fail_mode="closed")
    app.on_stop()(_raiser())
    response = TestClient(app).send(MockEvent.stop())
    assert response is not None and response.decision == "block"


def test_closed_permission_denies_with_permission_shape():
    """PermissionRequest must use the permission response, not a bare deny()."""
    app = HookApp(fail_mode="closed")
    app.on_permission("Bash")(_raiser())
    response = TestClient(app).send(MockEvent.permission_bash(command="ls"))
    assert response is not None
    # PermissionHookResponse carries behavior, not decision
    assert getattr(response, "behavior", None) == "deny"


def test_closed_non_blocking_event_stays_open():
    """SessionStart has no block semantics: closed still fails open, no crash."""
    app = HookApp(fail_mode="closed")
    app.on_session_start()(_raiser())
    assert TestClient(app).send(MockEvent.session_start()) is None


# ── DI miss (a crash via wiring, not handler body) ───────────────────────────

def test_closed_di_miss_denies():
    """Annotating a non-injectable param raises TypeError at call; closed denies."""

    class NotInjectable: ...

    def handler(event, dep: NotInjectable):  # dep can't be resolved -> TypeError
        return None

    app = HookApp(fail_mode="closed")
    app.pre_tool("Bash")(handler)
    response = TestClient(app).send(MockEvent.bash(command="ls"))
    assert response is not None and response.decision == "deny"


# ── no regression on the happy path ──────────────────────────────────────────

def test_closed_does_not_affect_successful_handler():
    """A handler that doesn't crash is untouched by fail_mode."""
    app = HookApp(fail_mode="closed")

    @app.pre_tool("Bash")
    def ok(event):
        return None  # allow

    assert TestClient(app).send(MockEvent.bash(command="ls")) is None


# ── strategy propagation (the broken promise) ────────────────────────────────

class _ClosedStrategy(Strategy):
    class Meta:
        name = "closed-strat"
        version = "1.0.0"
        hooks = ["on_stop"]
        fail_mode = "closed"

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("closed")
        bp.on_stop()(_raiser())
        return bp


class _OpenStrategy(Strategy):
    class Meta:
        name = "open-strat"
        version = "1.0.0"
        hooks = ["on_stop"]  # fail_mode defaults to "open"

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("open")
        bp.on_stop()(_raiser())
        return bp


def test_closed_strategy_blocks_on_error():
    """CleanState-style 'closed' strategy now actually blocks when it crashes."""
    app = HookApp()  # app default open
    app.include_strategy(_ClosedStrategy())
    response = TestClient(app).send(MockEvent.stop())
    assert response is not None and response.decision == "block"


def test_strategy_fail_mode_is_authoritative_over_app():
    """A strategy's own (default open) mode wins over a closed app default."""
    app = HookApp(fail_mode="closed")
    app.include_strategy(_OpenStrategy())
    assert TestClient(app).send(MockEvent.stop()) is None
