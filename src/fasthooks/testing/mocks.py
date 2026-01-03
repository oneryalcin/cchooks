"""Mock event factories for testing."""
from __future__ import annotations

from typing import Any

from fasthooks.events.lifecycle import (
    Notification,
    PreCompact,
    SessionEnd,
    SessionStart,
    Stop,
    SubagentStop,
    UserPromptSubmit,
)
from fasthooks.events.tools import (
    Bash,
    Edit,
    Glob,
    Grep,
    Read,
    Task,
    WebFetch,
    WebSearch,
    Write,
)


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
        tool_input: dict[str, Any] = {"command": command}
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

    # ═══════════════════════════════════════════════════════════════════════════
    # Additional tool events
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def grep(
        pattern: str,
        *,
        path: str | None = None,
        glob: str | None = None,
        output_mode: str | None = None,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Grep:
        """Create a Grep PreToolUse event."""
        tool_input: dict[str, Any] = {"pattern": pattern}
        if path:
            tool_input["path"] = path
        if glob:
            tool_input["glob"] = glob
        if output_mode:
            tool_input["output_mode"] = output_mode

        return Grep(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Grep",
            tool_input=tool_input,
            tool_use_id="test-tool-use",
        )

    @staticmethod
    def glob(
        pattern: str,
        *,
        path: str | None = None,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Glob:
        """Create a Glob PreToolUse event."""
        tool_input: dict[str, Any] = {"pattern": pattern}
        if path:
            tool_input["path"] = path

        return Glob(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Glob",
            tool_input=tool_input,
            tool_use_id="test-tool-use",
        )

    @staticmethod
    def task(
        prompt: str,
        *,
        description: str = "Test task",
        subagent_type: str | None = None,
        model: str | None = None,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Task:
        """Create a Task PreToolUse event."""
        tool_input: dict[str, Any] = {"prompt": prompt, "description": description}
        if subagent_type:
            tool_input["subagent_type"] = subagent_type
        if model:
            tool_input["model"] = model

        return Task(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Task",
            tool_input=tool_input,
            tool_use_id="test-tool-use",
        )

    @staticmethod
    def web_search(
        query: str,
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> WebSearch:
        """Create a WebSearch PreToolUse event."""
        return WebSearch(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="WebSearch",
            tool_input={"query": query},
            tool_use_id="test-tool-use",
        )

    @staticmethod
    def web_fetch(
        url: str,
        prompt: str = "",
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> WebFetch:
        """Create a WebFetch PreToolUse event."""
        return WebFetch(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="WebFetch",
            tool_input={"url": url, "prompt": prompt},
            tool_use_id="test-tool-use",
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Additional lifecycle events
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def subagent_stop(
        *,
        stop_hook_active: bool = False,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> SubagentStop:
        """Create a SubagentStop event."""
        return SubagentStop(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="SubagentStop",
            stop_hook_active=stop_hook_active,
        )

    @staticmethod
    def session_end(
        reason: str = "user_exit",
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> SessionEnd:
        """Create a SessionEnd event."""
        return SessionEnd(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="SessionEnd",
            reason=reason,
        )

    @staticmethod
    def user_prompt(
        prompt: str,
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> UserPromptSubmit:
        """Create a UserPromptSubmit event."""
        return UserPromptSubmit(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="UserPromptSubmit",
            prompt=prompt,
        )

    @staticmethod
    def notification(
        message: str,
        notification_type: str = "info",
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Notification:
        """Create a Notification event."""
        return Notification(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="Notification",
            message=message,
            notification_type=notification_type,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # PermissionRequest events
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def permission_bash(
        command: str,
        *,
        description: str | None = None,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Bash:
        """Create a Bash PermissionRequest event."""
        tool_input: dict[str, Any] = {"command": command}
        if description:
            tool_input["description"] = description

        return Bash(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PermissionRequest",
            tool_name="Bash",
            tool_input=tool_input,
            tool_use_id="test-tool-use",
        )

    @staticmethod
    def permission_write(
        file_path: str,
        content: str = "",
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Write:
        """Create a Write PermissionRequest event."""
        return Write(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PermissionRequest",
            tool_name="Write",
            tool_input={"file_path": file_path, "content": content},
            tool_use_id="test-tool-use",
        )

    @staticmethod
    def permission_edit(
        file_path: str,
        old_string: str,
        new_string: str,
        *,
        session_id: str = "test-session",
        cwd: str = "/workspace",
    ) -> Edit:
        """Create an Edit PermissionRequest event."""
        return Edit(
            session_id=session_id,
            cwd=cwd,
            permission_mode="default",
            hook_event_name="PermissionRequest",
            tool_name="Edit",
            tool_input={
                "file_path": file_path,
                "old_string": old_string,
                "new_string": new_string,
            },
            tool_use_id="test-tool-use",
        )
