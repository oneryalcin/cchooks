"""CLI entry point for FastHooks Studio."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import socket
import webbrowser
from contextlib import closing
from pathlib import Path

import uvicorn

from fasthooks.studio.server import create_app

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".fasthooks" / "studio.db"
DEFAULT_PORT = 5555
POLL_INTERVAL = 0.5  # 500ms


def _socket_is_open(host: str, port: int) -> bool:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        return sock.connect_ex((host, port)) == 0


async def db_watcher(db_path: Path, app: any) -> None:
    """Poll DB file for changes and notify clients."""
    last_stat = None

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            current_stat = db_path.stat()

            if last_stat is None:
                logger.info(f"Database file found: {db_path}")
                await app.notify_clients(json.dumps({"type": "db_updated"}))
            else:
                time_changed = abs(current_stat.st_mtime - last_stat.st_mtime) > 0.1
                size_changed = current_stat.st_size != last_stat.st_size
                inode_changed = current_stat.st_ino != last_stat.st_ino

                if time_changed or size_changed or inode_changed:
                    logger.debug("Database changed, notifying clients")
                    await app.notify_clients(json.dumps({"type": "db_updated"}))

            last_stat = current_stat

        except FileNotFoundError:
            if last_stat is not None:
                logger.info(f"Database file deleted: {db_path}")
                await app.notify_clients(json.dumps({"type": "db_updated"}))
            last_stat = None
            await asyncio.sleep(1)  # Wait longer if file missing

        except Exception as e:
            logger.warning(f"Error checking database file: {e}")
            await asyncio.sleep(1)


async def open_browser(host: str, port: int) -> None:
    """Wait for server to be ready then open browser."""
    while True:
        if _socket_is_open(host, port):
            url = f"http://{host}:{port}"
            logger.info(f"Opening browser: {url}")
            webbrowser.open_new(url)
            return
        await asyncio.sleep(0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description="FastHooks Studio")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to studio.db (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to bind to (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open browser automatically",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
        datefmt="%H:%M:%S",
    )

    db_path = args.db.expanduser()

    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        logger.info("Run hooks with SQLiteObserver to create the database.")
        return

    logger.info("Starting FastHooks Studio")
    logger.info(f"Database: {db_path}")
    logger.info(f"Server: http://{args.host}:{args.port}")

    app = create_app(db_path)

    # Run server with file watcher
    loop = asyncio.new_event_loop()

    config = uvicorn.Config(
        app=app,
        host=args.host,
        port=args.port,
        loop=loop,
        log_level="warning",  # Quieter uvicorn logs
    )
    server = uvicorn.Server(config)

    loop.create_task(server.serve())
    loop.create_task(db_watcher(db_path, app))

    if args.open:
        loop.create_task(open_browser(args.host, args.port))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
