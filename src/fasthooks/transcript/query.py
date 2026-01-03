"""Fluent query builder for transcript entries."""
from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Literal, TypeVar

if TYPE_CHECKING:
    from fasthooks.transcript.entries import (
        AssistantMessage,
        TranscriptEntry,
        UserMessage,
    )

T = TypeVar("T", bound="TranscriptEntry")

# Supported lookup operators
LOOKUPS = frozenset({
    "exact",      # field == value
    "contains",   # value in field (string)
    "startswith", # field.startswith(value)
    "endswith",   # field.endswith(value)
    "regex",      # re.search(value, field)
    "in",         # field in value (list)
    "gt",         # field > value
    "gte",        # field >= value
    "lt",         # field < value
    "lte",        # field <= value
    "isnull",     # (field is None) == value
})


class TranscriptQuery:
    """Fluent query builder for transcript entries.

    Provides a chainable API inspired by Django ORM and Tidyverse.

    Usage:
        # Start from transcript
        results = transcript.query() \\
            .filter(type="assistant") \\
            .where(lambda e: e.has_tool_use) \\
            .order_by("-timestamp") \\
            .limit(10) \\
            .all()

        # Type shortcuts
        transcript.query().assistants().with_tools().first()

        # Lookups
        transcript.query().filter(text__contains="error")
        transcript.query().filter(timestamp__gt=datetime(2024,1,1))

    Each method returns a new query (immutable), executed on terminals.
    """

    def __init__(self, entries: list[TranscriptEntry]):
        """Initialize with source entries.

        Args:
            entries: List of transcript entries to query
        """
        self._source = entries
        self._ops: list[tuple[str, Callable[[list], list]]] = []

    def _clone(self, name: str, op: Callable[[list], list]) -> TranscriptQuery:
        """Create a copy with an additional operation."""
        new = TranscriptQuery(self._source)
        new._ops = self._ops + [(name, op)]
        return new

    # === Core Filtering ===

    def filter(self, **kwargs: Any) -> TranscriptQuery:
        """Filter entries by field values.

        Supports Django-style lookups:
            filter(type="assistant")           # exact match
            filter(text__contains="error")     # substring
            filter(timestamp__gt=datetime(...)) # comparison
            filter(type__in=["user", "assistant"])

        Args:
            **kwargs: Field lookups as keyword arguments

        Returns:
            New TranscriptQuery with filter applied
        """
        desc = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
        return self._clone(
            f"filter({desc})",
            lambda entries: [e for e in entries if self._match(e, kwargs)],
        )

    def where(self, predicate: Callable[[Any], bool]) -> TranscriptQuery:
        """Filter entries by arbitrary predicate.

        Use for complex conditions that can't be expressed with lookups.

        Args:
            predicate: Function that returns True for entries to keep

        Returns:
            New TranscriptQuery with filter applied

        Example:
            query.where(lambda e: e.has_tool_use and len(e.tool_uses) > 2)
        """
        # Try to get a nice name for the predicate
        name = getattr(predicate, "__name__", "<lambda>")
        return self._clone(
            f"where({name})",
            lambda entries: [e for e in entries if predicate(e)],
        )

    def exclude(self, **kwargs: Any) -> TranscriptQuery:
        """Exclude entries matching criteria (inverse of filter).

        Args:
            **kwargs: Field lookups to exclude

        Returns:
            New TranscriptQuery with exclusion applied
        """
        desc = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
        return self._clone(
            f"exclude({desc})",
            lambda entries: [e for e in entries if not self._match(e, kwargs)],
        )

    # === Type Shortcuts ===

    def users(self) -> TranscriptQuery:
        """Filter to user messages only."""
        return self._clone(
            "users()",
            lambda entries: [e for e in entries if e.type == "user"],
        )

    def assistants(self) -> TranscriptQuery:
        """Filter to assistant messages only."""
        return self._clone(
            "assistants()",
            lambda entries: [e for e in entries if e.type == "assistant"],
        )

    def system(self) -> TranscriptQuery:
        """Filter to system entries only."""
        return self._clone(
            "system()",
            lambda entries: [e for e in entries if e.type == "system"],
        )

    def with_tools(self) -> TranscriptQuery:
        """Filter to entries with tool use."""
        return self._clone(
            "with_tools()",
            lambda entries: [e for e in entries if getattr(e, "has_tool_use", False)],
        )

    def with_errors(self) -> TranscriptQuery:
        """Filter to entries with tool errors."""
        def has_error(e: Any) -> bool:
            if hasattr(e, "tool_uses"):
                return any(
                    tu.result and tu.result.is_error
                    for tu in e.tool_uses
                )
            return False
        return self._clone("with_errors()", lambda entries: [e for e in entries if has_error(e)])

    def with_thinking(self) -> TranscriptQuery:
        """Filter to entries with thinking blocks."""
        return self._clone(
            "with_thinking()",
            lambda entries: [e for e in entries if getattr(e, "thinking", "")],
        )

    # === Time Filtering ===

    def since(self, ts: datetime | str) -> TranscriptQuery:
        """Filter to entries after timestamp (inclusive).

        Args:
            ts: Datetime or ISO format string

        Returns:
            New TranscriptQuery with time filter
        """
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return self._clone(
            f"since({ts.isoformat()})",
            lambda entries: [
                e for e in entries
                if getattr(e, "timestamp", None) and e.timestamp >= ts
            ],
        )

    def until(self, ts: datetime | str) -> TranscriptQuery:
        """Filter to entries before timestamp (inclusive).

        Args:
            ts: Datetime or ISO format string

        Returns:
            New TranscriptQuery with time filter
        """
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return self._clone(
            f"until({ts.isoformat()})",
            lambda entries: [
                e for e in entries
                if getattr(e, "timestamp", None) and e.timestamp <= ts
            ],
        )

    # === Ordering ===

    def order_by(self, *fields: str) -> TranscriptQuery:
        """Sort results by fields.

        Prefix field with - for descending order.

        Args:
            *fields: Field names to sort by

        Returns:
            New TranscriptQuery with ordering

        Example:
            query.order_by("-timestamp")  # newest first
            query.order_by("type", "-timestamp")  # by type, then newest
        """
        def _sort_key(x: Any, k: str) -> Any:
            """Get sort key, treating None as empty string (sorts first)."""
            val = getattr(x, k, None)
            return val if val is not None else ""

        def op(entries: list) -> list:
            result = list(entries)
            for field in reversed(fields):
                reverse = field.startswith("-")
                attr = field.lstrip("-")
                # Capture attr by value (k=attr) to avoid closure bug
                result.sort(key=lambda x, k=attr: _sort_key(x, k), reverse=reverse)
            return result

        return self._clone(f"order_by({', '.join(fields)})", op)

    # === Pagination ===

    def limit(self, n: int) -> TranscriptQuery:
        """Limit to first n results.

        Args:
            n: Maximum number of results

        Returns:
            New TranscriptQuery with limit
        """
        return self._clone(f"limit({n})", lambda entries: entries[:n])

    def offset(self, n: int) -> TranscriptQuery:
        """Skip first n results.

        Args:
            n: Number of results to skip

        Returns:
            New TranscriptQuery with offset
        """
        return self._clone(f"offset({n})", lambda entries: entries[n:])

    # === Terminals (execute query) ===

    def all(self) -> list[TranscriptEntry]:
        """Execute query and return all matching entries."""
        result = self._source
        for _, op in self._ops:
            result = op(result)
        return result

    def first(self) -> TranscriptEntry | None:
        """Return first matching entry or None."""
        result = self.limit(1).all()
        return result[0] if result else None

    def last(self) -> TranscriptEntry | None:
        """Return last matching entry or None."""
        result = self.all()
        return result[-1] if result else None

    def one(self) -> TranscriptEntry:
        """Return exactly one matching entry.

        Raises:
            ValueError: If query returns 0 or more than 1 result
        """
        result = self.all()
        if len(result) == 0:
            raise ValueError(f"Query returned no results: {self}")
        if len(result) > 1:
            raise ValueError(f"Query returned {len(result)} results, expected 1: {self}")
        return result[0]

    def count(self) -> int:
        """Return count of matching entries."""
        return len(self.all())

    def exists(self) -> bool:
        """Check if any entries match."""
        return len(self.limit(1).all()) > 0

    # === Lookup Matching ===

    def _match(self, entry: Any, criteria: dict[str, Any]) -> bool:
        """Check if entry matches all criteria."""
        for key, value in criteria.items():
            if not self._match_field(entry, key, value):
                return False
        return True

    def _match_field(self, entry: Any, key: str, value: Any) -> bool:
        """Match a single field lookup."""
        # Parse field__lookup
        parts = key.split("__")
        field = parts[0]
        lookup = parts[1] if len(parts) > 1 else "exact"

        # Validate lookup
        if lookup not in LOOKUPS:
            raise ValueError(
                f"Unknown lookup '{lookup}' in '{key}'. "
                f"Valid lookups: {', '.join(sorted(LOOKUPS))}"
            )

        # Get field value (support nested with .)
        field_val = self._get_field(entry, field)

        # Apply lookup
        if lookup == "exact":
            return field_val == value
        elif lookup == "contains":
            if field_val is None:
                return False
            return value in str(field_val)
        elif lookup == "startswith":
            if field_val is None:
                return False
            return str(field_val).startswith(value)
        elif lookup == "endswith":
            if field_val is None:
                return False
            return str(field_val).endswith(value)
        elif lookup == "regex":
            if field_val is None:
                return False
            return bool(re.search(value, str(field_val)))
        elif lookup == "in":
            return field_val in value
        elif lookup == "gt":
            return field_val is not None and field_val > value
        elif lookup == "gte":
            return field_val is not None and field_val >= value
        elif lookup == "lt":
            return field_val is not None and field_val < value
        elif lookup == "lte":
            return field_val is not None and field_val <= value
        elif lookup == "isnull":
            return (field_val is None) == value

        return False

    def _get_field(self, entry: Any, field: str) -> Any:
        """Get field value, supporting nested access."""
        # For now, just simple attribute access
        # TODO: Support nested like tool_uses__name with any() semantics
        return getattr(entry, field, None)

    # === Iteration ===

    def __iter__(self):
        """Iterate over results."""
        return iter(self.all())

    def __len__(self) -> int:
        """Return count of results."""
        return self.count()

    def __bool__(self) -> bool:
        """Check if query has results."""
        return self.exists()

    def __repr__(self) -> str:
        """Show query chain."""
        if self._ops:
            chain = " → ".join(name for name, _ in self._ops)
            return f"<TranscriptQuery: {chain}>"
        return f"<TranscriptQuery: (no filters), {len(self._source)} entries>"
