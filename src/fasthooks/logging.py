"""Built-in JSONL logging for fasthooks."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EventLogger:
    """JSONL event logger that writes to session-specific files.

    Logs all hook events to `{log_dir}/hooks-{session_id}.jsonl`
    and maintains a `latest.jsonl` symlink.
    """

    def __init__(self, log_dir: str | Path):
        """Initialize EventLogger.

        Args:
            log_dir: Directory to write log files
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, data: dict[str, Any]) -> None:
        """Log an event to the appropriate session file.

        Args:
            data: Raw hook input data
        """
        session_id = data.get("session_id", "unknown")
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build log entry
        entry = self._build_entry(data, ts)

        # Write to session file
        session_file = self.log_dir / f"hooks-{session_id}.jsonl"
        with open(session_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

        # Update latest.jsonl symlink
        self._update_symlink(session_id)

    def _build_entry(self, data: dict[str, Any], ts: str) -> dict[str, Any]:
        """Build a log entry with flattened fields.

        Args:
            data: Raw hook input data
            ts: Timestamp string

        Returns:
            Flattened log entry dict
        """
        event = data.get("hook_event_name", "unknown")
        tool_name = data.get("tool_name")
        tool_input = data.get("tool_input", {})

        entry: dict[str, Any] = {
            "ts": ts,
            "session_id": data.get("session_id"),
            "event": event,
            "cwd": data.get("cwd"),
            "permission_mode": data.get("permission_mode"),
        }

        # Tool events
        if tool_name:
            entry["tool_name"] = tool_name
            entry["tool_input"] = tool_input

            # Flatten tool-specific fields for easier querying
            if tool_name == "Bash":
                entry["bash_command"] = tool_input.get("command")
                entry["bash_description"] = tool_input.get("description")
            elif tool_name in ("Write", "Edit", "Read"):
                entry["file_path"] = tool_input.get("file_path")
            elif tool_name == "Grep":
                entry["grep_pattern"] = tool_input.get("pattern")
            elif tool_name == "Glob":
                entry["glob_pattern"] = tool_input.get("pattern")
            elif tool_name == "Task":
                entry["subagent_type"] = tool_input.get("subagent_type")
                entry["subagent_model"] = tool_input.get("model")
            elif tool_name == "WebSearch":
                entry["search_query"] = tool_input.get("query")
            elif tool_name == "WebFetch":
                entry["fetch_url"] = tool_input.get("url")

        # Tool response (PostToolUse)
        if data.get("tool_response"):
            entry["tool_response"] = data["tool_response"]
            # Extract agent_id for Task tool
            if tool_name == "Task":
                entry["agent_id"] = data["tool_response"].get("agentId")

        # Lifecycle event fields
        if event == "UserPromptSubmit":
            entry["prompt"] = data.get("prompt")
        elif event == "Stop":
            entry["stop_hook_active"] = data.get("stop_hook_active")
        elif event == "SubagentStop":
            entry["agent_id"] = data.get("agent_id")
            entry["stop_hook_active"] = data.get("stop_hook_active")
        elif event == "SessionStart":
            entry["source"] = data.get("source")
            entry["transcript_path"] = data.get("transcript_path")
        elif event == "SessionEnd":
            entry["reason"] = data.get("reason")
        elif event == "PreCompact":
            entry["trigger"] = data.get("trigger")
        elif event == "Notification":
            entry["message"] = data.get("message")
            entry["notification_type"] = data.get("notification_type")

        # Remove None values
        return {k: v for k, v in entry.items() if v is not None}

    def _update_symlink(self, session_id: str) -> None:
        """Update latest.jsonl symlink to current session file."""
        latest = self.log_dir / "latest.jsonl"
        try:
            latest.unlink(missing_ok=True)
            latest.symlink_to(f"hooks-{session_id}.jsonl")
        except OSError:
            pass  # Best effort
