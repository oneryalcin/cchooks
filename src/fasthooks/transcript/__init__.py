"""Rich transcript modeling for context engineering."""
from fasthooks.transcript.blocks import (
    ContentBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    parse_content_block,
)
from fasthooks.transcript.core import Transcript
from fasthooks.transcript.entries import (
    AssistantMessage,
    CompactBoundary,
    Entry,
    FileHistorySnapshot,
    StopHookSummary,
    SystemEntry,
    TranscriptEntry,
    UserMessage,
    parse_entry,
)

__all__ = [
    # Core
    "Transcript",
    # Blocks
    "ContentBlock",
    "TextBlock",
    "ThinkingBlock",
    "ToolResultBlock",
    "ToolUseBlock",
    "parse_content_block",
    # Entries
    "Entry",
    "UserMessage",
    "AssistantMessage",
    "SystemEntry",
    "CompactBoundary",
    "StopHookSummary",
    "FileHistorySnapshot",
    "TranscriptEntry",
    "parse_entry",
]
