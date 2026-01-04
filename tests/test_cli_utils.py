"""Tests for CLI utilities."""

from __future__ import annotations

import json
from pathlib import Path

from fasthooks.cli_utils import (
    backup_settings,
    delete_lock,
    find_project_root,
    get_lock_path,
    get_settings_path,
    make_relative_command,
    merge_hooks_config,
    read_lock,
    read_settings,
    remove_hooks_by_command,
    write_lock,
    write_settings,
)


class TestFindProjectRoot:
    """Tests for find_project_root."""

    def test_finds_claude_dir(self, tmp_path: Path):
        """Finds project root by .claude directory."""
        (tmp_path / ".claude").mkdir()
        (tmp_path / "subdir").mkdir()
        result = find_project_root(tmp_path / "subdir")
        assert result == tmp_path

    def test_finds_git_dir(self, tmp_path: Path):
        """Finds project root by .git directory."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "subdir").mkdir()
        result = find_project_root(tmp_path / "subdir")
        assert result == tmp_path

    def test_finds_pyproject_toml(self, tmp_path: Path):
        """Finds project root by pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "subdir").mkdir()
        result = find_project_root(tmp_path / "subdir")
        assert result == tmp_path

    def test_finds_package_json(self, tmp_path: Path):
        """Finds project root by package.json."""
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "subdir").mkdir()
        result = find_project_root(tmp_path / "subdir")
        assert result == tmp_path

    def test_claude_dir_priority(self, tmp_path: Path):
        """.claude takes priority over .git."""
        (tmp_path / ".git").mkdir()
        (tmp_path / ".claude").mkdir()
        (tmp_path / "subdir").mkdir()
        result = find_project_root(tmp_path / "subdir")
        assert (result / ".claude").is_dir()

    def test_fallback_to_start_path(self, tmp_path: Path):
        """Falls back to start path if no markers found."""
        (tmp_path / "subdir").mkdir()
        result = find_project_root(tmp_path / "subdir")
        assert result == (tmp_path / "subdir").resolve()

    def test_finds_root_from_deep_nesting(self, tmp_path: Path):
        """Finds project root from deeply nested directory."""
        (tmp_path / ".git").mkdir()
        deep_path = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep_path.mkdir(parents=True)
        result = find_project_root(deep_path)
        assert result == tmp_path


class TestMakeRelativeCommand:
    """Tests for make_relative_command."""

    def test_generates_correct_command(self, tmp_path: Path):
        """Generates correct uv command."""
        hooks_path = tmp_path / ".claude" / "hooks.py"
        result = make_relative_command(hooks_path, tmp_path)
        assert result == 'uv run --with fasthooks "$CLAUDE_PROJECT_DIR/.claude/hooks.py"'

    def test_nested_path(self, tmp_path: Path):
        """Works with nested paths."""
        hooks_path = tmp_path / "src" / "hooks" / "main.py"
        result = make_relative_command(hooks_path, tmp_path)
        assert result == 'uv run --with fasthooks "$CLAUDE_PROJECT_DIR/src/hooks/main.py"'

    def test_path_not_under_project_raises(self, tmp_path: Path):
        """Raises ValueError if hooks_path not under project_root."""
        hooks_path = tmp_path / "hooks.py"
        other_root = tmp_path / "other_project"
        other_root.mkdir()
        try:
            make_relative_command(hooks_path, other_root)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass  # Expected


class TestGetSettingsPath:
    """Tests for get_settings_path."""

    def test_project_scope(self, tmp_path: Path):
        """Project scope returns .claude/settings.json."""
        result = get_settings_path("project", tmp_path)
        assert result == tmp_path / ".claude" / "settings.json"

    def test_user_scope(self, tmp_path: Path):
        """User scope returns ~/.claude/settings.json."""
        result = get_settings_path("user", tmp_path)
        assert result == Path.home() / ".claude" / "settings.json"

    def test_local_scope(self, tmp_path: Path):
        """Local scope returns .claude/settings.local.json."""
        result = get_settings_path("local", tmp_path)
        assert result == tmp_path / ".claude" / "settings.local.json"


