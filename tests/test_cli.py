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
        assert "0.1.4" in result.stdout


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

    def test_init_short_flag_force(self, tmp_path: Path, monkeypatch):
        """fasthooks init -f works as alias for --force."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "hooks.py").write_text("existing")
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "init", "-f"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "HookApp" in (tmp_path / ".claude" / "hooks.py").read_text()

    def test_init_short_flag_path(self, tmp_path: Path, monkeypatch):
        """fasthooks init -p works as alias for --path."""
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "init", "-p", "custom/hooks.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (tmp_path / "custom" / "hooks.py").exists()


class TestInitCommandUnit:
    """Unit tests for init command (direct function calls for coverage)."""

    def test_run_init_creates_file(self, tmp_path: Path, monkeypatch):
        """run_init creates hooks.py file."""
        from io import StringIO

        from rich.console import Console

        from fasthooks.cli.commands.init import run_init

        monkeypatch.chdir(tmp_path)
        console = Console(file=StringIO(), force_terminal=True)
        result = run_init(".claude/hooks.py", force=False, console=console)
        assert result == 0
        assert (tmp_path / ".claude" / "hooks.py").exists()

    def test_run_init_permission_denied(self, tmp_path: Path, monkeypatch):
        """run_init handles permission errors gracefully."""
        from io import StringIO
        from unittest.mock import patch

        from rich.console import Console

        from fasthooks.cli.commands.init import run_init

        monkeypatch.chdir(tmp_path)
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        with patch("pathlib.Path.write_text", side_effect=PermissionError("denied")):
            result = run_init(".claude/hooks.py", force=False, console=console)

        assert result == 1
        assert "Permission denied" in output.getvalue()

    def test_run_init_oserror(self, tmp_path: Path, monkeypatch):
        """run_init handles OS errors gracefully."""
        from io import StringIO
        from unittest.mock import patch

        from rich.console import Console

        from fasthooks.cli.commands.init import run_init

        monkeypatch.chdir(tmp_path)
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            result = run_init(".claude/hooks.py", force=False, console=console)

        assert result == 1
        assert "Cannot write" in output.getvalue()


class TestInstallCommand:
    """Tests for fasthooks install command."""

    def test_install_full_flow(self, tmp_path: Path, monkeypatch):
        """fasthooks install creates settings.json and lock file."""
        monkeypatch.chdir(tmp_path)
        # Create hooks.py with a handler
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass

if __name__ == "__main__":
    app.run()
"""
        )

        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Validated" in result.stdout
        assert "PreToolUse:Bash" in result.stdout
        assert "Restart" in result.stdout

        # Check settings.json created
        settings = claude_dir / "settings.json"
        assert settings.exists()
        import json

        data = json.loads(settings.read_text())
        assert "PreToolUse" in data["hooks"]

        # Check lock file created
        lock = claude_dir / ".fasthooks.lock"
        assert lock.exists()

    def test_install_file_not_found(self, tmp_path: Path, monkeypatch):
        """fasthooks install errors if hooks.py not found."""
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", "nonexistent.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "File not found" in result.stdout

    def test_install_syntax_error(self, tmp_path: Path, monkeypatch):
        """fasthooks install errors on syntax error."""
        monkeypatch.chdir(tmp_path)
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def foo(")
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", "bad.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Syntax error" in result.stdout

    def test_install_no_hookapp(self, tmp_path: Path, monkeypatch):
        """fasthooks install errors if no HookApp found."""
        monkeypatch.chdir(tmp_path)
        no_app = tmp_path / "no_app.py"
        no_app.write_text("x = 1")
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", "no_app.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "No HookApp" in result.stdout

    def test_install_no_handlers(self, tmp_path: Path, monkeypatch):
        """fasthooks install errors if no handlers registered (exit code 2)."""
        monkeypatch.chdir(tmp_path)
        no_handlers = tmp_path / "no_handlers.py"
        no_handlers.write_text(
            """
from fasthooks import HookApp
app = HookApp()
"""
        )
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", "no_handlers.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "No handlers registered" in result.stdout

    def test_install_already_installed_skip(self, tmp_path: Path, monkeypatch):
        """fasthooks install skips if already installed."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # First install
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
        )

        # Second install - should skip
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Already installed" in result.stdout

    def test_install_force_reinstall(self, tmp_path: Path, monkeypatch):
        """fasthooks install --force reinstalls."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # First install
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
        )

        # Force reinstall
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py", "--force"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Backed up" in result.stdout
        assert (claude_dir / "settings.json.bak").exists()

    def test_install_scope_local(self, tmp_path: Path, monkeypatch):
        """fasthooks install --scope local uses settings.local.json."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py", "--scope", "local"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (claude_dir / "settings.local.json").exists()
        assert (claude_dir / ".fasthooks.local.lock").exists()

    def test_install_short_flags(self, tmp_path: Path, monkeypatch):
        """fasthooks install -s and -f work."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py", "-s", "local", "-f"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


