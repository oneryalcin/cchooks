"""Transcript entry types."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from fasthooks.transcript.blocks import (
    ContentBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    parse_content_block,
)

if TYPE_CHECKING:
    from fasthooks.transcript.core import Transcript


class Entry(BaseModel):
    """Base class for all transcript entries."""

    model_config = ConfigDict(
        extra="allow",  # Preserve unknown fields
        populate_by_name=True,  # Allow both alias and field name
        arbitrary_types_allowed=True,
    )

    type: str = ""
    uuid: str = ""
    parent_uuid: str | None = Field(default=None, alias="parentUuid")
    timestamp: datetime | None = None
    session_id: str = Field(default="", alias="sessionId")
    cwd: str = ""
    version: str = ""
    git_branch: str = Field(default="", alias="gitBranch")
    is_sidechain: bool = Field(default=False, alias="isSidechain")
    user_type: str = Field(default="", alias="userType")
    slug: str = ""
    is_synthetic: bool = Field(default=False, alias="isSynthetic")

    # Internal tracking
    _line_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize entry to dict for JSONL output.

        Uses camelCase aliases and excludes internal fields.
        mode='json' ensures datetime is serialized to ISO8601 string.
        """
        data = self.model_dump(by_alias=True, exclude_none=True, mode="json")
        # Remove internal fields
        data.pop("_line_number", None)
        return data


