"""Mock event factories for testing."""
from __future__ import annotations

from fasthooks.events.lifecycle import PreCompact, SessionStart, Stop
from fasthooks.events.tools import Bash, Edit, Read, Write


class MockEvent:
    """Factory for creating test events.

    Example:
        event = MockEvent.bash(command="ls -la")
        result = my_handler(event)
        assert result.decision != "deny"
    """

    @staticmethod
    def bash(
        command: str,
        *,
        description: str | None = None,
        timeout: int | None = None,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Bash:
        """Create a Bash PreToolUse event."""
        tool_input = {"command": command}
        if description:
            tool_input["description"] = description
        if timeout:
            tool_input["timeout"] = timeout

        return Bash(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input=tool_input,
            tool_use_id="test-tool-use",
        )

    @staticmethod
    def write(
        file_path: str,
        content: str = "",
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Write:
        """Create a Write PreToolUse event."""
        return Write(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Write",
            tool_input={"file_path": file_path, "content": content},
            tool_use_id="test-tool-use",
        )

    @staticmethod
    def read(
        file_path: str,
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Read:
        """Create a Read PreToolUse event."""
        return Read(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Read",
            tool_input={"file_path": file_path},
            tool_use_id="test-tool-use",
        )

    @staticmethod
    def edit(
        file_path: str,
        old_string: str,
        new_string: str,
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Edit:
        """Create an Edit PreToolUse event."""
        return Edit(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={
                "file_path": file_path,
                "old_string": old_string,
                "new_string": new_string,
            },
            tool_use_id="test-tool-use",
        )

    @staticmethod
    def stop(
        *,
        stop_hook_active: bool = False,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Stop:
        """Create a Stop event."""
        return Stop(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="Stop",
            stop_hook_active=stop_hook_active,
        )

    @staticmethod
    def session_start(
        source: str = "startup",
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> SessionStart:
        """Create a SessionStart event."""
        return SessionStart(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="SessionStart",
            source=source,
        )

    @staticmethod
    def pre_compact(
        trigger: str = "manual",
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> PreCompact:
        """Create a PreCompact event."""
        return PreCompact(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PreCompact",
            trigger=trigger,
        )
