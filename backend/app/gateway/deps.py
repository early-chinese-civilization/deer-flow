"""Centralized accessors for singleton objects stored on ``app.state``.

**Getters** (used by routers): raise 503 when a required dependency is
missing, except ``get_store`` which returns ``None``.

Initialization is handled directly in ``app.py`` via :class:`AsyncExitStack`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.auth.keycloak import KeycloakError
from app.gateway.auth.service import sync_user_from_access_token
from app.gateway.db.models import User
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


async def get_db() -> AsyncGenerator[AsyncSession, None]:
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
    kc_access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """获取当前用户（必须登录）

    从 HttpOnly `kc_access_token` 实时校验当前用户。

    这里故意不在依赖层做 refresh 回写，避免在普通业务接口里隐式改写浏览器 cookie。
    懒刷新和 cookie 重写由 `/api/auth/me`、`/api/auth/refresh` 两个显式认证入口负责。

    Args:
        kc_access_token: Access token（来自 cookie）
        db: 数据库会话

    Returns:
        User 对象

    Raises:
        HTTPException: 如果未登录或会话无效
    """
    if not kc_access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        return await sync_user_from_access_token(db=db, access_token=kc_access_token)
    except KeycloakError as exc:
        if exc.status >= 500:
            raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


async def get_current_user_optional(
    kc_access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """获取当前用户（可选，不强制登录）

    如果未登录或会话无效，返回 None 而不是抛出异常。

    Args:
        kc_access_token: Access token（来自 cookie）
        db: 数据库会话

    Returns:
        User 对象或 None
    """
    try:
        return await get_current_user(kc_access_token, db)
    except HTTPException:
        return None
