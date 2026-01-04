"""CleanStateStrategy - enforce clean state before stopping.

This is a simple strategy (1 hook) included for educational value.
The raw fasthooks equivalent is ~15 lines:

    @app.on_stop()
    def enforce_clean(event):
        result = subprocess.run(["git", "status", "--porcelain"],
                                capture_output=True, text=True, cwd=event.cwd)
        if result.stdout.strip():
            return block("Uncommitted changes exist")

Strategy adds: observability, YAML config, namespace isolation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from fasthooks import Blueprint, allow, block

from .base import Strategy


class CleanStateStrategy(Strategy):
    """Enforce clean repository state before stopping.

    Blocks stop if required files are missing or uncommitted changes exist.

    Example:
        strategy = CleanStateStrategy(
            require_files=["README.md", "pyproject.toml"],
            check_uncommitted=True,
        )
        app.include(strategy.get_blueprint())

    Checks:
        - Required files exist
        - No uncommitted git changes (if enabled)
    """

    class Meta:
        name = "clean-state"
        version = "1.0.0"
        description = "Enforce clean state before stopping"
        hooks = ["on_stop"]
        fail_mode = "closed"  # Block if strategy errors - safety first

    def __init__(
        self,
        *,
        require_files: list[str] | None = None,
        check_uncommitted: bool = True,
        exclude_paths: list[str] | None = None,
    ):
        """Initialize CleanStateStrategy.

        Args:
            require_files: Files that must exist before stopping.
            check_uncommitted: Whether to block on uncommitted git changes.
            exclude_paths: Paths to ignore when checking uncommitted changes.
        """
        # Set attributes before super().__init__() which calls _validate_config()
        self.require_files = require_files or []
        self.check_uncommitted = check_uncommitted
        self.exclude_paths = exclude_paths or []
        super().__init__()

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("clean-state")

        @bp.on_stop()
        def enforce_clean(event: Any) -> Any:
            issues = []
            project_dir = Path(event.cwd)

            # Check required files
            for f in self.require_files:
                if not (project_dir / f).exists():
                    issues.append(f"Missing required file: {f}")

            # Check uncommitted changes
            if self.check_uncommitted:
                uncommitted = self._get_uncommitted(project_dir)
                if uncommitted:
                    # Filter excluded paths
                    filtered = [
                        f for f in uncommitted
                        if not any(f.startswith(ex) for ex in self.exclude_paths)
                    ]
                    if filtered:
                        files_str = ", ".join(filtered[:5])
                        if len(filtered) > 5:
                            files_str += f" (+{len(filtered) - 5} more)"
                        issues.append(f"Uncommitted changes: {files_str}")

            if issues:
                return block(
                    "Cannot stop - clean state required:\n" +
                    "\n".join(f"- {i}" for i in issues)
                )

            return allow()

        return bp

    def _get_uncommitted(self, project_dir: Path) -> list[str]:
        """Get list of uncommitted files."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=project_dir,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Split on newlines, preserving leading chars for status parsing
                # Git status format: XY filename (2 chars status + space + filename)
                lines = result.stdout.rstrip("\n").split("\n")
                return [line[3:].strip() for line in lines if len(line) > 3]
        except Exception:
            pass
        return []
