"""Rich transcript modeling for context engineering."""
from fasthooks.transcript.blocks import (
    ContentBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UnknownBlock,
    parse_content_block,
)
from fasthooks.transcript.core import Transcript, TranscriptStats
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
from fasthooks.transcript.turn import Turn

__all__ = [
    # Core
    "Transcript",
    "TranscriptStats",
    "Turn",
    # Blocks
    "ContentBlock",
    "TextBlock",
    "ThinkingBlock",
    "ToolResultBlock",
    "ToolUseBlock",
    "UnknownBlock",
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
