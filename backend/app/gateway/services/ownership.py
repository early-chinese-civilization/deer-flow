"""Ownership and lazy-takeover helpers for thread-backed chat resources."""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Chat, User
from app.gateway.db.repository import ChatRepository

logger = logging.getLogger(__name__)


def _build_forbidden_error(detail: str | None) -> HTTPException:
    """Create a consistent 403 response for thread ownership failures."""
    return HTTPException(status_code=403, detail=detail or "Thread access denied")


async def ensure_chat_ownership(
    db: AsyncSession,
    thread_id: str,
    current_user: User | None,
    *,
    auto_create_workspace: bool = True,
) -> Chat | None:
    """Ensure a chat row exists for a thread when a signed-in user opens it.

    Legacy threads may pre-date the product chat tables. When a logged-in user
    opens one of those threads for the first time, we lazily take ownership by
    creating the corresponding ``chats`` row. Anonymous access remains read-only
    and does not create product records.
    """
    chat = await ChatRepository.get_chat_by_thread_id(db, thread_id)
    if chat is not None:
        return chat

    if current_user is None:
        logger.debug("Anonymous access to legacy thread %s does not trigger takeover", thread_id)
        return None

    workspace_id = uuid.uuid4() if auto_create_workspace else None
    logger.info("User %s is taking over legacy thread %s", current_user.id, thread_id)
    return await ChatRepository.create_chat(
        db=db,
        thread_id=thread_id,
        owner_user_id=current_user.id,
        workspace_id=workspace_id,
        status="idle",
    )


async def check_chat_access(
    db: AsyncSession,
    thread_id: str,
    current_user: User | None,
) -> tuple[bool, str | None]:
    """Return whether the caller may access the thread's chat record."""
    chat = await ChatRepository.get_chat_by_thread_id(db, thread_id)
    if chat is None:
        return True, None

    if current_user is None:
        return False, "Authentication is required to access this thread"

    if chat.owner_user_id != current_user.id:
        return False, f"Thread belongs to user {chat.owner_user_id}"

    return True, None


async def require_thread_access(
    *,
    db: AsyncSession | None,
    thread_id: str,
    current_user: User | None,
    auto_create_workspace: bool = True,
) -> Chat | None:
    """Guard thread access and optionally perform lazy takeover.

    This is the single router-facing helper for Phase 2 semantics:
    1. Existing chats must pass owner checks.
    2. Logged-in users opening legacy threads lazily create the chat row.
    3. Anonymous callers may keep read-only access to legacy threads.
    """
    if db is None:
        return None

    allowed, error_message = await check_chat_access(db, thread_id, current_user)
    if not allowed:
        raise _build_forbidden_error(error_message)

    chat = await ensure_chat_ownership(
        db,
        thread_id,
        current_user,
        auto_create_workspace=auto_create_workspace,
    )
    if chat is not None and current_user is not None and chat.owner_user_id != current_user.id:
        raise _build_forbidden_error(f"Thread belongs to user {chat.owner_user_id}")

    return chat
