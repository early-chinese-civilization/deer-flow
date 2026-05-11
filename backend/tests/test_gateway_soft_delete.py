from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.gateway.db.models import Thread, User, Workspace
from app.gateway.db.repository import ThreadRepository, UserRepository, WorkspaceRepository
from app.gateway.services import ownership


def test_core_gateway_tables_have_soft_delete_column():
    assert "deleted_at" in User.__table__.columns
    assert "deleted_at" in Workspace.__table__.columns
    assert "deleted_at" in Thread.__table__.columns


def test_core_repository_active_selects_filter_soft_deleted_rows():
    assert "users.deleted_at IS NULL" in str(UserRepository._active_user_stmt())
    assert "workspaces.deleted_at IS NULL" in str(WorkspaceRepository._active_workspace_stmt())
    assert "threads.deleted_at IS NULL" in str(ThreadRepository._active_thread_stmt())


@pytest.mark.anyio
async def test_require_thread_access_rejects_soft_deleted_thread():
    thread = SimpleNamespace(
        thread_id="thread-1",
        user_id=7,
        deleted_at=datetime(2026, 5, 7, tzinfo=UTC),
    )

    with patch(
        "app.gateway.services.ownership.ThreadRepository.get_thread_by_id",
        AsyncMock(return_value=thread),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await ownership.require_thread_access(
                db=object(),
                store=SimpleNamespace(),
                thread_id=thread.thread_id,
                current_user=SimpleNamespace(id=thread.user_id),
            )

    assert exc_info.value.status_code == 404