class TestInstallCommandUnit:
    """Unit tests for install command (direct function calls)."""

    def test_run_install_creates_files(self, tmp_path: Path, monkeypatch):
        """run_install creates settings and lock files."""
        from io import StringIO

        from rich.console import Console

        from fasthooks.cli.commands.install import run_install

        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        console = Console(file=StringIO(), force_terminal=True)
        result = run_install(".claude/hooks.py", "project", force=False, console=console)

        assert result == 0
        assert (claude_dir / "settings.json").exists()
        assert (claude_dir / ".fasthooks.lock").exists()

    def test_run_install_permission_error(self, tmp_path: Path, monkeypatch):
        """run_install handles permission errors."""
        from io import StringIO
        from unittest.mock import patch

        from rich.console import Console

        from fasthooks.cli.commands.install import run_install

        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        output = StringIO()
        console = Console(file=output, force_terminal=True)

        with patch(
            "fasthooks.cli.commands.install.write_settings",
            side_effect=PermissionError("denied"),
        ):
            result = run_install(".claude/hooks.py", "project", force=False, console=console)

        assert result == 1
        assert "Permission denied" in output.getvalue()


class TestUninstallCommand:
    """Tests for fasthooks uninstall command."""

    def test_uninstall_after_install(self, tmp_path: Path, monkeypatch):
        """fasthooks uninstall removes hooks after install."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # First install
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
        )

        # Now uninstall
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "uninstall"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Removed" in result.stdout
        assert "Deleted" in result.stdout
        assert "Restart" in result.stdout

        # Lock should be gone
        assert not (claude_dir / ".fasthooks.lock").exists()

        # Settings should have no hooks
        import json

        settings = json.loads((claude_dir / "settings.json").read_text())
        assert "hooks" not in settings or not settings.get("hooks")

    def test_uninstall_not_installed(self, tmp_path: Path, monkeypatch):
        """fasthooks uninstall errors if not installed."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude").mkdir()

        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "uninstall"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "No hooks installed" in result.stdout

    def test_uninstall_creates_backup(self, tmp_path: Path, monkeypatch):
        """fasthooks uninstall creates backup."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install first
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
        )

        # Uninstall
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "uninstall"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Backed up" in result.stdout
        assert (claude_dir / "settings.json.bak").exists()

    def test_uninstall_preserves_other_hooks(self, tmp_path: Path, monkeypatch):
        """fasthooks uninstall preserves hooks from other sources."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install our hooks
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
        )

        # Manually add another hook from different source
        import json

        settings_path = claude_dir / "settings.json"
        settings = json.loads(settings_path.read_text())
        settings["hooks"]["PreToolUse"].append(
            {"matcher": "Write", "hooks": [{"type": "command", "command": "other-script.py"}]}
        )
        settings_path.write_text(json.dumps(settings, indent=2))

        # Uninstall
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "uninstall"],
            capture_output=True,
        )

        # Other hook should be preserved
        final = json.loads(settings_path.read_text())
        assert "PreToolUse" in final["hooks"]
        assert any("other-script.py" in str(h) for h in final["hooks"]["PreToolUse"])

    def test_uninstall_scope_local(self, tmp_path: Path, monkeypatch):
        """fasthooks uninstall --scope local works."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install with local scope
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py", "--scope", "local"],
            capture_output=True,
        )

        # Uninstall with local scope
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "uninstall", "--scope", "local"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert not (claude_dir / ".fasthooks.local.lock").exists()

    def test_uninstall_short_flag(self, tmp_path: Path, monkeypatch):
        """fasthooks uninstall -s works."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install with local scope
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py", "-s", "local"],
            capture_output=True,
        )

        # Uninstall with short flag
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "uninstall", "-s", "local"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


