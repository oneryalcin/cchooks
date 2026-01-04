"""Observability event models (Pydantic v2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ObservabilityEvent(BaseModel):
    """Base event emitted by observability system."""

    # Correlation
    session_id: str
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Timing
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: float | None = None  # Set on hook_exit

    # Event type
    event_type: Literal["hook_enter", "hook_exit", "decision", "error", "custom"]

    # Context
    strategy_name: str
    hook_name: str  # e.g., "on_stop", "pre_tool:Bash"

    # Payload (verbosity-dependent)
    payload: dict[str, Any] = Field(default_factory=dict)

    # For custom events
    custom_event_type: str | None = None

    model_config = {"ser_json_timedelta": "iso8601"}


class DecisionEvent(ObservabilityEvent):
    """Emitted when strategy returns a decision."""

    event_type: Literal["decision"] = "decision"
    decision: Literal["approve", "deny", "block"]
    reason: str | None = None
    message: str | None = None  # Injected message
    dry_run: bool = False  # True if dry-run mode


class ErrorEvent(ObservabilityEvent):
    """Emitted when strategy throws an exception."""

    event_type: Literal["error"] = "error"
    error_type: str  # Exception class name
    error_message: str
    traceback: str | None = None  # Only in verbose mode
