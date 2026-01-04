"""TokenBudgetStrategy - warn on token usage thresholds.

This is a simple strategy (1 hook) included for educational value.
The raw fasthooks equivalent is ~10 lines:

    @app.post_tool()
    def check_tokens(event, transcript: Transcript):
        total = transcript.stats.input_tokens + transcript.stats.output_tokens
        if total >= 150_000:
            return allow(message="⚠️ Token limit approaching!")

Strategy adds: observability, YAML config, namespace isolation.
"""

from __future__ import annotations

from typing import Any

from fasthooks import Blueprint, allow
from fasthooks.depends import Transcript

from .base import Strategy


class TokenBudgetStrategy(Strategy):
    """Track token usage and inject warnings at thresholds.

    Monitors transcript token counts after each tool call. Injects
    progressively urgent warnings as usage approaches context limits.

    Example:
        strategy = TokenBudgetStrategy(
            warn_threshold=100_000,
            critical_threshold=150_000,
            emergency_threshold=180_000,
        )
        app.include(strategy.get_blueprint())

    Thresholds:
        - warn: "📊 Notice: Consider checkpointing"
        - critical: "⚠️ CRITICAL: Checkpoint soon"
        - emergency: "🚨 EMERGENCY: Commit NOW"
    """

    class Meta:
        name = "token-budget"
        version = "1.0.0"
        description = "Track and warn on token usage thresholds"
        hooks = ["post_tool:*"]
        fail_mode = "open"

    def __init__(
        self,
        *,
        warn_threshold: int = 100_000,
        critical_threshold: int = 150_000,
        emergency_threshold: int = 180_000,
    ):
        """Initialize TokenBudgetStrategy.

        Args:
            warn_threshold: Token count to trigger notice message.
            critical_threshold: Token count to trigger warning message.
            emergency_threshold: Token count to trigger emergency message.
        """
        # Set attributes before super().__init__() which calls _validate_config()
        self.warn_threshold = warn_threshold
        self.critical_threshold = critical_threshold
        self.emergency_threshold = emergency_threshold
        super().__init__()

    def _validate_config(self) -> None:
        """Validate thresholds are sensible."""
        if not (self.warn_threshold < self.critical_threshold < self.emergency_threshold):
            raise ValueError(
                "Thresholds must be: warn < critical < emergency. "
                f"Got: {self.warn_threshold} < {self.critical_threshold} "
                f"< {self.emergency_threshold}"
            )

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("token-budget")

        @bp.post_tool()
        def check_tokens(event: Any, transcript: Transcript) -> Any:
            stats = transcript.stats
            total = stats.input_tokens + stats.output_tokens

            if total >= self.emergency_threshold:
                return allow(
                    message=(
                        f"🚨 EMERGENCY: Token limit approaching!\n"
                        f"Used: {total:,} tokens\n"
                        "CHECKPOINT IMMEDIATELY: commit and update progress file."
                    )
                )
            elif total >= self.critical_threshold:
                return allow(
                    message=f"⚠️ CRITICAL: {total:,} tokens used. Checkpoint soon."
                )
            elif total >= self.warn_threshold:
                return allow(
                    message=f"📊 Notice: {total:,} tokens used. Consider checkpointing."
                )

            return None

        return bp
