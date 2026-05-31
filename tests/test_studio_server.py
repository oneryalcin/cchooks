"""Studio FastAPI server tests (needs the `studio` extra + httpx TestClient)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="studio extra not installed")
from starlette.testclient import TestClient  # noqa: E402

from fasthooks.studio.server import create_app  # noqa: E402

_SCHEMA = (
    "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "event_type TEXT NOT NULL, hook_id TEXT NOT NULL, timestamp REAL NOT NULL, "
    "session_id TEXT NOT NULL, hook_event_name TEXT NOT NULL, tool_name TEXT, "
    "handler_name TEXT, duration_ms REAL, decision TEXT, reason TEXT, "
    "input_preview TEXT, error_type TEXT, error_message TEXT, skip_reason TEXT)"
)


def _seed(db_path: Path, decisions: list[str]) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    for dec in decisions:
        conn.execute(
            "INSERT INTO events (event_type,hook_id,timestamp,session_id,"
            "hook_event_name,decision) VALUES ('handler_end','h',1.0,'s','PreToolUse',?)",
            (dec,),
        )
    conn.commit()
    conn.close()


def test_stats_folds_approve_into_allow_on_read(tmp_path: Path):
    """The reader must show one vocabulary even on a pre-migration DB.

    The read-only studio server never runs the observer's one-time migration, so
    get_stats folds the deprecated 'approve' into 'allow' in its aggregation —
    otherwise a human looking at the decisions breakdown sees two buckets for one
    concept (the exact symptom of #26).
    """
    db = tmp_path / "studio.db"
    _seed(db, ["approve", "approve", "allow", "deny", "block"])

    stats = TestClient(create_app(db)).get("/api/stats").json()

    assert stats["decisions"] == {"allow": 3, "deny": 1, "block": 1}
    assert "approve" not in stats["decisions"]
    # deny_rate counts deny + block over all decisions
    assert stats["decisions"]["deny"] + stats["decisions"]["block"] == 2


def test_stats_empty_db(tmp_path: Path):
    db = tmp_path / "studio.db"
    _seed(db, [])
    stats = TestClient(create_app(db)).get("/api/stats").json()
    assert stats["decisions"] == {}
    assert stats["deny_rate"] == 0
