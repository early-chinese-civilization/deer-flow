"""Database engine and session management for Gateway product tables."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.gateway.db.psycopg_compat import ensure_windows_selector_event_loop_policy

ensure_windows_selector_event_loop_policy()

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _normalize_database_url(url: str) -> str:
    """Normalize PostgreSQL URLs to SQLAlchemy's psycopg async dialect."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if not url.startswith("postgresql+psycopg://"):
        return f"postgresql+psycopg://{url}"
    return url


def get_database_url() -> str:
    """Return the configured database URL in psycopg async format."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is required")

    return _normalize_database_url(url)


def get_engine() -> AsyncEngine:
    """Return the shared async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_database_url(),
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
