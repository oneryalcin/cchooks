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
from fasthooks.transcript.query import TranscriptQuery
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
from fasthooks.transcript.factories import inject_tool_result
from fasthooks.transcript.turn import Turn

__all__ = [
    # Core
    "Transcript",
    "TranscriptQuery",
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
    # Factories
    "inject_tool_result",
]
