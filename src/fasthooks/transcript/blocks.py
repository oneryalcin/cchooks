"""Content block types embedded in transcript messages."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from fasthooks.transcript.core import Transcript


class TextBlock(BaseModel):
    """Plain text content in a message."""

    model_config = ConfigDict(extra="allow")  # Preserve unknown fields

    type: Literal["text"] = "text"
    text: str = ""


class ToolUseBlock(BaseModel):
    """Claude invoking a tool."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    type: Literal["tool_use"] = "tool_use"
    id: str = ""
    name: str = ""
    input: dict[str, Any] = Field(default_factory=dict)

    # Private - not serialized
    _transcript: Transcript | None = None

    def set_transcript(self, transcript: Transcript) -> None:
        """Set transcript reference for relationship lookups."""
        object.__setattr__(self, "_transcript", transcript)

    @property
    def result(self) -> ToolResultBlock | None:
        """Find the matching ToolResult by tool_use_id."""
        if self._transcript:
            return self._transcript.find_tool_result(self.id)
        return None


class ToolResultBlock(BaseModel):
    """Result of a tool execution."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = ""
    content: str = ""
    is_error: bool = False

    # Private - not serialized
    _transcript: Transcript | None = None
    _tool_use_result: dict[str, Any] | str | None = None

    def set_transcript(self, transcript: Transcript) -> None:
        """Set transcript reference for relationship lookups."""
        object.__setattr__(self, "_transcript", transcript)

    def set_tool_use_result(self, result: dict[str, Any] | str | None) -> None:
        """Set the structured tool result from entry."""
        object.__setattr__(self, "_tool_use_result", result)

    @property
    def tool_use(self) -> ToolUseBlock | None:
        """Find the matching ToolUse by tool_use_id."""
        if self._transcript:
            return self._transcript.find_tool_use(self.tool_use_id)
        return None


class ThinkingBlock(BaseModel):
    """Claude's extended thinking (read-only - signature cannot be forged)."""

    model_config = ConfigDict(extra="allow")

    type: Literal["thinking"] = "thinking"
    thinking: str = ""
    signature: str = ""


# Union type for all content blocks
ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock


def parse_content_block(
    data: dict[str, Any],
    transcript: Transcript | None = None,
    tool_use_result: dict[str, Any] | str | None = None,
) -> ContentBlock:
    """Parse a content block from raw dict based on type."""
    block_type = data.get("type", "")

    if block_type == "text":
        return TextBlock.model_validate(data)
    elif block_type == "tool_use":
        block = ToolUseBlock.model_validate(data)
        if transcript:
            block.set_transcript(transcript)
        return block
    elif block_type == "tool_result":
        block = ToolResultBlock.model_validate(data)
        if transcript:
            block.set_transcript(transcript)
        if tool_use_result:
            block.set_tool_use_result(tool_use_result)
        return block
    elif block_type == "thinking":
        return ThinkingBlock.model_validate(data)
    else:
        # Unknown block type - return as TextBlock with type overridden
        # We need to override type since TextBlock expects Literal["text"]
        data_copy = dict(data)
        data_copy["type"] = "text"  # Override to satisfy Literal
        block = TextBlock.model_validate(data_copy)
        # Store original type in model_extra
        return block