class UserMessage(Entry):
    """User's input to Claude."""

    type: Literal["user"] = "user"

    # Content - either string or parsed tool results
    # Note: We parse this separately since it's nested in message.content
    _content: str | list[ToolResultBlock] = ""

    # Additional fields from raw data
    thinking_metadata: dict[str, Any] | None = Field(
        default=None, alias="thinkingMetadata"
    )
    todos: list[Any] = Field(default_factory=list)
    tool_use_result: dict[str, Any] | str | None = Field(
        default=None, alias="toolUseResult"
    )
    is_meta: bool = Field(default=False, alias="isMeta")
    is_compact_summary: bool = Field(default=False, alias="isCompactSummary")
    is_visible_in_transcript_only: bool = Field(
        default=False, alias="isVisibleInTranscriptOnly"
    )

    @property
    def content(self) -> str | list[ToolResultBlock]:
        """Get message content."""
        return self._content

    @property
    def is_tool_result(self) -> bool:
        """Whether this is a tool result message."""
        return isinstance(self._content, list)

    @property
    def tool_results(self) -> list[ToolResultBlock]:
        """Get tool results if this is a tool result message."""
        if isinstance(self._content, list):
            return self._content
        return []

    @property
    def text(self) -> str:
        """Get text content if it's a text message."""
        if isinstance(self._content, str):
            return self._content
        return ""

    @classmethod
    def create(
        cls,
        content: str,
        *,
        parent: Entry | None = None,
        context: Entry | None = None,
        cwd: str | None = None,
        session_id: str | None = None,
        **overrides: Any,
    ) -> UserMessage:
        """Create a valid UserMessage with proper UUID/timestamp.

        Args:
            content: Message text
            parent: Entry this should follow (sets parent_uuid)
            context: Entry to copy metadata from (cwd, session_id, etc.)
            cwd: Override working directory
            session_id: Override session ID
            **overrides: Any other field overrides

        Returns:
            New UserMessage marked as synthetic
        """
        # Use context for metadata, fallback to parent, then defaults
        ctx = context or parent

        data: dict[str, Any] = {
            "uuid": str(uuid4()),
            "timestamp": datetime.now(timezone.utc),
            "is_synthetic": True,
            "user_type": "external",
        }

        # Copy metadata from context (only if it's an Entry with these fields)
        if ctx and isinstance(ctx, Entry):
            data["session_id"] = ctx.session_id
            data["cwd"] = ctx.cwd
            data["version"] = ctx.version
            data["git_branch"] = ctx.git_branch
            data["slug"] = ctx.slug
            data["is_sidechain"] = ctx.is_sidechain

        # Set parent_uuid
        if parent:
            data["parent_uuid"] = parent.uuid

        # Apply explicit overrides
        if cwd is not None:
            data["cwd"] = cwd
        if session_id is not None:
            data["session_id"] = session_id
        data.update(overrides)

        # Create instance and set content
        instance = cls.model_validate(data)
        object.__setattr__(instance, "_content", content)
        return instance

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict, reconstructing message structure from parsed content."""
        data = super().to_dict()

        # Reconstruct message.content from _content
        if isinstance(self._content, str):
            message_content: str | list[dict[str, Any]] = self._content
        else:
            # Serialize tool result blocks
            message_content = []
            for block in self._content:
                block_data = block.model_dump(by_alias=True, exclude_none=True)
                # Remove private fields
                block_data.pop("_transcript", None)
                block_data.pop("_tool_use_result", None)
                message_content.append(block_data)

        # Get existing message dict or create new one
        message = data.get("message", {})
        if not isinstance(message, dict):
            message = {}
        message["role"] = "user"
        message["content"] = message_content
        data["message"] = message

        return data

    @classmethod
    def from_raw(
        cls, data: dict[str, Any], transcript: Transcript | None = None
    ) -> UserMessage:
        """Parse from raw transcript dict, handling nested message.content."""
        # Extract message content
        message = data.get("message", {})
        raw_content = message.get("content", "")

        # Parse content
        if isinstance(raw_content, str):
            content: str | list[ToolResultBlock] = raw_content
        elif isinstance(raw_content, list):
            tool_use_result = data.get("toolUseResult")
            content = []
            for item in raw_content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    block = ToolResultBlock.model_validate(item)
                    if transcript:
                        block.set_transcript(transcript)
                    if tool_use_result:
                        block.set_tool_use_result(tool_use_result)
                    content.append(block)
        else:
            content = ""

        # Create instance with pydantic validation
        instance = cls.model_validate(data)
        object.__setattr__(instance, "_content", content)
        return instance


class AssistantMessage(Entry):
    """Claude's response."""

    type: Literal["assistant"] = "assistant"
    request_id: str = Field(default="", alias="requestId")

    # These come from nested message object
    _message_id: str = ""
    _model: str = ""
    _content: list[ContentBlock] = []
    _stop_reason: str | None = None
    _usage: dict[str, Any] = {}

    @property
    def message_id(self) -> str:
        """Anthropic message ID."""
        return self._message_id

    @property
    def model(self) -> str:
        """Model used for this response."""
        return self._model

    @property
    def content(self) -> list[ContentBlock]:
        """Content blocks in this message."""
        return self._content

    @property
    def stop_reason(self) -> str | None:
        """Stop reason if any."""
        return self._stop_reason

    @property
    def usage(self) -> dict[str, Any]:
        """Token usage statistics."""
        return self._usage

    @property
    def text(self) -> str:
        """Extract concatenated text from TextBlocks."""
        return "\n".join(b.text for b in self._content if isinstance(b, TextBlock))

    @property
    def tool_uses(self) -> list[ToolUseBlock]:
        """Extract ToolUseBlocks from content."""
        return [b for b in self._content if isinstance(b, ToolUseBlock)]

    @property
    def thinking(self) -> str:
        """Extract thinking text."""
        return "\n".join(
            b.thinking for b in self._content if isinstance(b, ThinkingBlock)
        )

    @property
    def has_tool_use(self) -> bool:
        """Whether this message contains tool use."""
        return any(isinstance(b, ToolUseBlock) for b in self._content)

    @classmethod
    def create(
        cls,
        content: str | list[ContentBlock],
        *,
        parent: Entry | None = None,
        context: Entry | None = None,
        model: str = "synthetic",
        stop_reason: str = "end_turn",
        cwd: str | None = None,
        session_id: str | None = None,
        **overrides: Any,
    ) -> AssistantMessage:
        """Create a valid AssistantMessage with proper UUID/timestamp.

        Args:
            content: Text string (becomes TextBlock) or list of ContentBlocks
            parent: Entry this should follow (sets parent_uuid)
            context: Entry to copy metadata from (cwd, session_id, etc.)
            model: Model name (default "synthetic")
            stop_reason: Stop reason (default "end_turn")
            cwd: Override working directory
            session_id: Override session ID
            **overrides: Any other field overrides

        Returns:
            New AssistantMessage marked as synthetic
        """
        # Use context for metadata, fallback to parent, then defaults
        ctx = context or parent

        data: dict[str, Any] = {
            "uuid": str(uuid4()),
            "timestamp": datetime.now(timezone.utc),
            "request_id": f"req_{secrets.token_hex(12)}",
            "is_synthetic": True,
            "user_type": "external",
        }

        # Copy metadata from context (only if it's an Entry with these fields)
        if ctx and isinstance(ctx, Entry):
            data["session_id"] = ctx.session_id
            data["cwd"] = ctx.cwd
            data["version"] = ctx.version
            data["git_branch"] = ctx.git_branch
            data["slug"] = ctx.slug
            data["is_sidechain"] = ctx.is_sidechain

        # Set parent_uuid
        if parent:
            data["parent_uuid"] = parent.uuid

        # Apply explicit overrides
        if cwd is not None:
            data["cwd"] = cwd
        if session_id is not None:
            data["session_id"] = session_id
        data.update(overrides)

        # Parse content
        if isinstance(content, str):
            blocks: list[ContentBlock] = [TextBlock(text=content)]
        else:
            blocks = content

        # Create instance and set private fields
        instance = cls.model_validate(data)
        object.__setattr__(instance, "_message_id", f"msg_{secrets.token_hex(12)}")
        object.__setattr__(instance, "_model", model)
        object.__setattr__(instance, "_content", blocks)
        object.__setattr__(instance, "_stop_reason", stop_reason)
        object.__setattr__(instance, "_usage", {})
        return instance

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict, reconstructing message structure from parsed content."""
        data = super().to_dict()

        # Serialize content blocks
        content_list = []
        for block in self._content:
            block_data = block.model_dump(by_alias=True, exclude_none=True)
            # Remove private fields
            block_data.pop("_transcript", None)
            block_data.pop("_tool_use_result", None)
            content_list.append(block_data)

        # Reconstruct message object
        message: dict[str, Any] = {
            "type": "message",
            "role": "assistant",
            "content": content_list,
        }
        if self._message_id:
            message["id"] = self._message_id
        if self._model:
            message["model"] = self._model
        if self._stop_reason is not None:
            message["stop_reason"] = self._stop_reason
        if self._usage:
            message["usage"] = self._usage

        data["message"] = message
        return data

    @classmethod
    def from_raw(
        cls, data: dict[str, Any], transcript: Transcript | None = None
    ) -> AssistantMessage:
        """Parse from raw transcript dict, handling nested message object."""
        message = data.get("message", {})
        raw_content = message.get("content", [])

        # Get validate setting from transcript (default to "warn")
        validate = transcript.validate if transcript else "warn"

        # Parse content blocks
        content = []
        if isinstance(raw_content, list):
            for item in raw_content:
                if isinstance(item, dict):
                    content.append(parse_content_block(item, transcript, validate=validate))

        # Create instance with pydantic validation
        instance = cls.model_validate(data)
        object.__setattr__(instance, "_message_id", message.get("id", ""))
        object.__setattr__(instance, "_model", message.get("model", ""))
        object.__setattr__(instance, "_content", content)
        object.__setattr__(instance, "_stop_reason", message.get("stop_reason"))
        object.__setattr__(instance, "_usage", message.get("usage", {}))
        return instance


class SystemEntry(Entry):
    """System events and metadata."""

    type: Literal["system"] = "system"
    subtype: str = ""
    content: str = ""
    level: str = ""


class CompactBoundary(SystemEntry):
    """Marks where context compaction occurred."""

    subtype: Literal["compact_boundary"] = "compact_boundary"
    logical_parent_uuid: str = Field(default="", alias="logicalParentUuid")
    compact_metadata: dict[str, Any] = Field(default_factory=dict, alias="compactMetadata")


class StopHookSummary(SystemEntry):
    """Summary of hook execution at stop."""

    subtype: Literal["stop_hook_summary"] = "stop_hook_summary"
    hook_count: int = Field(default=0, alias="hookCount")
    hook_infos: list[dict[str, Any]] = Field(default_factory=list, alias="hookInfos")
    hook_errors: list[Any] = Field(default_factory=list, alias="hookErrors")
    prevented_continuation: bool = Field(default=False, alias="preventedContinuation")
    stop_reason: str = Field(default="", alias="stopReason")
    has_output: bool = Field(default=False, alias="hasOutput")
    tool_use_id: str = Field(default="", alias="toolUseID")


class FileHistorySnapshot(BaseModel):
    """Tracks file backups for undo capability. Not a message entry."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: Literal["file-history-snapshot"] = "file-history-snapshot"
    message_id: str = Field(default="", alias="messageId")
    snapshot: dict[str, Any] = Field(default_factory=dict)
    is_snapshot_update: bool = Field(default=False, alias="isSnapshotUpdate")

    _line_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSONL output."""
        data = self.model_dump(by_alias=True, exclude_none=True, mode="json")
        data.pop("_line_number", None)
        return data


# Type alias for all entry types
TranscriptEntry = (
    UserMessage
    | AssistantMessage
    | SystemEntry
    | CompactBoundary
    | StopHookSummary
    | FileHistorySnapshot
    | Entry  # Fallback for unknown types
)


def parse_entry(
    data: dict[str, Any], transcript: Transcript | None = None
) -> TranscriptEntry:
    """Parse an entry from raw dict based on type."""
    entry_type = data.get("type", "")

    if entry_type == "user":
        return UserMessage.from_raw(data, transcript)
    elif entry_type == "assistant":
        return AssistantMessage.from_raw(data, transcript)
    elif entry_type == "system":
        subtype = data.get("subtype", "")
        if subtype == "compact_boundary":
            return CompactBoundary.model_validate(data)
        elif subtype == "stop_hook_summary":
            return StopHookSummary.model_validate(data)
        else:
            return SystemEntry.model_validate(data)
    elif entry_type == "file-history-snapshot":
        return FileHistorySnapshot.model_validate(data)
    else:
        # Unknown type - return base Entry
        return Entry.model_validate(data)
