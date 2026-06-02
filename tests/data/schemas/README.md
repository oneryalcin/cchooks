# Vendored Claude Code session schemas

These are **vendored copies** of the canonical Claude Code session JSONL schema,
used as a validation oracle for the transcript module (see
`tests/test_transcript_schema_oracle.py`). They let us assert that fasthooks both
*reads* and *writes* canonical Claude Code JSONL — `to_dict()` round-trip output
must validate against the schema for the record's CLI version.

## Provenance

| File | Source | Version |
|------|--------|---------|
| `claude-code-session-v2.0.76.schema.json` | [oneryalcin/agent-schemas](https://github.com/oneryalcin/agent-schemas) `claude-code/v2.0.76/session.schema.json` @ `dfa9f8f` | CLI 2.0.76 |
| `claude-code-session-v2.1.144.schema.json` | [oneryalcin/agent-schemas](https://github.com/oneryalcin/agent-schemas) `claude-code/v2.1.144/session.schema.json` @ `dfa9f8f` | CLI 2.1.97+ (current) |

The oracle (`_schema_path_for`) maps each sample's `version` field to the matching
schema here. The 2.1.x sample (`sample_subagent_v2_1.jsonl`) is a real subagent
transcript, **sanitized** (all `/Users/*` paths and personal handles replaced) —
its content is public `anthropics/claude-code` issue-tracker data.

## Updating

agent-schemas is the source of truth and is versioned per CLI release. When our
sample transcripts move to a newer CLI version (or to add coverage), copy the
matching `session.schema.json` here, update the table above with the source
commit, and point the oracle test at it. Do not hand-edit the vendored files —
they should match upstream byte-for-byte so drift is detectable.
