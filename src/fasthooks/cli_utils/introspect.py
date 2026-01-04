"""Introspection utilities for generating settings.json configuration."""

from __future__ import annotations

from typing import Any


def generate_settings(hooks: list[str], command: str) -> dict[str, Any]:
    """
    Generate settings.json hooks configuration.

    Takes a list of hook identifiers and generates the Claude Code
    settings.json structure.

    Args:
        hooks: List of hook identifiers like ["PreToolUse:Bash", "Stop"]
        command: Shell command to execute (e.g., 'uv run --with fasthooks "..."')

    Returns:
        Dict ready to merge into settings.json

    Example:
        >>> generate_settings(["PreToolUse:Bash", "Stop"], "cmd")
        {"hooks": {"PreToolUse": [...], "Stop": [...]}}
    """
    settings: dict[str, Any] = {"hooks": {}}

    # Group hooks by event type
    events: dict[str, set[str]] = {}
    for hook in hooks:
        if ":" in hook:
            event, matcher = hook.split(":", 1)
        else:
            event, matcher = hook, ""

        if event not in events:
            events[event] = set()
        if matcher:
            events[event].add(matcher)

    # Generate configuration for each event type
    for event, matchers in events.items():
        hook_entry = {"type": "command", "command": command}

        if matchers:
            # Tool event with matchers
            if "*" in matchers:
                # Catch-all: use "*" as matcher
                matcher_str = "*"
            else:
                # Combine with regex OR, sorted for deterministic output
                matcher_str = "|".join(sorted(matchers))

            settings["hooks"][event] = [{"matcher": matcher_str, "hooks": [hook_entry]}]
        else:
            # Lifecycle event (no matcher)
            settings["hooks"][event] = [{"hooks": [hook_entry]}]

    return settings
