"""Stateless runs endpoints -- stream and wait without a pre-existing thread.

These endpoints auto-create a temporary thread when no ``thread_id`` is
supplied in the request body.  When a ``thread_id`` **is** provided, it
is reused so that conversation history is preserved across calls.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

import app.gateway.services as gateway_services
from app.gateway.db.models import User
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
from deerflow.runtime import serialize_channel_values

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/runs", tags=["runs"])


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
) -> tuple[str, object]:
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
        return thread_id, access_record

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
    return thread_id, access_record


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
    thread_id, access_record = await _resolve_owned_thread_id(
        body=body,
        request=request,
        current_user=current_user,
        db=db,
    )
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    record = await gateway_services.start_run(
        body,
        thread_id,
        request,
        thread_record=access_record,
    )

    return StreamingResponse(
        gateway_services.sse_consumer(bridge, record, request, run_mgr),
        media_type="text/event-stream",
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
    thread_id, access_record = await _resolve_owned_thread_id(
        body=body,
        request=request,
        current_user=current_user,
        db=db,
    )
    record = await gateway_services.start_run(
        body,
        thread_id,
        request,
        thread_record=access_record,
    )

    if record.task is not None:
        try:
            await record.task
        except asyncio.CancelledError:
            pass

    checkpointer = get_checkpointer(request)
    config = {"configurable": {"thread_id": thread_id}}
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        if checkpoint_tuple is not None:
            checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
            channel_values = checkpoint.get("channel_values", {})
            return serialize_channel_values(channel_values)
    except Exception as exc:
        if is_runtime_state_unavailable(exc):
            logger.warning(
                "Runtime state backend unavailable while fetching final state for run %s",
                record.run_id,
            )
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to fetch final state for run %s", record.run_id)
        raise HTTPException(status_code=500, detail="Failed to fetch final run state") from exc

    return {"status": record.status.value, "error": record.error}
