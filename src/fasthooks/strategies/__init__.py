"""Strategy module for fasthooks.

Strategies are reusable, composable hook patterns with built-in observability.
"""

from .base import Strategy, StrategyMeta
from .clean_state import CleanStateStrategy
from .long_running import LongRunningStrategy
from .registry import StrategyConflictError, StrategyRegistry
from .token_budget import TokenBudgetStrategy

__all__ = [
    "Strategy",
    "StrategyMeta",
    "StrategyRegistry",
    "StrategyConflictError",
    "LongRunningStrategy",
    "TokenBudgetStrategy",
    "CleanStateStrategy",
]
