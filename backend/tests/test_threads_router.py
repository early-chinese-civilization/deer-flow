from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.gateway.routers import threads
from deerflow.config.paths import Paths


def test_delete_thread_data_removes_thread_directory(tmp_path):
    paths = Paths(tmp_path)
    thread_dir = paths.thread_dir("thread-cleanup")
    workspace = paths.sandbox_work_dir("thread-cleanup")
    uploads = paths.sandbox_uploads_dir("thread-cleanup")
    outputs = paths.sandbox_outputs_dir("thread-cleanup")

    for directory in [workspace, uploads, outputs]:
        directory.mkdir(parents=True, exist_ok=True)
    (workspace / "notes.txt").write_text("hello", encoding="utf-8")
    (uploads / "report.pdf").write_bytes(b"pdf")
    (outputs / "result.json").write_text("{}", encoding="utf-8")

    assert thread_dir.exists()

    response = threads._delete_thread_data("thread-cleanup", paths=paths)

    assert response.success is True
    assert not thread_dir.exists()


def test_delete_thread_data_is_idempotent_for_missing_directory(tmp_path):
    paths = Paths(tmp_path)

    response = threads._delete_thread_data("missing-thread", paths=paths)

    assert response.success is True
    assert not paths.thread_dir("missing-thread").exists()


def test_delete_thread_data_rejects_invalid_thread_id(tmp_path):
    paths = Paths(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        threads._delete_thread_data("../escape", paths=paths)

    assert exc_info.value.status_code == 422
    assert "Invalid thread_id" in exc_info.value.detail


def test_delete_thread_route_cleans_thread_directory(tmp_path):
    paths = Paths(tmp_path)
    thread_dir = paths.thread_dir("thread-route")
    paths.sandbox_work_dir("thread-route").mkdir(parents=True, exist_ok=True)
    (paths.sandbox_work_dir("thread-route") / "notes.txt").write_text("hello", encoding="utf-8")

    app = FastAPI()
    app.include_router(threads.router)

    with patch("app.gateway.routers.threads.get_paths", return_value=paths):
        with TestClient(app) as client:
            response = client.delete("/api/threads/thread-route")

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Deleted local thread data for thread-route"}
    assert not thread_dir.exists()


def test_delete_thread_route_rejects_invalid_thread_id(tmp_path):
    paths = Paths(tmp_path)

    app = FastAPI()
    app.include_router(threads.router)

    with patch("app.gateway.routers.threads.get_paths", return_value=paths):
        with TestClient(app) as client:
            response = client.delete("/api/threads/../escape")

    assert response.status_code == 404


def test_delete_thread_route_returns_422_for_route_safe_invalid_id(tmp_path):
    paths = Paths(tmp_path)

    app = FastAPI()
    app.include_router(threads.router)

    with patch("app.gateway.routers.threads.get_paths", return_value=paths):
        with TestClient(app) as client:
            response = client.delete("/api/threads/thread.with.dot")

    assert response.status_code == 422
    assert "Invalid thread_id" in response.json()["detail"]


def test_delete_thread_data_returns_generic_500_error(tmp_path):
    paths = Paths(tmp_path)

    with (
        patch.object(paths, "delete_thread_dir", side_effect=OSError("/secret/path")),
        patch.object(threads.logger, "exception") as log_exception,
    ):
        with pytest.raises(HTTPException) as exc_info:
            threads._delete_thread_data("thread-cleanup", paths=paths)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to delete local thread data."
    assert "/secret/path" not in exc_info.value.detail
    log_exception.assert_called_once_with("Failed to delete thread data for %s", "thread-cleanup")


def _make_request(*, checkpointer=None, store=None):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(checkpointer=checkpointer, store=store)))


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


@pytest.mark.anyio
async def test_search_threads_prefers_product_chats_without_runtime_reads():
    chat = SimpleNamespace(
        thread_id=uuid4(),
        title="Projected title",
        status="busy",
        created_at=datetime(2026, 4, 6, tzinfo=UTC),
        updated_at=datetime(2026, 4, 6, 1, tzinfo=UTC),
        owner_user_id=7,
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=_ScalarResult([chat])))
    current_user = SimpleNamespace(id=7)
    checkpointer = SimpleNamespace(
        aget_tuple=AsyncMock(side_effect=AssertionError("search must not hydrate from runtime state")),
    )

    async def _unexpected_alist(*args, **kwargs):
        raise AssertionError("search must not scan runtime state")
        if False:  # pragma: no cover
            yield None

    checkpointer.alist = _unexpected_alist

    results = await threads.search_threads(
        threads.ThreadSearchRequest(limit=10, offset=0),
        request=_make_request(checkpointer=checkpointer, store=None),
        current_user=current_user,
        db=db,
    )

    assert [result.thread_id for result in results] == [str(chat.thread_id)]
    assert results[0].status == "busy"
    assert results[0].values == {"title": "Projected title"}


@pytest.mark.anyio
async def test_search_threads_ignores_store_only_threads_when_product_db_is_available():
    current_user = SimpleNamespace(id=7)
    db = SimpleNamespace(execute=AsyncMock(return_value=_ScalarResult([])))

    class _StoreItem:
        def __init__(self, value):
            self.value = value

    store = SimpleNamespace(
        asearch=AsyncMock(
            return_value=[
                _StoreItem(
                    {
                        "thread_id": str(uuid4()),
                        "status": "idle",
                        "created_at": "2026-04-06T00:00:00Z",
                        "updated_at": "2026-04-06T00:00:00Z",
                        "metadata": {"source": "store-only"},
                    }
                )
            ]
        )
    )

    with patch(
        "app.gateway.routers.threads.ChatRepository.get_chat_by_thread_id",
        AsyncMock(return_value=None),
    ):
        results = await threads.search_threads(
            threads.ThreadSearchRequest(limit=10, offset=0),
            request=_make_request(checkpointer=None, store=store),
            current_user=current_user,
            db=db,
        )

    assert results == []


