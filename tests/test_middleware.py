"""Tests for middleware."""
import json
from io import StringIO

from fasthooks import HookApp, allow, deny


class TestMiddleware:
    def test_middleware_wraps_handlers(self):
        """Middleware wraps all handler calls."""
        app = HookApp()
        log = []

        @app.middleware
        def timing_middleware(event, call_next):
            log.append("before")
            response = call_next(event)
            log.append("after")
            return response

        @app.on_stop()
        def handle_stop(event):
            log.append("handler")
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        assert log == ["before", "handler", "after"]

    def test_middleware_can_short_circuit(self):
        """Middleware can prevent handler execution."""
        app = HookApp()
        calls = []

        @app.middleware
        def block_all(event, call_next):
            calls.append("middleware")
            return deny("Blocked by middleware")

        @app.on_stop()
        def handle_stop(event):
            calls.append("handler")
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        stdout = StringIO()
        app.run(stdin=stdin, stdout=stdout)

        assert calls == ["middleware"]  # handler never called
        stdout.seek(0)
        result = json.loads(stdout.read())
        assert result["decision"] == "deny"

    def test_multiple_middleware(self):
        """Multiple middleware are chained in order."""
        app = HookApp()
        log = []

        @app.middleware
        def first(event, call_next):
            log.append("first_before")
            response = call_next(event)
            log.append("first_after")
            return response

        @app.middleware
        def second(event, call_next):
            log.append("second_before")
            response = call_next(event)
            log.append("second_after")
            return response

        @app.on_stop()
        def handle_stop(event):
            log.append("handler")
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        # Middleware stack: first wraps second wraps handler
        assert log == [
            "first_before",
            "second_before",
            "handler",
            "second_after",
            "first_after",
        ]

    def test_middleware_receives_event(self):
        """Middleware receives the parsed event."""
        app = HookApp()
        captured = []

        @app.middleware
        def capture_event(event, call_next):
            captured.append(event.hook_event_name)
            return call_next(event)

        @app.on_stop()
        def handle_stop(event):
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        assert captured == ["Stop"]


class TestAsyncMiddleware:
    """Tests for async middleware support."""

    def test_async_middleware(self):
        """Async middleware works."""
        app = HookApp()
        log = []

        @app.middleware
        async def async_mw(event, call_next):
            log.append("before")
            response = await call_next(event)
            log.append("after")
            return response

        @app.on_stop()
        def handle_stop(event):
            log.append("handler")
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        assert log == ["before", "handler", "after"]

    def test_async_middleware_with_await(self):
        """Async middleware can use await."""
        import anyio

        app = HookApp()
        awaited = []

        @app.middleware
        async def async_mw(event, call_next):
            await anyio.sleep(0.001)
            awaited.append("middleware")
            return await call_next(event)

        @app.on_stop()
        def handle_stop(event):
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        assert awaited == ["middleware"]

    def test_mixed_sync_async_middleware(self):
        """Sync and async middleware work together."""
        app = HookApp()
        log = []

        @app.middleware
        def sync_mw(event, call_next):
            log.append("sync_before")
            response = call_next(event)
            log.append("sync_after")
            return response

        @app.middleware
        async def async_mw(event, call_next):
            log.append("async_before")
            response = await call_next(event)
            log.append("async_after")
            return response

        @app.on_stop()
        def handle_stop(event):
            log.append("handler")
            return allow()

        stdin = StringIO(json.dumps({
            "session_id": "test",
            "cwd": "/workspace",
            "permission_mode": "default",
            "hook_event_name": "Stop",
        }))
        app.run(stdin=stdin, stdout=StringIO())

        assert log == [
            "sync_before",
            "async_before",
            "handler",
            "async_after",
            "sync_after",
        ]