class TestUninstallCommandUnit:
    """Unit tests for uninstall command (direct function calls)."""

    def test_run_uninstall_removes_hooks(self, tmp_path: Path, monkeypatch):
        """run_uninstall removes hooks and deletes lock."""
        from io import StringIO

        from rich.console import Console

        from fasthooks.cli.commands.install import run_install
        from fasthooks.cli.commands.uninstall import run_uninstall

        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install first
        console = Console(file=StringIO(), force_terminal=True)
        run_install(".claude/hooks.py", "project", force=False, console=console)

        # Uninstall
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        result = run_uninstall("project", console)

        assert result == 0
        assert not (claude_dir / ".fasthooks.lock").exists()

    def test_run_uninstall_not_installed(self, tmp_path: Path, monkeypatch):
        """run_uninstall returns error if not installed."""
        from io import StringIO

        from rich.console import Console

        from fasthooks.cli.commands.uninstall import run_uninstall

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude").mkdir()

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        result = run_uninstall("project", console)

        assert result == 1
        assert "No hooks installed" in output.getvalue()

    def test_run_uninstall_corrupted_lock(self, tmp_path: Path, monkeypatch):
        """run_uninstall returns error if lock has no command."""
        import json
        from io import StringIO

        from rich.console import Console

        from fasthooks.cli.commands.uninstall import run_uninstall

        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        # Create corrupted lock (no command field)
        lock_path = claude_dir / ".fasthooks.lock"
        lock_path.write_text(json.dumps({"version": 1, "hooks_registered": []}))

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        result = run_uninstall("project", console)

        assert result == 1
        assert "corrupted" in output.getvalue()

    def test_run_uninstall_write_permission_error(self, tmp_path: Path, monkeypatch):
        """run_uninstall handles permission error on settings write."""
        from io import StringIO
        from unittest.mock import patch

        from rich.console import Console

        from fasthooks.cli.commands.install import run_install
        from fasthooks.cli.commands.uninstall import run_uninstall

        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install first
        console = Console(file=StringIO(), force_terminal=True)
        run_install(".claude/hooks.py", "project", force=False, console=console)

        # Uninstall with permission error
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        with patch(
            "fasthooks.cli.commands.uninstall.write_settings",
            side_effect=PermissionError("denied"),
        ):
            result = run_uninstall("project", console)

        assert result == 1
        assert "Permission denied" in output.getvalue()

    def test_run_uninstall_delete_permission_error(self, tmp_path: Path, monkeypatch):
        """run_uninstall handles permission error on lock delete."""
        from io import StringIO
        from unittest.mock import patch

        from rich.console import Console

        from fasthooks.cli.commands.install import run_install
        from fasthooks.cli.commands.uninstall import run_uninstall

        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install first
        console = Console(file=StringIO(), force_terminal=True)
        run_install(".claude/hooks.py", "project", force=False, console=console)

        # Uninstall with permission error on delete
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        with patch(
            "fasthooks.cli.commands.uninstall.delete_lock",
            side_effect=PermissionError("denied"),
        ):
            result = run_uninstall("project", console)

        assert result == 1
        assert "Permission denied" in output.getvalue()


class TestStatusCommand:
    """Tests for fasthooks status command."""

    def test_status_not_installed(self, tmp_path: Path, monkeypatch):
        """fasthooks status shows 'Not installed' when no hooks installed."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude").mkdir()

        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "status"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Not installed" in result.stdout

    def test_status_after_install(self, tmp_path: Path, monkeypatch):
        """fasthooks status shows installed hooks."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install first
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
        )

        # Check status
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "status"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Installed" in result.stdout
        assert ".claude/hooks.py" in result.stdout
        assert "PreToolUse:Bash" in result.stdout

    def test_status_single_scope(self, tmp_path: Path, monkeypatch):
        """fasthooks status --scope project shows only project scope."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude").mkdir()

        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "status", "--scope", "project"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Project scope" in result.stdout
        # Should not show other scopes
        assert "User scope" not in result.stdout
        assert "Local scope" not in result.stdout

    def test_status_invalid_scope(self, tmp_path: Path, monkeypatch):
        """fasthooks status --scope invalid errors."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude").mkdir()

        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "status", "--scope", "invalid"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Invalid scope" in result.stdout

    def test_status_handler_mismatch(self, tmp_path: Path, monkeypatch):
        """fasthooks status detects handler changes since install."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass

@app.on_stop()
def stop(event):
    pass
"""
        )

        # Install
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
        )

        # Modify hooks.py - remove on_stop, add pre_tool("Write")
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass

