"""Stateless runs endpoints -- stream and wait without a pre-existing thread.

These endpoints auto-create a temporary thread when no ``thread_id`` is
supplied in the request body.  When a ``thread_id`` **is** provided, it
is reused so that conversation history is preserved across calls.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

import app.gateway.services as gateway_services
from app.gateway.db.engine import get_db_session
from app.gateway.db.models import User
from app.gateway.db.repository import ThreadRepository, WorkspaceRepository
from app.gateway.deps import (
    get_checkpointer,
    get_current_user,
    get_db,
    get_run_manager,
    get_store,
    get_stream_bridge,
)
from app.gateway.routers import threads as threads_router
from app.gateway.routers.thread_runs import RunCreateRequest
from app.gateway.services.ownership import require_thread_access
from app.gateway.services.runtime_state import (
    is_runtime_state_unavailable,
    to_runtime_state_http_exception,
)
from app.gateway.services.thread_store import delete_thread_record
from deerflow.runtime import serialize_channel_values

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/runs", tags=["runs"])


@dataclass(frozen=True)
class _OwnedThreadResolution:
    thread_id: str
    access_record: object
    temporary: bool
    workspace_id: object | None = None


def _resolve_thread_id(body: RunCreateRequest) -> str:
    """Return the thread_id from the request body, or generate a new one."""
    thread_id = (body.config or {}).get("configurable", {}).get("thread_id")
    if thread_id:
        return str(thread_id)
    return str(uuid.uuid4())


async def _resolve_owned_thread_id(
    *,
    body: RunCreateRequest,
    request: Request,
    current_user: User,
    db: AsyncSession,
) -> _OwnedThreadResolution:
    """Return an owned thread binding, creating one when the stateless call has none."""
    thread_id = _resolve_thread_id(body)
    requested_thread_id = (body.config or {}).get("configurable", {}).get("thread_id")

    if requested_thread_id:
        access_record = await require_thread_access(
            db=db,
            store=get_store(request),
            thread_id=thread_id,
            current_user=current_user,
        )
        return _OwnedThreadResolution(
            thread_id=thread_id,
            access_record=access_record,
            temporary=False,
            workspace_id=getattr(access_record.thread, "workspace_id", None),
        )

    await threads_router.create_thread(
        threads_router.ThreadCreateRequest(
            thread_id=thread_id,
            metadata=body.metadata or {},
        ),
        request=request,
        current_user=current_user,
        db=db,
    )
    access_record = await require_thread_access(
        db=db,
        store=get_store(request),
        thread_id=thread_id,
        current_user=current_user,
    )
    return _OwnedThreadResolution(
        thread_id=thread_id,
        access_record=access_record,
        temporary=True,
        workspace_id=getattr(access_record.thread, "workspace_id", None),
    )


def _should_delete_temporary_thread(body: RunCreateRequest, resolution: _OwnedThreadResolution) -> bool:
    return resolution.temporary and body.on_completion == "delete"


async def _delete_temporary_thread_resources(
    *,
    thread_id: str,
    workspace_id: object | None,
    request: Request,
) -> None:
    """Best-effort cleanup for auto-created stateless run threads."""
    try:
        threads_router._delete_thread_data(thread_id)
    except HTTPException as exc:
        if exc.status_code not in {404, 422}:
            logger.warning("Failed to delete local temp thread data for %s", thread_id, exc_info=True)
    except Exception:
        logger.warning("Failed to delete local temp thread data for %s", thread_id, exc_info=True)

    store = get_store(request)
    if store is not None:
        try:
            await delete_thread_record(store, thread_id)
        except Exception:
            logger.warning("Failed to delete temp thread store record for %s", thread_id, exc_info=True)

    checkpointer = get_checkpointer(request)
    if hasattr(checkpointer, "adelete_thread"):
        try:
            await checkpointer.adelete_thread(thread_id)
        except Exception:
            logger.warning("Failed to delete temp thread checkpoints for %s", thread_id, exc_info=True)

    try:
        async with get_db_session() as db:
            await ThreadRepository.delete_thread(db=db, thread_id=thread_id, commit=False)
            if workspace_id is not None:
                await WorkspaceRepository.delete_workspace(
                    db=db,
                    workspace_id=workspace_id,
                    commit=False,
                )
            await db.commit()
    except Exception:
        logger.warning("Failed to delete temp thread DB records for %s", thread_id, exc_info=True)


async def _cleanup_temporary_thread_after_run(
    *,
    record,
    thread_id: str,
    workspace_id: object | None,
    request: Request,
) -> None:
    if record.task is not None:
        try:
            await record.task
        except asyncio.CancelledError:
            pass
        except Exception:
            # The run result has already been published; cleanup still applies.
            pass

    await _delete_temporary_thread_resources(
        thread_id=thread_id,
        workspace_id=workspace_id,
        request=request,
    )


@router.post("/stream")
async def stateless_stream(
    body: RunCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Create a run and stream events via SSE.

    If ``config.configurable.thread_id`` is provided, the run is created
    on the given thread so that conversation history is preserved.
    Otherwise a new temporary thread is created.
    """
    resolution = await _resolve_owned_thread_id(
        body=body,
        request=request,
        current_user=current_user,
        db=db,
    )
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    record = await gateway_services.start_run(
        body,
        resolution.thread_id,
        request,
        current_user=current_user,
        thread_record=resolution.access_record,
    )

    return StreamingResponse(
        gateway_services.sse_consumer(bridge, record, request, run_mgr),
        media_type="text/event-stream",
        background=(
            BackgroundTask(
                _cleanup_temporary_thread_after_run,
                record=record,
                thread_id=resolution.thread_id,
                workspace_id=resolution.workspace_id,
                request=request,
            )
            if _should_delete_temporary_thread(body, resolution)
            else None
        ),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/wait", response_model=dict)
async def stateless_wait(
    body: RunCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a run and block until completion.

    If ``config.configurable.thread_id`` is provided, the run is created
    on the given thread so that conversation history is preserved.
    Otherwise a new temporary thread is created.
    """
    resolution = await _resolve_owned_thread_id(
        body=body,
        request=request,
        current_user=current_user,
        db=db,
    )
    record = await gateway_services.start_run(
        body,
        resolution.thread_id,
        request,
        current_user=current_user,
        thread_record=resolution.access_record,
    )

    if record.task is not None:
        try:
            await record.task
        except asyncio.CancelledError:
            pass

    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": resolution.thread_id}}
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        if checkpoint_tuple is not None:
            checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
            channel_values = checkpoint.get("channel_values", {})
            result = serialize_channel_values(channel_values)
        else:
            result = {"status": record.status.value, "error": record.error}
    except Exception as exc:
        if is_runtime_state_unavailable(exc):
            logger.warning(
                "Runtime state backend unavailable while fetching final state for run %s",
                record.run_id,
            )
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to fetch final state for run %s", record.run_id)
        raise HTTPException(status_code=500, detail="Failed to fetch final run state") from exc

    if _should_delete_temporary_thread(body, resolution):
        await _delete_temporary_thread_resources(
            thread_id=resolution.thread_id,
            workspace_id=resolution.workspace_id,
            request=request,
        )

    return result
