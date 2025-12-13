"""Claude Agent SDK integration for fasthooks.

This module provides utilities for using Claude as a sub-agent in
background tasks.

Requires the claude-agent-sdk package:
    pip install fasthooks[claude]

Usage:
    from fasthooks.contrib.claude import ClaudeAgent, agent_task

    # Direct usage
    agent = ClaudeAgent(model="haiku")
    response = await agent.query("What is 2+2?")

    # As a background task
    @agent_task(model="sonnet", system_prompt="You are a code reviewer.")
    async def review_code(agent: ClaudeAgent, code: str) -> str:
        return await agent.query(f"Review this code:\\n{code}")
"""

from fasthooks.contrib.claude.agent import ClaudeAgent, Model, agent_task

__all__ = ["ClaudeAgent", "Model", "agent_task"]
