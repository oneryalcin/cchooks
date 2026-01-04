"""Long-running agent strategy.

Implements the two-agent pattern for long-running autonomous agents:
- Initializer Agent: First session sets up feature_list.json, init.sh, git
- Coding Agent: Subsequent sessions make incremental progress

Based on Anthropic's "Effective Harnesses for Long-Running Agents" article.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Literal

from fasthooks import Blueprint, allow, block, context
from fasthooks.depends import State

from .base import Strategy

# Initializer prompt template
INITIALIZER_PROMPT = """
## YOUR ROLE - INITIALIZER AGENT (Session 1 of Many)

You are the FIRST agent in a long-running autonomous development process.
Your job is to set up the foundation for all future coding agents.

### FIRST: Read the Project Specification

If there's an `app_spec.txt` or similar specification file, read it carefully.
This contains the complete specification for what you need to build.

### CRITICAL FIRST TASK: Create {feature_list}

Create a file called `{feature_list}` with {min_features}+ detailed end-to-end test cases.
This file is the single source of truth for what needs to be built.

**Format:**
```json
[
  {{
    "category": "functional",
    "description": "Brief description of what this test verifies",
    "steps": [
      "Step 1: Navigate to relevant page",
      "Step 2: Perform action",
      "Step 3: Verify expected result"
    ],
    "passes": false
  }},
  {{
    "category": "style",
    "description": "Brief description of UI/UX requirement",
    "steps": [
      "Step 1: Navigate to page",
      "Step 2: Take screenshot",
      "Step 3: Verify visual requirements"
    ],
    "passes": false
  }}
]
```

**Requirements for {feature_list}:**
- Minimum {min_features} features total with testing steps for each
- Both "functional" and "style" categories
- Order features by priority: foundational features first
- ALL tests start with `"passes": false`
- Cover every feature in the spec exhaustively

**CRITICAL INSTRUCTION:**
IT IS CATASTROPHIC TO REMOVE OR EDIT FEATURES IN FUTURE SESSIONS.
Features can ONLY be marked as passing (change `"passes": false` to `"passes": true`).
Never remove features, never edit descriptions, never modify testing steps.
This ensures no functionality is missed.

### SECOND TASK: Create {init_script}

Create a script called `{init_script}` that future agents can use to quickly
set up and run the development environment. The script should:

1. Install any required dependencies
2. Start any necessary servers or services
3. Print helpful information about how to access the running application

### THIRD TASK: Initialize Git

Create a git repository and make your first commit with:
- {feature_list} (complete with all {min_features}+ features)
- {init_script} (environment setup script)
- README.md (project overview and setup instructions)

Commit message: "Initial setup: {feature_list}, {init_script}, and project structure"

### FOURTH TASK: Create Project Structure

Set up the basic project structure based on what's needed.
This typically includes directories for frontend, backend, and any other components.

### OPTIONAL: Start Implementation

If you have time remaining in this session, you may begin implementing
the highest-priority features from {feature_list}. Remember:
- Work on ONE feature at a time
- Test thoroughly before marking `"passes": true`
- Commit your progress before session ends

### ENDING THIS SESSION

Before your context fills up:
1. Commit all work with descriptive messages
2. Create `{progress_file}` with a summary of what you accomplished
3. Ensure {feature_list} is complete and saved
4. Leave the environment in a clean, working state

The next agent will continue from here with a fresh context window.

**Remember:** You have unlimited time across many sessions. Focus on
quality over speed. Production-ready is the goal.
"""

# Coding prompt template
CODING_PROMPT = """
## YOUR ROLE - CODING AGENT

You are continuing work on a long-running autonomous development task.
This is a FRESH context window - you have no memory of previous sessions.

### STEP 1: GET YOUR BEARINGS (MANDATORY)

Start by orienting yourself:
```bash
pwd
ls -la
cat {progress_file}
cat {feature_list} | head -50
git log --oneline -10
```

