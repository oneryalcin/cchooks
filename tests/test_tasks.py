"""Tests for background tasks system."""

import time

import pytest

from fasthooks import HookApp, allow
from fasthooks.tasks import (
    BackgroundTasks,
    ImmediateBackend,
    InMemoryBackend,
    PendingResults,
    Task,
    TaskResult,
    TaskStatus,
    task,
)
from fasthooks.testing import MockEvent, TestClient

# ═══════════════════════════════════════════════════════════════
# Task and TaskResult tests
# ═══════════════════════════════════════════════════════════════


def test_task_decorator_simple():
    """Test @task decorator creates Task object."""

    @task
    def my_task(x: int) -> int:
        return x * 2

    assert isinstance(my_task, Task)
    assert my_task.name == "my_task"
    assert my_task.priority == 0
    assert my_task.ttl == 300


def test_task_decorator_with_options():
    """Test @task decorator with custom options."""

    @task(priority=5, ttl=600)
    def slow_task(query: str) -> str:
        return f"result: {query}"

    assert isinstance(slow_task, Task)
    assert slow_task.priority == 5
    assert slow_task.ttl == 600


def test_task_with_transform():
    """Test @task with transform function."""

    @task(transform=lambda r: f"Transformed: {r}")
    def my_task(x: int) -> int:
        return x * 2

    result = my_task(5)
    assert result == "Transformed: 10"


def test_task_callable():
    """Test Task is directly callable."""

    @task
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5


def test_task_result_status_transitions():
    """Test TaskResult status transitions."""
    result = TaskResult(
        id="test-id",
        session_id="test-session",
        key="test-key",
    )

    assert result.status == TaskStatus.PENDING
    assert not result.is_finished

    result.set_running()
    assert result.status == TaskStatus.RUNNING
    assert result.started_at is not None

    result.set_completed("done")
    assert result.status == TaskStatus.COMPLETED
    assert result.value == "done"
    assert result.is_finished
    assert result.finished_at is not None


def test_task_result_failed():
    """Test TaskResult failure handling."""
    result = TaskResult(
        id="test-id",
        session_id="test-session",
        key="test-key",
    )

    error = ValueError("Something went wrong")
    result.set_failed(error)

    assert result.status == TaskStatus.FAILED
    assert result.error is error
    assert result.is_finished


def test_task_result_cancelled():
    """Test TaskResult cancellation."""
    result = TaskResult(
        id="test-id",
        session_id="test-session",
        key="test-key",
    )

    result.set_cancelled()
    assert result.status == TaskStatus.CANCELLED
    assert result.is_finished


def test_task_result_ttl_expiry():
    """Test TaskResult TTL expiry check."""
    result = TaskResult(
        id="test-id",
        session_id="test-session",
        key="test-key",
        ttl=1,  # 1 second TTL
        created_at=time.time() - 2,  # Created 2 seconds ago
    )

    assert result.is_expired


# ═══════════════════════════════════════════════════════════════
# ImmediateBackend tests
# ═══════════════════════════════════════════════════════════════


