"""Tool-specific event models with typed properties."""
from __future__ import annotations

from typing import Any, cast

from pydantic import ConfigDict

from fasthooks.events.base import BaseEvent


class ToolEvent(BaseEvent):
    """Base class for tool-related events (PreToolUse, PostToolUse)."""

    model_config = ConfigDict(extra="ignore")

    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str
    tool_response: dict[str, Any] | None = None  # Only for PostToolUse events


class Bash(ToolEvent):
    """Bash tool event with typed accessors."""

    @property
    def command(self) -> str:
        """The bash command to execute."""
        return cast(str, self.tool_input.get("command", ""))

    @property
    def description(self) -> str | None:
        """Optional description of the command."""
        return self.tool_input.get("description")

    @property
    def timeout(self) -> int | None:
        """Optional timeout in milliseconds."""
        return self.tool_input.get("timeout")

    @property
    def run_in_background(self) -> bool | None:
        """Whether to run in background."""
        return self.tool_input.get("run_in_background")


class Write(ToolEvent):
    """Write tool event."""

    @property
    def file_path(self) -> str:
        """Path to file being written."""
        return cast(str, self.tool_input.get("file_path", ""))

    @property
    def content(self) -> str:
        """Content to write."""
        return cast(str, self.tool_input.get("content", ""))


class Read(ToolEvent):
    """Read tool event."""

    @property
    def file_path(self) -> str:
        """Path to file being read."""
        return cast(str, self.tool_input.get("file_path", ""))

    @property
    def offset(self) -> int | None:
        """Optional line offset."""
        return self.tool_input.get("offset")

    @property
    def limit(self) -> int | None:
        """Optional line limit."""
        return self.tool_input.get("limit")


class Edit(ToolEvent):
    """Edit tool event."""

    @property
    def file_path(self) -> str:
        """Path to file being edited."""
        return cast(str, self.tool_input.get("file_path", ""))

    @property
    def old_string(self) -> str:
        """String to replace."""
        return cast(str, self.tool_input.get("old_string", ""))

    @property
    def new_string(self) -> str:
        """Replacement string."""
        return cast(str, self.tool_input.get("new_string", ""))

    @property
    def replace_all(self) -> bool | None:
        """Whether to replace all occurrences."""
        return self.tool_input.get("replace_all")


class Grep(ToolEvent):
    """Grep tool event."""

    @property
    def pattern(self) -> str:
        """Search pattern."""
        return cast(str, self.tool_input.get("pattern", ""))

    @property
    def path(self) -> str | None:
        """Path to search in."""
        return self.tool_input.get("path")

    @property
    def glob(self) -> str | None:
        """Glob pattern for files."""
        return self.tool_input.get("glob")

    @property
    def output_mode(self) -> str | None:
        """Output mode."""
        return self.tool_input.get("output_mode")


class Glob(ToolEvent):
    """Glob tool event."""

    @property
    def pattern(self) -> str:
        """Glob pattern."""
        return cast(str, self.tool_input.get("pattern", ""))

    @property
    def path(self) -> str | None:
        """Base path."""
        return self.tool_input.get("path")


class Task(ToolEvent):
    """Task (subagent) tool event."""

    @property
    def description(self) -> str:
        """Task description."""
        return cast(str, self.tool_input.get("description", ""))

    @property
    def prompt(self) -> str:
        """Task prompt."""
        return cast(str, self.tool_input.get("prompt", ""))

    @property
    def subagent_type(self) -> str | None:
        """Type of subagent."""
        return self.tool_input.get("subagent_type")

    @property
    def model(self) -> str | None:
        """Model to use."""
        return self.tool_input.get("model")

    @property
    def run_in_background(self) -> bool | None:
        """Whether to run in background."""
        return self.tool_input.get("run_in_background")

    @property
    def agent_id(self) -> str | None:
        """Agent ID from PostToolUse response."""
        if self.tool_response:
            return self.tool_response.get("agentId")
        return None

    @property
    def response_text(self) -> str:
        """Extract text content from Task response (PostToolUse only)."""
        if not self.tool_response:
            return ""
        content = self.tool_response.get("content", [])
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(cast(str, block.get("text", "")))
        return "\n".join(texts)


class WebSearch(ToolEvent):
    """WebSearch tool event."""

    @property
    def query(self) -> str:
        """Search query."""
        return cast(str, self.tool_input.get("query", ""))


class WebFetch(ToolEvent):
    """WebFetch tool event."""

    @property
    def url(self) -> str:
        """URL to fetch."""
        return cast(str, self.tool_input.get("url", ""))

    @property
    def prompt(self) -> str:
        """Prompt for processing."""
        return cast(str, self.tool_input.get("prompt", ""))