### STEP 2: START SERVERS (IF NOT RUNNING)

If `{init_script}` exists, run it:
```bash
chmod +x {init_script}
./{init_script}
```

### STEP 3: VERIFICATION TEST (CRITICAL!)

**MANDATORY BEFORE NEW WORK:**

The previous session may have introduced bugs. Before implementing anything
new, you MUST verify that existing passing features still work.

Run 1-2 of the features marked as `"passes": true` to verify they still work.

**If you find ANY issues:**
- Mark that feature as `"passes": false` immediately
- Fix all issues BEFORE moving to new features

### STEP 4: CHOOSE ONE FEATURE TO IMPLEMENT

Look at {feature_list} and find the highest-priority feature with `"passes": false`.

Focus on completing ONE feature perfectly in this session before moving on.
It's ok if you only complete one feature - there will be more sessions.

### STEP 5: IMPLEMENT THE FEATURE

Implement the chosen feature thoroughly:
1. Write the code (frontend and/or backend as needed)
2. Test manually to verify it works
3. Fix any issues discovered
4. Verify the feature works end-to-end

### STEP 6: UPDATE {feature_list} (CAREFULLY!)

**YOU CAN ONLY MODIFY ONE FIELD: "passes"**

After thorough verification, change:
```json
"passes": false
```
to:
```json
"passes": true
```

**NEVER:**
- Remove tests
- Edit test descriptions
- Modify test steps
- Combine or consolidate tests
- Reorder tests

### STEP 7: COMMIT YOUR PROGRESS

Make a descriptive git commit:
```bash
git add .
git commit -m "Implement [feature name] - verified end-to-end"
```

### STEP 8: UPDATE PROGRESS NOTES

Update `{progress_file}` with:
- What you accomplished this session
- Which test(s) you completed
- Any issues discovered or fixed
- What should be worked on next
- Current completion status (e.g., "15/30 tests passing")

### STEP 9: END SESSION CLEANLY

Before context fills up:
1. Commit all working code
2. Update {progress_file}
3. Update {feature_list} if tests verified
4. Ensure no uncommitted changes
5. Leave app in working state (no broken features)

---

**Your Goal:** Complete all features in {feature_list}

**This Session's Goal:** Complete at least one feature perfectly

**Priority:** Fix broken tests before implementing new features