class TestGetLockPath:
    """Tests for get_lock_path."""

    def test_project_scope(self, tmp_path: Path):
        """Project scope returns .claude/.fasthooks.lock."""
        result = get_lock_path("project", tmp_path)
        assert result == tmp_path / ".claude" / ".fasthooks.lock"

    def test_user_scope(self, tmp_path: Path):
        """User scope returns ~/.claude/.fasthooks.lock."""
        result = get_lock_path("user", tmp_path)
        assert result == Path.home() / ".claude" / ".fasthooks.lock"

    def test_local_scope(self, tmp_path: Path):
        """Local scope returns .claude/.fasthooks.local.lock."""
        result = get_lock_path("local", tmp_path)
        assert result == tmp_path / ".claude" / ".fasthooks.local.lock"


class TestReadSettings:
    """Tests for read_settings."""

    def test_missing_file_returns_empty(self, tmp_path: Path):
        """Returns {} for missing file."""
        result = read_settings(tmp_path / "settings.json")
        assert result == {}

    def test_reads_valid_json(self, tmp_path: Path):
        """Reads valid JSON file."""
        path = tmp_path / "settings.json"
        path.write_text('{"hooks": {}}')
        result = read_settings(path)
        assert result == {"hooks": {}}

    def test_reads_jsonc_with_line_comments(self, tmp_path: Path):
        """Reads JSONC with // line comments."""
        path = tmp_path / "settings.json"
        path.write_text(
            """{
            // This is a comment
            "hooks": {}
        }"""
        )
        result = read_settings(path)
        assert result == {"hooks": {}}

    def test_reads_jsonc_with_block_comments(self, tmp_path: Path):
        """Reads JSONC with /* */ block comments."""
        path = tmp_path / "settings.json"
        path.write_text(
            """{
            /* This is a
               multi-line block comment */
            "hooks": {}
        }"""
        )
        result = read_settings(path)
        assert result == {"hooks": {}}

    def test_reads_jsonc_trailing_comma(self, tmp_path: Path):
        """Reads JSONC with trailing commas."""
        path = tmp_path / "settings.json"
        path.write_text('{"hooks": {},}')
        result = read_settings(path)
        assert result == {"hooks": {}}

    def test_invalid_json_raises(self, tmp_path: Path):
        """Raises ValueError for invalid JSON."""
        path = tmp_path / "settings.json"
        path.write_text("not json")
        try:
            read_settings(path)
            assert False, "Should have raised"
        except ValueError as e:
            assert "Invalid JSON" in str(e)


class TestWriteSettings:
    """Tests for write_settings."""

    def test_writes_json(self, tmp_path: Path):
        """Writes valid JSON."""
        path = tmp_path / "settings.json"
        write_settings(path, {"hooks": {}})
        content = path.read_text()
        assert json.loads(content) == {"hooks": {}}

    def test_creates_parent_dirs(self, tmp_path: Path):
        """Creates parent directories."""
        path = tmp_path / ".claude" / "settings.json"
        write_settings(path, {})
        assert path.exists()

    def test_formats_with_indent(self, tmp_path: Path):
        """Formats with 2-space indent."""
        path = tmp_path / "settings.json"
        write_settings(path, {"a": 1})
        content = path.read_text()
        assert "  " in content  # Has indentation


class TestBackupSettings:
    """Tests for backup_settings."""

    def test_missing_file_returns_none(self, tmp_path: Path):
        """Returns None for missing file."""
        result = backup_settings(tmp_path / "settings.json")
        assert result is None

    def test_creates_backup(self, tmp_path: Path):
        """Creates .bak file."""
        path = tmp_path / "settings.json"
        path.write_text('{"original": true}')
        result = backup_settings(path)
        assert result == tmp_path / "settings.json.bak"
        assert result.read_text() == '{"original": true}'


