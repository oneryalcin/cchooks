"""Transcript entry types."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
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


def _content_block_to_wire(block: BaseModel) -> dict[str, Any]:
    """Serialize a content block to its JSONL wire dict.

    Used to rebuild ``message.content`` so in-place block mutations persist on
    save; the rest of the ``message`` is preserved verbatim from the raw record.
    """
    return block.model_dump(by_alias=True, exclude_none=True)


class Entry(BaseModel):
    """Base for *any* JSONL stream record — messages and bookkeeping alike.

    Holds only what every record shares: the ``type`` discriminator, the internal
    line number, and JSONL (de)serialization. The conversation-graph fields
    (uuid, parent_uuid, session metadata) live on :class:`MessageEntry`, so a
    non-message record like :class:`FileHistorySnapshot` does not inherit — and
    therefore does not re-serialize — a dozen empty ``uuid``/``sessionId``/``cwd``
    fields it never had on the wire.
    """

    model_config = ConfigDict(
        extra="allow",  # Preserve unknown fields
        populate_by_name=True,  # Allow both alias and field name
        arbitrary_types_allowed=True,
    )

    type: str = ""

    # Internal tracking
    _line_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize entry to dict for JSONL output.

        Wire-faithful: ``exclude_unset`` emits only the fields that parsing (or a
        factory) actually set, so a parsed-then-saved record matches the canonical
        Claude Code JSONL rather than gaining a dozen defaulted-to-False/"" fields
        (isMeta, isSynthetic, slug, ...) it never had. The ``type`` discriminator
        is forced because factory-created entries leave it at its class default
        (hence "unset"), yet every real record carries it.

        Uses camelCase aliases. mode='json' serializes datetime to ISO8601.
        """
        data = self.model_dump(by_alias=True, exclude_unset=True, mode="json")
        data.pop("_line_number", None)
        data["type"] = self.type
        return data


class MessageEntry(Entry):
    """A record that participates in the conversation graph.

    It carries ``uuid``/``parent_uuid`` plus the session metadata used to link
    entries into a tree. Despite the name this is broader than "chat message":
    :class:`UserMessage`, :class:`AssistantMessage`, :class:`SystemEntry` (and its
    subtypes), and unknown-but-graph-shaped records are all ``MessageEntry``.

    The ``isinstance(e, MessageEntry)`` discriminator therefore means "has graph
    identity" — exactly what separates these from :class:`FileHistorySnapshot`,
    which is a bare bookkeeping record with no uuid/parent. Do not re-narrow this
    to "is a chat message" by name; that reintroduces the bug this layer fixes.
    """

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


class UserMessage(MessageEntry):
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
    tool_use_result: dict[str, Any] | str | list[Any] | None = Field(
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
        parent: MessageEntry | None = None,
        context: MessageEntry | None = None,
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
            "timestamp": datetime.now(UTC),
            "is_synthetic": True,
            "user_type": "external",
        }

        # Copy metadata from context (only if it's an Entry with these fields)
        if ctx and isinstance(ctx, MessageEntry):
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
        """Serialize, refreshing ``message.content`` from the parsed blocks.

        The other ``message`` keys are preserved verbatim from the raw record
        (the base dump keeps it as an extra), so nothing fasthooks doesn't model
        is lost. ``content`` is rebuilt from ``_content`` so in-place block
        mutations persist on save. A synthetic/factory entry (no raw ``message``)
        gets a minimal one.
        """
        data = super().to_dict()
        raw_message = data.get("message")
        message = dict(raw_message) if isinstance(raw_message, dict) else {"role": "user"}
        if isinstance(self._content, str):
            message["content"] = self._content
        else:
            message["content"] = [_content_block_to_wire(b) for b in self._content]
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


class AssistantMessage(MessageEntry):
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
        parent: MessageEntry | None = None,
        context: MessageEntry | None = None,
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
            "timestamp": datetime.now(UTC),
            "request_id": f"req_{secrets.token_hex(12)}",
            "is_synthetic": True,
            "user_type": "external",
        }

        # Copy metadata from context (only if it's an Entry with these fields)
        if ctx and isinstance(ctx, MessageEntry):
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
        """Serialize, refreshing ``message.content`` from the parsed blocks.

        For a parsed record the raw ``message`` is preserved (base-dump extra) and
        only ``content`` is rebuilt — so fields fasthooks doesn't model
        (stop_sequence, ...) survive, while in-place block mutations persist on
        save. A synthetic/factory entry (no raw ``message``) builds one from the
        parsed private fields.
        """
        data = super().to_dict()
        message = data.get("message")
        if isinstance(message, dict):
            message = dict(message)
        else:
            message = {"type": "message", "role": "assistant"}
            if self._message_id:
                message["id"] = self._message_id
            if self._model:
                message["model"] = self._model
            if self._stop_reason is not None:
                message["stop_reason"] = self._stop_reason
            if self._usage:
                message["usage"] = self._usage
        message["content"] = [_content_block_to_wire(b) for b in self._content]
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


class SystemEntry(MessageEntry):
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


class FileHistorySnapshot(Entry):
    """Tracks file backups for undo capability. A bookkeeping record, *not* a
    message: it has no uuid/parent and never participates in the conversation
    graph. Extends :class:`Entry` (not :class:`MessageEntry`) so it reuses the
    shared config/``_line_number``/``to_dict`` without inheriting graph fields.
    """

    type: Literal["file-history-snapshot"] = "file-history-snapshot"
    message_id: str = Field(default="", alias="messageId")
    snapshot: dict[str, Any] = Field(default_factory=dict)
    is_snapshot_update: bool = Field(default=False, alias="isSnapshotUpdate")


# Type alias for all entry types. MessageEntry is the catch-all: parse_entry
# returns it for unknown types (an unrecognized record still links into the
# graph), and FileHistorySnapshot is the one non-message record. A bare Entry is
# never produced, so it is not a member.
TranscriptEntry = (
    UserMessage
    | AssistantMessage
    | SystemEntry
    | CompactBoundary
    | StopHookSummary
    | FileHistorySnapshot
    | MessageEntry  # Fallback for unknown graph-shaped records
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
        # Unknown type. Treat it as a graph record (MessageEntry, not bare Entry):
        # an unrecognized stream record that carries uuid/parentUuid should still
        # link into the conversation graph, matching pre-#25 behavior.
        return MessageEntry.model_validate(data)
