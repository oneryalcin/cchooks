"""Integration tests for LongRunningStrategy with real git."""

import json
import pytest
from pathlib import Path
from typing import Any

from fasthooks.strategies import LongRunningStrategy
from fasthooks.testing import StrategyTestClient

from .conftest import RealGitProject


def get_response_text(response: Any) -> str:
    """Extract text from response (handles ContextResponse and HookResponse)."""
    if response is None:
        return ""
    if hasattr(response, "additional_context") and response.additional_context:
        return response.additional_context
    if hasattr(response, "message") and response.message:
        return response.message
    return ""


class TestRealGitIntegration:
    """Integration tests with real git operations."""

    def test_stop_blocked_with_uncommitted_changes(
        self, real_git_project: RealGitProject
    ):
        """Stop is blocked when git has uncommitted changes."""
        real_git_project.write_file("new.py", "# new file")
        assert real_git_project.has_uncommitted()

        strategy = LongRunningStrategy(
            enforce_commits=True,
            require_progress_update=False,
        )
        client = StrategyTestClient(strategy, project_dir=real_git_project.path)

        response = client.trigger_stop()

        assert response is not None
        assert getattr(response, "decision", None) == "block"
        assert "uncommitted" in (getattr(response, "reason", "") or "").lower()

    def test_stop_allowed_after_commit(
        self, real_git_project: RealGitProject
    ):
        """Stop is allowed after changes are committed."""
        real_git_project.write_file("new.py", "# new file")
        real_git_project.commit("Add new file")
        assert not real_git_project.has_uncommitted()

        strategy = LongRunningStrategy(
            enforce_commits=True,
            require_progress_update=False,
        )
        client = StrategyTestClient(strategy, project_dir=real_git_project.path)

        response = client.trigger_stop()

        # Should not block
        if response is not None:
            assert getattr(response, "decision", None) != "block"

    def test_coding_context_shows_git_log(
        self, real_git_project: RealGitProject
    ):
        """Coding context includes recent commits."""
        # Make some commits
        real_git_project.write_file("file1.py", "# first")
        real_git_project.commit("Add file1")
        real_git_project.write_file("file2.py", "# second")
        real_git_project.commit("Add file2")

        # Add feature list
        real_git_project.write_file(
            "feature_list.json",
            json.dumps([{"description": "test", "passes": False}]),
        )
        real_git_project.commit("Add feature list")

        strategy = LongRunningStrategy()
        client = StrategyTestClient(strategy, project_dir=real_git_project.path)

        response = client.trigger_session_start(source="startup")

        text = get_response_text(response)
        # Should contain recent commit messages
        assert "file1" in text.lower() or "file2" in text.lower() or "commit" in text.lower()

    def test_exclude_paths_with_real_git(
        self, real_git_project: RealGitProject
    ):
        """Excluded paths don't trigger uncommitted warning."""
        # Create uncommitted file in excluded directory
        real_git_project.write_file("hooks/main.py", "# hook")

        strategy = LongRunningStrategy(
            enforce_commits=True,
            require_progress_update=False,
            exclude_paths=["hooks/"],
        )
        client = StrategyTestClient(strategy, project_dir=real_git_project.path)

        response = client.trigger_stop()

        # Should not block - hooks/ is excluded
        if response is not None:
            assert getattr(response, "decision", None) != "block"

    def test_full_workflow(
        self, real_git_project: RealGitProject
    ):
        """Full workflow: session start → work → commit → stop."""
        strategy = LongRunningStrategy(
            enforce_commits=True,
            require_progress_update=True,
        )
        client = StrategyTestClient(strategy, project_dir=real_git_project.path)

        # 1. Session start (initializer mode - no feature list)
        response = client.trigger_session_start(source="startup")
        assert response is not None
        client.assert_event_emitted("session_type", type="initializer")

        # 2. Create feature list
        real_git_project.write_file(
            "feature_list.json",
            json.dumps([{"description": "feat1", "passes": False}]),
        )

        # 3. Try to stop - should be blocked (uncommitted + no progress)
        response = client.trigger_stop()
        assert getattr(response, "decision", None) == "block"

        # 4. Commit feature list
        real_git_project.commit("Add feature list")

        # 5. Update progress file (write actual file + trigger event)
        real_git_project.write_file("claude-progress.txt", "Session 1: Created features")
        real_git_project.commit("Update progress")
        client.trigger_post_write("claude-progress.txt", "Session 1: Created features")

        # 6. Now stop should work (committed + progress updated)
        client.clear_events()
        response = client.trigger_stop()
        if response is not None:
            assert getattr(response, "decision", None) != "block"


class TestRealFileOperations:
    """Integration tests with real file operations."""

    def test_reads_real_feature_list(
        self, real_git_project: RealGitProject
    ):
        """Strategy reads actual feature_list.json content."""
        features = [
            {"description": "Login", "passes": True},
            {"description": "Logout", "passes": True},
            {"description": "Dashboard", "passes": False},
        ]
        real_git_project.write_file("feature_list.json", json.dumps(features))
        real_git_project.commit("Add features")

        strategy = LongRunningStrategy()
        client = StrategyTestClient(strategy, project_dir=real_git_project.path)

        response = client.trigger_session_start(source="startup")

        text = get_response_text(response)
        assert "2/3" in text  # 2 passing out of 3

    def test_reads_real_progress_file(
        self, real_git_project: RealGitProject
    ):
        """Strategy reads actual progress file."""
        real_git_project.write_file(
            "feature_list.json",
            json.dumps([{"description": "test", "passes": False}]),
        )
        real_git_project.write_file(
            "claude-progress.txt",
            "Session 1: Started project\n\nSession 2: Added login",
        )
        real_git_project.commit("Add files")

        strategy = LongRunningStrategy()
        client = StrategyTestClient(strategy, project_dir=real_git_project.path)

        response = client.trigger_session_start(source="startup")

        text = get_response_text(response)
        # Should include content from progress file
        assert "login" in text.lower() or "session" in text.lower()
