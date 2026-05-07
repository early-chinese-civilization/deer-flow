from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.gateway.routers import threads
from deerflow.config.paths import Paths


def _make_thread(**overrides):
    base = {
        "thread_id": "thread-1",
        "user_id": 7,
        "workspace_id": uuid4(),
        "title": "Stored title",
        "status": "idle",
        "metadata": {},
        "created_at": datetime(2026, 4, 6, tzinfo=UTC),
        "updated_at": datetime(2026, 4, 6, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_store_record(**overrides):
    base = {
        "thread_id": "thread-1",
        "status": "idle",
        "metadata": {},
        "values": {"title": "Stored title"},
        "created_at": 1_775_404_800.0,
        "updated_at": 1_775_408_400.0,
    }
    base.update(overrides)
    return base


def _make_access_record(*, thread=None, store_record=None):
    bound_thread = thread or _make_thread()
    bound_store_record = store_record or _make_store_record(thread_id=bound_thread.thread_id)
    return SimpleNamespace(thread=bound_thread, store_record=bound_store_record)


def _make_request(*, checkpointer=None, store=None):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(checkpointer=checkpointer, store=store)))


async def _db_dependency():
    yield SimpleNamespace()


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


def test_delete_thread_route_cleans_thread_directory_and_db_records(tmp_path):
    paths = Paths(tmp_path)
    thread_dir = paths.thread_dir("thread-route")
    thread = _make_thread(thread_id="thread-route")
    access_record = _make_access_record(
        thread=thread,
        store_record=_make_store_record(thread_id="thread-route"),
    )
    paths.sandbox_work_dir("thread-route").mkdir(parents=True, exist_ok=True)
    (paths.sandbox_work_dir("thread-route") / "notes.txt").write_text("hello", encoding="utf-8")

    app = FastAPI()
    app.include_router(threads.router)
    app.state.store = SimpleNamespace(adelete=AsyncMock(return_value=None))
    app.state.checkpointer = SimpleNamespace(adelete_thread=AsyncMock(return_value=None))
    app.dependency_overrides[threads.get_current_user] = lambda: SimpleNamespace(id=thread.user_id)
    app.dependency_overrides[threads.get_db] = _db_dependency

    with (
        patch("app.gateway.routers.threads.get_paths", return_value=paths),
        patch("app.gateway.routers.threads.require_thread_access", AsyncMock(return_value=access_record)),
        patch("app.gateway.routers.threads.ThreadRepository.delete_thread", AsyncMock(return_value=True)) as delete_thread_mock,
        patch("app.gateway.routers.threads.delete_thread_record", AsyncMock(return_value=None)) as delete_store_mock,
        patch("app.gateway.routers.threads.WorkspaceRepository.delete_workspace", AsyncMock(return_value=True)) as delete_workspace_mock,
    ):
        with TestClient(app) as client:
            response = client.delete("/api/threads/thread-route")

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Deleted local thread data for thread-route"}
    assert not thread_dir.exists()
    assert delete_thread_mock.await_count == 1
    assert delete_store_mock.await_count == 1
    assert delete_workspace_mock.await_count == 0


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
    thread = _make_thread(thread_id="thread.with.dot")
    access_record = _make_access_record(
        thread=thread,
        store_record=_make_store_record(thread_id="thread.with.dot"),
    )

    app = FastAPI()
    app.include_router(threads.router)
    app.state.store = SimpleNamespace(adelete=AsyncMock(return_value=None))
    app.state.checkpointer = SimpleNamespace(adelete_thread=AsyncMock(return_value=None))
    app.dependency_overrides[threads.get_current_user] = lambda: SimpleNamespace(id=thread.user_id)
    app.dependency_overrides[threads.get_db] = _db_dependency

    with (
        patch("app.gateway.routers.threads.get_paths", return_value=paths),
        patch("app.gateway.routers.threads.require_thread_access", AsyncMock(return_value=access_record)),
        patch("app.gateway.routers.threads.ThreadRepository.delete_thread", AsyncMock(return_value=True)),
    ):
        with TestClient(app) as client:
            response = client.delete("/api/threads/thread.with.dot")

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Deleted local thread data for thread.with.dot"}


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


