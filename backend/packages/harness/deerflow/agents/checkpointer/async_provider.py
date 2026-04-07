"""Async checkpointer factory.

Provides an **async context manager** for long-running async servers that need
proper resource cleanup.

Supported backends: memory, sqlite, postgres.

Usage (e.g. FastAPI lifespan)::

    from deerflow.agents.checkpointer.async_provider import make_checkpointer

    async with make_checkpointer() as checkpointer:
        app.state.checkpointer = checkpointer  # InMemorySaver if not configured

For sync usage see :mod:`deerflow.agents.checkpointer.provider`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from collections.abc import AsyncIterator

from langgraph.types import Checkpointer
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from deerflow.agents.checkpointer.provider import (
    POSTGRES_CONN_REQUIRED,
    POSTGRES_INSTALL,
    SQLITE_INSTALL,
)
from deerflow.config.app_config import get_app_config
from deerflow.runtime.store._sqlite_utils import ensure_sqlite_parent_dir, resolve_sqlite_conn_str

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Windows event loop fix for psycopg
# ---------------------------------------------------------------------------


def _ensure_compatible_event_loop():
    """Ensure event loop is compatible with psycopg on Windows.

    psycopg requires SelectorEventLoop on Windows, but Python 3.8+ defaults
    to ProactorEventLoop. This function switches to SelectorEventLoop if needed.
    """
    if sys.platform == "win32":
        try:
            loop = asyncio.get_running_loop()
            # Check if we're using ProactorEventLoop
            if isinstance(loop, asyncio.ProactorEventLoop):
                logger.warning(
                    "Detected ProactorEventLoop on Windows. psycopg requires SelectorEventLoop. "
                    "This should be fixed at application startup by setting the event loop policy."
                )
        except RuntimeError:
            # No running loop yet - set policy for future loops
            if isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy):
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                logger.info("Set WindowsSelectorEventLoopPolicy for psycopg compatibility")


# ---------------------------------------------------------------------------
# Async factory
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def _async_checkpointer(config) -> AsyncIterator[Checkpointer]:
    """Async context manager that constructs and tears down a checkpointer."""
    if config.type == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        logger.info("Checkpointer: using InMemorySaver (in-process, not persistent)")
        yield InMemorySaver()
        return

    if config.type == "sqlite":
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        except ImportError as exc:
            raise ImportError(SQLITE_INSTALL) from exc

        conn_str = resolve_sqlite_conn_str(config.connection_string or "store.db")
        ensure_sqlite_parent_dir(conn_str)
        async with AsyncSqliteSaver.from_conn_string(conn_str) as saver:
            await saver.setup()
            logger.info("Checkpointer: using AsyncSqliteSaver (%s)", conn_str)
            yield saver
        return

    if config.type == "postgres":
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        except ImportError as exc:
            raise ImportError(POSTGRES_INSTALL) from exc

        if not config.connection_string:
            raise ValueError(POSTGRES_CONN_REQUIRED)

        # Ensure compatible event loop on Windows
        _ensure_compatible_event_loop()

        pool_kwargs = {
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        }
        pool = AsyncConnectionPool(
            config.connection_string,
            min_size=1,
            max_size=5,
            kwargs=pool_kwargs,
        )
        async with pool:
            saver = AsyncPostgresSaver(conn=pool)
            await saver.setup()
            logger.info(
                "Checkpointer: using AsyncPostgresSaver with connection pool (min_size=%s, max_size=%s)",
                1,
                5,
            )
            yield saver
        return

    raise ValueError(f"Unknown checkpointer type: {config.type!r}")


# ---------------------------------------------------------------------------
# Public async context manager
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def make_checkpointer() -> AsyncIterator[Checkpointer]:
    """Async context manager that yields a checkpointer for the caller's lifetime.
    Resources are opened on enter and closed on exit — no global state::

        async with make_checkpointer() as checkpointer:
            app.state.checkpointer = checkpointer

    Yields an ``InMemorySaver`` when no checkpointer is configured in *config.yaml*.
    """

    config = get_app_config()

    if config.checkpointer is None:
        from langgraph.checkpoint.memory import InMemorySaver

        logger.warning("No 'checkpointer' section in config.yaml — using InMemorySaver. Thread state will be lost on server restart. Configure a sqlite or postgres backend for persistence.")
        yield InMemorySaver()
        return

    async with _async_checkpointer(config.checkpointer) as saver:
        yield saver
