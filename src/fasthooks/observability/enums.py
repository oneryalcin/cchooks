"""Observability enums."""

from enum import Enum


class Verbosity(Enum):
    """Verbosity level for observability events."""

    MINIMAL = "minimal"  # Just decisions and errors
    STANDARD = "standard"  # Hook enter/exit + decisions + errors
    VERBOSE = "verbose"  # Full payload, tracebacks, timing details


class TerminalOutput(Enum):
    """Terminal output verbosity."""

    QUIET = "quiet"  # No output
    NORMAL = "normal"  # Show blocks/denies only
    VERBOSE = "verbose"  # Show all decisions
