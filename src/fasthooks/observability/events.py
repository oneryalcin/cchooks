"""Observability event models (Pydantic v2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# =============================================================================
# HookApp Observability Events
# =============================================================================


class HookObservabilityEvent(BaseModel):
    """Event emitted by HookApp observability system.

    Passed to observers. Immutable by convention (don't mutate).
    Use .model_dump() for raw dict access.
    """

    # Identity
    event_type: str  # hook_start, handler_end, etc.
    hook_id: str  # UUID for this hook invocation
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Context
    session_id: str  # From Claude Code input
    hook_event_name: str  # PreToolUse, PostToolUse, Stop, etc.
    tool_name: str | None = None  # Bash, Write, etc. (None for Stop/lifecycle)
    handler_name: str | None = None  # Function name (None for hook-level events)

    # Timing (for *_end events only)
    duration_ms: float | None = None  # Handler execution time (excludes DI)

    # Decision (for handler_end, hook_end)
    decision: str | None = None  # "allow", "deny", "block"
    reason: str | None = None  # Denial reason if any

    # Content (truncated)
    input_preview: str | None = None  # First 4096 chars of hook input JSON

    # Error (for *_error events only)
    error_type: str | None = None  # Exception class name
    error_message: str | None = None  # str(exception)

    # Skip info (for handler_skip only)
    skip_reason: str | None = None  # "early deny from {handler}", "guard failed"

    model_config = {"ser_json_timedelta": "iso8601"}


# =============================================================================
# Strategy Observability Events (existing)
# =============================================================================


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
