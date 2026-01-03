"""Turn abstraction for grouping assistant messages by requestId."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from fasthooks.transcript.blocks import ToolUseBlock


class Turn(BaseModel):
    """Groups assistant entries by requestId into a logical turn.

    A single user prompt can result in multiple assistant entries
    (thinking, tool_use, text response) that share the same requestId.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    request_id: str
    entries: list[Any] = Field(default_factory=list)  # AssistantMessage at runtime

    @property
    def thinking(self) -> str:
        """Combined thinking from all entries."""
        return "\n".join(e.thinking for e in self.entries if e.thinking)

    @property
    def text(self) -> str:
        """Combined text response."""
        return "\n".join(e.text for e in self.entries if e.text)

    @property
    def tool_uses(self) -> list[ToolUseBlock]:
        """All tool uses in this turn."""
        return [tu for e in self.entries for tu in e.tool_uses]

    @property
    def is_complete(self) -> bool:
        """Whether turn finished (has end_turn stop_reason)."""
        return any(e.stop_reason == "end_turn" for e in self.entries)

    @property
    def has_tool_use(self) -> bool:
        """Whether this turn contains any tool use."""
        return any(e.has_tool_use for e in self.entries)

    @property
    def has_error(self) -> bool:
        """Whether any tool result was an error."""
        for tu in self.tool_uses:
            if tu.result and tu.result.is_error:
                return True
        return False

    @property
    def model(self) -> str:
        """Model used for this turn (from first entry)."""
        return self.entries[0].model if self.entries else ""

    def __len__(self) -> int:
        return len(self.entries)

    def __repr__(self) -> str:
        return f"Turn({self.request_id}, entries={len(self.entries)}, tools={len(self.tool_uses)})"