@app.pre_tool("Write")
def check_write(event):
    pass
"""
        )

        # Check status
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "status"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Handlers changed" in result.stdout
        assert "Added" in result.stdout
        assert "Removed" in result.stdout
        assert "PreToolUse:Write" in result.stdout
        assert "Stop" in result.stdout

    def test_status_validation_error(self, tmp_path: Path, monkeypatch):
        """fasthooks status reports import errors."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
        )

        # Break hooks.py
        hooks_py.write_text(
            """
from fasthooks import HookApp
import nonexistent_module  # This will fail

app = HookApp()
"""
        )

        # Check status
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "status"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Validation error" in result.stdout
        assert "nonexistent_module" in result.stdout

    def test_status_multiple_scopes_warning(self, tmp_path: Path, monkeypatch):
        """fasthooks status warns when multiple scopes have hooks."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install in project scope
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
        )

        # Install in local scope
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py", "--scope", "local"],
            capture_output=True,
        )

        # Check status
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "status"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "MULTIPLE scopes" in result.stdout


class TestStatusCommandUnit:
    """Unit tests for status command functions."""

    def test_status_corrupted_settings_json(self, tmp_path: Path, monkeypatch):
        """fasthooks status handles corrupted settings.json gracefully."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install first
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
        )

        # Corrupt settings.json
        (claude_dir / "settings.json").write_text("{invalid json")

        # Status should not crash
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "status"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Settings mismatch" in result.stdout or "Invalid JSON" in result.stdout

    def test_status_deleted_settings_json(self, tmp_path: Path, monkeypatch):
        """fasthooks status handles deleted settings.json gracefully."""
        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Install first
        subprocess.run(
            [sys.executable, "-m", "fasthooks", "install", ".claude/hooks.py"],
            capture_output=True,
        )

        # Delete settings.json
        (claude_dir / "settings.json").unlink()

        # Status should not crash
        result = subprocess.run(
            [sys.executable, "-m", "fasthooks", "status"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Settings mismatch" in result.stdout

    def test_get_scope_status_not_installed(self, tmp_path: Path, monkeypatch):
        """get_scope_status returns not installed status."""
        from fasthooks.cli.commands.status import get_scope_status

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude").mkdir()

        status = get_scope_status("project", tmp_path)
        assert status.installed is False
        assert status.lock_data is None

    def test_get_scope_status_installed(self, tmp_path: Path, monkeypatch):
        """get_scope_status returns installed status with details."""
        import json

        from fasthooks.cli.commands.status import get_scope_status

        monkeypatch.chdir(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        # Create hooks.py
        hooks_py = claude_dir / "hooks.py"
        hooks_py.write_text(
            """
from fasthooks import HookApp
app = HookApp()

@app.pre_tool("Bash")
def check(event):
    pass
"""
        )

        # Create lock file
        lock_path = claude_dir / ".fasthooks.lock"
        lock_data = {
            "version": 1,
            "installed_at": "2024-01-15T10:30:00+00:00",
            "hooks_path": ".claude/hooks.py",
            "hooks_registered": ["PreToolUse:Bash"],
            "command": "uv run hooks.py",
        }
        lock_path.write_text(json.dumps(lock_data))

        # Create settings.json with matching command
        settings_path = claude_dir / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [{"type": "command", "command": "uv run hooks.py"}],
                            }
                        ]
                    }
                }
            )
        )

        status = get_scope_status("project", tmp_path)
        assert status.installed is True
        assert status.lock_data is not None
        assert status.handlers_match is True
        assert status.settings_in_sync is True

    def test_run_status_success(self, tmp_path: Path, monkeypatch):
        """run_status returns 0 on success."""
        from io import StringIO

        from rich.console import Console

        from fasthooks.cli.commands.status import run_status

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".claude").mkdir()

        output = StringIO()
        console = Console(file=output, force_terminal=True)
        result = run_status(None, console)

        assert result == 0
        assert "Not installed" in output.getvalue()


