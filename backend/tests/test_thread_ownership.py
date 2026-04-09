from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.gateway.services import ownership


def _make_thread(**overrides):
    base = {
        "thread_id": "thread-1",
        "user_id": 7,
        "workspace_id": uuid4(),
        "status": "idle",
        "title": None,
        "thread_metadata": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_store_record(**overrides):
    base = {
        "thread_id": "thread-1",
        "status": "idle",
        "metadata": {},
        "values": {},
        "created_at": 1_775_404_800.0,
        "updated_at": 1_775_408_400.0,
    }
    base.update(overrides)
    return base


@pytest.mark.anyio
async def test_require_thread_access_returns_db_and_store_records():
    thread = _make_thread()
    store_record = _make_store_record(thread_id=thread.thread_id)

    with (
        patch("app.gateway.services.ownership.ThreadRepository.get_thread_by_id", AsyncMock(return_value=thread)),
        patch("app.gateway.services.ownership.get_thread_record", AsyncMock(return_value=store_record)),
    ):
        access_record = await ownership.require_thread_access(
            db=object(),
            store=SimpleNamespace(),
            thread_id=thread.thread_id,
            current_user=SimpleNamespace(id=thread.user_id),
        )

    assert access_record.thread is thread
    assert access_record.store_record == store_record


@pytest.mark.anyio
async def test_require_thread_access_rejects_db_only_thread_without_store_record():
    thread = _make_thread()

    with (
        patch("app.gateway.services.ownership.ThreadRepository.get_thread_by_id", AsyncMock(return_value=thread)),
        patch("app.gateway.services.ownership.get_thread_record", AsyncMock(return_value=None)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await ownership.require_thread_access(
                db=object(),
                store=SimpleNamespace(),
                thread_id=thread.thread_id,
                current_user=SimpleNamespace(id=thread.user_id),
            )

    assert exc_info.value.status_code == 404
