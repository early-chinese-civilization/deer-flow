"""Centralized accessors for singleton objects stored on ``app.state``.

**Getters** (used by routers): raise 503 when a required dependency is
missing, except ``get_store`` which returns ``None``.

Initialization is handled directly in ``app.py`` via :class:`AsyncExitStack`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from deerflow.runtime import RunManager, StreamBridge


@asynccontextmanager
async def langgraph_runtime(app: FastAPI) -> AsyncGenerator[None, None]:
    """Bootstrap and tear down all LangGraph runtime singletons.

    Usage in ``app.py``::

        async with langgraph_runtime(app):
            yield
    """
    from deerflow.agents.checkpointer.async_provider import make_checkpointer
    from deerflow.runtime import make_store, make_stream_bridge

    async with AsyncExitStack() as stack:
        app.state.stream_bridge = await stack.enter_async_context(make_stream_bridge())
        app.state.checkpointer = await stack.enter_async_context(make_checkpointer())
        app.state.store = await stack.enter_async_context(make_store())
        app.state.run_manager = RunManager()
        yield


# ---------------------------------------------------------------------------
# Getters – called by routers per-request
# ---------------------------------------------------------------------------


def get_stream_bridge(request: Request) -> StreamBridge:
    """Return the global :class:`StreamBridge`, or 503."""
    bridge = getattr(request.app.state, "stream_bridge", None)
    if bridge is None:
        raise HTTPException(status_code=503, detail="Stream bridge not available")
    return bridge


def get_run_manager(request: Request) -> RunManager:
    """Return the global :class:`RunManager`, or 503."""
    mgr = getattr(request.app.state, "run_manager", None)
    if mgr is None:
        raise HTTPException(status_code=503, detail="Run manager not available")
    return mgr


def get_checkpointer(request: Request):
    """Return the global checkpointer, or 503."""
    cp = getattr(request.app.state, "checkpointer", None)
    if cp is None:
        raise HTTPException(status_code=503, detail="Checkpointer not available")
    return cp


def get_store(request: Request):
    """Return the global store (may be ``None`` if not configured)."""
    return getattr(request.app.state, "store", None)


# ---------------------------------------------------------------------------
# 数据库和认证依赖
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator:
    """获取数据库会话（依赖注入）

    使用示例:
        @router.get("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    from app.gateway.db.engine import get_db_session

    async with get_db_session() as session:
        yield session


async def get_current_user(
    deer_session: str | None = None,
    db = None,
):
    """获取当前用户（必须登录）

    从 cookie 中读取 session_id，查询数据库获取用户信息。

    Args:
        deer_session: 会话ID（来自 cookie）
        db: 数据库会话

    Returns:
        User 对象

    Raises:
        HTTPException: 如果未登录或会话无效
    """
    from datetime import datetime, timezone
    from fastapi import Cookie, Depends
    from sqlalchemy import select

    from app.gateway.auth.session import SessionManager
    from app.gateway.db.models import User

    # 注意：这个函数需要在路由中使用 Depends 时自动注入参数
    # 实际使用时应该这样：
    # async def get_current_user(
    #     deer_session: str | None = Cookie(default=None),
    #     db: AsyncSession = Depends(get_db),
    # ) -> User:

    if not deer_session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # 获取会话
    session = await SessionManager.get_session(db, deer_session)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    # 检查过期
    if session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    # 获取用户
    stmt = select(User).where(User.id == session.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def get_current_user_optional(
    deer_session: str | None = None,
    db = None,
):
    """获取当前用户（可选，不强制登录）

    如果未登录或会话无效，返回 None 而不是抛出异常。

    Args:
        deer_session: 会话ID（来自 cookie）
        db: 数据库会话

    Returns:
        User 对象或 None
    """
    try:
        return await get_current_user(deer_session, db)
    except HTTPException:
        return None