class TestMergeHooksConfig:
    """Tests for merge_hooks_config."""

    def test_empty_existing(self):
        """Merges into empty settings."""
        existing = {}
        new = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "our.py"}]}]}}
        result = merge_hooks_config(existing, new, "our.py")
        assert "PreToolUse" in result["hooks"]

    def test_preserves_other_hooks(self):
        """Preserves hooks from other commands."""
        existing = {
            "hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"command": "other.py"}]}]}
        }
        new = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "our.py"}]}]}}
        result = merge_hooks_config(existing, new, "our.py")
        assert len(result["hooks"]["PreToolUse"]) == 2

    def test_replaces_our_old_entry(self):
        """Replaces our old entry on reinstall."""
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Write", "hooks": [{"command": "other.py"}]},
                    {"matcher": "Bash", "hooks": [{"command": "our.py"}]},
                ]
            }
        }
        new = {"hooks": {"PreToolUse": [{"matcher": "Bash|Edit", "hooks": [{"command": "our.py"}]}]}}
        result = merge_hooks_config(existing, new, "our.py")
        assert len(result["hooks"]["PreToolUse"]) == 2
        matchers = [e["matcher"] for e in result["hooks"]["PreToolUse"]]
        assert "Write" in matchers
        assert "Bash|Edit" in matchers
        assert "Bash" not in matchers

    def test_preserves_non_hooks_settings(self):
        """Preserves allowedTools and other settings."""
        existing = {"allowedTools": ["Bash"], "hooks": {}}
        new = {"hooks": {"Stop": [{"hooks": [{"command": "our.py"}]}]}}
        result = merge_hooks_config(existing, new, "our.py")
        assert result["allowedTools"] == ["Bash"]

    def test_merges_multiple_event_types(self):
        """Merges hooks across multiple event types."""
        existing = {
            "hooks": {
                "PreToolUse": [{"matcher": "Write", "hooks": [{"command": "other.py"}]}],
                "Stop": [{"hooks": [{"command": "other.py"}]}],
            }
        }
        new = {
            "hooks": {
                "PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "our.py"}]}],
                "PostToolUse": [{"matcher": "*", "hooks": [{"command": "our.py"}]}],
                "Stop": [{"hooks": [{"command": "our.py"}]}],
            }
        }
        result = merge_hooks_config(existing, new, "our.py")
        # PreToolUse should have both entries
        assert len(result["hooks"]["PreToolUse"]) == 2
        # PostToolUse should be added
        assert "PostToolUse" in result["hooks"]
        # Stop should have both entries
        assert len(result["hooks"]["Stop"]) == 2


class TestRemoveHooksByCommand:
    """Tests for remove_hooks_by_command."""

    def test_removes_matching_entries(self):
        """Removes entries matching command."""
        settings = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Write", "hooks": [{"command": "other.py"}]},
                    {"matcher": "Bash", "hooks": [{"command": "our.py"}]},
                ],
                "Stop": [{"hooks": [{"command": "our.py"}]}],
            }
        }
        result, count = remove_hooks_by_command(settings, "our.py")
        assert count == 2
        assert len(result["hooks"]["PreToolUse"]) == 1
        assert "Stop" not in result["hooks"]

    def test_preserves_other_entries(self):
        """Preserves entries from other commands."""
        settings = {
            "hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"command": "other.py"}]}]}
        }
        result, count = remove_hooks_by_command(settings, "our.py")
        assert count == 0
        assert len(result["hooks"]["PreToolUse"]) == 1

    def test_preserves_non_hooks_settings(self):
        """Preserves allowedTools and other settings."""
        settings = {
            "allowedTools": ["Bash"],
            "hooks": {"Stop": [{"hooks": [{"command": "our.py"}]}]},
        }
        result, _ = remove_hooks_by_command(settings, "our.py")
        assert result["allowedTools"] == ["Bash"]

    def test_empty_settings(self):
        """Handles empty settings."""
        result, count = remove_hooks_by_command({}, "our.py")
        assert count == 0
        assert result == {}


class TestLockFile:
    """Tests for lock file utilities."""

    def test_read_missing_returns_none(self, tmp_path: Path):
        """read_lock returns None for missing file."""
        result = read_lock(tmp_path / ".fasthooks.lock")
        assert result is None

    def test_read_invalid_returns_none(self, tmp_path: Path):
        """read_lock returns None for invalid JSON."""
        path = tmp_path / ".fasthooks.lock"
        path.write_text("not json")
        result = read_lock(path)
        assert result is None

    def test_write_and_read(self, tmp_path: Path):
        """write_lock and read_lock round-trip."""
        path = tmp_path / ".fasthooks.lock"
        data = {"version": 1, "hooks_path": ".claude/hooks.py"}
        write_lock(path, data)
        result = read_lock(path)
        assert result == data

    def test_write_creates_parent_dirs(self, tmp_path: Path):
        """write_lock creates parent directories."""
        path = tmp_path / ".claude" / ".fasthooks.lock"
        write_lock(path, {"version": 1})
        assert path.exists()

    def test_delete_existing(self, tmp_path: Path):
        """delete_lock removes existing file."""
        path = tmp_path / ".fasthooks.lock"
        path.write_text("{}")
        result = delete_lock(path)
        assert result is True
        assert not path.exists()

    def test_delete_missing(self, tmp_path: Path):
        """delete_lock returns False for missing file."""
        result = delete_lock(tmp_path / ".fasthooks.lock")
        assert result is False
