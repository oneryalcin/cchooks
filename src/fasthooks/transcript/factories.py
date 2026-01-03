"""Factory functions for creating transcript entries."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from fasthooks.transcript.blocks import ToolResultBlock, ToolUseBlock
from fasthooks.transcript.entries import AssistantMessage, Entry, UserMessage

if TYPE_CHECKING:
    from fasthooks.transcript.core import Transcript


def inject_tool_result(
    transcript: Transcript,
    tool_name: str,
    tool_input: dict[str, Any],
    result: str,
    *,
    is_error: bool = False,
    position: int | Literal["start", "end"] = "end",
) -> tuple[AssistantMessage, UserMessage]:
    """Inject a fake tool use + result pair into transcript.

    Creates an AssistantMessage with a ToolUseBlock and a UserMessage with
    the corresponding ToolResultBlock. Handles all the wiring (matching IDs,
    parent_uuid chain).

    Args:
        transcript: Transcript to modify
        tool_name: Name of tool (e.g., "Bash", "Read", "Write")
        tool_input: Tool input dict (e.g., {"command": "ls -la"})
        result: Tool result content string
        is_error: Whether result is an error
        position: Where to insert - int index, "start", or "end" (default)

    Returns:
        Tuple of (AssistantMessage, UserMessage) that were inserted

    Example:
        assistant, user = inject_tool_result(
            transcript,
            "Read",
            {"file_path": "/config.json"},
            '{"setting": "value"}'
        )
    """
    # Generate matching tool_use_id
    tool_use_id = f"toolu_{secrets.token_hex(12)}"

    # Get context entry for metadata (find last Entry, skip FileHistorySnapshot etc.)
    context: Entry | None = None
    for e in reversed(transcript.entries):
        if isinstance(e, Entry):
            context = e
            break

    # Determine insertion position and parent
    if position == "start":
        insert_idx = 0
        parent = None
    elif position == "end":
        insert_idx = len(transcript.entries)
        parent = transcript.entries[-1] if transcript.entries else None
    else:
        insert_idx = position
        parent = transcript.entries[insert_idx - 1] if insert_idx > 0 else None

    # Create assistant message with tool use
    tool_use = ToolUseBlock(id=tool_use_id, name=tool_name, input=tool_input)
    assistant = AssistantMessage.create(
        content=[tool_use],
        parent=parent,
        context=context,
        stop_reason="tool_use",
    )

    # Create user message with tool result
    tool_result = ToolResultBlock(
        tool_use_id=tool_use_id,
        content=result,
        is_error=is_error,
    )
    user_data: dict[str, Any] = {
        "uuid": str(uuid4()),
        "timestamp": datetime.now(timezone.utc),
        "parent_uuid": assistant.uuid,
        "is_synthetic": True,
        "user_type": "external",
    }
    # Copy metadata from context if available
    if context:
        user_data["session_id"] = context.session_id
        user_data["cwd"] = context.cwd
        user_data["version"] = context.version
        user_data["git_branch"] = context.git_branch
        user_data["slug"] = context.slug
        user_data["is_sidechain"] = context.is_sidechain
    user = UserMessage.model_validate(user_data)
    object.__setattr__(user, "_content", [tool_result])

    # Insert into transcript
    transcript.insert(insert_idx, assistant)
    transcript.insert(insert_idx + 1, user)

    return assistant, user
