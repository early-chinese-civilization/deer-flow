"""数据库引擎和会话管理。"""

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

# 全局引擎和会话工厂
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _normalize_database_url(url: str) -> str:
    """把同步风格的 PostgreSQL URL 标准化成 asyncpg 形式。"""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if not url.startswith("postgresql+asyncpg://"):
        return f"postgresql+asyncpg://{url}"
    return url


def get_database_url() -> str:
    """从环境变量获取数据库 URL

    Returns:
        数据库连接 URL (asyncpg 格式)

    Raises:
        ValueError: 如果 DATABASE_URL 环境变量未设置
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is required")

    return _normalize_database_url(url)


def get_engine() -> AsyncEngine:
    """获取全局数据库引擎（单例模式）

    Returns:
        AsyncEngine 实例
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_database_url(),
            pool_size=10,  # 连接池大小
            max_overflow=20,  # 最大溢出连接数
            pool_pre_ping=True,  # 连接前检查可用性
            echo=False,  # 不打印 SQL 日志
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取会话工厂（单例模式）

    Returns:
        async_sessionmaker 实例
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,  # 提交后不过期对象
        )
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（用于依赖注入）

    使用示例:
        async with get_db_session() as session:
            result = await session.execute(select(User))

    Yields:
        AsyncSession 实例
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
