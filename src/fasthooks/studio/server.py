"""FastAPI server for FastHooks Studio."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fasthooks.studio.connection_manager import ConnectionManager
from fasthooks.transcript import Transcript

# Static files directory (bundled frontend)
STATIC_DIR = Path(__file__).parent / "static"


def create_app(db_path: Path) -> FastAPI:
    """Create FastAPI app with all routes."""
    app = FastAPI(title="FastHooks Studio", version="0.1.0")

    # CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    manager = ConnectionManager()

    def get_db() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    # Sessions endpoints
    @app.get("/api/sessions")
    def list_sessions() -> list[dict[str, Any]]:
        """List all sessions with summary stats."""
        conn = get_db()
        rows = conn.execute("""
            SELECT
                session_id,
                COUNT(*) as event_count,
                COUNT(DISTINCT hook_id) as hook_count,
                MIN(timestamp) as first_seen,
                MAX(timestamp) as last_seen,
                json_extract(
                    (SELECT input_preview FROM events e2
                     WHERE e2.session_id = events.session_id
                     AND input_preview IS NOT NULL LIMIT 1),
                    '$.transcript_path'
                ) as transcript_path
            FROM events
            GROUP BY session_id
            ORDER BY last_seen DESC
        """).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        """Get session detail."""
        conn = get_db()
        row = conn.execute("""
            SELECT
                session_id,
                COUNT(*) as event_count,
                COUNT(DISTINCT hook_id) as hook_count,
                MIN(timestamp) as first_seen,
                MAX(timestamp) as last_seen,
                json_extract(
                    (SELECT input_preview FROM events e2
                     WHERE e2.session_id = ?
                     AND input_preview IS NOT NULL LIMIT 1),
                    '$.transcript_path'
                ) as transcript_path
            FROM events
            WHERE session_id = ?
        """, (session_id, session_id)).fetchone()
        conn.close()

        if not row or not row["session_id"]:
            raise HTTPException(status_code=404, detail="Session not found")

        return dict(row)

    @app.get("/api/sessions/{session_id}/conversation")
    def get_conversation(session_id: str) -> dict[str, Any]:
        """Get full conversation with hooks inline."""
        conn = get_db()

        # Get transcript path
        row = conn.execute("""
            SELECT json_extract(input_preview, '$.transcript_path') as path
            FROM events
            WHERE session_id = ? AND input_preview IS NOT NULL
            LIMIT 1
        """, (session_id,)).fetchone()

        if not row or not row["path"]:
            raise HTTPException(status_code=404, detail="Transcript not found")

        transcript_path = row["path"]

        # Check if transcript file exists
        if not Path(transcript_path).exists():
            raise HTTPException(
                status_code=404,
                detail=f"Transcript file not found: {transcript_path}"
            )

        # Load transcript
        transcript = Transcript(transcript_path)

        # Build tool_use_id -> hook_id map
        tool_use_hooks = conn.execute("""
            SELECT
                json_extract(input_preview, '$.tool_use_id') as tool_use_id,
                hook_id
            FROM events
            WHERE session_id = ? AND input_preview IS NOT NULL
        """, (session_id,)).fetchall()

        tool_hook_map = {row["tool_use_id"]: row["hook_id"] for row in tool_use_hooks}

        # Build entries list
        entries: list[dict[str, Any]] = []

        for entry in transcript.all_entries:
            etype = type(entry).__name__

            if etype == "UserMessage":
                content = entry.content if hasattr(entry, "content") else []
                if isinstance(content, list) and content:
                    first = content[0]
                    if hasattr(first, "type") and first.type == "tool_result":
                        entries.append({
                            "type": "tool_result",
                            "tool_use_id": first.tool_use_id,
                            "content": first.content if hasattr(first, "content") else str(first),
                        })
                    else:
                        entries.append({
                            "type": "user_message",
                            "content": str(first) if not isinstance(first, str) else first,
                        })
                elif isinstance(content, str):
                    entries.append({
                        "type": "user_message",
                        "content": content,
                    })

            elif etype == "AssistantMessage":
                content = entry.content if hasattr(entry, "content") else []
                for block in content:
                    btype = getattr(block, "type", None)

                    if btype == "thinking":
                        entries.append({
                            "type": "thinking",
                            "content": block.thinking if hasattr(block, "thinking") else "",
                        })
                    elif btype == "text":
                        entries.append({
                            "type": "text",
                            "content": block.text if hasattr(block, "text") else "",
                        })
                    elif btype == "tool_use":
                        tool_use_id = block.id
                        hook_id = tool_hook_map.get(tool_use_id)

                        hooks_data = None
                        if hook_id:
                            # Get all events for this hook
                            events = conn.execute("""
                                SELECT event_type, handler_name, duration_ms,
                                       decision, reason, input_preview
                                FROM events
                                WHERE hook_id = ?
                                ORDER BY id
                            """, (hook_id,)).fetchall()

                            handlers = []
                            total_duration = None
                            hook_event_name = None
                            input_preview = None

                            for e in events:
                                if e["event_type"] == "hook_start":
                                    if e["input_preview"]:
                                        input_preview = json.loads(e["input_preview"])
                                        hook_event_name = input_preview.get("hook_event_name")
                                elif e["event_type"] == "hook_end":
                                    total_duration = e["duration_ms"]
                                elif e["event_type"] == "handler_end":
                                    handlers.append({
                                        "name": e["handler_name"],
                                        "decision": e["decision"],
                                        "duration_ms": e["duration_ms"],
                                        "reason": e["reason"],
                                    })
                                elif e["event_type"] == "handler_skip":
                                    handlers.append({
                                        "name": e["handler_name"],
                                        "decision": "skip",
                                        "duration_ms": None,
                                        "reason": e["reason"],
                                    })

                            hooks_data = {
                                "hook_id": hook_id,
                                "hook_event_name": hook_event_name,
                                "total_duration_ms": total_duration,
                                "handlers": handlers,
                                "input_preview": input_preview,
                            }

                        entries.append({
                            "type": "tool_use",
                            "id": tool_use_id,
                            "name": block.name,
                            "input": block.input if hasattr(block, "input") else {},
                            "hooks": hooks_data,
                        })

        conn.close()

        # Stats
        ts = transcript.stats
        stats = {
            "tokens_in": ts.input_tokens if hasattr(ts, "input_tokens") else 0,
            "tokens_out": ts.output_tokens if hasattr(ts, "output_tokens") else 0,
            "messages": ts.messages if hasattr(ts, "messages") else 0,
            "turns": ts.turns if hasattr(ts, "turns") else 0,
            "tool_calls": len(transcript.tool_uses),
            "hooks_fired": len(tool_hook_map),
        }

        return {
            "session_id": session_id,
            "transcript_path": transcript_path,
            "entries": entries,
            "stats": stats,
        }

    @app.get("/api/sessions/{session_id}/hooks")
    def get_session_hooks(session_id: str) -> list[dict[str, Any]]:
        """Get all hook events for a session, grouped by hook_id."""
        conn = get_db()
        rows = conn.execute("""
            SELECT * FROM events
            WHERE session_id = ?
            ORDER BY id
        """, (session_id,)).fetchall()
        conn.close()

        # Group by hook_id
        hooks: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            hook_id = row["hook_id"]
            if hook_id not in hooks:
                hooks[hook_id] = []
            hooks[hook_id].append(dict(row))

        return [{"hook_id": k, "events": v} for k, v in hooks.items()]

    @app.get("/api/hooks/{hook_id}")
    def get_hook(hook_id: str) -> dict[str, Any]:
        """Get single hook detail."""
        conn = get_db()
        rows = conn.execute("""
            SELECT * FROM events
            WHERE hook_id = ?
            ORDER BY id
        """, (hook_id,)).fetchall()
        conn.close()

        if not rows:
            raise HTTPException(status_code=404, detail="Hook not found")

        events = [dict(row) for row in rows]
        input_preview = None
        for e in events:
            if e.get("input_preview"):
                input_preview = json.loads(e["input_preview"])
                break

        return {
            "hook_id": hook_id,
            "events": events,
            "input_preview": input_preview,
        }

    @app.get("/api/stats")
    def get_stats() -> dict[str, Any]:
        """Get global statistics."""
        conn = get_db()

        total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        total_hooks = conn.execute("SELECT COUNT(DISTINCT hook_id) FROM events").fetchone()[0]
        total_sessions = conn.execute("SELECT COUNT(DISTINCT session_id) FROM events").fetchone()[0]

        # Decision breakdown
        decisions = conn.execute("""
            SELECT decision, COUNT(*) as count
            FROM events
            WHERE event_type = 'handler_end' AND decision IS NOT NULL
            GROUP BY decision
        """).fetchall()

        decision_counts = {row["decision"]: row["count"] for row in decisions}

        # Average handler duration
        avg_duration = conn.execute("""
            SELECT AVG(duration_ms) FROM events
            WHERE event_type = 'handler_end' AND duration_ms IS NOT NULL
        """).fetchone()[0]

        conn.close()

        total_decisions = sum(decision_counts.values())
        deny_count = decision_counts.get("deny", 0) + decision_counts.get("block", 0)

        return {
            "total_events": total_events,
            "total_hooks": total_hooks,
            "total_sessions": total_sessions,
            "decisions": decision_counts,
            "deny_rate": deny_count / total_decisions if total_decisions > 0 else 0,
            "avg_handler_duration_ms": avg_duration,
        }

    # Attach notify_clients to app for file watcher
    async def notify_clients(message: str) -> None:
        await manager.broadcast(message)

    app.notify_clients = notify_clients  # type: ignore[attr-defined]

    # Serve static frontend if bundled
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        # Serve static assets (js, css, etc.)
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        # Catch-all for SPA routing - serve index.html
        @app.get("/{path:path}")
        async def serve_spa(path: str) -> FileResponse:
            # Check if it's a static file
            file_path = STATIC_DIR / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            # Otherwise serve index.html for SPA routing
            return FileResponse(STATIC_DIR / "index.html")

        @app.get("/")
        async def serve_index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app
