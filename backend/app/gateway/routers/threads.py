"""Thread CRUD, state, and history endpoints backed by Store + checkpointer."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import User
from app.gateway.db.repository import WorkspaceRepository
from app.gateway.deps import get_checkpointer, get_current_user, get_db, get_store
from app.gateway.services.ownership import require_thread_access
from app.gateway.services.runtime_state import (
    is_runtime_state_unavailable,
    to_runtime_state_http_exception,
)
from app.gateway.services.thread_store import (
    StoreUnavailableError,
    ThreadRecord,
    coerce_owner_user_id,
    delete_thread_record,
    get_thread_record,
    get_workspace_id,
    put_thread_record,
    search_thread_records,
    upsert_thread_record,
)
from deerflow.config.paths import Paths, get_paths
from deerflow.runtime import serialize_channel_values

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/threads", tags=["threads"])


class ThreadDeleteResponse(BaseModel):
    """Response model for thread cleanup."""

    success: bool
    message: str


class ThreadResponse(BaseModel):
    """Response model for a single thread."""

    thread_id: str = Field(description="Unique thread identifier")
    workspace_id: str | None = Field(default=None, description="Bound workspace ID")
    status: str = Field(default="idle", description="Thread status: idle, busy, interrupted, error")
    created_at: str = Field(default="", description="ISO timestamp")
    updated_at: str = Field(default="", description="ISO timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Thread metadata")
    values: dict[str, Any] = Field(default_factory=dict, description="Current state channel values")
    interrupts: dict[str, Any] = Field(default_factory=dict, description="Pending interrupts")


class ThreadCreateRequest(BaseModel):
    """Request body for creating a thread."""

    thread_id: str | None = Field(default=None, description="Optional thread ID (auto-generated if omitted)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Initial metadata")


class ThreadSearchRequest(BaseModel):
    """Request body for searching threads."""

    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata filter (exact match)")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    status: str | None = Field(default=None, description="Filter by thread status")


class ThreadStateResponse(BaseModel):
    """Response model for thread state."""

    values: dict[str, Any] = Field(default_factory=dict, description="Current channel values")
    next: list[str] = Field(default_factory=list, description="Next tasks to execute")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Checkpoint metadata")
    checkpoint: dict[str, Any] = Field(default_factory=dict, description="Checkpoint info")
    checkpoint_id: str | None = Field(default=None, description="Current checkpoint ID")
    parent_checkpoint_id: str | None = Field(default=None, description="Parent checkpoint ID")
    created_at: str | None = Field(default=None, description="Checkpoint timestamp")
    tasks: list[dict[str, Any]] = Field(default_factory=list, description="Interrupted task details")


class ThreadPatchRequest(BaseModel):
    """Request body for patching thread metadata."""

    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata to merge")


class ThreadStateUpdateRequest(BaseModel):
    """Request body for updating thread state."""

    values: dict[str, Any] | None = Field(default=None, description="Channel values to merge")
    checkpoint_id: str | None = Field(default=None, description="Checkpoint to branch from")
    checkpoint: dict[str, Any] | None = Field(default=None, description="Full checkpoint object")
    as_node: str | None = Field(default=None, description="Node identity for the update")


class HistoryEntry(BaseModel):
    """Single checkpoint history entry."""

    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    next: list[str] = Field(default_factory=list)


class ThreadHistoryRequest(BaseModel):
    """Request body for checkpoint history."""

    limit: int = Field(default=10, ge=1, le=100, description="Maximum entries")
    before: str | None = Field(default=None, description="Cursor for pagination")


def _delete_thread_data(thread_id: str, paths: Paths | None = None) -> ThreadDeleteResponse:
    """Delete local persisted filesystem data for a thread."""
    path_manager = paths or get_paths()
    try:
        path_manager.delete_thread_dir(thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError:
        logger.debug("No local thread data to delete for %s", thread_id)
        return ThreadDeleteResponse(success=True, message=f"No local data for {thread_id}")
    except Exception as exc:
        logger.exception("Failed to delete thread data for %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to delete local thread data.") from exc

    logger.info("Deleted local thread data for %s", thread_id)
    return ThreadDeleteResponse(success=True, message=f"Deleted local thread data for {thread_id}")


def _stringify_timestamp(value: Any) -> str:
    """Serialize Store timestamps for API responses."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _timestamp_sort_key(value: Any) -> float:
    """Normalize Store timestamps so thread lists sort consistently."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return 0.0
    return 0.0


def _root_checkpoint_config(
    thread_id: str,
    *,
    checkpoint_id: str | None = None,
) -> dict[str, dict[str, str]]:
    """Build the root checkpoint config for a thread."""
    configurable: dict[str, str] = {
        "thread_id": thread_id,
        "checkpoint_ns": "",
    }
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


def _build_thread_response(
    record: ThreadRecord,
    *,
    values: dict[str, Any] | None = None,
    status: str | None = None,
) -> ThreadResponse:
    """Build a response model from a Store-backed thread record."""
    return ThreadResponse(
        thread_id=record["thread_id"],
        workspace_id=get_workspace_id(record),
        status=status or str(record.get("status", "idle")),
        created_at=_stringify_timestamp(record.get("created_at")),
        updated_at=_stringify_timestamp(record.get("updated_at")),
        metadata=dict(record.get("metadata") or {}),
        values=values if values is not None else dict(record.get("values") or {}),
    )


def _derive_thread_status(checkpoint_tuple: Any, default_status: str = "idle") -> str:
    """Derive thread status from checkpoint metadata when available."""
    if checkpoint_tuple is None:
        return default_status

    pending_writes = getattr(checkpoint_tuple, "pending_writes", None) or []
    for pending_write in pending_writes:
        if len(pending_write) >= 2 and pending_write[1] == "__error__":
            return "error"

    tasks = getattr(checkpoint_tuple, "tasks", None)
    if tasks:
        return "interrupted"
    return default_status


async def _cleanup_failed_thread_creation(
    *,
    store,
    checkpointer,
    thread_id: str,
    rollback_db: Callable[[], Awaitable[None]],
    delete_checkpoint: bool,
    delete_store_record_on_failure: bool,
) -> None:
    """Rollback partially-created thread resources after creation fails."""
    try:
        await rollback_db()
    except Exception:
        logger.warning("Failed to rollback workspace creation for thread %s", thread_id, exc_info=True)

    if delete_store_record_on_failure and store is not None:
        try:
            await delete_thread_record(store, thread_id)
        except Exception:
            logger.warning("Failed to remove store record for thread %s", thread_id, exc_info=True)

    if delete_checkpoint and hasattr(checkpointer, "adelete_thread"):
        try:
            await checkpointer.adelete_thread(thread_id)
        except Exception:
            logger.warning("Failed to remove checkpoint thread %s after create failure", thread_id, exc_info=True)


@router.delete("/{thread_id}", response_model=ThreadDeleteResponse)
async def delete_thread_data(
    thread_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadDeleteResponse:
    """Delete local filesystem data, Store metadata, bound workspace, and checkpoints."""
    store = get_store(request)
    thread_record = await require_thread_access(
        store=store,
        thread_id=thread_id,
        current_user=current_user,
    )

    response = _delete_thread_data(thread_id)

    workspace_id = get_workspace_id(thread_record)
    if workspace_id is not None:
        try:
            await WorkspaceRepository.delete_workspace(db, workspace_id)
        except Exception as exc:
            logger.exception("Failed to delete workspace %s for thread %s", workspace_id, thread_id)
            raise HTTPException(status_code=500, detail="Failed to delete workspace") from exc

    if store is not None:
        try:
            await delete_thread_record(store, thread_id)
        except Exception:
            logger.debug("Could not delete store record for thread %s (not critical)", thread_id)

    checkpointer = getattr(request.app.state, "checkpointer", None)
    if checkpointer is not None and hasattr(checkpointer, "adelete_thread"):
        try:
            await checkpointer.adelete_thread(thread_id)
        except Exception:
            logger.debug("Could not delete checkpoints for thread %s (not critical)", thread_id)

    return response


@router.post("", response_model=ThreadResponse)
async def create_thread(
    body: ThreadCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadResponse:
    """Create a new authenticated thread backed by Store metadata."""
    store = get_store(request)
    if store is None:
        raise HTTPException(status_code=503, detail="Thread metadata store unavailable")

    checkpointer = get_checkpointer(request)
    thread_id = body.thread_id or str(uuid.uuid4())
    now = time.time()
    config = _root_checkpoint_config(thread_id)

    try:
        existing_record = await get_thread_record(store, thread_id)
    except StoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Thread metadata store unavailable") from exc

    try:
        existing_checkpoint = await checkpointer.aget_tuple(config)
    except Exception as exc:
        if is_runtime_state_unavailable(exc):
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to check existing checkpoint for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to create thread") from exc

    if existing_record is not None:
        owner_user_id = coerce_owner_user_id(existing_record)
        if owner_user_id is None:
            raise HTTPException(status_code=403, detail="Thread is missing an owner")
        if owner_user_id != current_user.id:
            raise HTTPException(status_code=403, detail=f"Thread belongs to user {owner_user_id}")
        if existing_checkpoint is None:
            raise HTTPException(
                status_code=409,
                detail="Thread exists in thread metadata but is missing runtime state",
            )
        return _build_thread_response(existing_record)

    if existing_checkpoint is not None:
        raise HTTPException(
            status_code=409,
            detail="Thread exists in runtime state but is missing thread metadata",
        )

    workspace = await WorkspaceRepository.create_workspace(
        db=db,
        owner_user_id=current_user.id,
        name=None,
        commit=False,
    )
    created_record: ThreadRecord = {
        "thread_id": thread_id,
        "owner_user_id": current_user.id,
        "workspace_id": str(workspace.id),
        "status": "idle",
        "created_at": now,
        "updated_at": now,
        "metadata": dict(body.metadata),
        "values": {},
    }
    checkpoint_created = False
    store_record_written = False

    try:
        from langgraph.checkpoint.base import empty_checkpoint

        checkpoint_metadata = {
            "step": -1,
            "source": "input",
            "writes": None,
            "parents": {},
            **body.metadata,
            "created_at": now,
        }
        await checkpointer.aput(config, empty_checkpoint(), checkpoint_metadata, {})
        checkpoint_created = True

        await put_thread_record(store, created_record)
        store_record_written = True

        await db.commit()
    except Exception as exc:
        await _cleanup_failed_thread_creation(
            store=store,
            checkpointer=checkpointer,
            thread_id=thread_id,
            rollback_db=db.rollback,
            delete_checkpoint=checkpoint_created,
            delete_store_record_on_failure=store_record_written,
        )
        if isinstance(exc, StoreUnavailableError):
            raise HTTPException(status_code=503, detail="Thread metadata store unavailable") from exc
        if is_runtime_state_unavailable(exc):
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to create thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to create thread") from exc

    logger.info("Thread created: %s", thread_id)
    return _build_thread_response(created_record)


@router.post("/search", response_model=list[ThreadResponse])
async def search_threads(
    body: ThreadSearchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> list[ThreadResponse]:
    """Search thread metadata from Store for the authenticated user."""
    store = get_store(request)
    if store is None:
        raise HTTPException(status_code=503, detail="Thread metadata store unavailable")

    try:
        items = await search_thread_records(store, limit=10_000)
    except StoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Thread metadata store unavailable") from exc

    matching_records: list[ThreadRecord] = []
    for item in items:
        value = getattr(item, "value", None)
        if not isinstance(value, dict) or not value.get("thread_id"):
            continue
        if coerce_owner_user_id(value) != current_user.id:
            continue
        if body.status and value.get("status") != body.status:
            continue
        metadata = value.get("metadata") or {}
        if any(metadata.get(key) != expected for key, expected in body.metadata.items()):
            continue
        matching_records.append(value)

    matching_records.sort(
        key=lambda record: _timestamp_sort_key(record.get("updated_at") or record.get("created_at")),
        reverse=True,
    )
    paged_records = matching_records[body.offset : body.offset + body.limit]
    return [_build_thread_response(record) for record in paged_records]


@router.patch("/{thread_id}", response_model=ThreadResponse)
async def patch_thread(
    thread_id: str,
    body: ThreadPatchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> ThreadResponse:
    """Merge metadata into a Store-backed thread record."""
    store = get_store(request)
    thread_record = await require_thread_access(
        store=store,
        thread_id=thread_id,
        current_user=current_user,
    )

    try:
        updated_record = await upsert_thread_record(
            store,
            thread_id,
            metadata=body.metadata,
        )
    except StoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Thread metadata store unavailable") from exc
    except Exception as exc:
        logger.exception("Failed to patch thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to update thread") from exc

    if not updated_record.get("workspace_id"):
        updated_record["workspace_id"] = get_workspace_id(thread_record)
    return _build_thread_response(updated_record)


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> ThreadResponse:
    """Get thread metadata from Store and runtime state from the checkpointer."""
    store = get_store(request)
    thread_record = await require_thread_access(
        store=store,
        thread_id=thread_id,
        current_user=current_user,
    )
    checkpointer = get_checkpointer(request)

    try:
        checkpoint_tuple = await checkpointer.aget_tuple(
            _root_checkpoint_config(thread_id)
        )
    except Exception as exc:
        if is_runtime_state_unavailable(exc):
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to get checkpoint for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread") from exc

    if checkpoint_tuple is None:
        return _build_thread_response(thread_record)

    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    channel_values = serialize_channel_values(checkpoint.get("channel_values", {}))
    title = (thread_record.get("values") or {}).get("title")
    if title and "title" not in channel_values:
        channel_values["title"] = title

    return _build_thread_response(
        thread_record,
        values=channel_values,
        status=_derive_thread_status(checkpoint_tuple, default_status=str(thread_record.get("status", "idle"))),
    )


@router.get("/{thread_id}/state", response_model=ThreadStateResponse)
async def get_thread_state(
    thread_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> ThreadStateResponse:
    """Get the latest runtime state snapshot for a thread."""
    await require_thread_access(
        store=get_store(request),
        thread_id=thread_id,
        current_user=current_user,
    )
    checkpointer = get_checkpointer(request)

    try:
        checkpoint_tuple = await checkpointer.aget_tuple(
            _root_checkpoint_config(thread_id)
        )
    except Exception as exc:
        if is_runtime_state_unavailable(exc):
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to get state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread state") from exc

    if checkpoint_tuple is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    metadata = getattr(checkpoint_tuple, "metadata", {}) or {}
    checkpoint_id = getattr(checkpoint_tuple, "config", {}).get("configurable", {}).get("checkpoint_id")
    parent_checkpoint_id = None
    parent_config = getattr(checkpoint_tuple, "parent_config", None)
    if parent_config:
        parent_checkpoint_id = parent_config.get("configurable", {}).get("checkpoint_id")

    tasks_raw = getattr(checkpoint_tuple, "tasks", []) or []
    next_tasks = [task.name for task in tasks_raw if hasattr(task, "name")]
    tasks = [{"id": getattr(task, "id", ""), "name": getattr(task, "name", "")} for task in tasks_raw]

    return ThreadStateResponse(
        values=serialize_channel_values(checkpoint.get("channel_values", {})),
        next=next_tasks,
        metadata=metadata,
        checkpoint={"id": checkpoint_id, "ts": str(metadata.get("created_at", ""))},
        checkpoint_id=checkpoint_id,
        parent_checkpoint_id=parent_checkpoint_id,
        created_at=str(metadata.get("created_at", "")),
        tasks=tasks,
    )


@router.post("/{thread_id}/state", response_model=ThreadStateResponse)
async def update_thread_state(
    thread_id: str,
    body: ThreadStateUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> ThreadStateResponse:
    """Write a new checkpoint and best-effort mirror title changes into Store."""
    store = get_store(request)
    await require_thread_access(
        store=store,
        thread_id=thread_id,
        current_user=current_user,
    )
    checkpointer = get_checkpointer(request)

    read_config = _root_checkpoint_config(
        thread_id,
        checkpoint_id=body.checkpoint_id,
    )

    try:
        checkpoint_tuple = await checkpointer.aget_tuple(read_config)
    except Exception as exc:
        if is_runtime_state_unavailable(exc):
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to get state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread state") from exc

    if checkpoint_tuple is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    checkpoint: dict[str, Any] = dict(getattr(checkpoint_tuple, "checkpoint", {}) or {})
    metadata: dict[str, Any] = dict(getattr(checkpoint_tuple, "metadata", {}) or {})
    channel_values: dict[str, Any] = dict(checkpoint.get("channel_values", {}))

    if body.values:
        channel_values.update(body.values)

    checkpoint["channel_values"] = channel_values
    metadata["updated_at"] = time.time()

    if body.as_node:
        metadata["source"] = "update"
        metadata["step"] = metadata.get("step", 0) + 1
        metadata["writes"] = {body.as_node: body.values}

    try:
        new_config = await checkpointer.aput(
            _root_checkpoint_config(thread_id),
            checkpoint,
            metadata,
            {},
        )
    except Exception as exc:
        if is_runtime_state_unavailable(exc):
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to update state for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to update thread state") from exc

    if store is not None:
        try:
            values = {"title": body.values["title"]} if body.values and "title" in body.values else None
            await upsert_thread_record(store, thread_id, values=values)
        except Exception:
            logger.debug("Failed to sync store metadata for thread %s after state update", thread_id, exc_info=True)

    checkpoint_id = None
    if isinstance(new_config, dict):
        checkpoint_id = new_config.get("configurable", {}).get("checkpoint_id")

    return ThreadStateResponse(
        values=serialize_channel_values(channel_values),
        next=[],
        metadata=metadata,
        checkpoint_id=checkpoint_id,
        created_at=str(metadata.get("created_at", "")),
    )


@router.post("/{thread_id}/history", response_model=list[HistoryEntry])
async def get_thread_history(
    thread_id: str,
    body: ThreadHistoryRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> list[HistoryEntry]:
    """Get checkpoint history for an owned thread."""
    await require_thread_access(
        store=get_store(request),
        thread_id=thread_id,
        current_user=current_user,
    )
    checkpointer = get_checkpointer(request)

    config = _root_checkpoint_config(
        thread_id,
        checkpoint_id=body.before,
    )

    entries: list[HistoryEntry] = []
    try:
        async for checkpoint_tuple in checkpointer.alist(config, limit=body.limit):
            checkpoint_config = getattr(checkpoint_tuple, "config", {})
            parent_config = getattr(checkpoint_tuple, "parent_config", None)
            metadata = getattr(checkpoint_tuple, "metadata", {}) or {}
            checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}

            checkpoint_id = checkpoint_config.get("configurable", {}).get("checkpoint_id", "")
            parent_checkpoint_id = None
            if parent_config:
                parent_checkpoint_id = parent_config.get("configurable", {}).get("checkpoint_id")

            tasks_raw = getattr(checkpoint_tuple, "tasks", []) or []
            next_tasks = [task.name for task in tasks_raw if hasattr(task, "name")]

            entries.append(
                HistoryEntry(
                    checkpoint_id=checkpoint_id,
                    parent_checkpoint_id=parent_checkpoint_id,
                    metadata=metadata,
                    values=serialize_channel_values(checkpoint.get("channel_values", {})),
                    created_at=str(metadata.get("created_at", "")),
                    next=next_tasks,
                )
            )
    except Exception as exc:
        if is_runtime_state_unavailable(exc):
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to get history for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread history") from exc

    return entries
