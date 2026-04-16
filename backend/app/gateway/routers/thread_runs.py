"""Runs endpoints - create, stream, wait, cancel."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
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
from app.gateway.services.ownership import require_thread_access
from app.gateway.services.runtime_state import (
    is_runtime_state_unavailable,
    to_runtime_state_http_exception,
)
from deerflow.runtime import RunRecord, serialize_channel_values

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/threads", tags=["runs"])


class RunCreateRequest(BaseModel):
    assistant_id: str | None = Field(default=None, description="Agent / assistant to use")
    input: dict[str, Any] | None = Field(default=None, description="Graph input (e.g. {messages: [...]})")
    command: dict[str, Any] | None = Field(default=None, description="LangGraph Command")
    metadata: dict[str, Any] | None = Field(default=None, description="Run metadata")
    config: dict[str, Any] | None = Field(default=None, description="RunnableConfig overrides")
    context: dict[str, Any] | None = Field(default=None, description="DeerFlow context overrides (model_name, thinking_enabled, etc.)")
    webhook: str | None = Field(default=None, description="Completion callback URL")
    checkpoint_id: str | None = Field(default=None, description="Resume from checkpoint")
    checkpoint: dict[str, Any] | None = Field(default=None, description="Full checkpoint object")
    interrupt_before: list[str] | Literal["*"] | None = Field(default=None, description="Nodes to interrupt before")
    interrupt_after: list[str] | Literal["*"] | None = Field(default=None, description="Nodes to interrupt after")
    stream_mode: list[str] | str | None = Field(default=None, description="Stream mode(s)")
    stream_subgraphs: bool = Field(default=False, description="Include subgraph events")
    stream_resumable: bool | None = Field(default=None, description="SSE resumable mode")
    on_disconnect: Literal["cancel", "continue"] = Field(default="cancel", description="Behaviour on SSE disconnect")
    on_completion: Literal["delete", "keep"] = Field(default="keep", description="Delete temp thread on completion")
    multitask_strategy: Literal["reject", "rollback", "interrupt", "enqueue"] = Field(default="reject", description="Concurrency strategy")
    after_seconds: float | None = Field(default=None, description="Delayed execution")
    if_not_exists: Literal["reject", "create"] = Field(default="create", description="Thread creation policy")
    feedback_keys: list[str] | None = Field(default=None, description="LangSmith feedback keys")


class RunResponse(BaseModel):
    run_id: str
    thread_id: str
    assistant_id: str | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    multitask_strategy: str = "reject"
    created_at: str = ""
    updated_at: str = ""


def _record_to_response(record: RunRecord) -> RunResponse:
    return RunResponse(
        run_id=record.run_id,
        thread_id=record.thread_id,
        assistant_id=record.assistant_id,
        status=record.status.value,
        metadata=record.metadata,
        kwargs=record.kwargs,
        multitask_strategy=record.multitask_strategy,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _root_checkpoint_config(thread_id: str) -> dict[str, dict[str, str]]:
    """Build the root checkpoint config for a thread."""
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


async def _require_owned_thread(
    *,
    thread_id: str,
    request: Request,
    current_user: User,
    db: AsyncSession,
) -> Any:
    """Load and authorize the DB-backed thread record for this request."""
    return await require_thread_access(
        db=db,
        store=get_store(request),
        thread_id=thread_id,
        current_user=current_user,
    )


@router.post("/{thread_id}/runs", response_model=RunResponse)
async def create_run(
    thread_id: str,
    body: RunCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    """Create a background run (returns immediately)."""
    thread_record = await _require_owned_thread(
        thread_id=thread_id,
        request=request,
        current_user=current_user,
        db=db,
    )

    record = await gateway_services.start_run(
        body,
        thread_id,
        request,
        thread_record=thread_record,
    )
    return _record_to_response(record)


@router.post("/{thread_id}/runs/stream")
async def stream_run(
    thread_id: str,
    body: RunCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Create a run and stream events via SSE."""
    thread_record = await _require_owned_thread(
        thread_id=thread_id,
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
        thread_record=thread_record,
    )

    return StreamingResponse(
        gateway_services.sse_consumer(bridge, record, request, run_mgr),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Location": f"/api/threads/{thread_id}/runs/{record.run_id}/stream",
        },
    )


