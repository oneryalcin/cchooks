"""Strategy-specific test fixtures."""

from pathlib import Path

import pytest

from fasthooks.strategies import LongRunningStrategy
from fasthooks.testing import StrategyTestClient


@pytest.fixture
def strategy() -> LongRunningStrategy:
    """Default LongRunningStrategy."""
    return LongRunningStrategy()


@pytest.fixture
def strategy_client(strategy: LongRunningStrategy, tmp_path: Path) -> StrategyTestClient:
    """StrategyTestClient with tmp project directory."""
    return StrategyTestClient(strategy, project_dir=tmp_path)


@pytest.fixture
def strategy_with_commits(tmp_path: Path) -> StrategyTestClient:
    """Strategy with enforce_commits=True."""
    strategy = LongRunningStrategy(enforce_commits=True)
    return StrategyTestClient(strategy, project_dir=tmp_path)


@pytest.fixture
def strategy_no_progress(tmp_path: Path) -> StrategyTestClient:
    """Strategy with require_progress_update=False."""
    strategy = LongRunningStrategy(require_progress_update=False)
    return StrategyTestClient(strategy, project_dir=tmp_path)
