"""Ownership helpers that require both DB binding and Store metadata."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Thread, User
from app.gateway.db.repository import ThreadRepository
from app.gateway.services.thread_store import StoreUnavailableError, ThreadRecord, get_thread_record


@dataclass(frozen=True)
class ThreadAccessRecord:
    """Resolved thread resources from the business DB and Store."""

    thread: Thread
    store_record: ThreadRecord


def _thread_not_found_error(thread_id: str) -> HTTPException:
    """Return the canonical 404 for missing thread metadata."""
    return HTTPException(status_code=404, detail=f"Thread {thread_id} not found")


def _store_unavailable_error() -> HTTPException:
    """Return the canonical 503 for Store connectivity failures."""
    return HTTPException(status_code=503, detail="Thread metadata store unavailable")


def _require_authenticated_user(current_user: User | None) -> User:
    """Return the authenticated user or raise a 401."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return current_user


async def require_thread_access(
    *,
    db: AsyncSession,
    store,
    thread_id: str,
    current_user: User | None,
) -> ThreadAccessRecord:
    """Validate that the caller owns a thread bound in DB and mirrored in Store."""
    user = _require_authenticated_user(current_user)
    if store is None:
        raise _store_unavailable_error()

    thread = await ThreadRepository.get_thread_by_id(db, thread_id)
    if thread is None:
        raise _thread_not_found_error(thread_id)
    if getattr(thread, "deleted_at", None) is not None:
        raise _thread_not_found_error(thread_id)
    if thread.user_id != user.id:
        raise HTTPException(status_code=403, detail=f"Thread belongs to user {thread.user_id}")

    try:
        store_record = await get_thread_record(store, thread_id)
    except StoreUnavailableError as exc:
        raise _store_unavailable_error() from exc

    if store_record is None:
        raise _thread_not_found_error(thread_id)
    return ThreadAccessRecord(thread=thread, store_record=store_record)
