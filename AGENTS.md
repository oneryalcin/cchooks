# Repository Guidelines

## Project Structure & Module Organization

- `src/fasthooks/`: library code (src-layout package).
  - `app.py`: `HookApp` entry point and dispatch.
  - `events/`: Pydantic models for hook events (tool + lifecycle).
  - `responses.py`: `allow()/deny()/block()` helpers and serialization.
  - `depends/`: injectable deps like `Transcript` and `State`.
  - `testing/`: `MockEvent` and `TestClient` helpers.
  - `tasks/`: background task utilities.
- `tests/`: pytest suite (files named `test_*.py`).
- `docs/`: MkDocs content; `site/` is generated output.
- `dist/`/`build/`: build artifacts (generated).

## Build, Test, and Development Commands

This repo uses `uv` and a Makefile wrapper:

- `make install`: sync dev deps (`uv sync`).
- `make test`: run pytest with coverage (see `pyproject.toml` addopts).
- `make lint`: `ruff check` on `src/fasthooks` and `tests`.
- `make format`: `ruff format` + autofixable lint fixes.
- `make typecheck`: `mypy` (strict).
- `make check`: run `lint`, `typecheck`, and `test`.
- `make docs-serve`: serve docs locally at `http://localhost:8000`.

Example: `uv run pytest tests/test_app.py::test_dispatch -v`

## Coding Style & Naming Conventions

- Python `>=3.11` (type checking targets Python `3.12`).
- Indentation: 4 spaces; max line length: 100 (Ruff).
- Naming: `snake_case` for functions/vars, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Prefer explicit types (mypy strict) and small, composable modules under `src/fasthooks/`.

## Testing Guidelines

- Framework: `pytest` + `pytest-asyncio` (`asyncio_mode=auto`).
- Keep tests focused and name them descriptively (`test_<behavior>.py`, `test_<thing>_<does>.py`).
- New features and bug fixes should include a regression test in `tests/` and keep coverage warnings actionable.

## Commit & Pull Request Guidelines

- Commit messages are short, imperative, and capitalized (examples in history: `Add …`, `Update …`, `Refactor: …`, `Bump version to X.Y.Z`).
- PRs should explain the behavior change, include tests (or rationale), and update `docs/` when the public API/CLI changes.
- For documentation-heavy PRs, include a screenshot or note from `make docs-serve` when it improves review.

## Security & Configuration Tips

- Hooks are invoked via stdin/stdout JSON; avoid side effects at import time and keep file I/O explicit.
- Don’t commit generated artifacts (`site/`, `dist/`) or local caches (`.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.venv/`).
- Release workflow: tag `vX.Y.Z` to trigger GitHub Release; PyPI publish steps live in `PUBLISH.md`.