@pytest.mark.anyio
async def test_get_thread_does_not_reconcile_projection_on_read():
    checkpoint_tuple = SimpleNamespace(
        config={"configurable": {"thread_id": "thread-1", "checkpoint_id": "ckpt-1"}},
        checkpoint={"channel_values": {"title": "Runtime title"}},
        metadata={"created_at": "2026-04-06T00:00:00Z"},
        parent_config=None,
        pending_writes=[],
        tasks=[],
    )
    checkpointer = SimpleNamespace(aget_tuple=AsyncMock(return_value=checkpoint_tuple))

    with (
        patch("app.gateway.routers.threads.require_thread_access", AsyncMock(return_value=None)),
        patch(
            "app.gateway.services.projection.ProjectionService.project_from_checkpoint",
            AsyncMock(side_effect=AssertionError("get_thread must stay side-effect free")),
        ),
    ):
        response = await threads.get_thread(
            "thread-1",
            request=_make_request(checkpointer=checkpointer, store=None),
            current_user=None,
            db=object(),
        )

    assert response.thread_id == "thread-1"
    assert response.values["title"] == "Runtime title"


@pytest.mark.anyio
async def test_get_thread_state_does_not_reconcile_projection_on_read():
    checkpoint_tuple = SimpleNamespace(
        config={"configurable": {"thread_id": "thread-1", "checkpoint_id": "ckpt-1"}},
        checkpoint={"channel_values": {"title": "Runtime title", "messages": []}},
        metadata={"created_at": "2026-04-06T00:00:00Z"},
        parent_config=None,
        pending_writes=[],
        tasks=[],
    )
    checkpointer = SimpleNamespace(aget_tuple=AsyncMock(return_value=checkpoint_tuple))

    with (
        patch("app.gateway.routers.threads.require_thread_access", AsyncMock(return_value=None)),
        patch(
            "app.gateway.services.projection.ProjectionService.project_from_checkpoint",
            AsyncMock(side_effect=AssertionError("state reads must not reconcile")),
        ),
    ):
        response = await threads.get_thread_state(
            "thread-1",
            request=_make_request(checkpointer=checkpointer, store=None),
            current_user=None,
            db=object(),
        )

    assert response.checkpoint_id == "ckpt-1"
    assert response.values["title"] == "Runtime title"


@pytest.mark.anyio
async def test_get_thread_history_does_not_reconcile_projection_on_read():
    checkpoint_tuple = SimpleNamespace(
        config={"configurable": {"thread_id": "thread-1", "checkpoint_id": "ckpt-1"}},
        checkpoint={"channel_values": {"title": "Runtime title"}},
        metadata={"created_at": "2026-04-06T00:00:00Z"},
        parent_config=None,
        pending_writes=[],
        tasks=[],
    )

    async def _history(*args, **kwargs):
        yield checkpoint_tuple

    checkpointer = SimpleNamespace(alist=_history)

    with (
        patch("app.gateway.routers.threads.require_thread_access", AsyncMock(return_value=None)),
        patch(
            "app.gateway.services.projection.ProjectionService.project_from_checkpoint",
            AsyncMock(side_effect=AssertionError("history reads must not reconcile")),
        ),
    ):
        response = await threads.get_thread_history(
            "thread-1",
            threads.ThreadHistoryRequest(limit=10),
            request=_make_request(checkpointer=checkpointer, store=None),
            current_user=None,
            db=object(),
        )

    assert [entry.checkpoint_id for entry in response] == ["ckpt-1"]
    assert response[0].values["title"] == "Runtime title"


@pytest.mark.anyio
async def test_create_thread_returns_existing_chat_without_runtime_idempotency():
    thread_id = uuid4()
    chat = SimpleNamespace(
        thread_id=thread_id,
        title="Projected title",
        status="idle",
        created_at=datetime(2026, 4, 6, tzinfo=UTC),
        updated_at=datetime(2026, 4, 6, 1, tzinfo=UTC),
    )
    checkpointer = SimpleNamespace(
        aget_tuple=AsyncMock(side_effect=AssertionError("existing chats should short-circuit before runtime lookup"))
    )

    with patch(
        "app.gateway.routers.threads.ChatRepository.get_chat_by_thread_id",
        AsyncMock(return_value=chat),
    ):
        response = await threads.create_thread(
            threads.ThreadCreateRequest(thread_id=str(thread_id)),
            request=_make_request(checkpointer=checkpointer, store=None),
            current_user=SimpleNamespace(id=1),
            db=object(),
        )

    assert response.thread_id == str(thread_id)
    assert response.values == {"title": "Projected title"}
    assert response.status == "idle"


@pytest.mark.anyio
async def test_create_thread_rejects_orphan_runtime_thread_without_chat_record():
    checkpoint_tuple = SimpleNamespace(
        config={"configurable": {"thread_id": "thread-1", "checkpoint_id": "ckpt-1"}},
        checkpoint={"channel_values": {}},
        metadata={"created_at": "2026-04-06T00:00:00Z"},
        parent_config=None,
        pending_writes=[],
        tasks=[],
    )
    checkpointer = SimpleNamespace(aget_tuple=AsyncMock(return_value=checkpoint_tuple))

    with patch(
        "app.gateway.routers.threads.ChatRepository.get_chat_by_thread_id",
        AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await threads.create_thread(
                threads.ThreadCreateRequest(thread_id="thread-1"),
                request=_make_request(checkpointer=checkpointer, store=None),
                current_user=SimpleNamespace(id=1),
                db=object(),
            )

    assert exc_info.value.status_code == 409