**You have unlimited time.** Take as long as needed to get it right.
"""


class LongRunningStrategy(Strategy):
    """Harness for long-running autonomous agents.

    Implements the two-agent pattern:
    - Initializer: First run sets up feature_list.json, init.sh, git
    - Coding: Subsequent runs make incremental progress

    Example:
        strategy = LongRunningStrategy(
            feature_list="feature_list.json",
            progress_file="claude-progress.txt",
            enforce_commits=True,
        )
        app.include(strategy.get_blueprint())
    """

    class Meta:
        name = "long-running"
        version = "1.0.0"
        description = "Harness for long-running autonomous agents"
        hooks = [
            "on_sessionstart",
            "on_stop",
            "on_precompact",
            "post_tool:Write",
            "post_tool:Edit",
            "post_tool:Bash",
        ]
        fail_mode: Literal["open", "closed"] = "open"
        custom_events = ["session_type", "feature_progress", "checkpoint_needed"]

    # Default file paths
    DEFAULT_FEATURE_LIST = "feature_list.json"
    DEFAULT_PROGRESS_FILE = "claude-progress.txt"
    DEFAULT_INIT_SCRIPT = "init.sh"
    DEFAULT_MIN_FEATURES = 30

    # Default paths to exclude from uncommitted changes check
    DEFAULT_EXCLUDE_PATHS = ["hooks/", ".claude/", ".fasthooks-state/", "fasthooks-state/"]

    def __init__(
        self,
        *,
        feature_list: str = DEFAULT_FEATURE_LIST,
        progress_file: str = DEFAULT_PROGRESS_FILE,
        init_script: str = DEFAULT_INIT_SCRIPT,
        min_features: int = DEFAULT_MIN_FEATURES,
        enforce_commits: bool = True,
        warn_uncommitted: bool = True,
        require_progress_update: bool = True,
        exclude_paths: list[str] | None = None,
        **config: Any,
    ):
        super().__init__(**config)
        self.feature_list = feature_list
        self.progress_file = progress_file
        self.init_script = init_script
        self.min_features = min_features
        self.enforce_commits = enforce_commits
        self.warn_uncommitted = warn_uncommitted
        self.require_progress_update = require_progress_update
        self.exclude_paths = exclude_paths or self.DEFAULT_EXCLUDE_PATHS

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("long-running")

        @bp.on_session_start()
        def on_session_start(event: Any, state: State) -> Any:
            return self._handle_session_start(event, state)

        @bp.on_stop()
        def on_stop(event: Any, state: State) -> Any:
            return self._handle_stop(event, state)

        @bp.on_pre_compact()
        def on_pre_compact(event: Any, state: State) -> Any:
            return self._handle_pre_compact(event, state)

        @bp.post_tool("Write")
        def post_write(event: Any, state: State) -> Any:
            return self._track_write(event, state)

        @bp.post_tool("Edit")
        def post_edit(event: Any, state: State) -> Any:
            return self._track_write(event, state)  # Same logic as Write

        @bp.post_tool("Bash")
        def post_bash(event: Any, state: State) -> Any:
            return self._track_bash(event, state)

        return bp

    # ═══════════════════════════════════════════════════════════════
    # Session Start Handler
    # ═══════════════════════════════════════════════════════════════

    def _handle_session_start(self, event: Any, state: State) -> Any:
        """Route to initializer or coding agent context."""
        project_dir = Path(event.cwd)
        feature_file = project_dir / self.feature_list

        # Initialize strategy state namespace
        ns = state.setdefault(self.Meta.name, {})
        ns["session_count"] = ns.get("session_count", 0) + 1
        ns["files_modified"] = []
        ns["commits_made"] = []
        ns["progress_updated"] = False
        state.save()

        source = getattr(event, "source", "startup")

        if source == "startup":
            if not feature_file.exists():
                # First run - inject initializer context
                self.emit_custom("session_type", {"type": "initializer"})
                return context(self._get_initializer_context())
            else:
                # Subsequent run - inject coding context
                self.emit_custom("session_type", {"type": "coding"})
                return context(self._get_coding_context(project_dir, ns))
        else:
            # Compact or resume
            self.emit_custom("session_type", {"type": "compact_resume"})
            return context(self._get_compact_context(project_dir, ns))

    def _get_initializer_context(self) -> str:
        """Build initializer prompt."""
        return INITIALIZER_PROMPT.format(
            feature_list=self.feature_list,
            progress_file=self.progress_file,
            init_script=self.init_script,
            min_features=self.min_features,
        )

    def _get_coding_context(self, project_dir: Path, ns: dict[str, Any]) -> str:
        """Build coding agent context with status and instructions."""
        # Dynamic status section
        passing, total = self._count_features(project_dir)
        self.emit_custom("feature_progress", {"passing": passing, "total": total})

        status_lines = [
            "## Current Project Status",
            f"- Features: {passing}/{total} passing",
            f"- Session #{ns.get('session_count', 1)}",
        ]

        # Recent git commits
        commits = self._get_recent_commits(project_dir, limit=5)
        if commits:
            status_lines.append("- Recent commits:")
            for c in commits[:3]:
                status_lines.append(f"  - {c}")

        # Progress file summary
        progress = self._read_progress(project_dir)
        if progress:
            summary = progress[:150] + "..." if len(progress) > 150 else progress
            status_lines.append(f"- Last session notes: {summary}")

        # Current task (if tracked)
        if current := ns.get("current_feature"):
            status_lines.append(f"- In progress: {current}")

        status_lines.append("")

        # Full coding prompt with instructions
        coding_instructions = CODING_PROMPT.format(
            feature_list=self.feature_list,
            progress_file=self.progress_file,
            init_script=self.init_script,
        )

        return "\n".join(status_lines) + coding_instructions

    def _get_compact_context(self, project_dir: Path, ns: dict[str, Any]) -> str:
        """Minimal context after compaction."""
        passing, total = self._count_features(project_dir)

        return f"""## Context Restored After Compaction

