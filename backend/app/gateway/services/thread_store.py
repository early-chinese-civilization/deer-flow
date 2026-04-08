"""Thread metadata helpers backed by LangGraph Store."""

from __future__ import annotations

import time
from typing import Any, TypedDict, cast

from psycopg import OperationalError

THREADS_NS: tuple[str, ...] = ("threads",)

_UNSET = object()


class ThreadValues(TypedDict, total=False):
    """User-facing values mirrored into the thread metadata record."""

    title: str


class ThreadRecord(TypedDict, total=False):
    """Normalized Store payload for thread metadata."""

    thread_id: str
    owner_user_id: int | None
    workspace_id: str | None
    status: str
    created_at: float
    updated_at: float
    metadata: dict[str, Any]
    values: ThreadValues


class StoreUnavailableError(RuntimeError):
    """Raised when the auxiliary thread metadata Store is unavailable."""


def is_store_unavailable(exc: Exception) -> bool:
    """Return whether the error indicates a transient Store connectivity issue."""
    if isinstance(exc, OperationalError):
        return True

    message = str(exc).lower()
    return "connection is closed" in message or "closed connection" in message


def coerce_owner_user_id(record: ThreadRecord | dict[str, Any] | None) -> int | None:
    """Normalize the stored owner identifier into an integer when possible."""
    if not isinstance(record, dict):
        return None

    raw_value = record.get("owner_user_id")
    if raw_value is None:
        return None
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str) and raw_value.isdigit():
        return int(raw_value)
    return None


def get_workspace_id(record: ThreadRecord | dict[str, Any] | None) -> str | None:
    """Return the workspace identifier stored in the thread metadata record."""
    if not isinstance(record, dict):
        return None

    raw_value = record.get("workspace_id")
    if raw_value is None:
        return None
    return str(raw_value)


async def get_thread_record(store, thread_id: str) -> ThreadRecord | None:
    """Fetch a thread metadata record from the Store."""
    try:
        item = await store.aget(THREADS_NS, thread_id)
    except Exception as exc:
        if is_store_unavailable(exc):
            raise StoreUnavailableError("Thread metadata store unavailable") from exc
        raise

    if item is None or not isinstance(item.value, dict):
        return None
    return cast(ThreadRecord, item.value)


async def put_thread_record(store, record: ThreadRecord) -> None:
    """Write a thread metadata record to the Store."""
    try:
        await store.aput(THREADS_NS, record["thread_id"], record)
    except Exception as exc:
        if is_store_unavailable(exc):
            raise StoreUnavailableError("Thread metadata store unavailable") from exc
        raise


async def delete_thread_record(store, thread_id: str) -> None:
    """Delete a thread metadata record from the Store."""
    try:
        await store.adelete(THREADS_NS, thread_id)
    except Exception as exc:
        if is_store_unavailable(exc):
            raise StoreUnavailableError("Thread metadata store unavailable") from exc
        raise


async def search_thread_records(store, *, limit: int) -> list[Any]:
    """Search Store-backed thread records."""
    try:
        return await store.asearch(THREADS_NS, limit=limit)
    except Exception as exc:
        if is_store_unavailable(exc):
            raise StoreUnavailableError("Thread metadata store unavailable") from exc
        raise


async def upsert_thread_record(
    store,
    thread_id: str,
    *,
    owner_user_id: int | None | object = _UNSET,
    workspace_id: str | None | object = _UNSET,
    metadata: dict[str, Any] | None = None,
    values: dict[str, Any] | None = None,
    status: str | None = None,
    created_at: float | None = None,
    updated_at: float | None = None,
) -> ThreadRecord:
    """Create or update a thread metadata record in the Store."""
    now = time.time() if updated_at is None else updated_at
    existing = await get_thread_record(store, thread_id)

    if existing is None:
        record: ThreadRecord = {
            "thread_id": thread_id,
            "status": status or "idle",
            "created_at": now if created_at is None else created_at,
            "updated_at": now,
            "metadata": dict(metadata or {}),
            "values": cast(ThreadValues, dict(values or {})),
        }
        if owner_user_id is not _UNSET:
            record["owner_user_id"] = cast(int | None, owner_user_id)
        if workspace_id is not _UNSET:
            record["workspace_id"] = cast(str | None, workspace_id)

        await put_thread_record(store, record)
        return record

    record = cast(ThreadRecord, dict(existing))
    record["updated_at"] = now
    if status is not None:
        record["status"] = status
    if owner_user_id is not _UNSET:
        record["owner_user_id"] = cast(int | None, owner_user_id)
    if workspace_id is not _UNSET:
        record["workspace_id"] = cast(str | None, workspace_id)
    if metadata:
        record.setdefault("metadata", {}).update(metadata)
    if values:
        record.setdefault("values", {}).update(values)

    await put_thread_record(store, record)
    return record
