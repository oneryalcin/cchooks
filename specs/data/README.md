# Sample Transcript Data

Real Claude Code transcript samples for reference and testing.

## Files

### sample_main_transcript.jsonl

Full session transcript demonstrating:
- User text messages
- Assistant responses with thinking blocks
- Tool use (Bash, Write, Read)
- Tool results (success and error)
- Multiple tools in one turn
- File history snapshots
- System entries (stop_hook_summary)
- Compaction (compact_boundary + summary)
- Meta messages (command outputs)

**Session ID:** `c45af7b1-cb7c-4e51-93db-8cbb250a877a`

### sample_agent_sidechain.jsonl

Subagent transcript (Explore agent) demonstrating:
- `isSidechain: true` flag
- `agentId` field (e.g., "af1ff21")
- Warmup message pattern
- Agent-specific system prompts

**Agent ID:** `af1ff21`

### sample_hook_logs.jsonl

Hook execution logs (separate from transcript) demonstrating:
- SessionStart (startup and compact resume)
- UserPromptSubmit
- PreToolUse / PostToolUse
- Stop / SubagentStop
- PreCompact
- Notification

**Note:** Hook logs use different format than transcripts:
- `ts` instead of `timestamp`
- `event` instead of `type`
- Flat structure (no nested `message`)

## Usage

Use these files to:
1. Validate transcript parsing implementation
2. Understand edge cases (compaction, errors, multi-tool)
3. Test relationship indexing (tool_use_id → tool_result)
4. Verify entry field handling

## Source

Captured from a real Claude Code session on 2026-01-02 with:
- Basic tool operations (ls, file create/read)
- Intentional error (cat nonexistent.txt)
- Multi-tool turn (Write + Read + Bash)
- Manual compaction (/compact)
