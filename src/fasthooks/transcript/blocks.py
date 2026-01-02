"""Content block types embedded in transcript messages."""
from __future__ import annotations

import warnings
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
    content: str | list[dict[str, Any]] = ""  # Can be string or structured content
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


class UnknownBlock(BaseModel):
    """Fallback for unrecognized block types.

    Preserves the original type and all data for forward compatibility.
    """

    model_config = ConfigDict(extra="allow")

    type: str = ""  # Preserves original type string
    text: str = ""  # For convenience, try to extract text if present


# Union type for all content blocks
ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock | UnknownBlock


def parse_content_block(
    data: dict[str, Any],
    transcript: Transcript | None = None,
    tool_use_result: dict[str, Any] | str | None = None,
    validate: Literal["strict", "warn", "none"] = "warn",
) -> ContentBlock:
    """Parse a content block from raw dict based on type.

    Args:
        data: Raw block dict from transcript
        transcript: Transcript for relationship lookups
        tool_use_result: Structured tool result from entry
        validate: Validation mode - "strict" raises, "warn" logs warning, "none" silent
    """
    block_type = data.get("type", "")

    if block_type == "text":
        return TextBlock.model_validate(data)
    elif block_type == "tool_use":
        tool_use = ToolUseBlock.model_validate(data)
        if transcript:
            tool_use.set_transcript(transcript)
        return tool_use
    elif block_type == "tool_result":
        tool_result = ToolResultBlock.model_validate(data)
        if transcript:
            tool_result.set_transcript(transcript)
        if tool_use_result:
            tool_result.set_tool_use_result(tool_use_result)
        return tool_result
    elif block_type == "thinking":
        return ThinkingBlock.model_validate(data)
    else:
        # Unknown block type - preserve original type for forward compatibility
        if validate == "strict":
            raise ValueError(f"Unknown content block type: {block_type!r}")
        elif validate == "warn":
            warnings.warn(
                f"Unknown content block type: {block_type!r}. "
                "Consider updating fasthooks to support this type.",
                UserWarning,
                stacklevel=2,
            )
        # Return UnknownBlock that preserves original type
        return UnknownBlock.model_validate(data)
