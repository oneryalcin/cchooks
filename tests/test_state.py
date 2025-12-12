"""Tests for State dependency."""
import json

from fasthooks.depends import State


class TestStateBasic:
    def test_create_state(self, tmp_path):
        """State can be instantiated."""
        state_file = tmp_path / "state.json"
        s = State(state_file)
        assert s is not None

    def test_state_is_dict(self, tmp_path):
        """State behaves like a dict."""
        state_file = tmp_path / "state.json"
        s = State(state_file)
        s["key"] = "value"
        assert s["key"] == "value"
        assert s.get("missing") is None
        assert s.get("missing", "default") == "default"

    def test_state_dict_operations(self, tmp_path):
        """State supports standard dict operations."""
        state_file = tmp_path / "state.json"
        s = State(state_file)
        s["a"] = 1
        s["b"] = 2
        assert len(s) == 2
        assert "a" in s
        assert list(s.keys()) == ["a", "b"]
        del s["a"]
        assert "a" not in s


class TestStatePersistence:
    def test_state_saves_on_save(self, tmp_path):
        """State persists to file on save()."""
        state_file = tmp_path / "state.json"
        s = State(state_file)
        s["count"] = 42
        s.save()

        # Read file directly
        data = json.loads(state_file.read_text())
        assert data["count"] == 42

    def test_state_loads_existing(self, tmp_path):
        """State loads existing data on init."""
        state_file = tmp_path / "state.json"
        state_file.write_text('{"existing": "data", "num": 123}')

        s = State(state_file)
        assert s["existing"] == "data"
        assert s["num"] == 123

    def test_state_roundtrip(self, tmp_path):
        """State survives save and reload."""
        state_file = tmp_path / "state.json"

        # Create and save
        s1 = State(state_file)
        s1["session_count"] = 5
        s1["tools_used"] = ["Bash", "Read", "Write"]
        s1.save()

        # Load fresh
        s2 = State(state_file)
        assert s2["session_count"] == 5
        assert s2["tools_used"] == ["Bash", "Read", "Write"]

    def test_state_handles_missing_file(self, tmp_path):
        """State starts empty if file doesn't exist."""
        state_file = tmp_path / "nonexistent" / "state.json"
        s = State(state_file)
        assert len(s) == 0

    def test_state_handles_corrupt_file(self, tmp_path):
        """State starts empty if file is corrupt."""
        state_file = tmp_path / "state.json"
        state_file.write_text("not valid json {{{")

        s = State(state_file)
        assert len(s) == 0

    def test_state_creates_parent_dirs(self, tmp_path):
        """State.save() creates parent directories."""
        state_file = tmp_path / "deep" / "nested" / "state.json"
        s = State(state_file)
        s["key"] = "value"
        s.save()

        assert state_file.exists()
        assert json.loads(state_file.read_text()) == {"key": "value"}


class TestStateContextManager:
    def test_state_context_manager(self, tmp_path):
        """State can be used as context manager for auto-save."""
        state_file = tmp_path / "state.json"

        with State(state_file) as s:
            s["auto_saved"] = True

        # Should be saved
        data = json.loads(state_file.read_text())
        assert data["auto_saved"] is True

    def test_state_context_manager_exception(self, tmp_path):
        """State saves even if exception occurs."""
        state_file = tmp_path / "state.json"

        try:
            with State(state_file) as s:
                s["before_error"] = True
                raise ValueError("test error")
        except ValueError:
            pass

        # Should still be saved
        data = json.loads(state_file.read_text())
        assert data["before_error"] is True


class TestStateSessionScoped:
    def test_state_factory(self, tmp_path):
        """State.for_session() creates session-scoped state."""
        s = State.for_session("session-123", state_dir=tmp_path)
        s["key"] = "value"
        s.save()

        expected_file = tmp_path / "session-123.json"
        assert expected_file.exists()

    def test_state_factory_isolation(self, tmp_path):
        """Different sessions have isolated state."""
        s1 = State.for_session("session-a", state_dir=tmp_path)
        s1["name"] = "Alice"
        s1.save()

        s2 = State.for_session("session-b", state_dir=tmp_path)
        s2["name"] = "Bob"
        s2.save()

        # Reload and verify isolation
        s1_reload = State.for_session("session-a", state_dir=tmp_path)
        s2_reload = State.for_session("session-b", state_dir=tmp_path)

        assert s1_reload["name"] == "Alice"
        assert s2_reload["name"] == "Bob"
