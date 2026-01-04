"""Tests for LongRunningStrategy."""

import json
from pathlib import Path
from typing import Any

import pytest

from fasthooks.strategies import LongRunningStrategy
from fasthooks.testing import StrategyTestClient


def get_response_text(response: Any) -> str:
    """Extract text from response (handles ContextResponse and HookResponse)."""
    if response is None:
        return ""
    # ContextResponse uses additional_context
    if hasattr(response, "additional_context") and response.additional_context:
        return response.additional_context
    # HookResponse uses message
    if hasattr(response, "message") and response.message:
        return response.message
    return ""


class TestSessionStart:
    """SessionStart handler tests."""

    @pytest.mark.parametrize("has_feature_list,expected_type", [
        (False, "initializer"),
        (True, "coding"),
    ])
    def test_detects_session_type(
        self,
        strategy_client: StrategyTestClient,
        has_feature_list: bool,
        expected_type: str,
    ):
        """SessionStart returns correct context based on feature_list.json existence."""
        if has_feature_list:
            strategy_client.setup_project(files={
                "feature_list.json": '[{"description": "test", "passes": false}]',
            })

        strategy_client.trigger_session_start(source="startup")
        strategy_client.assert_event_emitted("session_type", type=expected_type)

    def test_initializer_context_contains_instructions(
        self, strategy_client: StrategyTestClient
    ):
        """Initializer context includes setup instructions."""
        response = strategy_client.trigger_session_start(source="startup")

        assert response is not None
        text = get_response_text(response)
        assert "feature_list" in text.lower()
        assert "git" in text.lower()

    def test_coding_context_contains_status(
        self, strategy_client: StrategyTestClient
    ):
        """Coding context includes feature status."""
        strategy_client.setup_project(files={
            "feature_list.json": json.dumps([
                {"description": "feat1", "passes": True},
                {"description": "feat2", "passes": False},
            ]),
        })

        response = strategy_client.trigger_session_start(source="startup")

        assert response is not None
        text = get_response_text(response)
        assert "1/2" in text  # 1 passing out of 2

    def test_compact_source_uses_minimal_context(
        self, strategy_client: StrategyTestClient
    ):
        """Compact source returns minimal recovery context."""
        strategy_client.setup_project(files={
            "feature_list.json": "[]",
        })

        response = strategy_client.trigger_session_start(source="compact")

        assert response is not None
        text = get_response_text(response)
        assert "compaction" in text.lower()


class TestStop:
    """Stop handler tests."""

    def test_allows_clean_state(
        self, strategy_no_progress: StrategyTestClient
    ):
        """Stop allowed when no uncommitted changes and progress updated."""
        strategy_no_progress.setup_git()
        # No uncommitted changes, progress not required

        response = strategy_no_progress.trigger_stop()

        # Should allow (None or approve decision)
        if response is not None:
            assert getattr(response, "decision", None) != "block"

    def test_blocks_uncommitted_changes(
        self, strategy_with_commits: StrategyTestClient
    ):
        """Stop blocked when uncommitted changes exist."""
        strategy_with_commits.setup_git()
        strategy_with_commits.add_uncommitted("dirty.py")

        response = strategy_with_commits.trigger_stop()

        assert response is not None
        assert getattr(response, "decision", None) == "block"
        strategy_with_commits.assert_blocked("uncommitted")

    def test_blocks_missing_progress_update(
        self, tmp_path: Path
    ):
        """Stop blocked when progress file not updated."""
        strategy = LongRunningStrategy(
            enforce_commits=False,
            require_progress_update=True,
        )
        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.setup_git()
        # Don't update progress file

        response = client.trigger_stop()

        assert response is not None
        assert getattr(response, "decision", None) == "block"

    def test_allows_after_progress_update(
        self, tmp_path: Path
    ):
        """Stop allowed after progress file is updated."""
        strategy = LongRunningStrategy(
            enforce_commits=False,
            require_progress_update=True,
        )
        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.setup_git()

        # Trigger session start to initialize state
        client.trigger_session_start()

        # Update progress file via post_write trigger
        client.trigger_post_write("claude-progress.txt", "Session notes")

        response = client.trigger_stop()

        # Should not block
        if response is not None:
            assert getattr(response, "decision", None) != "block"


