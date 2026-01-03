# Dependencies

Injectable dependencies for hook handlers.

## Transcript

Access to the conversation history and statistics. See [Transcript API](transcript.md) for full documentation.

::: fasthooks.depends.transcript.Transcript
    options:
      members:
        - __init__
        - stats
        - entries
        - user_messages
        - assistant_messages
        - tool_uses
        - tool_results
        - query

::: fasthooks.depends.transcript.TranscriptStats
    options:
      members:
        - input_tokens
        - output_tokens
        - cache_read_tokens
        - cache_creation_tokens
        - tool_calls
        - error_count
        - message_count
        - turn_count
        - compact_count
        - duration_seconds
        - slug

## State

Persistent session-scoped storage.

::: fasthooks.depends.state.State
    options:
      members:
        - for_session
        - save
        - __getitem__
        - __setitem__
        - get
