"""Observability event models (Pydantic v2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal, cast, overload

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Decision vocabulary
# =============================================================================


class Decision(str, Enum):
    """The canonical decision vocabulary recorded across observability.

    "allow" is the modern Claude Code term (``permissionDecision: allow/deny/ask``);
    "approve" is the deprecated wire value that maps to "allow". We record the
    modern term everywhere so a single query works regardless of which code path
    produced the row. ``HookResponse.decision`` keeps "approve" internally (it
    maps correctly at the protocol layer) — only the observability record is
    normalized.
    """

    ALLOW = "allow"
    DENY = "deny"
    BLOCK = "block"
    ASK = "ask"


@overload
def normalize_decision(value: object, *, default: Decision) -> Decision | str: ...
@overload
def normalize_decision(value: object, *, default: None = ...) -> Decision | str | None: ...
def normalize_decision(value: object, *, default: Decision | None = None) -> Decision | str | None:
    """Map a hook response, a raw decision string, or None to :class:`Decision`.

    Accepts a response object (reads ``.behavior`` for permission responses,
    else ``.decision``), a raw string, an existing :class:`Decision`, or None.
    ``approve`` is folded into ``allow``. An *unrecognized* string is passed
    through unchanged rather than masked as ``allow`` — a miswrite should be
    visible in the data, not silently recorded as the most permissive outcome.

    ``default`` is returned when there is no decision to read (None, or a
    response like ``context()`` that carries neither). Callers choose what "no
    decision" means: ``Decision.ALLOW`` for per-handler records (a handler that
    returned nothing allowed), or None for hook-level records (absent).
    """
    if value is None:
        return default
    behavior = getattr(value, "behavior", None)
    if behavior == "deny":
        return Decision.DENY
    if behavior == "allow":
        return Decision.ALLOW
    raw = getattr(value, "decision", None)
    if raw is None and isinstance(value, str):
        raw = value
    if raw is None:
        return default
    if raw == "deny":
        return Decision.DENY
    if raw == "block":
        return Decision.BLOCK
    if raw == "ask":
        return Decision.ASK
    if raw in ("allow", "approve"):
        return Decision.ALLOW
    return cast(str, raw)  # unknown: surface it, don't mask as allow


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

    # Decision (for handler_end, hook_end) — canonical Decision vocabulary.
    decision: Decision | str | None = None
    reason: str | None = None  # Denial reason if any

    @field_validator("decision", mode="before")
    @classmethod
    def _normalize_decision(cls, v: object) -> Decision | str | None:
        # Coerce here too, never raise: this model is constructed in HookApp._emit
        # *outside* a try, so a ValidationError would break the hook (fail-open).
        return normalize_decision(v)

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
    decision: Decision | str  # canonical Decision; tolerant of unknown passthrough
    reason: str | None = None
    message: str | None = None  # Injected message
    dry_run: bool = False  # True if dry-run mode

    @field_validator("decision", mode="before")
    @classmethod
    def _normalize_decision(cls, v: object) -> Decision | str | None:
        return normalize_decision(v)


class ErrorEvent(ObservabilityEvent):
    """Emitted when strategy throws an exception."""

    event_type: Literal["error"] = "error"
    error_type: str  # Exception class name
    error_message: str
    traceback: str | None = None  # Only in verbose mode
