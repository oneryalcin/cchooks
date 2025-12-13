"""Claude Agent SDK integration for background tasks.

This module provides a simplified wrapper around the Claude Agent SDK
for use with fasthooks background tasks.

Requires the claude-agent-sdk package:
    pip install fasthooks[claude]
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from fasthooks.tasks.base import Task

if TYPE_CHECKING:
    from claude_agent_sdk import ClaudeAgentOptions  # type: ignore[import-not-found]

# Model type for type hints
Model = Literal["sonnet", "opus", "haiku"]


def _check_sdk_installed() -> None:
    """Check if claude-agent-sdk is installed."""
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "claude-agent-sdk is required for ClaudeAgent. "
            "Install with: pip install fasthooks[claude]"
        ) from e


@dataclass
class ClaudeAgent:
    """Simplified wrapper for Claude Agent SDK.

    Provides a simple interface for querying Claude in background tasks.

    Usage:
        agent = ClaudeAgent(model="haiku", system_prompt="You are helpful.")

        # Simple query
        response = await agent.query("What is 2+2?")

        # With tools
        agent = ClaudeAgent(allowed_tools=["Read", "Grep"])
        response = await agent.query("Find all TODO comments in src/")

    Context manager usage:
        async with ClaudeAgent(model="sonnet") as agent:
            response = await agent.query("Explain this code")
    """

    model: Model | str | None = None
    system_prompt: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    max_turns: int | None = None
    max_budget_usd: float | None = None
    cwd: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        _check_sdk_installed()

    def _build_options(self, **overrides: Any) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions from agent config and overrides."""
        from claude_agent_sdk import ClaudeAgentOptions

        kwargs: dict[str, Any] = {}

        # Apply agent defaults
        if self.model:
            kwargs["model"] = self.model
        if self.system_prompt:
            kwargs["system_prompt"] = self.system_prompt
        if self.allowed_tools:
            kwargs["allowed_tools"] = self.allowed_tools.copy()
        if self.max_turns:
            kwargs["max_turns"] = self.max_turns
        if self.max_budget_usd:
            kwargs["max_budget_usd"] = self.max_budget_usd
        if self.cwd:
            kwargs["cwd"] = self.cwd

        # Apply overrides
        kwargs.update(overrides)

        return ClaudeAgentOptions(**kwargs)

    async def query(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        allowed_tools: list[str] | None = None,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
        cwd: str | None = None,
    ) -> str:
        """Query Claude and return the text response.

        Args:
            prompt: The prompt to send to Claude
            system_prompt: Override system prompt for this query
            allowed_tools: Override allowed tools for this query
            max_turns: Override max turns for this query
            max_budget_usd: Override budget limit for this query
            cwd: Override working directory for this query

        Returns:
            The text response from Claude

        Raises:
            ImportError: If claude-agent-sdk is not installed
            Exception: If the query fails
        """
        from claude_agent_sdk import (
            AssistantMessage,
            TextBlock,
        )
        from claude_agent_sdk import (
            query as sdk_query,
        )

        # Build options with overrides
        overrides: dict[str, Any] = {}
        if system_prompt is not None:
            overrides["system_prompt"] = system_prompt
        if allowed_tools is not None:
            overrides["allowed_tools"] = allowed_tools
        if max_turns is not None:
            overrides["max_turns"] = max_turns
        if max_budget_usd is not None:
            overrides["max_budget_usd"] = max_budget_usd
        if cwd is not None:
            overrides["cwd"] = cwd

        options = self._build_options(**overrides)

        # Collect text responses
        text_parts: list[str] = []

        async for message in sdk_query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)

        return "".join(text_parts)

    async def __aenter__(self) -> ClaudeAgent:
        """Enter async context."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context."""
        pass  # No cleanup needed for query-based usage


def agent_task(
    model: Model | str = "haiku",
    system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
    *,
    ttl: int = 300,
    priority: int = 0,
) -> Callable[[Callable[..., Any]], Task]:
    """Decorator to create a background task that uses Claude Agent.

    The decorated function receives a `ClaudeAgent` instance as its first
    argument, pre-configured with the specified options.

    Usage:
        @agent_task(model="haiku", system_prompt="You are a code reviewer.")
        async def review_code(agent: ClaudeAgent, code: str) -> str:
            return await agent.query(f"Review this code:\\n{code}")

        # Then use in a handler:
        @app.pre_tool("Write")
        def on_write(event, tasks: BackgroundTasks):
            tasks.add(review_code, event.content, key="review")

    Args:
        model: Claude model to use (haiku, sonnet, opus)
        system_prompt: System prompt for the agent
        allowed_tools: Tools the agent can use
        max_turns: Maximum conversation turns
        max_budget_usd: Budget limit for the query
        ttl: Time-to-live for task result (seconds)
        priority: Task priority (higher = more important)

    Returns:
        Task decorator
    """

    def decorator(func: Callable[..., Any]) -> Task:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            agent = ClaudeAgent(
                model=model,
                system_prompt=system_prompt,
                allowed_tools=allowed_tools or [],
                max_turns=max_turns,
                max_budget_usd=max_budget_usd,
            )
            return await func(agent, *args, **kwargs)

        return Task(func=wrapper, ttl=ttl, priority=priority)

    return decorator
