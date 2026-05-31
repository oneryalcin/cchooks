"""Decision-vocabulary unification (#26).

One canonical vocabulary (allow/deny/block/ask) is recorded across the
observability boundary, regardless of which code path produced the row. The
deprecated "approve" is folded into "allow" (the modern protocol term).
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from fasthooks import HookApp, allow, ask, block, deny, deny_permission
from fasthooks.observability import Decision, EventCapture, normalize_decision
from fasthooks.observability.events import HookObservabilityEvent
from fasthooks.observability.observers.sqlite import SQLiteObserver
from fasthooks.testing import MockEvent, TestClient


def _handler_end_decision(response: object) -> object:
    """Record the handler_end decision for a handler returning ``response``."""
    app = HookApp()
    obs = EventCapture()
    app.add_observer(obs)

    @app.pre_tool("Bash")
    def handler(event):
        return response

    TestClient(app).send(MockEvent.bash("ls"))
    ends = [e for e in obs.events if e.event_type == "handler_end"]
    return ends[0].decision


@pytest.mark.parametrize(
    "response, expected",
    [
        (None, "allow"),  # handler returned nothing -> allowed
        (allow(), "allow"),  # allow() decision is "approve" internally -> "allow"
        (deny("x"), "deny"),
        (block("x"), "block"),
        (ask("x"), "ask"),
    ],
)
def test_handler_end_records_canonical_vocabulary(response, expected):
    assert _handler_end_decision(response) == expected
    # never the deprecated term
    assert _handler_end_decision(response) != "approve"


# ── normalize_decision unit cases ────────────────────────────────────────────

def test_permission_deny_records_deny_not_allow():
    """PermissionHookResponse uses .behavior; a deny must not default to allow."""
    assert normalize_decision(deny_permission("nope")) is Decision.DENY


def test_approve_is_folded_into_allow():
    assert normalize_decision("approve") is Decision.ALLOW
    assert normalize_decision(allow(), default=Decision.ALLOW) is Decision.ALLOW


def test_unknown_decision_passes_through_not_masked_as_allow():
    """A miswrite stays visible in the data rather than masquerading as allow."""
    assert normalize_decision("weird") == "weird"


def test_none_default_is_caller_controlled():
    assert normalize_decision(None) is None  # absent
    assert normalize_decision(None, default=Decision.ALLOW) is Decision.ALLOW


# ── model validator (crash-safe coercion at construction) ────────────────────

def test_event_validator_coerces_approve_to_allow():
    e = HookObservabilityEvent(
        event_type="handler_end",
        hook_id="h",
        session_id="s",
        hook_event_name="PreToolUse",
        decision="approve",
    )
    assert e.decision is Decision.ALLOW


def test_event_validator_never_raises_on_stray_value():
    """Observability is constructed outside a try in _emit; it must not raise."""
    e = HookObservabilityEvent(
        event_type="handler_end",
        hook_id="h",
        session_id="s",
        hook_event_name="PreToolUse",
        decision="something_unexpected",
    )
    assert e.decision == "something_unexpected"  # surfaced, not crashed


# ── one-time SQLite migration ────────────────────────────────────────────────

def test_sqlite_migration_folds_approve_once():
    with tempfile.TemporaryDirectory() as d:
        dbp = Path(d) / "studio.db"
        conn = sqlite3.connect(dbp)
        conn.execute(
            "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "event_type TEXT NOT NULL, hook_id TEXT NOT NULL, timestamp REAL NOT NULL, "
            "session_id TEXT NOT NULL, hook_event_name TEXT NOT NULL, tool_name TEXT, "
            "handler_name TEXT, duration_ms REAL, decision TEXT, reason TEXT, "
            "input_preview TEXT, error_type TEXT, error_message TEXT, skip_reason TEXT)"
        )
        for dec in ("approve", "approve", "deny"):
            conn.execute(
                "INSERT INTO events (event_type,hook_id,timestamp,session_id,"
                "hook_event_name,decision) VALUES ('handler_end','h',1.0,'s','PreToolUse',?)",
                (dec,),
            )
        conn.commit()
        conn.close()

        SQLiteObserver(db_path=dbp)  # triggers gated migration

        conn = sqlite3.connect(dbp)
        counts = dict(conn.execute("SELECT decision, COUNT(*) FROM events GROUP BY decision"))
        assert counts == {"allow": 2, "deny": 1}
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1

        # gated: a new approve inserted later is NOT re-migrated
        conn.execute(
            "INSERT INTO events (event_type,hook_id,timestamp,session_id,"
            "hook_event_name,decision) VALUES ('handler_end','h',1.0,'s','PreToolUse','approve')"
        )
        conn.commit()
        conn.close()
        SQLiteObserver(db_path=dbp)
        conn = sqlite3.connect(dbp)
        counts = dict(conn.execute("SELECT decision, COUNT(*) FROM events GROUP BY decision"))
        assert counts["approve"] == 1  # untouched after the one-time migration
