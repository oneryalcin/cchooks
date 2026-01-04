"""Strategy test client for testing strategies."""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fasthooks.depends import State, Transcript
from fasthooks.testing.mocks import MockEvent

if TYPE_CHECKING:
    from fasthooks.observability import ObservabilityEvent
    from fasthooks.responses import BaseHookResponse
    from fasthooks.strategies.base import Strategy


class StrategyTestClient:
    """Full-featured test client for strategies.

    Provides helpers for:
    - Project setup (files, git)
    - Triggering hooks
    - Capturing observability events
    - Assertions

    Example:
        strategy = LongRunningStrategy(enforce_commits=True)
        client = StrategyTestClient(strategy)

        client.setup_project(files={"feature_list.json": "[]"})
        client.setup_git()

        response = client.trigger_session_start()
        assert response.decision == "approve"

        client.assert_event_emitted("session_type", type="coding")
    """

    def __init__(
        self,
        strategy: Strategy,
        *,
        project_dir: Path | str | None = None,
        session_id: str = "test-session",
        mock_transcript: Any = None,
    ):
        """Initialize StrategyTestClient.

        Args:
            strategy: Strategy instance to test.
            project_dir: Project directory (uses tmp if None).
            session_id: Session ID for events.
            mock_transcript: Optional mock Transcript for testing token-based strategies.
        """
        self.strategy = strategy
        self.project_dir = Path(project_dir) if project_dir else Path("/tmp/test-project")
        self.session_id = session_id
        self._events: list[ObservabilityEvent] = []
        self._state: State | None = None
        self._transcript: Transcript | Any | None = mock_transcript
        self._git_initialized = False

        # Register event collector
        @strategy.on_observe
        def collect(event: ObservabilityEvent) -> None:
            self._events.append(event)

    @property
    def events(self) -> list[ObservabilityEvent]:
        """All captured observability events."""
        return self._events

    @property
    def state(self) -> State:
        """Get or create State for this session."""
        if self._state is None:
            state_dir = self.project_dir / ".fasthooks-state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self._state = State.for_session(self.session_id, state_dir)
        return self._state

    def set_transcript(self, transcript: Any) -> None:
        """Set mock transcript for testing.

        Args:
            transcript: Mock Transcript object with stats attribute.
        """
        self._transcript = transcript

    # ═══════════════════════════════════════════════════════════════════════════
    # Project Setup
    # ═══════════════════════════════════════════════════════════════════════════

    def setup_project(self, files: dict[str, str] | None = None) -> None:
        """Set up project directory with files.

        Args:
            files: Dict of {filename: content} to create.
        """
        self.project_dir.mkdir(parents=True, exist_ok=True)
        if files:
            for name, content in files.items():
                path = self.project_dir / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

    def setup_git(self, *, initial_commit: bool = True) -> None:
        """Initialize git repository.

        Args:
            initial_commit: Whether to make initial commit.
        """
        self.project_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init"],
            cwd=self.project_dir,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=self.project_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=self.project_dir,
            capture_output=True,
        )
        self._git_initialized = True

        if initial_commit:
            # Create initial file and commit
            (self.project_dir / ".gitkeep").write_text("")
            subprocess.run(
                ["git", "add", "."],
                cwd=self.project_dir,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=self.project_dir,
                capture_output=True,
            )

    def add_uncommitted(self, filename: str, content: str = "# uncommitted") -> None:
        """Add an uncommitted file to the project.

        Args:
            filename: File to create.
            content: File content.
        """
        path = self.project_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def commit_all(self, message: str = "Test commit") -> None:
        """Commit all changes.

        Args:
            message: Commit message.
        """
        subprocess.run(
            ["git", "add", "."],
            cwd=self.project_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.project_dir,
            capture_output=True,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Hook Triggers
    # ═══════════════════════════════════════════════════════════════════════════

    def trigger_session_start(
        self, source: str = "startup"
    ) -> BaseHookResponse | None:
        """Trigger SessionStart hook.

        Args:
            source: Event source ("startup", "compact", "resume").

        Returns:
            Hook response or None.
        """
        event = MockEvent.session_start(
            source=source,
            session_id=self.session_id,
            cwd=str(self.project_dir),
        )
        return self._invoke_hook("on_session_start", event)

    def trigger_stop(self) -> BaseHookResponse | None:
        """Trigger Stop hook.

        Returns:
            Hook response or None.
        """
        event = MockEvent.stop(
            session_id=self.session_id,
            cwd=str(self.project_dir),
        )
        return self._invoke_hook("on_stop", event)

    def trigger_pre_compact(self, trigger: str = "manual") -> BaseHookResponse | None:
        """Trigger PreCompact hook.

        Args:
            trigger: What triggered compaction.

        Returns:
            Hook response or None.
        """
        event = MockEvent.pre_compact(
            trigger=trigger,
            session_id=self.session_id,
            cwd=str(self.project_dir),
        )
        return self._invoke_hook("on_pre_compact", event)

    def trigger_post_write(
        self, file_path: str, content: str = ""
    ) -> BaseHookResponse | None:
        """Trigger PostToolUse for Write.

        Args:
            file_path: Path that was written.
            content: Content that was written.

        Returns:
            Hook response or None.
        """
        event = MockEvent.write(
            file_path=file_path,
            content=content,
            session_id=self.session_id,
            cwd=str(self.project_dir),
        )
        # Mark as PostToolUse
        event_dict = event.model_dump()
        event_dict["hook_event_name"] = "PostToolUse"
        return self._invoke_hook("post_tool:Write", event, event_dict)

    def trigger_post_bash(self, command: str) -> BaseHookResponse | None:
        """Trigger PostToolUse for Bash.

        Args:
            command: Command that was executed.

        Returns:
            Hook response or None.
        """
        event = MockEvent.bash(
            command=command,
            session_id=self.session_id,
            cwd=str(self.project_dir),
        )
        event_dict = event.model_dump()
        event_dict["hook_event_name"] = "PostToolUse"
        return self._invoke_hook("post_tool:Bash", event, event_dict)

    def _invoke_hook(
        self,
        hook_name: str,
        event: Any,
        event_dict: dict[str, Any] | None = None,
    ) -> BaseHookResponse | None:
        """Invoke a hook on the strategy's blueprint.

        Args:
            hook_name: Hook identifier (e.g., "on_stop", "post_tool:Write").
            event: Typed event object.
            event_dict: Optional dict override for event.

        Returns:
            Hook response or None.
        """
        bp = self.strategy.get_blueprint()

        # Map hook names to registry keys
        LIFECYCLE_MAP = {
            "on_stop": "Stop",
            "on_session_start": "SessionStart",
            "on_pre_compact": "PreCompact",
            "on_session_end": "SessionEnd",
            "on_subagent_stop": "SubagentStop",
            "on_notification": "Notification",
            "on_user_prompt": "UserPromptSubmit",
        }

        # Find the right handler
        if hook_name.startswith("on_"):
            # Lifecycle hook - use PascalCase key
            lifecycle_key = LIFECYCLE_MAP.get(hook_name, "")
            handlers = bp._lifecycle_handlers.get(lifecycle_key, [])
        elif hook_name.startswith("post_tool:"):
            tool = hook_name.split(":")[1]
            # Also check catch-all handlers
            handlers = bp._post_tool_handlers.get(tool, [])
            handlers = handlers + bp._post_tool_handlers.get("*", [])
        elif hook_name.startswith("pre_tool:"):
            tool = hook_name.split(":")[1]
            handlers = bp._pre_tool_handlers.get(tool, [])
            handlers = handlers + bp._pre_tool_handlers.get("*", [])
        else:
            handlers = []

        # Run handlers with DI
        for handler, guard in handlers:
            if guard and not guard(event):
                continue
            result = self._call_with_di(handler, event)
            if result is not None:
                return result

        return None

    def _call_with_di(self, handler: Any, event: Any) -> Any:
        """Call handler with dependency injection based on signature.

        Args:
            handler: Handler function.
            event: Event object.

        Returns:
            Handler result.
        """
        sig = inspect.signature(handler)
        kwargs: dict[str, Any] = {}

        for name, param in sig.parameters.items():
            if name == "event" or param.annotation is type(event):
                continue  # First positional arg is event
            if param.annotation is State or name == "state":
                kwargs[name] = self.state
            elif param.annotation is Transcript or name == "transcript":
                kwargs[name] = self._transcript

        return handler(event, **kwargs)

    # ═══════════════════════════════════════════════════════════════════════════
    # Assertions
    # ═══════════════════════════════════════════════════════════════════════════

    def assert_blocked(self, reason_contains: str | None = None) -> None:
        """Assert that a block decision was made.

        Args:
            reason_contains: Optional substring to check in reason.
        """
        decisions = [e for e in self._events if e.event_type == "decision"]
        blocks = [e for e in decisions if getattr(e, "decision", None) == "block"]

        assert blocks, f"No block decisions found. Decisions: {[getattr(e, 'decision', None) for e in decisions]}"

        if reason_contains:
            reasons = [getattr(e, "reason", "") or "" for e in blocks]
            assert any(
                reason_contains.lower() in r.lower() for r in reasons
            ), f"No block with '{reason_contains}' in reason. Reasons: {reasons}"

    def assert_allowed(self) -> None:
        """Assert that an allow/approve decision was made."""
        decisions = [e for e in self._events if e.event_type == "decision"]
        approves = [e for e in decisions if getattr(e, "decision", None) == "approve"]

        assert approves, f"No approve decisions found. Decisions: {[getattr(e, 'decision', None) for e in decisions]}"

    def assert_event_emitted(
        self, custom_event_type: str, **payload_match: Any
    ) -> None:
        """Assert that a custom event was emitted.

        Args:
            custom_event_type: Type of custom event.
            **payload_match: Expected payload values.
        """
        custom_events = [
            e for e in self._events
            if e.event_type == "custom" and e.custom_event_type == custom_event_type
        ]

        assert custom_events, (
            f"No custom event '{custom_event_type}' found. "
            f"Custom events: {[e.custom_event_type for e in self._events if e.event_type == 'custom']}"
        )

        if payload_match:
            for event in custom_events:
                if all(event.payload.get(k) == v for k, v in payload_match.items()):
                    return  # Found matching event

            payloads = [e.payload for e in custom_events]
            raise AssertionError(
                f"No '{custom_event_type}' event with payload {payload_match}. "
                f"Found payloads: {payloads}"
            )

    def clear_events(self) -> None:
        """Clear captured events."""
        self._events.clear()
