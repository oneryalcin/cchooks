"""Tests for contrib.claude module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# Mock claude_agent_sdk types
@dataclass
class MockTextBlock:
    """Mock TextBlock."""

    text: str


@dataclass
class MockAssistantMessage:
    """Mock AssistantMessage."""

    content: list[Any]


@dataclass
class MockResultMessage:
    """Mock ResultMessage."""

    subtype: str
    total_cost_usd: float | None = None


@dataclass
class MockClaudeAgentOptions:
    """Mock ClaudeAgentOptions."""

    model: str | None = None
    system_prompt: str | None = None
    allowed_tools: list[str] | None = None
    max_turns: int | None = None
    max_budget_usd: float | None = None
    cwd: str | None = None


async def mock_query_generator(*args: Any, **kwargs: Any):
    """Mock query generator that yields test messages."""
    yield MockAssistantMessage(content=[MockTextBlock(text="Hello ")])
    yield MockAssistantMessage(content=[MockTextBlock(text="World!")])
    yield MockResultMessage(subtype="success", total_cost_usd=0.001)


@pytest.fixture
def mock_sdk():
    """Mock the claude_agent_sdk module."""
    mock_module = MagicMock()
    mock_module.ClaudeAgentOptions = MockClaudeAgentOptions
    mock_module.AssistantMessage = MockAssistantMessage
    mock_module.TextBlock = MockTextBlock
    mock_module.query = mock_query_generator

    with patch.dict("sys.modules", {"claude_agent_sdk": mock_module}):
        yield mock_module


class TestClaudeAgent:
    """Tests for ClaudeAgent class."""

    def test_init_without_sdk_raises(self):
        """Test that ClaudeAgent raises ImportError without SDK."""
        # Remove any cached imports
        import sys

        # Temporarily remove claude_agent_sdk from modules
        original = sys.modules.get("claude_agent_sdk")
        sys.modules["claude_agent_sdk"] = None  # type: ignore

        try:
            from fasthooks.contrib.claude.agent import ClaudeAgent

            with pytest.raises(ImportError, match="claude-agent-sdk is required"):
                ClaudeAgent()
        finally:
            if original is not None:
                sys.modules["claude_agent_sdk"] = original
            else:
                sys.modules.pop("claude_agent_sdk", None)

    def test_init_with_defaults(self, mock_sdk):
        """Test ClaudeAgent initialization with defaults."""
        from fasthooks.contrib.claude.agent import ClaudeAgent

        agent = ClaudeAgent()
        assert agent.model is None
        assert agent.system_prompt is None
        assert agent.allowed_tools == []
        assert agent.max_turns is None
        assert agent.max_budget_usd is None
        assert agent.cwd is None

    def test_init_with_options(self, mock_sdk):
        """Test ClaudeAgent initialization with options."""
        from fasthooks.contrib.claude.agent import ClaudeAgent

        agent = ClaudeAgent(
            model="haiku",
            system_prompt="You are helpful.",
            allowed_tools=["Read", "Grep"],
            max_turns=5,
            max_budget_usd=0.10,
            cwd="/tmp",
        )
        assert agent.model == "haiku"
        assert agent.system_prompt == "You are helpful."
        assert agent.allowed_tools == ["Read", "Grep"]
        assert agent.max_turns == 5
        assert agent.max_budget_usd == 0.10
        assert agent.cwd == "/tmp"

    def test_build_options_with_defaults(self, mock_sdk):
        """Test _build_options with agent defaults."""
        from fasthooks.contrib.claude.agent import ClaudeAgent

        agent = ClaudeAgent(model="sonnet", system_prompt="Test prompt")
        options = agent._build_options()

        assert options.model == "sonnet"
        assert options.system_prompt == "Test prompt"

    def test_build_options_with_overrides(self, mock_sdk):
        """Test _build_options with overrides."""
        from fasthooks.contrib.claude.agent import ClaudeAgent

        agent = ClaudeAgent(model="haiku", system_prompt="Default prompt")
        options = agent._build_options(
            model="sonnet", system_prompt="Override prompt", max_turns=10
        )

        assert options.model == "sonnet"
        assert options.system_prompt == "Override prompt"
        assert options.max_turns == 10

    @pytest.mark.asyncio
    async def test_query_returns_text(self, mock_sdk):
        """Test that query returns concatenated text."""
        from fasthooks.contrib.claude.agent import ClaudeAgent

        agent = ClaudeAgent()
        result = await agent.query("What is 2+2?")

        assert result == "Hello World!"

    @pytest.mark.asyncio
    async def test_query_with_overrides(self, mock_sdk):
        """Test query with parameter overrides."""
        from fasthooks.contrib.claude.agent import ClaudeAgent

        agent = ClaudeAgent(model="haiku")

        # The query should work with overrides
        result = await agent.query(
            "Test prompt",
            system_prompt="Override system",
            allowed_tools=["Bash"],
            max_turns=3,
            max_budget_usd=0.05,
            cwd="/tmp/test",
        )

        assert result == "Hello World!"

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_sdk):
        """Test async context manager."""
        from fasthooks.contrib.claude.agent import ClaudeAgent

        async with ClaudeAgent(model="haiku") as agent:
            result = await agent.query("Test")
            assert result == "Hello World!"


class TestAgentTask:
    """Tests for agent_task decorator."""

    def test_agent_task_creates_task(self, mock_sdk):
        """Test that agent_task creates a Task object."""
        from fasthooks.contrib.claude.agent import agent_task
        from fasthooks.tasks.base import Task

        @agent_task(model="haiku", system_prompt="Test")
        async def my_task(agent, x: int) -> str:
            return f"Result: {x}"

        assert isinstance(my_task, Task)
        assert my_task.ttl == 300  # default
        assert my_task.priority == 0  # default

    def test_agent_task_custom_ttl_priority(self, mock_sdk):
        """Test agent_task with custom TTL and priority."""
        from fasthooks.contrib.claude.agent import agent_task
        from fasthooks.tasks.base import Task

        @agent_task(model="sonnet", ttl=600, priority=5)
        async def high_priority_task(agent) -> str:
            return "done"

        assert isinstance(high_priority_task, Task)
        assert high_priority_task.ttl == 600
        assert high_priority_task.priority == 5

    @pytest.mark.asyncio
    async def test_agent_task_injects_agent(self, mock_sdk):
        """Test that agent_task injects ClaudeAgent as first arg."""
        from fasthooks.contrib.claude.agent import ClaudeAgent, agent_task

        received_agent = None

        @agent_task(model="haiku", system_prompt="Reviewer")
        async def review_task(agent: ClaudeAgent, code: str) -> str:
            nonlocal received_agent
            received_agent = agent
            # In real use, would call agent.query()
            return f"Reviewed: {code}"

        # Call the task's underlying function
        result = await review_task.func("def foo(): pass")

        assert received_agent is not None
        assert isinstance(received_agent, ClaudeAgent)
        assert received_agent.model == "haiku"
        assert received_agent.system_prompt == "Reviewer"
        assert result == "Reviewed: def foo(): pass"

    @pytest.mark.asyncio
    async def test_agent_task_with_kwargs(self, mock_sdk):
        """Test agent_task with keyword arguments."""
        from fasthooks.contrib.claude.agent import agent_task

        @agent_task(model="sonnet", allowed_tools=["Read", "Grep"])
        async def search_task(agent, query: str, *, case_sensitive: bool = False) -> str:
            return f"Search: {query} (case={case_sensitive})"

        result = await search_task.func("TODO", case_sensitive=True)
        assert result == "Search: TODO (case=True)"

    @pytest.mark.asyncio
    async def test_agent_task_uses_agent_query(self, mock_sdk):
        """Test that agent_task can use agent.query()."""
        from fasthooks.contrib.claude.agent import ClaudeAgent, agent_task

        @agent_task(model="haiku")
        async def query_task(agent: ClaudeAgent, prompt: str) -> str:
            return await agent.query(prompt)

        result = await query_task.func("What is 2+2?")
        assert result == "Hello World!"


class TestImports:
    """Test module imports."""

    def test_contrib_claude_exports(self, mock_sdk):
        """Test that contrib.claude exports expected items."""
        from fasthooks.contrib.claude import ClaudeAgent, Model, agent_task

        assert ClaudeAgent is not None
        assert agent_task is not None
        assert Model is not None  # Type alias


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_query_empty_response(self, mock_sdk):
        """Test query with empty response."""
        from fasthooks.contrib.claude.agent import ClaudeAgent

        # Create a mock that yields no text blocks
        async def empty_query_generator(*args, **kwargs):
            yield MockAssistantMessage(content=[])
            yield MockResultMessage(subtype="success")

        mock_sdk.query = empty_query_generator

        agent = ClaudeAgent()
        result = await agent.query("Test")
        assert result == ""

    @pytest.mark.asyncio
    async def test_query_multiple_text_blocks(self, mock_sdk):
        """Test query with multiple text blocks in one message."""
        from fasthooks.contrib.claude.agent import ClaudeAgent

        async def multi_block_query_generator(*args, **kwargs):
            yield MockAssistantMessage(
                content=[
                    MockTextBlock(text="Part 1. "),
                    MockTextBlock(text="Part 2. "),
                    MockTextBlock(text="Part 3."),
                ]
            )
            yield MockResultMessage(subtype="success")

        mock_sdk.query = multi_block_query_generator

        agent = ClaudeAgent()
        result = await agent.query("Test")
        assert result == "Part 1. Part 2. Part 3."

    def test_allowed_tools_not_shared(self, mock_sdk):
        """Test that allowed_tools list is not shared between instances."""
        from fasthooks.contrib.claude.agent import ClaudeAgent

        agent1 = ClaudeAgent(allowed_tools=["Read"])
        agent2 = ClaudeAgent(allowed_tools=["Write"])

        assert agent1.allowed_tools == ["Read"]
        assert agent2.allowed_tools == ["Write"]

        # Modifying one should not affect the other
        agent1.allowed_tools.append("Grep")
        assert "Grep" not in agent2.allowed_tools

    def test_build_options_copies_allowed_tools(self, mock_sdk):
        """Test that _build_options copies allowed_tools."""
        from fasthooks.contrib.claude.agent import ClaudeAgent

        agent = ClaudeAgent(allowed_tools=["Read", "Write"])
        options = agent._build_options()

        # Modifying options should not affect agent
        options.allowed_tools.append("Grep")
        assert "Grep" not in agent.allowed_tools
