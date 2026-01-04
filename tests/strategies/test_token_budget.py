"""Tests for TokenBudgetStrategy."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from fasthooks.strategies import TokenBudgetStrategy
from fasthooks.testing import StrategyTestClient


def get_response_text(response: Any) -> str:
    """Extract text from response."""
    if response is None:
        return ""
    if hasattr(response, "additional_context") and response.additional_context:
        return response.additional_context
    if hasattr(response, "message") and response.message:
        return response.message
    return ""


def make_mock_transcript(input_tokens: int, output_tokens: int) -> MagicMock:
    """Create mock Transcript with stats."""
    mock = MagicMock()
    mock.stats.input_tokens = input_tokens
    mock.stats.output_tokens = output_tokens
    return mock


class TestThresholdValidation:
    """Threshold validation tests."""

    def test_valid_thresholds(self):
        """Valid ascending thresholds work."""
        strategy = TokenBudgetStrategy(
            warn_threshold=100_000,
            critical_threshold=150_000,
            emergency_threshold=180_000,
        )
        assert strategy.warn_threshold == 100_000

    def test_invalid_thresholds_raises(self):
        """Non-ascending thresholds raise ValueError."""
        with pytest.raises(ValueError, match="warn < critical < emergency"):
            TokenBudgetStrategy(
                warn_threshold=150_000,
                critical_threshold=100_000,  # Less than warn
                emergency_threshold=180_000,
            )

    def test_equal_thresholds_raises(self):
        """Equal thresholds raise ValueError."""
        with pytest.raises(ValueError):
            TokenBudgetStrategy(
                warn_threshold=100_000,
                critical_threshold=100_000,  # Same as warn
                emergency_threshold=180_000,
            )


class TestTokenWarnings:
    """Token warning tests."""

    @pytest.fixture
    def strategy(self) -> TokenBudgetStrategy:
        return TokenBudgetStrategy(
            warn_threshold=100,
            critical_threshold=200,
            emergency_threshold=300,
        )

    @pytest.fixture
    def client(self, strategy: TokenBudgetStrategy, tmp_path: Path) -> StrategyTestClient:
        return StrategyTestClient(strategy, project_dir=tmp_path)

    def test_no_warning_below_threshold(self, client: StrategyTestClient):
        """No message when tokens below warn threshold."""
        client.set_transcript(make_mock_transcript(25, 25))  # 50 total

        response = client.trigger_post_bash("ls")

        # Should return None or allow without message
        if response is not None:
            text = get_response_text(response)
            assert "token" not in text.lower()

    def test_warn_threshold_message(self, client: StrategyTestClient):
        """Inject notice at warn threshold."""
        client.set_transcript(make_mock_transcript(75, 75))  # 150 total

        response = client.trigger_post_bash("ls")

        text = get_response_text(response)
        assert "notice" in text.lower() or "150" in text

    def test_critical_threshold_message(self, client: StrategyTestClient):
        """Inject warning at critical threshold."""
        client.set_transcript(make_mock_transcript(125, 125))  # 250 total

        response = client.trigger_post_bash("ls")

        text = get_response_text(response)
        assert "critical" in text.lower()

    def test_emergency_threshold_message(self, client: StrategyTestClient):
        """Inject emergency at emergency threshold."""
        client.set_transcript(make_mock_transcript(200, 200))  # 400 total

        response = client.trigger_post_bash("ls")

        text = get_response_text(response)
        assert "emergency" in text.lower()


class TestObservability:
    """Observability event tests."""

    def test_emits_hook_events(self, tmp_path: Path):
        """Strategy emits hook_enter and hook_exit events."""
        strategy = TokenBudgetStrategy()
        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.set_transcript(make_mock_transcript(50, 50))

        client.trigger_post_bash("ls")

        event_types = [e.event_type for e in client.events]
        assert "hook_enter" in event_types
        assert "hook_exit" in event_types

    def test_strategy_name_in_events(self, tmp_path: Path):
        """Events include correct strategy name."""
        strategy = TokenBudgetStrategy()
        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.set_transcript(make_mock_transcript(50, 50))

        client.trigger_post_bash("ls")

        assert all(e.strategy_name == "token-budget" for e in client.events)
