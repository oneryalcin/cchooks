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

# All Claude Code events that support http hooks (per the hooks reference;
# SessionStart/Setup and display-only events are excluded — they don't support
# http). Used by `install --http` so one running server receives every event it
# might handle and recipes added later work without reinstalling. Tool-name
# events get a "*" matcher; the rest fire without one.
_HTTP_TOOL_EVENTS = [
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "PermissionDenied",
]
_HTTP_PLAIN_EVENTS = [
    "PostToolBatch",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "TaskCreated",
    "TaskCompleted",
    "TeammateIdle",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "Notification",
    "PreCompact",
    "PostCompact",
    "SessionEnd",
    "ConfigChange",
    "CwdChanged",
    "InstructionsLoaded",
    "Elicitation",
    "ElicitationResult",
    "WorktreeCreate",
    "WorktreeRemove",
]


def http_all_hooks() -> list[str]:
    """Hook identifiers covering every http-compatible Claude Code event.

    Returned in the same ``"Event[:matcher]"`` form ``generate_settings``
    consumes: tool events as ``"<Event>:*"``, the rest bare.
    """
    return [f"{e}:*" for e in _HTTP_TOOL_EVENTS] + list(_HTTP_PLAIN_EVENTS)


def generate_settings(
    hooks: list[str],
    command: str,
    *,
    hook_type: str = "command",
    auth_env: str | None = None,
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
        auth_env: For http hooks, the name of an env var holding the shared
            secret. When set, each entry gets an ``Authorization: Bearer``
            header referencing it (via Claude Code's ``${VAR}`` interpolation)
            plus ``allowedEnvVars`` — so the secret stays in the environment,
            never in settings.json.

    Returns:
        Dict ready to merge into settings.json

    Example:
        >>> generate_settings(["PreToolUse:Bash", "Stop"], "cmd")
        {"hooks": {"PreToolUse": [...], "Stop": [...]}}
    """
    settings: dict[str, Any] = {"hooks": {}}

    def _entry() -> dict[str, Any]:
        if hook_type == "http":
            entry: dict[str, Any] = {"type": "http", "url": command}
            if auth_env:
                entry["headers"] = {"Authorization": f"Bearer ${{{auth_env}}}"}
                entry["allowedEnvVars"] = [auth_env]
            return entry
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
