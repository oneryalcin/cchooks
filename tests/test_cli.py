"""Tests for CLI commands."""

import subprocess
import sys
from pathlib import Path


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
    """Stub commands that are not yet implemented."""

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


class TestInitCommand:
    """Tests for fasthooks init command."""

    def test_init_creates_hooks_file(self, tmp_path: Path, monkeypatch):
        """fasthooks init creates .claude/hooks.py."""
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "init"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (tmp_path / ".claude" / "hooks.py").exists()
        assert "Created" in result.stdout

    def test_init_file_has_pep723_header(self, tmp_path: Path, monkeypatch):
        """Generated file has PEP 723 script header."""
        monkeypatch.chdir(tmp_path)
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "init"],
            capture_output=True,
        )
        content = (tmp_path / ".claude" / "hooks.py").read_text()
        assert "# /// script" in content
        assert "# requires-python" in content
        assert "# dependencies" in content
        assert "# ///" in content

    def test_init_file_has_hookapp(self, tmp_path: Path, monkeypatch):
        """Generated file has working HookApp example."""
        monkeypatch.chdir(tmp_path)
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "init"],
            capture_output=True,
        )
        content = (tmp_path / ".claude" / "hooks.py").read_text()
        assert "from fasthooks import HookApp" in content
        assert "app = HookApp()" in content
        assert "@app.pre_tool" in content
        assert "app.run()" in content

    def test_init_errors_if_exists(self, tmp_path: Path, monkeypatch):
        """fasthooks init errors if file exists."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "hooks.py").write_text("existing")
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "init"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "already exists" in result.stdout

    def test_init_force_overwrites(self, tmp_path: Path, monkeypatch):
        """fasthooks init --force overwrites existing file."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "hooks.py").write_text("existing")
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "init", "--force"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        content = (tmp_path / ".claude" / "hooks.py").read_text()
        assert "existing" not in content
        assert "HookApp" in content

    def test_init_custom_path(self, tmp_path: Path, monkeypatch):
        """fasthooks init --path uses custom location."""
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "init", "--path", "custom/hooks.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (tmp_path / "custom" / "hooks.py").exists()

    def test_init_creates_parent_dirs(self, tmp_path: Path, monkeypatch):
        """fasthooks init creates parent directories automatically."""
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "init", "--path", "a/b/c/hooks.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (tmp_path / "a" / "b" / "c" / "hooks.py").exists()


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
