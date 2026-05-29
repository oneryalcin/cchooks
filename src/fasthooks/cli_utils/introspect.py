"""Introspection utilities for generating settings.json configuration."""

from __future__ import annotations

from typing import Any

# Events that match on tool name. A matcher-less registration of one of these
# (e.g. @app.on("PreToolUse")) means "every tool", so it must install as a "*"
# matcher — otherwise a sibling @app.pre_tool("Bash") would collapse coverage
# to just Bash and Claude Code would never deliver the other tools' events.
_TOOL_EVENTS = frozenset(
    {
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "PermissionRequest",
        "PermissionDenied",
    }
)


def generate_settings(
    hooks: list[str], command: str, *, hook_type: str = "command"
) -> dict[str, Any]:
    """
    Generate settings.json hooks configuration.

    Takes a list of hook identifiers and generates the Claude Code
    settings.json structure.

    Args:
        hooks: List of hook identifiers like ["PreToolUse:Bash", "Stop"]
        command: The hook's identity string. For ``hook_type="command"`` this
            is the shell command (e.g. 'uv run --with fasthooks "..."'); for
            ``hook_type="http"`` it is the endpoint URL.
        hook_type: "command" (default) or "http".

    Returns:
        Dict ready to merge into settings.json

    Example:
        >>> generate_settings(["PreToolUse:Bash", "Stop"], "cmd")
        {"hooks": {"PreToolUse": [...], "Stop": [...]}}
    """
    settings: dict[str, Any] = {"hooks": {}}

    def _entry() -> dict[str, str]:
        if hook_type == "http":
            return {"type": "http", "url": command}
        return {"type": "command", "command": command}

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
        elif event in _TOOL_EVENTS:
            # Bare tool-event registration (e.g. @app.on("PreToolUse")) = all tools
            events[event].add("*")

    # Generate configuration for each event type
    for event, matchers in events.items():
        hook_entry = _entry()

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
