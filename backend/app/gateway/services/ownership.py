"""Store-backed ownership helpers for thread resources."""

from __future__ import annotations

from fastapi import HTTPException

from app.gateway.db.models import User
from app.gateway.services.thread_store import (
    StoreUnavailableError,
    ThreadRecord,
    coerce_owner_user_id,
    get_thread_record,
)


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
    store,
    thread_id: str,
    current_user: User | None,
) -> ThreadRecord:
    """Validate that the caller owns the requested thread record."""
    user = _require_authenticated_user(current_user)
    if store is None:
        raise _store_unavailable_error()

    try:
        record = await get_thread_record(store, thread_id)
    except StoreUnavailableError as exc:
        raise _store_unavailable_error() from exc

    if record is None:
        raise _thread_not_found_error(thread_id)

    owner_user_id = coerce_owner_user_id(record)
    if owner_user_id is None:
        raise HTTPException(status_code=403, detail="Thread is missing an owner")
    if owner_user_id != user.id:
        raise HTTPException(status_code=403, detail=f"Thread belongs to user {owner_user_id}")

    return record