@pytest.mark.anyio
async def test_search_threads_reads_store_values_for_db_bound_threads():
    thread = _make_thread(title="DB title", status="idle")
    current_user = SimpleNamespace(id=7)
    store_record = _make_store_record(
        thread_id=thread.thread_id,
        status="busy",
        metadata={"source": "store"},
        values={"title": "Projected title"},
    )

    with patch(
        "app.gateway.routers.threads.ThreadRepository.search_threads",
        AsyncMock(return_value=[thread]),
    ) as search_mock:
        with patch(
            "app.gateway.routers.threads.get_thread_record",
            AsyncMock(return_value=store_record),
        ) as get_store_mock:
            results = await threads.search_threads(
                threads.ThreadSearchRequest(limit=10, offset=0, status="busy", metadata={"source": "store"}),
                request=_make_request(checkpointer=None, store=SimpleNamespace()),
                current_user=current_user,
                db=object(),
            )

    assert search_mock.await_count == 1
    assert get_store_mock.await_count == 1
    assert [result.thread_id for result in results] == [thread.thread_id]
    assert results[0].status == "busy"
    assert results[0].values == {"title": "Projected title"}
    assert results[0].workspace_id == str(thread.workspace_id)


@pytest.mark.anyio
async def test_search_threads_ignores_db_threads_without_store_records():
    thread = _make_thread()

    with patch(
        "app.gateway.routers.threads.ThreadRepository.search_threads",
        AsyncMock(return_value=[thread]),
    ):
        with patch(
            "app.gateway.routers.threads.get_thread_record",
            AsyncMock(return_value=None),
        ):
            results = await threads.search_threads(
                threads.ThreadSearchRequest(limit=10, offset=0),
                request=_make_request(checkpointer=None, store=SimpleNamespace()),
                current_user=SimpleNamespace(id=thread.user_id),
                db=object(),
            )

    assert results == []


@pytest.mark.anyio
async def test_search_threads_supports_null_workspace_bindings():
    thread = _make_thread(workspace_id=None)

    with patch(
        "app.gateway.routers.threads.ThreadRepository.search_threads",
        AsyncMock(return_value=[thread]),
    ):
        with patch(
            "app.gateway.routers.threads.get_thread_record",
            AsyncMock(return_value=_make_store_record(thread_id=thread.thread_id)),
        ):
            results = await threads.search_threads(
                threads.ThreadSearchRequest(limit=10, offset=0),
                request=_make_request(checkpointer=None, store=SimpleNamespace()),
                current_user=SimpleNamespace(id=thread.user_id),
                db=object(),
            )

    assert results[0].workspace_id is None


@pytest.mark.anyio
async def test_get_thread_uses_db_binding_and_runtime_values():
    thread = _make_thread(title="Stored title")
    access_record = _make_access_record(
        thread=thread,
        store_record=_make_store_record(thread_id="thread-1", values={"title": "Stored title"}),
    )
    checkpoint_tuple = SimpleNamespace(
        config={"configurable": {"thread_id": "thread-1", "checkpoint_id": "ckpt-1"}},
        checkpoint={"channel_values": {"title": "Runtime title"}},
        metadata={"created_at": "2026-04-06T00:00:00Z"},
        parent_config=None,
        pending_writes=[],
        tasks=[],
    )
    checkpointer = SimpleNamespace(aget_tuple=AsyncMock(return_value=checkpoint_tuple))

    with patch("app.gateway.routers.threads.require_thread_access", AsyncMock(return_value=access_record)):
        response = await threads.get_thread(
            "thread-1",
            request=_make_request(checkpointer=checkpointer, store=None),
            current_user=SimpleNamespace(id=thread.user_id),
            db=object(),
        )

    assert response.thread_id == "thread-1"
    assert response.workspace_id == str(thread.workspace_id)
    assert response.values["title"] == "Runtime title"


