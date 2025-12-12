"""Tests for CLI commands."""
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from fasthooks.cli import app

runner = CliRunner()


class TestCLIHelp:
    """Tests for CLI help."""

    def test_help_shows_commands(self):
        """--help shows available commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "run" in result.output

    def test_version_flag(self):
        """--version shows version."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "fasthooks" in result.output
        assert "0.1.0" in result.output

    def test_short_version_flag(self):
        """-v shows version."""
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "fasthooks" in result.output


class TestCLIInit:
    """Tests for init command."""

    def test_init_creates_project(self):
        """init creates project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "my-hooks"

            result = runner.invoke(app, ["init", str(project_dir)])

            assert result.exit_code == 0
            assert project_dir.exists()
            assert (project_dir / "hooks.py").exists()
            assert (project_dir / "pyproject.toml").exists()

    def test_init_hooks_file_content(self):
        """Generated hooks.py has valid starter code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "my-hooks"

            runner.invoke(app, ["init", str(project_dir)])

            hooks_file = project_dir / "hooks.py"
            content = hooks_file.read_text()

            assert "from fasthooks import" in content
            assert "HookApp" in content
            assert "app.run()" in content
            assert "@app.pre_tool" in content
            assert "@app.on_stop" in content

    def test_init_pyproject_content(self):
        """Generated pyproject.toml has valid content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "my-hooks"

            runner.invoke(app, ["init", str(project_dir)])

            pyproject_file = project_dir / "pyproject.toml"
            content = pyproject_file.read_text()

            assert "fasthooks" in content
            assert "my_hooks" in content  # name with underscores

    def test_init_existing_dir_with_files_error(self):
        """init fails if directory exists with files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "existing"
            project_dir.mkdir()
            (project_dir / "hooks.py").write_text("existing")

            result = runner.invoke(app, ["init", str(project_dir)])

            assert result.exit_code == 1
            # Output may have newlines from rich formatting
            assert "already" in result.output and "exists" in result.output

    def test_init_empty_existing_dir_succeeds(self):
        """init succeeds if directory exists but is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "empty"
            project_dir.mkdir()

            result = runner.invoke(app, ["init", str(project_dir)])

            assert result.exit_code == 0
            assert (project_dir / "hooks.py").exists()

    def test_init_creates_nested_dirs(self):
        """init creates nested directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "deep" / "nested" / "hooks"

            result = runner.invoke(app, ["init", str(project_dir)])

            assert result.exit_code == 0
            assert project_dir.exists()

    def test_init_shows_next_steps(self):
        """init shows next steps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "my-hooks"

            result = runner.invoke(app, ["init", str(project_dir)])

            assert "Next steps" in result.output
            assert "cd" in result.output
            assert "uv sync" in result.output
            assert "settings.json" in result.output


class TestCLIRun:
    """Tests for run command."""

    def test_run_help(self):
        """run --help shows usage."""
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "hooks.py" in result.output

    def test_run_missing_file_error(self):
        """run fails if hooks.py doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to temp dir where no hooks.py exists
            result = runner.invoke(app, ["run", f"{tmpdir}/nonexistent.py"])

            assert result.exit_code == 1
            # Output may have newlines from rich formatting
            assert "not" in result.output and "found" in result.output

    def test_run_executes_hooks_file(self):
        """run executes the hooks file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hooks_file = Path(tmpdir) / "hooks.py"
            hooks_file.write_text("""
# Simple test file that just prints
print("HOOKS_EXECUTED")
""")

            result = runner.invoke(app, ["run", str(hooks_file)])

            assert result.exit_code == 0
            assert "HOOKS_EXECUTED" in result.output

    def test_run_default_path(self):
        """run uses hooks.py as default."""
        result = runner.invoke(app, ["run", "--help"])
        assert "default" in result.output.lower() or "hooks.py" in result.output


class TestCLIMain:
    """Tests for main entry point."""

    def test_no_args_shows_help(self):
        """No args shows help (exit 2 due to no_args_is_help=True)."""
        result = runner.invoke(app, [])
        # typer exits with 2 when no_args_is_help triggers
        assert result.exit_code == 2
        assert "init" in result.output
        assert "run" in result.output
