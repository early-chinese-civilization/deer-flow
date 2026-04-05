"""Gateway dependency providers and runtime accessors."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.auth.keycloak import KeycloakError
from app.gateway.auth.service import sync_user_from_access_token
from app.gateway.db.models import User
from deerflow.runtime import RunManager, StreamBridge


@asynccontextmanager
async def langgraph_runtime(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize and tear down shared LangGraph runtime objects."""
    from deerflow.agents.checkpointer.async_provider import make_checkpointer
    from deerflow.runtime import make_store, make_stream_bridge

    async with AsyncExitStack() as stack:
        app.state.stream_bridge = await stack.enter_async_context(make_stream_bridge())
        app.state.checkpointer = await stack.enter_async_context(make_checkpointer())
        app.state.store = await stack.enter_async_context(make_store())
        app.state.run_manager = RunManager()
        yield


def get_stream_bridge(request: Request) -> StreamBridge:
    """Return the global stream bridge or raise 503."""
    bridge = getattr(request.app.state, "stream_bridge", None)
    if bridge is None:
        raise HTTPException(status_code=503, detail="Stream bridge not available")
    return bridge


def get_run_manager(request: Request) -> RunManager:
    """Return the global run manager or raise 503."""
    run_manager = getattr(request.app.state, "run_manager", None)
    if run_manager is None:
        raise HTTPException(status_code=503, detail="Run manager not available")
    return run_manager


def get_checkpointer(request: Request) -> Any:
    """Return the global checkpointer or raise 503."""
    checkpointer = getattr(request.app.state, "checkpointer", None)
    if checkpointer is None:
        raise HTTPException(status_code=503, detail="Checkpointer not available")
    return checkpointer


def get_store(request: Request) -> Any:
    """Return the global store, which may be unavailable in some modes."""
    return getattr(request.app.state, "store", None)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for request-scoped dependencies."""
    from app.gateway.db.engine import get_db_session

    async with get_db_session() as session:
        yield session


def _map_keycloak_error(exc: KeycloakError) -> HTTPException:
    """Convert upstream auth failures into API-facing HTTP errors."""
    if exc.status >= 500:
        return HTTPException(status_code=503, detail="Authentication service unavailable")
    return HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user(
    kc_access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the current user from the access-token cookie.

    This dependency intentionally does not refresh tokens or rewrite cookies.
    Refresh flows stay in explicit auth endpoints such as ``/api/auth/me`` and
    ``/api/auth/refresh`` so regular business endpoints remain side-effect free.
    """
    if not kc_access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        return await sync_user_from_access_token(db=db, access_token=kc_access_token)
    except KeycloakError as exc:
        raise _map_keycloak_error(exc) from exc


async def get_current_user_optional(
    kc_access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Resolve the current user, returning ``None`` when unauthenticated."""
    try:
        return await get_current_user(kc_access_token, db)
    except HTTPException:
        return None


async def get_db_optional() -> AsyncGenerator[AsyncSession | None, None]:
    """Yield a database session when available, otherwise ``None``.

    This is used for backward-compatible endpoints where we prefer degraded
    behavior over failing the whole request when the database is unavailable.
    """
    from app.gateway.db.engine import get_db_session

    session_context = get_db_session()
    try:
        session = await session_context.__aenter__()
    except Exception:
        yield None
        return

    try:
        yield session
    except BaseException as exc:
        await session_context.__aexit__(type(exc), exc, exc.__traceback__)
        raise
    else:
        await session_context.__aexit__(None, None, None)


async def get_current_user_optional_no_db(
    kc_access_token: str | None = Cookie(default=None),
    db: AsyncSession | None = Depends(get_db_optional),
) -> User | None:
    """Resolve the current user when both auth and DB are optional."""
    if db is None or not kc_access_token:
        return None

    try:
        return await get_current_user(kc_access_token, db)
    except HTTPException:
        return None