def test_immediate_backend_enqueue():
    """Test ImmediateBackend executes tasks immediately."""
    backend = ImmediateBackend()

    @task
    def double(x: int) -> int:
        return x * 2

    result = backend.enqueue(
        double,
        (5,),
        {},
        session_id="test-session",
        key="double",
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.value == 10


def test_immediate_backend_pop():
    """Test ImmediateBackend pop retrieves and removes result."""
    backend = ImmediateBackend()

    @task
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    backend.enqueue(greet, ("World",), {}, session_id="s1", key="greeting")

    # First pop returns value
    value = backend.pop("s1", "greeting")
    assert value == "Hello, World!"

    # Second pop returns None (already removed)
    assert backend.pop("s1", "greeting") is None


def test_immediate_backend_pop_all():
    """Test ImmediateBackend pop_all retrieves all results for session."""
    backend = ImmediateBackend()

    @task
    def echo(x: int) -> int:
        return x

    backend.enqueue(echo, (1,), {}, session_id="s1", key="a")
    backend.enqueue(echo, (2,), {}, session_id="s1", key="b")
    backend.enqueue(echo, (3,), {}, session_id="s2", key="c")  # Different session

    values = backend.pop_all("s1")
    assert set(values) == {1, 2}

    # s2 result still there
    assert backend.pop("s2", "c") == 3


def test_immediate_backend_error_handling():
    """Test ImmediateBackend handles task errors."""
    backend = ImmediateBackend()

    @task
    def fail():
        raise ValueError("Intentional failure")

    result = backend.enqueue(fail, (), {}, session_id="s1", key="fail")

    assert result.status == TaskStatus.FAILED
    assert isinstance(result.error, ValueError)


def test_immediate_backend_pop_errors():
    """Test ImmediateBackend pop_errors retrieves failed tasks."""
    backend = ImmediateBackend()

    @task
    def fail():
        raise ValueError("Error!")

    @task
    def succeed() -> str:
        return "ok"

    backend.enqueue(fail, (), {}, session_id="s1", key="fail1")
    backend.enqueue(fail, (), {}, session_id="s1", key="fail2")
    backend.enqueue(succeed, (), {}, session_id="s1", key="ok")

    errors = backend.pop_errors("s1")
    assert len(errors) == 2
    assert all(isinstance(err, ValueError) for _, err in errors)


def test_immediate_backend_has():
    """Test ImmediateBackend has checks for completed results."""
    backend = ImmediateBackend()

    @task
    def echo(x: int) -> int:
        return x

    assert not backend.has("s1", "key")
    assert not backend.has("s1")

    backend.enqueue(echo, (1,), {}, session_id="s1", key="key")

    assert backend.has("s1", "key")
    assert backend.has("s1")
    assert not backend.has("s1", "other")


def test_immediate_backend_cancel():
    """Test ImmediateBackend cancel (no-op for immediate)."""
    backend = ImmediateBackend()

    @task
    def echo(x: int) -> int:
        return x

    # Task already completed by the time cancel is called
    backend.enqueue(echo, (1,), {}, session_id="s1", key="key")
    assert not backend.cancel("s1", "key")


# ═══════════════════════════════════════════════════════════════
# InMemoryBackend tests
# ═══════════════════════════════════════════════════════════════


def test_inmemory_backend_enqueue():
    """Test InMemoryBackend enqueues and executes tasks."""
    backend = InMemoryBackend(max_workers=2)

    @task
    def slow_double(x: int) -> int:
        time.sleep(0.1)
        return x * 2

    result = backend.enqueue(
        slow_double,
        (5,),
        {},
        session_id="test-session",
        key="double",
    )

    # Initially pending or running
    assert result.status in (TaskStatus.PENDING, TaskStatus.RUNNING)

    # Wait for completion
    time.sleep(0.3)

    # Check result is completed
    task_result = backend.get("test-session", "double")
    assert task_result is not None
    assert task_result.status == TaskStatus.COMPLETED
    assert task_result.value == 10

    backend.shutdown()


def test_inmemory_backend_cancel():
    """Test InMemoryBackend cancel."""
    backend = InMemoryBackend(max_workers=1)

    @task
    def slow_task() -> str:
        time.sleep(1)
        return "done"

    # Enqueue but don't wait
    backend.enqueue(slow_task, (), {}, session_id="s1", key="slow")

    # Cancel immediately
    cancelled = backend.cancel("s1", "slow")
    # May or may not succeed depending on timing
    assert isinstance(cancelled, bool)

    backend.shutdown(wait=False)


# ═══════════════════════════════════════════════════════════════
# DI Integration tests
# ═══════════════════════════════════════════════════════════════


def test_background_tasks_di():
    """Test BackgroundTasks dependency injection."""
    backend = ImmediateBackend()
    app = HookApp(task_backend=backend)

    @task
    def process(x: int) -> int:
        return x * 2

    @app.pre_tool("Bash")
    def handler(event, tasks: BackgroundTasks):
        tasks.add(process, 5, key="result")
        return allow()

    client = TestClient(app)
    client.send(MockEvent.bash(command="ls"))

    # Task should have been enqueued and completed (ImmediateBackend)
    assert backend.has("test-session", "result")
    assert backend.pop("test-session", "result") == 10


def test_pending_results_di():
    """Test PendingResults dependency injection."""
    backend = ImmediateBackend()
    app = HookApp(task_backend=backend)

    # Pre-populate a result
    @task
    def dummy() -> str:
        return "cached"

    backend.enqueue(dummy, (), {}, session_id="test-session", key="memory")

    results_received = []

    @app.pre_tool("Bash")
    def handler(event, pending: PendingResults):
        if result := pending.pop("memory"):
            results_received.append(result)
        return allow()

    client = TestClient(app)
    client.send(MockEvent.bash(command="ls"))

    assert results_received == ["cached"]
    # Result should be removed after pop
    assert not backend.has("test-session", "memory")


def test_background_tasks_and_pending_results_together():
    """Test using both BackgroundTasks and PendingResults."""
    backend = ImmediateBackend()
    app = HookApp(task_backend=backend)

    @task
    def compute(x: int) -> int:
        return x * 3

    results_retrieved = []

    @app.pre_tool("Bash")
    def handler(event, tasks: BackgroundTasks, pending: PendingResults):
        if result := pending.pop("compute"):
            # Second call - cached result available
            results_retrieved.append(result)
            return allow()

        # First call - enqueue task
        tasks.add(compute, 7, key="compute")
        return allow()

    client = TestClient(app)

    # First call - enqueues task
    response1 = client.send(MockEvent.bash(command="ls"))
    assert response1 is None  # allow() returns None
    assert len(results_retrieved) == 0

    # Second call - retrieves result
    response2 = client.send(MockEvent.bash(command="ls"))
    assert response2 is None  # allow() still returns None
    assert results_retrieved == [21]  # But result was retrieved


def test_default_task_backend():
    """Test HookApp creates default InMemoryBackend."""
    app = HookApp()

    # Accessing task_backend should create default backend
    backend = app.task_backend
    assert isinstance(backend, InMemoryBackend)

    # Same instance on subsequent access
    assert app.task_backend is backend


def test_custom_task_backend():
    """Test HookApp accepts custom task backend."""
    custom_backend = ImmediateBackend()
    app = HookApp(task_backend=custom_backend)

    assert app.task_backend is custom_backend


# ═══════════════════════════════════════════════════════════════
# Async tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_immediate_backend_wait():
    """Test ImmediateBackend wait (returns immediately)."""
    backend = ImmediateBackend()

    @task
    def echo(x: int) -> int:
        return x

    backend.enqueue(echo, (42,), {}, session_id="s1", key="answer")

    result = await backend.wait("s1", "answer", timeout=1.0)
    assert result == 42


@pytest.mark.asyncio
async def test_immediate_backend_wait_all():
    """Test ImmediateBackend wait_all."""
    backend = ImmediateBackend()

    @task
    def echo(x: int) -> int:
        return x

    backend.enqueue(echo, (1,), {}, session_id="s1", key="a")
    backend.enqueue(echo, (2,), {}, session_id="s1", key="b")

    results = await backend.wait_all("s1", ["a", "b"], timeout=1.0)
    assert results == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_immediate_backend_wait_any():
    """Test ImmediateBackend wait_any."""
    backend = ImmediateBackend()

    @task
    def echo(x: int) -> int:
        return x

    backend.enqueue(echo, (1,), {}, session_id="s1", key="first")

    result = await backend.wait_any("s1", ["first", "second"], timeout=1.0)
    assert result == ("first", 1)


@pytest.mark.asyncio
async def test_pending_results_wait():
    """Test PendingResults async wait methods."""
    backend = ImmediateBackend()

    @task
    def echo(x: int) -> int:
        return x

    backend.enqueue(echo, (99,), {}, session_id="s1", key="value")

    pending = PendingResults(backend, "s1")

    result = await pending.wait("value", timeout=1.0)
    assert result == 99


# ═══════════════════════════════════════════════════════════════
# TTL and cleanup tests
# ═══════════════════════════════════════════════════════════════


def test_ttl_cleanup():
    """Test expired results are cleaned up."""
    backend = ImmediateBackend()

    @task(ttl=0)  # Immediate expiry
    def echo(x: int) -> int:
        return x

    backend.enqueue(echo, (1,), {}, session_id="s1", key="expired")

    # Small delay to ensure TTL expires
    time.sleep(0.01)

    # Should be cleaned up on next access
    assert backend.get("s1", "expired") is None
