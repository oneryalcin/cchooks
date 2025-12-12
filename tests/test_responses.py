"""Tests for response builders."""
import json

from fasthooks import allow, deny, block


class TestAllow:
    def test_allow_basic(self):
        """allow() returns approve decision."""
        response = allow()
        assert response.decision == "approve"

    def test_allow_with_message(self):
        """allow(message=...) includes system message."""
        response = allow(message="Hook approved this")
        assert response.decision == "approve"
        assert response.message == "Hook approved this"

    def test_allow_with_modify(self):
        """allow(modify=...) includes updated input."""
        response = allow(modify={"command": "ls -la"})
        assert response.decision == "approve"
        assert response.modify == {"command": "ls -la"}

    def test_allow_to_json_empty(self):
        """allow() produces minimal JSON."""
        response = allow()
        # Empty response is valid - just exit 0
        assert response.to_json() in ("", "{}")

    def test_allow_to_json_with_modify(self):
        """allow(modify=...) produces correct JSON structure."""
        response = allow(modify={"command": "ls -la"})
        data = json.loads(response.to_json())
        assert data["hookSpecificOutput"]["updatedInput"] == {"command": "ls -la"}


class TestDeny:
    def test_deny_basic(self):
        """deny() returns deny decision with reason."""
        response = deny("Not allowed")
        assert response.decision == "deny"
        assert response.reason == "Not allowed"

    def test_deny_with_interrupt(self):
        """deny(interrupt=True) stops Claude entirely."""
        response = deny("Critical error", interrupt=True)
        assert response.decision == "deny"
        assert response.interrupt is True

    def test_deny_to_json(self):
        """deny() produces correct JSON."""
        response = deny("Blocked")
        data = json.loads(response.to_json())
        assert data["decision"] == "deny"
        assert data["reason"] == "Blocked"


class TestBlock:
    def test_block_basic(self):
        """block() returns block decision for Stop hooks."""
        response = block("Keep working")
        assert response.decision == "block"
        assert response.reason == "Keep working"

    def test_block_to_json(self):
        """block() produces correct JSON."""
        response = block("Not done yet")
        data = json.loads(response.to_json())
        assert data["decision"] == "block"
        assert data["reason"] == "Not done yet"