class TestPreCompact:
    """PreCompact handler tests."""

    def test_returns_checkpoint_message(
        self, strategy_client: StrategyTestClient
    ):
        """PreCompact returns checkpoint reminder."""
        strategy_client.setup_project(files={
            "feature_list.json": "[]",
        })

        response = strategy_client.trigger_pre_compact()

        assert response is not None
        text = get_response_text(response)
        assert "checkpoint" in text.lower()

    def test_emits_checkpoint_needed_event(
        self, strategy_client: StrategyTestClient
    ):
        """PreCompact emits checkpoint_needed custom event."""
        strategy_client.setup_project(files={
            "feature_list.json": "[]",
        })

        strategy_client.trigger_pre_compact()

        strategy_client.assert_event_emitted("checkpoint_needed", reason="compaction")


class TestPostWrite:
    """PostToolUse Write handler tests."""

    def test_tracks_progress_file_update(
        self, strategy_client: StrategyTestClient
    ):
        """Write to progress file sets progress_updated flag."""
        strategy_client.trigger_session_start()

        # Write to progress file
        strategy_client.trigger_post_write("claude-progress.txt", "Session notes")

        # Check state
        ns = strategy_client.state.get("long-running", {})
        assert ns.get("progress_updated") is True

    def test_tracks_files_modified(
        self, strategy_client: StrategyTestClient
    ):
        """Write tracks modified files."""
        strategy_client.trigger_session_start()

        strategy_client.trigger_post_write("src/main.py", "code")
        strategy_client.trigger_post_write("src/utils.py", "more code")

        ns = strategy_client.state.get("long-running", {})
        assert "src/main.py" in ns.get("files_modified", [])
        assert "src/utils.py" in ns.get("files_modified", [])


class TestPostBash:
    """PostToolUse Bash handler tests."""

    def test_tracks_git_commits(
        self, strategy_client: StrategyTestClient
    ):
        """Bash with git commit is tracked."""
        strategy_client.trigger_session_start()

        strategy_client.trigger_post_bash("git commit -m 'test'")

        ns = strategy_client.state.get("long-running", {})
        assert len(ns.get("commits_made", [])) == 1

    def test_ignores_non_commit_commands(
        self, strategy_client: StrategyTestClient
    ):
        """Non-git commands are not tracked as commits."""
        strategy_client.trigger_session_start()

        strategy_client.trigger_post_bash("ls -la")
        strategy_client.trigger_post_bash("git status")

        ns = strategy_client.state.get("long-running", {})
        assert len(ns.get("commits_made", [])) == 0


class TestFeatureCounting:
    """Feature list parsing tests."""

    def test_counts_passing_features(
        self, strategy_client: StrategyTestClient
    ):
        """Correctly counts passing features."""
        strategy_client.setup_project(files={
            "feature_list.json": json.dumps([
                {"description": "feat1", "passes": True},
                {"description": "feat2", "passes": True},
                {"description": "feat3", "passes": False},
            ]),
        })

        response = strategy_client.trigger_session_start()

        text = get_response_text(response)
        assert "2/3" in text

    def test_handles_empty_feature_list(
        self, strategy_client: StrategyTestClient
    ):
        """Empty feature list returns 0/0."""
        strategy_client.setup_project(files={
            "feature_list.json": "[]",
        })

        response = strategy_client.trigger_session_start()

        text = get_response_text(response)
        assert "0/0" in text

    def test_handles_malformed_json(
        self, strategy_client: StrategyTestClient, caplog
    ):
        """Malformed JSON doesn't crash, logs warning."""
        strategy_client.setup_project(files={
            "feature_list.json": "not valid json {{{",
        })

        # Should not raise
        response = strategy_client.trigger_session_start()

        # Should still return a response (initializer since file is broken)
        assert response is not None


class TestExcludePaths:
    """Exclude paths from uncommitted check tests."""

    def test_excludes_hooks_directory(
        self, tmp_path: Path
    ):
        """Files in hooks/ are excluded from uncommitted check."""
        strategy = LongRunningStrategy(
            enforce_commits=True,
            require_progress_update=False,
            exclude_paths=["hooks/"],
        )
        client = StrategyTestClient(strategy, project_dir=tmp_path)
        client.setup_git()

        # Add uncommitted file in hooks/
        (tmp_path / "hooks").mkdir()
        (tmp_path / "hooks" / "main.py").write_text("# hook code")

        response = client.trigger_stop()

        # Should not block because hooks/ is excluded
        if response is not None:
            assert getattr(response, "decision", None) != "block"