@pytest.mark.anyio
async def test_get_thread_state_does_not_need_store_for_ownership():
    thread = _make_thread()
    access_record = _make_access_record(thread=thread)
    checkpoint_tuple = SimpleNamespace(
        config={"configurable": {"thread_id": "thread-1", "checkpoint_id": "ckpt-1"}},
        checkpoint={"channel_values": {"title": "Runtime title", "messages": []}},
        metadata={"created_at": "2026-04-06T00:00:00Z"},
        parent_config=None,
        pending_writes=[],
        tasks=[],
    )
    checkpointer = SimpleNamespace(aget_tuple=AsyncMock(return_value=checkpoint_tuple))

    with patch("app.gateway.routers.threads.require_thread_access", AsyncMock(return_value=access_record)):
        response = await threads.get_thread_state(
            "thread-1",
            request=_make_request(checkpointer=checkpointer, store=None),
            current_user=SimpleNamespace(id=thread.user_id),
            db=object(),
        )

    assert response.checkpoint_id == "ckpt-1"
    assert response.values["title"] == "Runtime title"


@pytest.mark.anyio
async def test_get_thread_history_does_not_need_store_for_ownership():
    thread = _make_thread()
    access_record = _make_access_record(thread=thread)
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

    with patch("app.gateway.routers.threads.require_thread_access", AsyncMock(return_value=access_record)):
        response = await threads.get_thread_history(
            "thread-1",
            threads.ThreadHistoryRequest(limit=10),
            request=_make_request(checkpointer=checkpointer, store=None),
            current_user=SimpleNamespace(id=thread.user_id),
            db=object(),
        )

    assert [entry.checkpoint_id for entry in response] == ["ckpt-1"]
    assert response[0].values["title"] == "Runtime title"


@pytest.mark.anyio
async def test_update_thread_state_syncs_title_back_to_store_and_db():
    thread = _make_thread()
    access_record = _make_access_record(thread=thread)
    checkpoint_tuple = SimpleNamespace(
        config={"configurable": {"thread_id": "thread-1", "checkpoint_id": "ckpt-1"}},
        checkpoint={"channel_values": {"title": "Old title"}},
        metadata={"created_at": "2026-04-06T00:00:00Z"},
        parent_config=None,
        pending_writes=[],
        tasks=[],
    )
    checkpointer = SimpleNamespace(
        aget_tuple=AsyncMock(return_value=checkpoint_tuple),
        aput=AsyncMock(return_value={"configurable": {"thread_id": "thread-1", "checkpoint_id": "ckpt-2"}}),
    )

    with (
        patch("app.gateway.routers.threads.require_thread_access", AsyncMock(return_value=access_record)),
        patch("app.gateway.routers.threads.upsert_thread_record", AsyncMock(return_value=_make_store_record(values={"title": "New title"}))) as upsert_mock,
        patch("app.gateway.routers.threads.ThreadRepository.update_thread", AsyncMock(return_value=thread)) as update_mock,
    ):
        response = await threads.update_thread_state(
            "thread-1",
            threads.ThreadStateUpdateRequest(values={"title": "New title"}),
            request=_make_request(checkpointer=checkpointer, store=SimpleNamespace()),
            current_user=SimpleNamespace(id=thread.user_id),
            db=object(),
        )

    assert response.checkpoint_id == "ckpt-2"
    assert upsert_mock.await_count == 1
    assert update_mock.await_count == 1


@pytest.mark.anyio
async def test_create_thread_returns_existing_thread_when_db_and_store_exist():
    thread = _make_thread(thread_id=str(uuid4()), title="DB title", status="idle")
    store_record = _make_store_record(
        thread_id=thread.thread_id,
        status="busy",
        values={"title": "Projected title"},
    )
    checkpointer = SimpleNamespace(aget_tuple=AsyncMock(side_effect=AssertionError("existing DB threads should short-circuit before runtime lookup")))

    with patch(
        "app.gateway.routers.threads.ThreadRepository.get_thread_by_id",
        AsyncMock(return_value=thread),
    ):
        with patch(
            "app.gateway.routers.threads.get_thread_record",
            AsyncMock(return_value=store_record),
        ):
            response = await threads.create_thread(
                threads.ThreadCreateRequest(thread_id=thread.thread_id),
                request=_make_request(checkpointer=checkpointer, store=SimpleNamespace()),
                current_user=SimpleNamespace(id=thread.user_id),
                db=object(),
            )

    assert response.thread_id == thread.thread_id
    assert response.values == {"title": "Projected title"}
    assert response.status == "busy"


