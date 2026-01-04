"""Tests for CLI commands."""

import subprocess
import sys


class TestCLIHelp:
    def test_cli_help(self):
        """fasthooks --help shows available commands."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "init" in result.stdout
        assert "install" in result.stdout
        assert "uninstall" in result.stdout
        assert "status" in result.stdout

    def test_cli_version(self):
        """fasthooks --version shows version."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "fasthooks" in result.stdout
        assert "0.1.3" in result.stdout


class TestCLIStubs:
    """Phase 1: All commands are stubs that print 'Not implemented'."""

    def test_init_stub(self):
        """fasthooks init prints 'Not implemented yet'."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "init"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Not implemented" in result.stdout

    def test_install_stub(self):
        """fasthooks install prints 'Not implemented yet'."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", "hooks.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Not implemented" in result.stdout

    def test_uninstall_stub(self):
        """fasthooks uninstall prints 'Not implemented yet'."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "uninstall"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Not implemented" in result.stdout

    def test_status_stub(self):
        """fasthooks status prints 'Not implemented yet'."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "status"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Not implemented" in result.stdout


class TestCLICommandHelp:
    """Each command has --help."""

    def test_init_help(self):
        """fasthooks init --help shows options."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "init", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--path" in result.stdout
        assert "--force" in result.stdout

    def test_install_help(self):
        """fasthooks install --help shows options."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--scope" in result.stdout
        assert "--force" in result.stdout

    def test_uninstall_help(self):
        """fasthooks uninstall --help shows options."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "uninstall", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--scope" in result.stdout

    def test_status_help(self):
        """fasthooks status --help shows options."""
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "status", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--scope" in result.stdout
