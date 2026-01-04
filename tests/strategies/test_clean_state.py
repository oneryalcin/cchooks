"""Tests for CleanStateStrategy."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from fasthooks.strategies import CleanStateStrategy
from fasthooks.testing import StrategyTestClient


def get_response_text(response: Any) -> str:
    """Extract text from response."""
    if response is None:
        return ""
    if hasattr(response, "reason") and response.reason:
        return response.reason
    if hasattr(response, "message") and response.message:
        return response.message
    return ""


class TestRequiredFiles:
    """Required files check tests."""

    def test_blocks_when_required_file_missing(self, tmp_path: Path):
        """Block stop if required file doesn't exist."""
        strategy = CleanStateStrategy(
            require_files=["README.md"],
            check_uncommitted=False,
        )
        client = StrategyTestClient(strategy, project_dir=tmp_path)

        response = client.trigger_stop()

        assert response is not None
        assert getattr(response, "decision", None) == "block"
        assert "readme.md" in get_response_text(response).lower()

    def test_allows_when_required_file_exists(self, tmp_path: Path):
        """Allow stop if required files exist."""
        (tmp_path / "README.md").write_text("# Project")

        strategy = CleanStateStrategy(
            require_files=["README.md"],
            check_uncommitted=False,
        )
        client = StrategyTestClient(strategy, project_dir=tmp_path)

        response = client.trigger_stop()

        # Should not block
        if response is not None:
            assert getattr(response, "decision", None) != "block"

    def test_multiple_required_files(self, tmp_path: Path):
        """Check multiple required files."""
        (tmp_path / "README.md").write_text("# Project")
        # pyproject.toml missing

        strategy = CleanStateStrategy(
            require_files=["README.md", "pyproject.toml"],
            check_uncommitted=False,
        )
        client = StrategyTestClient(strategy, project_dir=tmp_path)

        response = client.trigger_stop()

        assert response is not None
        assert getattr(response, "decision", None) == "block"
        assert "pyproject.toml" in get_response_text(response).lower()


class TestUncommittedChanges:
    """Uncommitted changes check tests."""

    def test_blocks_on_uncommitted_changes(self, tmp_path: Path):
        """Block stop when git has uncommitted changes."""
        strategy = CleanStateStrategy(check_uncommitted=True)
        client = StrategyTestClient(strategy, project_dir=tmp_path)

        # Mock git status returning dirty state
        with patch("fasthooks.strategies.clean_state.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=" M file.py\n?? new.py\n",
            )

            response = client.trigger_stop()

        assert response is not None
        assert getattr(response, "decision", None) == "block"
        assert "uncommitted" in get_response_text(response).lower()

    def test_allows_on_clean_state(self, tmp_path: Path):
        """Allow stop when git is clean."""
        strategy = CleanStateStrategy(check_uncommitted=True)
        client = StrategyTestClient(strategy, project_dir=tmp_path)

        # Mock git status returning clean state
        with patch("fasthooks.strategies.clean_state.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
            )

            response = client.trigger_stop()

        # Should not block
        if response is not None:
            assert getattr(response, "decision", None) != "block"

    def test_excludes_specified_paths(self, tmp_path: Path):
        """Excluded paths don't trigger uncommitted warning."""
        strategy = CleanStateStrategy(
            check_uncommitted=True,
            exclude_paths=["hooks/", ".claude/"],
        )
        client = StrategyTestClient(strategy, project_dir=tmp_path)

        # Mock git status with changes only in excluded paths
        with patch("fasthooks.strategies.clean_state.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=" M hooks/main.py\n?? .claude/settings.json\n",
            )

            response = client.trigger_stop()

        # Should not block - all changes in excluded paths
        if response is not None:
            assert getattr(response, "decision", None) != "block"

    def test_partial_exclude(self, tmp_path: Path):
        """Mix of excluded and non-excluded changes."""
        strategy = CleanStateStrategy(
            check_uncommitted=True,
            exclude_paths=["hooks/"],
        )
        client = StrategyTestClient(strategy, project_dir=tmp_path)

        # Mock git status with mixed changes
        with patch("fasthooks.strategies.clean_state.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=" M hooks/main.py\n M src/app.py\n",
            )

            response = client.trigger_stop()

        # Should block - src/app.py not excluded
        assert response is not None
        assert getattr(response, "decision", None) == "block"
        assert "src/app.py" in get_response_text(response)


class TestCombinedChecks:
    """Combined file and git checks."""

    def test_multiple_issues(self, tmp_path: Path):
        """Report both missing files and uncommitted changes."""
        strategy = CleanStateStrategy(
            require_files=["README.md"],
            check_uncommitted=True,
        )
        client = StrategyTestClient(strategy, project_dir=tmp_path)

        with patch("fasthooks.strategies.clean_state.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=" M dirty.py\n",
            )

            response = client.trigger_stop()

        assert response is not None
        assert getattr(response, "decision", None) == "block"
        reason = get_response_text(response).lower()
        assert "readme.md" in reason
        assert "uncommitted" in reason


class TestObservability:
    """Observability event tests."""

    def test_emits_hook_events(self, tmp_path: Path):
        """Strategy emits hook_enter and hook_exit events."""
        strategy = CleanStateStrategy(check_uncommitted=False)
        events = []

        @strategy.on_observe
        def collect(event):
            events.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.trigger_stop()

        event_types = [e.event_type for e in events]
        assert "hook_enter" in event_types
        assert "hook_exit" in event_types

    def test_emits_decision_event(self, tmp_path: Path):
        """Strategy emits decision event."""
        strategy = CleanStateStrategy(check_uncommitted=False)
        events = []

        @strategy.on_observe
        def collect(event):
            events.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.trigger_stop()

        decisions = [e for e in events if e.event_type == "decision"]
        assert len(decisions) == 1

    def test_strategy_name_in_events(self, tmp_path: Path):
        """Events include correct strategy name."""
        strategy = CleanStateStrategy(check_uncommitted=False)
        events = []

        @strategy.on_observe
        def collect(event):
            events.append(event)

        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.trigger_stop()

        assert all(e.strategy_name == "clean-state" for e in events)


class TestFailMode:
    """Fail mode tests."""

    def test_fail_mode_is_closed(self):
        """CleanStateStrategy uses fail_mode=closed."""
        strategy = CleanStateStrategy()
        meta = strategy.get_meta()
        assert meta.fail_mode == "closed"
