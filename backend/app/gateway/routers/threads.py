"""Thread CRUD, state, and history endpoints backed by DB bindings + Store metadata."""

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
from app.gateway.db.repository import ThreadRepository, WorkspaceRepository
from app.gateway.deps import get_checkpointer, get_current_user, get_db, get_store
from app.gateway.services.ownership import require_thread_access
from app.gateway.services.runtime_state import (
    is_runtime_state_unavailable,
    to_runtime_state_http_exception,
)
from app.gateway.services.thread_store import (
    StoreUnavailableError,
    ThreadRecord,
    delete_thread_record,
    get_thread_record,
    put_thread_record,
    upsert_thread_record,
)
from deerflow.config.paths import Paths, get_paths
from deerflow.runtime import serialize_channel_values

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/threads", tags=["threads"])

_SEARCH_SCAN_LIMIT = 10_000


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
    workspace_id: str | None = Field(default=None, description="可选的 workspace ID，用于新会话绑定草稿 workspace")
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


def _store_unavailable_error() -> HTTPException:
    """Return the canonical 503 for Store connectivity failures."""
    return HTTPException(status_code=503, detail="Thread metadata store unavailable")


def _normalize_workspace_id(workspace_id: str | None) -> str | None:
    """规范化可选的 workspace UUID 字符串，校验格式是否合法"""
    if workspace_id is None:
        return None

    try:
        return str(uuid.UUID(workspace_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid workspace_id") from exc


def _require_store(request: Request):
    """Return the Store instance or raise a 503 when unavailable."""
    store = get_store(request)
    if store is None:
        raise _store_unavailable_error()
    return store


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


def _validate_thread_id(thread_id: str, paths: Paths | None = None) -> None:
    """Validate a thread ID before using it anywhere in request handling."""
    path_manager = paths or get_paths()
    try:
        path_manager.thread_dir(thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _stringify_timestamp(value: Any) -> str:
    """Serialize timestamps for API responses."""
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


def _stringify_workspace_id(value: Any) -> str | None:
    """Normalize workspace IDs for API responses."""
    if value is None:
        return None
    return str(value)


def _store_metadata(store_record: ThreadRecord | dict[str, Any]) -> dict[str, Any]:
    """Extract Store-backed metadata."""
    raw_metadata = store_record.get("metadata") if isinstance(store_record, dict) else None
    return dict(raw_metadata) if isinstance(raw_metadata, dict) else {}


def _store_values(store_record: ThreadRecord | dict[str, Any]) -> dict[str, Any]:
    """Extract Store-backed values."""
    raw_values = store_record.get("values") if isinstance(store_record, dict) else None
    return dict(raw_values) if isinstance(raw_values, dict) else {}


def _store_title(store_record: ThreadRecord | dict[str, Any]) -> str | None:
    """Extract the persisted thread title from Store values."""
    raw_title = _store_values(store_record).get("title")
    if isinstance(raw_title, str) and raw_title.strip():
        return raw_title
    return None


def _build_thread_response(
    *,
    thread: Any,
    store_record: ThreadRecord | dict[str, Any],
    values: dict[str, Any] | None = None,
    status: str | None = None,
) -> ThreadResponse:
    """Build an API response from a DB thread row and Store metadata record."""
    response_values = dict(values or {})
    title = _store_title(store_record)
    if title and "title" not in response_values:
        response_values["title"] = title

    thread_id = str(getattr(thread, "thread_id", None) or store_record["thread_id"])
    workspace_id = _stringify_workspace_id(getattr(thread, "workspace_id", None))
    thread_status = str(status or store_record.get("status", "idle"))
    created_at = store_record.get("created_at")
    updated_at = store_record.get("updated_at")

    return ThreadResponse(
        thread_id=thread_id,
        workspace_id=workspace_id,
        status=thread_status,
        created_at=_stringify_timestamp(created_at),
        updated_at=_stringify_timestamp(updated_at),
        metadata=_store_metadata(store_record),
        values=response_values,
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
        logger.warning("Failed to rollback thread creation for %s", thread_id, exc_info=True)

    if delete_store_record_on_failure and store is not None:
        try:
            await delete_thread_record(store, thread_id)
        except Exception:
            logger.warning("Failed to remove mirrored store record for %s", thread_id, exc_info=True)

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
    """Delete thread-local files, Store metadata, checkpoints, and the DB binding."""
    _validate_thread_id(thread_id)
    store = get_store(request)
    await require_thread_access(
        db=db,
        store=store,
        thread_id=thread_id,
        current_user=current_user,
    )

    response = _delete_thread_data(thread_id)

    if store is None:
        raise _store_unavailable_error()

    try:
        await delete_thread_record(store, thread_id)
    except StoreUnavailableError as exc:
        raise _store_unavailable_error() from exc
    except Exception as exc:
        logger.exception("Failed to delete Store metadata for %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to delete thread") from exc

    checkpointer = get_checkpointer(request)
    if hasattr(checkpointer, "adelete_thread"):
        try:
            await checkpointer.adelete_thread(thread_id)
        except Exception as exc:
            if is_runtime_state_unavailable(exc):
                raise to_runtime_state_http_exception(exc) from exc
            logger.exception("Failed to delete checkpoints for %s", thread_id)
            raise HTTPException(status_code=500, detail="Failed to delete thread") from exc

    try:
        await ThreadRepository.delete_thread(db=db, thread_id=thread_id)
    except Exception as exc:
        logger.exception("Failed to delete DB thread state for %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to delete thread") from exc

    return response


@router.post("", response_model=ThreadResponse)
async def create_thread(
    body: ThreadCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadResponse:
    """Create a new thread with DB binding and Store runtime metadata."""
    checkpointer = get_checkpointer(request)
    store = _require_store(request)
    thread_id = body.thread_id or str(uuid.uuid4())
    requested_workspace_id = _normalize_workspace_id(body.workspace_id)

    existing_thread = await ThreadRepository.get_thread_by_id(
        db=db,
        thread_id=thread_id,
    )
    try:
        existing_store_record = await get_thread_record(store, thread_id)
    except StoreUnavailableError as exc:
        raise _store_unavailable_error() from exc

    if existing_thread is not None:
        if existing_thread.user_id != current_user.id:
            raise HTTPException(status_code=403, detail=f"Thread belongs to user {existing_thread.user_id}")
        if requested_workspace_id is not None:
            existing_workspace_id = str(existing_thread.workspace_id) if existing_thread.workspace_id is not None else None
            if existing_workspace_id != requested_workspace_id:
                raise HTTPException(
                    status_code=409,
                    detail="Thread already exists with a different workspace binding",
                )
        if existing_store_record is None:
            raise HTTPException(
                status_code=409,
                detail="Thread exists in DB metadata but is missing Store metadata",
            )
        return _build_thread_response(thread=existing_thread, store_record=existing_store_record)

    if existing_store_record is not None:
        raise HTTPException(
            status_code=409,
            detail="Thread exists in Store metadata but is missing DB metadata",
        )

    try:
        existing_checkpoint = await checkpointer.aget_tuple(_root_checkpoint_config(thread_id))
    except Exception as exc:
        if is_runtime_state_unavailable(exc):
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to check existing checkpoint for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to create thread") from exc

    if existing_checkpoint is not None:
        raise HTTPException(
            status_code=409,
            detail="Thread exists in runtime state but is missing business metadata",
        )

    if requested_workspace_id is None:
        workspace = await WorkspaceRepository.create_workspace(
            db=db,
            user_id=current_user.id,
            name=None,
            commit=False,
        )
    else:
        workspace = await WorkspaceRepository.get_workspace_by_id(
            db=db,
            workspace_id=requested_workspace_id,
        )
        if workspace is None:
            workspace = await WorkspaceRepository.create_workspace(
                db=db,
                user_id=current_user.id,
                name=None,
                id=uuid.UUID(requested_workspace_id),
                commit=False,
            )
        elif workspace.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail=f"Workspace belongs to user {workspace.user_id}",
            )
    created_thread = await ThreadRepository.create_thread(
        db=db,
        thread_id=thread_id,
        user_id=current_user.id,
        agent_id=None,
        workspace_id=workspace.id,
        metadata=body.metadata,
        commit=False,
    )

    checkpoint_created = False
    store_record_written = False
    now = time.time()
    mirror_record: ThreadRecord = {
        "thread_id": thread_id,
        "status": "idle",
        "created_at": now,
        "updated_at": now,
        "metadata": dict(body.metadata),
        "values": {},
    }

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
        await checkpointer.aput(
            _root_checkpoint_config(thread_id),
            empty_checkpoint(),
            checkpoint_metadata,
            {},
        )
        checkpoint_created = True

        await put_thread_record(store, mirror_record)
        store_record_written = True
        await db.commit()
    except StoreUnavailableError as exc:
        await _cleanup_failed_thread_creation(
            store=store,
            checkpointer=checkpointer,
            thread_id=thread_id,
            rollback_db=db.rollback,
            delete_checkpoint=checkpoint_created,
            delete_store_record_on_failure=store_record_written,
        )
        raise _store_unavailable_error() from exc
    except Exception as exc:
        await _cleanup_failed_thread_creation(
            store=store,
            checkpointer=checkpointer,
            thread_id=thread_id,
            rollback_db=db.rollback,
            delete_checkpoint=checkpoint_created,
            delete_store_record_on_failure=store_record_written,
        )
        if is_runtime_state_unavailable(exc):
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to create thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to create thread") from exc

    logger.info("Thread created: %s", thread_id)
    return _build_thread_response(thread=created_thread, store_record=mirror_record)


@router.post("/search", response_model=list[ThreadResponse])
async def search_threads(
    body: ThreadSearchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ThreadResponse]:
    """Search DB-bound threads and hydrate the user-facing fields from Store."""
    store = _require_store(request)
    candidate_threads = await ThreadRepository.search_threads(
        db=db,
        user_id=current_user.id,
        status=None,
        metadata=None,
        limit=_SEARCH_SCAN_LIMIT,
        offset=0,
    )

    matching_threads: list[tuple[Any, ThreadRecord]] = []
    for thread in candidate_threads:
        try:
            store_record = await get_thread_record(store, str(thread.thread_id))
        except StoreUnavailableError as exc:
            raise _store_unavailable_error() from exc

        if store_record is None:
            continue
        if body.status and store_record.get("status") != body.status:
            continue

        metadata = _store_metadata(store_record)
        if any(metadata.get(key) != expected for key, expected in body.metadata.items()):
            continue
        matching_threads.append((thread, store_record))

    matching_threads.sort(
        key=lambda item: _timestamp_sort_key(item[1].get("updated_at") or item[1].get("created_at")),
        reverse=True,
    )
    paged_threads = matching_threads[body.offset : body.offset + body.limit]
    return [_build_thread_response(thread=thread, store_record=store_record) for thread, store_record in paged_threads]


@router.patch("/{thread_id}", response_model=ThreadResponse)
async def patch_thread(
    thread_id: str,
    body: ThreadPatchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadResponse:
    """Merge metadata into a Store-backed thread record and mirror it to the DB."""
    store = _require_store(request)
    access_record = await require_thread_access(
        db=db,
        store=store,
        thread_id=thread_id,
        current_user=current_user,
    )

    try:
        updated_store_record = await upsert_thread_record(
            store,
            thread_id,
            metadata=body.metadata,
        )
    except StoreUnavailableError as exc:
        raise _store_unavailable_error() from exc
    except Exception as exc:
        logger.exception("Failed to patch thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to update thread") from exc

    updated_thread = access_record.thread
    try:
        mirrored_thread = await ThreadRepository.update_thread(
            db=db,
            thread_id=thread_id,
            metadata=body.metadata,
        )
        if mirrored_thread is not None:
            updated_thread = mirrored_thread
    except Exception:
        logger.warning("Failed to mirror thread metadata into DB for %s", thread_id, exc_info=True)

    return _build_thread_response(thread=updated_thread, store_record=updated_store_record)


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadResponse:
    """Get thread metadata from Store and runtime state from the checkpointer."""
    access_record = await require_thread_access(
        db=db,
        store=get_store(request),
        thread_id=thread_id,
        current_user=current_user,
    )
    checkpointer = get_checkpointer(request)

    try:
        checkpoint_tuple = await checkpointer.aget_tuple(_root_checkpoint_config(thread_id))
    except Exception as exc:
        if is_runtime_state_unavailable(exc):
            raise to_runtime_state_http_exception(exc) from exc
        logger.exception("Failed to get checkpoint for thread %s", thread_id)
        raise HTTPException(status_code=500, detail="Failed to get thread") from exc

    if checkpoint_tuple is None:
        return _build_thread_response(thread=access_record.thread, store_record=access_record.store_record)

    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    channel_values = serialize_channel_values(checkpoint.get("channel_values", {}))
    return _build_thread_response(
        thread=access_record.thread,
        store_record=access_record.store_record,
        values=channel_values,
        status=_derive_thread_status(
            checkpoint_tuple,
            default_status=str(access_record.store_record.get("status", "idle")),
        ),
    )


@router.get("/{thread_id}/state", response_model=ThreadStateResponse)
async def get_thread_state(
    thread_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadStateResponse:
    """Get the latest runtime state snapshot for a thread."""
    await require_thread_access(
        db=db,
        store=get_store(request),
        thread_id=thread_id,
        current_user=current_user,
    )
    checkpointer = get_checkpointer(request)

    try:
        checkpoint_tuple = await checkpointer.aget_tuple(_root_checkpoint_config(thread_id))
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
    db: AsyncSession = Depends(get_db),
) -> ThreadStateResponse:
    """Write a new checkpoint and sync title changes into Store then DB."""
    store = _require_store(request)
    await require_thread_access(
        db=db,
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

    if body.values and "title" in body.values:
        try:
            await upsert_thread_record(
                store,
                thread_id,
                values={"title": str(body.values["title"])},
            )
        except StoreUnavailableError as exc:
            raise _store_unavailable_error() from exc
        except Exception as exc:
            logger.exception("Failed to sync thread title into Store for %s", thread_id)
            raise HTTPException(status_code=500, detail="Failed to update thread title") from exc

        try:
            await ThreadRepository.update_thread(
                db=db,
                thread_id=thread_id,
                title=str(body.values["title"]),
            )
        except Exception:
            logger.warning("Failed to mirror thread title into DB for %s", thread_id, exc_info=True)

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
    db: AsyncSession = Depends(get_db),
) -> list[HistoryEntry]:
    """Get checkpoint history for an owned thread."""
    await require_thread_access(
        db=db,
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
