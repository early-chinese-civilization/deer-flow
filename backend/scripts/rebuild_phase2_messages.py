"""Rebuild Phase 2 message truth rows from the latest checkpoint state."""

from __future__ import annotations

import argparse
import asyncio
import sys
from contextlib import AsyncExitStack
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def rebuild_thread_messages(*, thread_id: str, checkpointer) -> tuple[str, bool, str]:
    """Rebuild a single thread from its latest checkpoint truth."""
    from app.gateway.db.engine import get_db_session
    from app.gateway.db.repository import MessageRepository
    from app.gateway.services.message_mirror import extract_user_visible_messages

    checkpoint_tuple = await checkpointer.aget_tuple(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    )
    if checkpoint_tuple is None:
        return thread_id, False, "missing checkpoint"

    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    channel_values = checkpoint.get("channel_values", {})
    if not isinstance(channel_values.get("messages"), list):
        return thread_id, False, "checkpoint has no values.messages"

    messages = extract_user_visible_messages("values", channel_values)
    async with get_db_session() as db:
        await MessageRepository.sync_visible_messages(
            db=db,
            thread_id=thread_id,
            messages=messages,
        )
    return thread_id, True, f"rebuilt {len(messages)} messages"


async def rebuild_all_threads(*, limit: int | None = None) -> list[tuple[str, bool, str]]:
    """Rebuild message truth rows for all known chats."""
    from sqlalchemy import select

    from app.gateway.db.engine import get_db_session
    from app.gateway.db.models import Chat
    from deerflow.agents.checkpointer.async_provider import make_checkpointer

    async with AsyncExitStack() as stack:
        checkpointer = await stack.enter_async_context(make_checkpointer())
        async with get_db_session() as db:
            stmt = select(Chat.thread_id).order_by(Chat.created_at)
            if limit is not None:
                stmt = stmt.limit(limit)
            result = await db.execute(stmt)
            thread_ids = [str(thread_id) for thread_id in result.scalars().all()]

        results: list[tuple[str, bool, str]] = []
        for thread_id in thread_ids:
            results.append(await rebuild_thread_messages(thread_id=thread_id, checkpointer=checkpointer))
        return results


async def _async_main(limit: int | None) -> int:
    results = await rebuild_all_threads(limit=limit)
    rebuilt_count = 0
    skipped_count = 0

    for thread_id, rebuilt, message in results:
        status = "rebuilt" if rebuilt else "skipped"
        print(f"[{status}] {thread_id} - {message}")
        if rebuilt:
            rebuilt_count += 1
        else:
            skipped_count += 1

    print(f"Completed rebuild for {len(results)} chats: {rebuilt_count} rebuilt, {skipped_count} skipped.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild Phase 2 messages from the latest checkpoint truth."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only rebuild the first N chats.",
    )
    args = parser.parse_args()
    return asyncio.run(_async_main(limit=args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
