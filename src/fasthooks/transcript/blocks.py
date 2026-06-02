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


class ImageBlock(BaseModel):
    """An image in a message (2.1.x).

    ``source`` is the image payload — base64 (``{type, media_type, data}``) or a
    URL (``{type: url, url}``). Kept as a dict so either form round-trips
    verbatim.
    """

    model_config = ConfigDict(extra="allow")

    type: Literal["image"] = "image"
    source: dict[str, Any] = Field(default_factory=dict)


class ServerToolUseBlock(BaseModel):
    """A server-side tool invocation (e.g. ``advisor``, ``web_search``).

    Same shape as :class:`ToolUseBlock`, but the call runs on Anthropic's side
    (ids are ``srvtoolu_…``). Added for 2.1.x transcripts.
    """

    model_config = ConfigDict(extra="allow")

    type: Literal["server_tool_use"] = "server_tool_use"
    id: str = ""
    name: str = ""
    input: dict[str, Any] = Field(default_factory=dict)


class AdvisorToolResultBlock(BaseModel):
    """Result of a server-side ``advisor`` tool call (2.1.x).

    ``content`` is the advisor payload — a dict (``{type: advisor_result, …}``),
    string, or list depending on the result. Optional fields default to ``None``
    so an absent field is not re-emitted on round-trip.
    """

    model_config = ConfigDict(extra="allow")

    type: Literal["advisor_tool_result"] = "advisor_tool_result"
    tool_use_id: str | None = None
    content: str | dict[str, Any] | list[Any] | None = None


class UnknownBlock(BaseModel):
    """Fallback for unrecognized block types.

    Preserves the original type and all data for forward compatibility.
    """

    model_config = ConfigDict(extra="allow")

    type: str = ""  # Preserves original type string
    text: str = ""  # For convenience, try to extract text if present


# Union type for all content blocks
ContentBlock = (
    TextBlock
    | ToolUseBlock
    | ToolResultBlock
    | ThinkingBlock
    | ImageBlock
    | ServerToolUseBlock
    | AdvisorToolResultBlock
    | UnknownBlock
)


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
    elif block_type == "image":
        return ImageBlock.model_validate(data)
    elif block_type == "server_tool_use":
        return ServerToolUseBlock.model_validate(data)
    elif block_type == "advisor_tool_result":
        return AdvisorToolResultBlock.model_validate(data)
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
