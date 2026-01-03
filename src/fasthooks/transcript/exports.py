"""Export transcript to various formats."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fasthooks.transcript.core import Transcript
    from fasthooks.transcript.entries import TranscriptEntry


def to_markdown(
    transcript: Transcript,
    *,
    include_thinking: bool = True,
    include_tool_input: bool = True,
    max_content_length: int | None = 500,
) -> str:
    """Export transcript to markdown string.

    Args:
        transcript: Transcript to export
        include_thinking: Include thinking blocks (collapsed)
        include_tool_input: Include tool input JSON
        max_content_length: Truncate long content (None = no limit)

    Returns:
        Markdown formatted string
    """
    from fasthooks.transcript.entries import AssistantMessage, SystemEntry, UserMessage

    lines: list[str] = ["# Transcript", ""]

    for entry in transcript.entries:
        if isinstance(entry, UserMessage):
            lines.extend(_format_user_message(entry, max_content_length))
        elif isinstance(entry, AssistantMessage):
            lines.extend(
                _format_assistant_message(
                    entry, include_thinking, include_tool_input, max_content_length
                )
            )
        elif isinstance(entry, SystemEntry):
            lines.extend(_format_system_entry(entry))

    return "\n".join(lines)


def _truncate(text: str, max_len: int | None) -> str:
    """Truncate text if needed."""
    if max_len is None or len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _format_user_message(
    entry: UserMessage, max_len: int | None
) -> list[str]:
    """Format a user message entry."""
    from fasthooks.transcript.entries import UserMessage

    lines = ["## User", ""]

    if entry.text:
        lines.append(_truncate(entry.text, max_len))
        lines.append("")
    elif entry.is_tool_result:
        for tr in entry.tool_results:
            tool_use = tr.tool_use
            tool_name = tool_use.name if tool_use else "Unknown"
            status = "❌ Error" if tr.is_error else "✓"
            lines.append(f"**Tool Result: {tool_name}** {status}")
            lines.append("")
            lines.append("```")
            lines.append(_truncate(tr.content, max_len))
            lines.append("```")
            lines.append("")

    return lines


def _format_assistant_message(
    entry: AssistantMessage,
    include_thinking: bool,
    include_tool_input: bool,
    max_len: int | None,
) -> list[str]:
    """Format an assistant message entry."""
    lines = ["## Assistant", ""]

    # Thinking (collapsed)
    if include_thinking and entry.thinking:
        lines.append("<details><summary>💭 Thinking</summary>")
        lines.append("")
        lines.append(_truncate(entry.thinking, max_len))
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # Text response
    if entry.text:
        lines.append(_truncate(entry.text, max_len))
        lines.append("")

    # Tool uses
    for tu in entry.tool_uses:
        lines.append(f"### 🔧 Tool: {tu.name}")
        lines.append("")
        if include_tool_input and tu.input:
            lines.append("```json")
            input_str = json.dumps(tu.input, indent=2)
            lines.append(_truncate(input_str, max_len))
            lines.append("```")
            lines.append("")

    return lines


def _format_system_entry(entry: SystemEntry) -> list[str]:
    """Format a system entry."""
    from fasthooks.transcript.entries import CompactBoundary

    lines = []

    if isinstance(entry, CompactBoundary):
        lines.append("---")
        lines.append("*Context compacted*")
        lines.append("---")
        lines.append("")
    elif entry.subtype:
        lines.append(f"*[System: {entry.subtype}]*")
        lines.append("")

    return lines


def to_html(
    transcript: Transcript,
    *,
    include_thinking: bool = True,
    include_tool_input: bool = True,
    max_content_length: int | None = 500,
    title: str = "Transcript",
) -> str:
    """Export transcript to HTML string.

    Wraps markdown in a simple HTML template with basic styling.

    Args:
        transcript: Transcript to export
        include_thinking: Include thinking blocks
        include_tool_input: Include tool input JSON
        max_content_length: Truncate long content
        title: HTML page title

    Returns:
        HTML formatted string
    """
    md_content = to_markdown(
        transcript,
        include_thinking=include_thinking,
        include_tool_input=include_tool_input,
        max_content_length=max_content_length,
    )

    # Simple HTML wrapper with basic CSS
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            line-height: 1.6;
            color: #333;
        }}
        h1 {{ border-bottom: 2px solid #333; padding-bottom: 0.5rem; }}
        h2 {{ color: #0066cc; margin-top: 2rem; }}
        h3 {{ color: #666; }}
        pre {{
            background: #f5f5f5;
            padding: 1rem;
            border-radius: 4px;
            overflow-x: auto;
        }}
        code {{ background: #f5f5f5; padding: 0.2rem 0.4rem; border-radius: 3px; }}
        details {{ margin: 1rem 0; padding: 0.5rem; background: #f9f9f9; border-radius: 4px; }}
        summary {{ cursor: pointer; font-weight: bold; }}
        hr {{ border: none; border-top: 1px solid #ddd; margin: 2rem 0; }}
    </style>
</head>
<body>
<pre style="white-space: pre-wrap; background: none; font-family: inherit;">
{_escape_html(md_content)}
</pre>
</body>
</html>"""
    return html


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def to_json(transcript: Transcript, *, indent: int = 2) -> str:
    """Export transcript to pretty-printed JSON array.

    Args:
        transcript: Transcript to export
        indent: JSON indentation (default 2)

    Returns:
        JSON formatted string (array of entry dicts)
    """
    entries = [entry.to_dict() for entry in transcript.entries]
    return json.dumps(entries, indent=indent, ensure_ascii=False)


def to_jsonl(transcript: Transcript) -> str:
    """Export transcript to JSONL string (one JSON object per line).

    Args:
        transcript: Transcript to export

    Returns:
        JSONL formatted string
    """
    lines = [json.dumps(entry.to_dict(), ensure_ascii=False) for entry in transcript.entries]
    return "\n".join(lines)
