"""Integration test fixtures with real I/O."""

import subprocess
import pytest
from pathlib import Path


class RealGitProject:
    """Helper for creating real git repos in tests."""

    def __init__(self, path: Path):
        self.path = path
        subprocess.run(
            ["git", "init"],
            cwd=path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=path,
            capture_output=True,
        )
        # Initial commit
        (path / ".gitkeep").write_text("")
        subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=path,
            capture_output=True,
        )

    def write_file(self, name: str, content: str) -> Path:
        """Write a file to the project."""
        path = self.path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def commit(self, message: str = "commit") -> None:
        """Commit all changes."""
        subprocess.run(["git", "add", "."], cwd=self.path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.path,
            capture_output=True,
        )

    def has_uncommitted(self) -> bool:
        """Check if there are uncommitted changes."""
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.path,
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())


@pytest.fixture
def real_git_project(tmp_path: Path) -> RealGitProject:
    """Real git repository in tmp_path."""
    return RealGitProject(tmp_path)