@pytest.mark.anyio
async def test_create_thread_rejects_db_thread_without_store_record():
    thread = _make_thread(thread_id="thread-1")

    with patch(
        "app.gateway.routers.threads.ThreadRepository.get_thread_by_id",
        AsyncMock(return_value=thread),
    ):
        with patch(
            "app.gateway.routers.threads.get_thread_record",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await threads.create_thread(
                    threads.ThreadCreateRequest(thread_id="thread-1"),
                    request=_make_request(checkpointer=SimpleNamespace(), store=SimpleNamespace()),
                    current_user=SimpleNamespace(id=thread.user_id),
                    db=object(),
                )

    assert exc_info.value.status_code == 409


@pytest.mark.anyio
async def test_create_thread_rejects_store_thread_without_db_record():
    checkpointer = SimpleNamespace(
        aget_tuple=AsyncMock(return_value=None),
    )

    with patch(
        "app.gateway.routers.threads.ThreadRepository.get_thread_by_id",
        AsyncMock(return_value=None),
    ):
        with patch(
            "app.gateway.routers.threads.get_thread_record",
            AsyncMock(return_value=_make_store_record(thread_id="thread-1")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await threads.create_thread(
                    threads.ThreadCreateRequest(thread_id="thread-1"),
                    request=_make_request(checkpointer=checkpointer, store=SimpleNamespace()),
                    current_user=SimpleNamespace(id=1),
                    db=object(),
                )

    assert exc_info.value.status_code == 409


@pytest.mark.anyio
async def test_create_thread_rejects_orphan_runtime_thread_without_db_record():
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
        "app.gateway.routers.threads.ThreadRepository.get_thread_by_id",
        AsyncMock(return_value=None),
    ):
        with patch(
            "app.gateway.routers.threads.get_thread_record",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await threads.create_thread(
                    threads.ThreadCreateRequest(thread_id="thread-1"),
                    request=_make_request(checkpointer=checkpointer, store=SimpleNamespace()),
                    current_user=SimpleNamespace(id=1),
                    db=object(),
                )

    assert exc_info.value.status_code == 409


@pytest.mark.anyio
async def test_create_thread_persists_db_thread_and_store_record_without_owner_or_workspace():
    workspace_id = uuid4()
    created_thread = _make_thread(thread_id="thread-new", workspace_id=workspace_id, title=None, metadata={"source": "ui"})
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    store = SimpleNamespace()
    checkpointer = SimpleNamespace(
        aget_tuple=AsyncMock(return_value=None),
        aput=AsyncMock(return_value={"configurable": {"thread_id": "thread-new", "checkpoint_id": "ckpt-1"}}),
    )

    with (
        patch("app.gateway.routers.threads.ThreadRepository.get_thread_by_id", AsyncMock(return_value=None)),
        patch("app.gateway.routers.threads.get_thread_record", AsyncMock(return_value=None)),
        patch(
            "app.gateway.routers.threads.WorkspaceRepository.create_workspace",
            AsyncMock(return_value=SimpleNamespace(id=workspace_id)),
        ),
        patch(
            "app.gateway.routers.threads.ThreadRepository.create_thread",
            AsyncMock(return_value=created_thread),
        ),
        patch("app.gateway.routers.threads.put_thread_record", AsyncMock()) as put_store_mock,
    ):
        response = await threads.create_thread(
            threads.ThreadCreateRequest(thread_id="thread-new", metadata={"source": "ui"}),
            request=_make_request(checkpointer=checkpointer, store=store),
            current_user=SimpleNamespace(id=created_thread.user_id),
            db=db,
        )

    assert response.thread_id == "thread-new"
    assert response.workspace_id == str(workspace_id)
    assert put_store_mock.await_count == 1
    stored_record = put_store_mock.await_args.args[1]
    assert "user_id" not in stored_record
    assert "workspace_id" not in stored_record