@router.post("/{thread_id}/runs/wait", response_model=dict)
async def wait_run(
    thread_id: str,
    body: RunCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a run and block until it completes, returning the final state."""
    thread_record = await _require_owned_thread(
        thread_id=thread_id,
        request=request,
        current_user=current_user,
        db=db,
    )
    record = await gateway_services.start_run(
        body,
        thread_id,
        request,
        thread_record=thread_record,
    )

    if record.task is not None:
        try:
            await record.task
        except asyncio.CancelledError:
            pass

    checkpointer = get_checkpointer(request)
    try:
        checkpoint_tuple = await checkpointer.aget_tuple(_root_checkpoint_config(thread_id))
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


@router.get("/{thread_id}/runs", response_model=list[RunResponse])
async def list_runs(
    thread_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RunResponse]:
    """List all runs for a thread."""
    _ = request
    await _require_owned_thread(
        thread_id=thread_id,
        request=request,
        current_user=current_user,
        db=db,
    )
    run_mgr = get_run_manager(request)
    records = await run_mgr.list_by_thread(thread_id)
    return [_record_to_response(record) for record in records]


@router.get("/{thread_id}/runs/{run_id}", response_model=RunResponse)
async def get_run(
    thread_id: str,
    run_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    """Get details of a specific run."""
    await _require_owned_thread(
        thread_id=thread_id,
        request=request,
        current_user=current_user,
        db=db,
    )
    run_mgr = get_run_manager(request)
    record = run_mgr.get(run_id)
    if record is None or record.thread_id != thread_id:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return _record_to_response(record)


@router.post("/{thread_id}/runs/{run_id}/cancel")
async def cancel_run(
    thread_id: str,
    run_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    wait: bool = Query(default=False, description="Block until run completes after cancel"),
    action: Literal["interrupt", "rollback"] = Query(default="interrupt", description="Cancel action"),
) -> Response:
    """Cancel a running or pending run."""
    await _require_owned_thread(
        thread_id=thread_id,
        request=request,
        current_user=current_user,
        db=db,
    )
    run_mgr = get_run_manager(request)
    record = run_mgr.get(run_id)
    if record is None or record.thread_id != thread_id:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    cancelled = await run_mgr.cancel(run_id, action=action)
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id} is not cancellable (status: {record.status.value})",
        )

    if wait and record.task is not None:
        try:
            await record.task
        except asyncio.CancelledError:
            pass
        return Response(status_code=204)

    return Response(status_code=202)


@router.get("/{thread_id}/runs/{run_id}/join")
async def join_run(
    thread_id: str,
    run_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Join an existing run's SSE stream."""
    await _require_owned_thread(
        thread_id=thread_id,
        request=request,
        current_user=current_user,
        db=db,
    )
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    record = run_mgr.get(run_id)
    if record is None or record.thread_id != thread_id:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return StreamingResponse(
        gateway_services.sse_consumer(bridge, record, request, run_mgr),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.api_route("/{thread_id}/runs/{run_id}/stream", methods=["GET", "POST"], response_model=None)
async def stream_existing_run(
    thread_id: str,
    run_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    action: Literal["interrupt", "rollback"] | None = Query(default=None, description="Cancel action"),
    wait: int = Query(default=0, description="Block until cancelled (1) or return immediately (0)"),
):
    """Join an existing run's SSE stream (GET), or cancel-then-stream (POST)."""
    await _require_owned_thread(
        thread_id=thread_id,
        request=request,
        current_user=current_user,
        db=db,
    )
    run_mgr = get_run_manager(request)
    record = run_mgr.get(run_id)
    if record is None or record.thread_id != thread_id:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if action is not None:
        cancelled = await run_mgr.cancel(run_id, action=action)
        if cancelled and wait and record.task is not None:
            try:
                await record.task
            except (asyncio.CancelledError, Exception):
                pass
            return Response(status_code=204)

    bridge = get_stream_bridge(request)
    return StreamingResponse(
        gateway_services.sse_consumer(bridge, record, request, run_mgr),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
