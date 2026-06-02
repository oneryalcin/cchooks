"""Transcript schema oracle (#32).

Validates fasthooks' transcript serialization against the *canonical* Claude Code
session JSON Schema (vendored from agent-schemas; see tests/data/schemas/README).

The guard is round-trip fidelity: parsing a real session transcript and calling
`to_dict()` must produce JSONL that still validates against the schema for that
record's CLI version. Without it, `Transcript.save()` silently drifts from the
wire format — e.g. emitting fasthooks-internal defaults (isMeta/isSynthetic/slug)
the real records never had, or dropping message fields fasthooks doesn't model
(stop_sequence). Both regressions are invisible to fasthooks' own round-trip
tests, which only check the fields fasthooks knows about.

Samples span CLI versions (2.0.x and 2.1.x, incl. a subagent transcript), each
validated against the matching vendored schema.
"""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
from jsonschema import Draft202012Validator  # noqa: E402
from jsonschema.exceptions import best_match  # noqa: E402

from fasthooks.transcript import Transcript  # noqa: E402

_DATA = Path(__file__).parent.parent / "specs" / "data"
_SCHEMAS = Path(__file__).parent / "data" / "schemas"

# Session transcripts only. sample_hook_logs.jsonl is a hook-event log (stdin
# records: event/tool_name/tool_input), a different artifact the session schema
# does not — and should not — model.
_SESSION_SAMPLES = [
    "sample_main_transcript",   # CLI 2.0.76
    "sample_agent_sidechain",   # CLI 2.0.76
    "sample_subagent_v2_1",     # CLI 2.1.x subagent (sanitized) — current format
]


def _schema_path_for(version: str) -> Path:
    """Map a CLI version to its vendored canonical schema (fail loudly if none).

    Mirrors agent-schemas' own version buckets. Add a vendored schema + branch
    here when a sample moves to a CLI version not yet covered.
    """
    major, minor, _ = (int(p) for p in version.split(".")[:3])
    if (major, minor) == (2, 0):
        return _SCHEMAS / "claude-code-session-v2.0.76.schema.json"
    if (major, minor) == (2, 1):  # the 2.1.144 schema covers CLI 2.1.97+
        return _SCHEMAS / "claude-code-session-v2.1.144.schema.json"
    raise AssertionError(f"no vendored schema for CLI {version} — vendor one")


@cache
def _validator_for(version: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads(_schema_path_for(version).read_text()))


def _raw_lines(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (_DATA / f"{name}.jsonl").read_text().splitlines()
        if line.strip()
    ]


def _sample_version(name: str) -> str:
    versions = {r["version"] for r in _raw_lines(name) if r.get("version")}
    assert len(versions) == 1, f"{name} has no single CLI version: {versions}"
    return versions.pop()


@pytest.mark.parametrize("sample", _SESSION_SAMPLES)
def test_raw_samples_conform_to_canonical_schema(sample):
    """Sanity: our fixtures are real, schema-valid Claude Code JSONL.

    If this fails, the sample was hand-edited (or over-sanitized) into a shape
    Claude Code never emits — fix the fixture, not the schema.
    """
    validator = _validator_for(_sample_version(sample))
    for i, line in enumerate(_raw_lines(sample)):
        err = best_match(validator.iter_errors(line))
        assert err is None, f"{sample} raw line {i} invalid: {err.message}"


@pytest.mark.parametrize("sample", _SESSION_SAMPLES)
def test_to_dict_roundtrip_stays_canonical(sample):
    """fasthooks parse -> to_dict must re-validate against the canonical schema.

    This is the #32 guard: save() must not drift from the wire format. Covers a
    2.1.x subagent transcript so the current format (incl. tool_use/tool_result
    chains across a sidechain) is exercised, not only the legacy 2.0.x shape.
    """
    validator = _validator_for(_sample_version(sample))
    t = Transcript(_DATA / f"{sample}.jsonl")
    t.load()
    entries = list(t.entries) + list(t.archived)
    assert entries, f"{sample} parsed to no entries"

    for entry in entries:
        out = entry.to_dict()
        err = best_match(validator.iter_errors(out))
        assert err is None, (
            f"{sample} {type(entry).__name__} (uuid={out.get('uuid')}) "
            f"to_dict() not schema-valid at "
            f"{'/'.join(map(str, err.absolute_path)) or '(root)'}: {err.message}"
        )