class TestCheckSettingsSync:
    """Isolated unit tests for check_settings_sync function."""

    def test_check_settings_sync_in_sync(self, tmp_path: Path):
        """Returns True when settings match lock."""
        import json

        from fasthooks.cli.commands.status import check_settings_sync

        lock_data = {
            "hooks_registered": ["PreToolUse:Bash", "Stop"],
            "command": "uv run hooks.py",
        }

        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {"matcher": "Bash", "hooks": [{"command": "uv run hooks.py"}]}
                        ],
                        "Stop": [{"hooks": [{"command": "uv run hooks.py"}]}],
                    }
                }
            )
        )

        in_sync, error = check_settings_sync(lock_data, settings_path, "uv run hooks.py")
        assert in_sync is True
        assert error is None

    def test_check_settings_sync_missing_event(self, tmp_path: Path):
        """Returns False when settings missing event type."""
        import json

        from fasthooks.cli.commands.status import check_settings_sync

        lock_data = {
            "hooks_registered": ["PreToolUse:Bash", "Stop"],
            "command": "uv run hooks.py",
        }

        # Missing Stop in settings
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {"matcher": "Bash", "hooks": [{"command": "uv run hooks.py"}]}
                        ],
                    }
                }
            )
        )

        in_sync, error = check_settings_sync(lock_data, settings_path, "uv run hooks.py")
        assert in_sync is False
        assert error is None

    def test_check_settings_sync_invalid_json(self, tmp_path: Path):
        """Returns False with error message for invalid JSON."""
        from fasthooks.cli.commands.status import check_settings_sync

        lock_data = {
            "hooks_registered": ["PreToolUse:Bash"],
            "command": "uv run hooks.py",
        }

        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{invalid json")

        in_sync, error = check_settings_sync(lock_data, settings_path, "uv run hooks.py")
        assert in_sync is False
        assert error is not None
        assert "Invalid JSON" in error

    def test_check_settings_sync_missing_file(self, tmp_path: Path):
        """Returns False when settings file doesn't exist."""
        from fasthooks.cli.commands.status import check_settings_sync

        lock_data = {
            "hooks_registered": ["PreToolUse:Bash"],
            "command": "uv run hooks.py",
        }

        settings_path = tmp_path / "nonexistent.json"

        in_sync, error = check_settings_sync(lock_data, settings_path, "uv run hooks.py")
        assert in_sync is False  # No events found = mismatch
        assert error is None

    def test_check_settings_sync_multiple_handlers_same_event(self, tmp_path: Path):
        """Handles multiple handlers for same event type."""
        import json

        from fasthooks.cli.commands.status import check_settings_sync

        # Lock has PreToolUse:Bash and PreToolUse:Write (both PreToolUse)
        lock_data = {
            "hooks_registered": ["PreToolUse:Bash", "PreToolUse:Write"],
            "command": "uv run hooks.py",
        }

        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {"matcher": "Bash|Write", "hooks": [{"command": "uv run hooks.py"}]}
                        ],
                    }
                }
            )
        )

        in_sync, error = check_settings_sync(lock_data, settings_path, "uv run hooks.py")
        assert in_sync is True
        assert error is None

    def test_check_settings_sync_lifecycle_events(self, tmp_path: Path):
        """Handles lifecycle events without colon (Stop, SessionStart)."""
        import json

        from fasthooks.cli.commands.status import check_settings_sync

        lock_data = {
            "hooks_registered": ["Stop", "SessionStart"],
            "command": "uv run hooks.py",
        }

        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "Stop": [{"hooks": [{"command": "uv run hooks.py"}]}],
                        "SessionStart": [{"hooks": [{"command": "uv run hooks.py"}]}],
                    }
                }
            )
        )

        in_sync, error = check_settings_sync(lock_data, settings_path, "uv run hooks.py")
        assert in_sync is True
        assert error is None

    def test_check_settings_sync_empty_hooks_registered(self, tmp_path: Path):
        """Handles empty hooks_registered list."""
        import json

        from fasthooks.cli.commands.status import check_settings_sync

        lock_data = {
            "hooks_registered": [],
            "command": "uv run hooks.py",
        }

        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({}))

        in_sync, error = check_settings_sync(lock_data, settings_path, "uv run hooks.py")
        assert in_sync is True  # Both empty = in sync
        assert error is None


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