- Features: {passing}/{total} passing
- Session #{ns.get('session_count', '?')}
- Files modified this session: {len(ns.get('files_modified', []))}

Read `{self.progress_file}` and `git log` for full context.
Continue with current task or pick next feature from {self.feature_list}.
"""

    # ═══════════════════════════════════════════════════════════════
    # Stop Handler
    # ═══════════════════════════════════════════════════════════════

    def _handle_stop(self, event: Any, state: State) -> Any:
        """Enforce clean state before stopping."""
        project_dir = Path(event.cwd)
        ns = state.get(self.Meta.name, {})
        issues = []
        warnings = []

        # Check uncommitted changes
        uncommitted = self._check_uncommitted(project_dir)
        if uncommitted:
            files = ", ".join(uncommitted[:5])
            if len(uncommitted) > 5:
                files += f" (+{len(uncommitted) - 5} more)"
            msg = f"Uncommitted changes in: {files}"
            if self.enforce_commits:
                issues.append(msg)
            elif self.warn_uncommitted:
                warnings.append(msg)

        # Check progress file updated
        if self.require_progress_update and not ns.get("progress_updated"):
            issues.append(f"Please update {self.progress_file} with session summary")

        if issues:
            return block(
                "Cannot stop - please address:\n" + "\n".join(f"- {i}" for i in issues)
            )

        if warnings:
            return allow(
                message="⚠️ Warning:\n" + "\n".join(f"- {w}" for w in warnings)
            )

        return allow()

    # ═══════════════════════════════════════════════════════════════
    # Pre-Compact Handler
    # ═══════════════════════════════════════════════════════════════

    def _handle_pre_compact(self, event: Any, state: State) -> Any:
        """Inject state summary before compaction."""
        ns = state.get(self.Meta.name, {})
        project_dir = Path(event.cwd)
        passing, total = self._count_features(project_dir)

        self.emit_custom("checkpoint_needed", {"reason": "compaction"})

        return allow(
            message=f"""## COMPACTION CHECKPOINT

Before context is compacted, note:
- Features: {passing}/{total} passing
- Files modified: {ns.get('files_modified', [])}
- Commits made: {len(ns.get('commits_made', []))}

