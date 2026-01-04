"""fasthooks CLI - Manage Claude Code hooks with ease."""

from __future__ import annotations


def main() -> None:
    """CLI entry point."""
    from fasthooks.cli.app import app

    app()


__all__ = ["main"]
