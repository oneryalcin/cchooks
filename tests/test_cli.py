"""Tests for CLI commands."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestCLIRun:
    def test_cli_run_help(self):
        """cchooks run --help shows usage."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "run", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "run" in result.stdout.lower() or "hook" in result.stdout.lower()


class TestCLIInit:
    def test_cli_init_creates_project(self, tmp_path):
        """cchooks init creates project structure."""
        project_dir = tmp_path / "my-hooks"

        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "init", str(project_dir)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert project_dir.exists()
        assert (project_dir / "hooks.py").exists()
        assert (project_dir / "pyproject.toml").exists()

    def test_cli_init_hooks_file_content(self, tmp_path):
        """Generated hooks.py has valid starter code."""
        project_dir = tmp_path / "my-hooks"

        subprocess.run(
            [sys.executable, "-m", "fasthooks", "init", str(project_dir)],
            capture_output=True,
            text=True,
        )

        hooks_file = project_dir / "hooks.py"
        content = hooks_file.read_text()

        # Should have basic structure
        assert "from fasthooks import" in content
        assert "HookApp" in content
        assert "app.run()" in content

    def test_cli_init_existing_dir_error(self, tmp_path):
        """cchooks init fails if directory exists with files."""
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        (project_dir / "hooks.py").write_text("existing")

        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "init", str(project_dir)],
            capture_output=True,
            text=True,
        )

        # Should warn or fail gracefully
        assert result.returncode != 0 or "exist" in result.stderr.lower()


class TestCLIHelp:
    def test_cli_help(self):
        """cchooks --help shows available commands."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "init" in result.stdout
        assert "run" in result.stdout