If you have uncommitted work, commit NOW before compaction.
Update {self.progress_file} with current status.
"""
        )

    # ═══════════════════════════════════════════════════════════════
    # Tool Tracking Handlers
    # ═══════════════════════════════════════════════════════════════

    def _track_write(self, event: Any, state: State) -> Any | None:
        """Track writes, warn on feature_list.json structural changes."""
        ns = state.setdefault(self.Meta.name, {})
        file_path = getattr(event, "file_path", "")
        ns.setdefault("files_modified", []).append(file_path)

        # Track progress file updates (use Path for accurate comparison)
        if self._is_target_file(file_path, self.progress_file, event):
            ns["progress_updated"] = True

        state.save()

        # Warn on feature list structural changes
        if self._is_target_file(file_path, self.feature_list, event):
            if self._is_structural_change(event):
                return allow(
                    message=(
                        "WARNING: You modified the structure of feature_list.json.\n"
                        "Only the 'passes' field should be changed. "
                        "Consider reverting structural changes."
                    )
                )

        return None

    def _is_target_file(self, file_path: str, target: str, event: Any) -> bool:
        """Check if file_path matches target file (handles relative/absolute paths)."""
        if not file_path:
            return False
        try:
            fp = Path(file_path)
            # Check filename match
            if fp.name == Path(target).name:
                return True
            # Check if it ends with target path
            if file_path.endswith(target):
                return True
            # Check resolved path match
            cwd = Path(getattr(event, "cwd", "."))
            target_path = (cwd / target).resolve()
            return fp.resolve() == target_path
        except Exception:
            return False

    def _track_bash(self, event: Any, state: State) -> Any | None:
        """Track git commits."""
        ns = state.setdefault(self.Meta.name, {})
        command = getattr(event, "command", "")

        if self._is_git_commit(command):
            ns.setdefault("commits_made", []).append(command)
            state.save()

        return None

    def _is_git_commit(self, command: str) -> bool:
        """Check if command is a git commit (handles various formats)."""
        if not command:
            return False
        # Strip leading whitespace and handle common patterns
        cmd = command.strip()
        # Direct git commit
        if cmd.startswith("git commit"):
            return True
        # Via && chain: "git add . && git commit"
        if "git commit" in cmd:
            return True
        return False

    # ═══════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════

    def _count_features(self, project_dir: Path) -> tuple[int, int]:
        """Count passing/total features in feature_list.json."""
        feature_file = project_dir / self.feature_list
        if not feature_file.exists():
            return 0, 0

        try:
            features = json.loads(feature_file.read_text())
            total = len(features)
            passing = sum(1 for f in features if f.get("passes", False))
            return passing, total
        except (json.JSONDecodeError, OSError):
            return 0, 0

    def _get_recent_commits(self, project_dir: Path, limit: int = 5) -> list[str]:
        """Get recent git commit messages."""
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", f"-{limit}"],
                capture_output=True,
                text=True,
                cwd=project_dir,
            )
            if result.returncode == 0:
                return [ln for ln in result.stdout.strip().split("\n") if ln]
        except Exception:
            pass
        return []

    def _read_progress(self, project_dir: Path) -> str:
        """Read last entry from progress file."""
        progress_file = project_dir / self.progress_file
        if not progress_file.exists():
            return ""

        try:
            content = progress_file.read_text()
            # Return last paragraph (most recent session)
            paragraphs = content.strip().split("\n\n")
            return paragraphs[-1] if paragraphs else ""
        except OSError:
            return ""

    def _is_git_repo(self, project_dir: Path) -> bool:
        """Check if project_dir is a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                cwd=project_dir,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _check_uncommitted(self, project_dir: Path) -> list[str]:
        """Return list of uncommitted files, empty if clean or not a git repo.

        Excludes paths matching self.exclude_paths patterns.
        """
        if not self._is_git_repo(project_dir):
            # Not a git repo - can't check uncommitted
            return []
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=project_dir,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                files = [ln[3:].strip() for ln in lines if ln]
                # Filter out excluded paths
                return [
                    f
                    for f in files
                    if not any(f.startswith(excl) for excl in self.exclude_paths)
                ]
        except Exception:
            pass
        return []

    def _is_structural_change(self, event: Any) -> bool:
        """Check if feature_list.json change modified structure (not just passes)."""
        try:
            project_dir = Path(event.cwd)
            content = getattr(event, "content", None)
            if not content:
                return False

            features = json.loads(content)

            # Load previous version from git
            result = subprocess.run(
                ["git", "show", f"HEAD:{self.feature_list}"],
                capture_output=True,
                text=True,
                cwd=project_dir,
            )
            if result.returncode != 0:
                return False  # No previous version

            old_features = json.loads(result.stdout)

            # Compare: same count, same descriptions, only passes changed
            if len(features) != len(old_features):
                return True

            for new, old in zip(features, old_features):
                for key in set(new.keys()) | set(old.keys()):
                    if key == "passes":
                        continue
                    if new.get(key) != old.get(key):
                        return True

            return False
        except Exception:
            return False  # Can't determine, assume ok
