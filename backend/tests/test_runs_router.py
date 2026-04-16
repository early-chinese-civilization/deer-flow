from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.gateway.routers import runs


def _make_request(*, checkpoint=None, store=None):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                checkpointer=SimpleNamespace(aget_tuple=AsyncMock(return_value=checkpoint)),
                store=store or SimpleNamespace(),
            )
        )
    )


def _make_record(*, status: str = "queued", error=None):
    return SimpleNamespace(
        run_id="run-1",
        task=None,
        status=SimpleNamespace(value=status),
        error=error,
    )


@pytest.mark.anyio
async def test_stateless_wait_creates_bound_thread_for_authenticated_user() -> None:
    body = runs.RunCreateRequest(
        input={"messages": []},
        metadata={"source": "ui"},
        on_completion="keep",
    )
    checkpoint = SimpleNamespace(checkpoint={"channel_values": {"answer": "ok"}})
    request = _make_request(checkpoint=checkpoint)
    access_record = SimpleNamespace(thread=SimpleNamespace(thread_id="generated-thread"), store_record={})

    with (
        patch("app.gateway.routers.runs.threads_router.create_thread", AsyncMock()) as create_thread_mock,
        patch("app.gateway.routers.runs.require_thread_access", AsyncMock(return_value=access_record)),
        patch("app.gateway.routers.runs.gateway_services.start_run", AsyncMock(return_value=_make_record())) as start_run_mock,
    ):
        result = await runs.stateless_wait(
            body,
            request,
            current_user=SimpleNamespace(id=7),
            db=object(),
        )

    created_request = create_thread_mock.await_args.args[0]
    assert created_request.thread_id
    assert created_request.metadata == {"source": "ui"}
    assert start_run_mock.await_args.args[1] == created_request.thread_id
    assert start_run_mock.await_args.kwargs["thread_record"] is access_record
    assert result == {"answer": "ok"}


@pytest.mark.anyio
async def test_stateless_wait_reuses_owned_thread_without_creating_new_one() -> None:
    body = runs.RunCreateRequest(
        config={"configurable": {"thread_id": "thread-1"}},
        on_completion="keep",
    )
    request = _make_request(checkpoint=None)
    access_record = SimpleNamespace(thread=SimpleNamespace(thread_id="thread-1"), store_record={})

    with (
        patch("app.gateway.routers.runs.threads_router.create_thread", AsyncMock()) as create_thread_mock,
        patch("app.gateway.routers.runs.require_thread_access", AsyncMock(return_value=access_record)),
        patch(
            "app.gateway.routers.runs.gateway_services.start_run",
            AsyncMock(return_value=_make_record(status="running")),
        ) as start_run_mock,
    ):
        result = await runs.stateless_wait(
            body,
            request,
            current_user=SimpleNamespace(id=7),
            db=object(),
        )

    create_thread_mock.assert_not_awaited()
    assert start_run_mock.await_args.args[1] == "thread-1"
    assert result == {"status": "running", "error": None}


@pytest.mark.anyio
async def test_stateless_wait_deletes_temporary_thread_by_default() -> None:
    body = runs.RunCreateRequest(
        input={"messages": []},
        metadata={"source": "ui"},
    )
    checkpoint = SimpleNamespace(checkpoint={"channel_values": {"answer": "ok"}})
    request = _make_request(checkpoint=checkpoint)
    access_record = SimpleNamespace(
        thread=SimpleNamespace(thread_id="generated-thread", workspace_id="workspace-1"),
        store_record={},
    )

    with (
        patch("app.gateway.routers.runs.threads_router.create_thread", AsyncMock()) as create_thread_mock,
        patch("app.gateway.routers.runs.require_thread_access", AsyncMock(return_value=access_record)),
        patch("app.gateway.routers.runs.gateway_services.start_run", AsyncMock(return_value=_make_record())),
        patch("app.gateway.routers.runs._delete_temporary_thread_resources", AsyncMock()) as cleanup_mock,
    ):
        result = await runs.stateless_wait(
            body,
            request,
            current_user=SimpleNamespace(id=7),
            db=object(),
        )

    created_thread_id = create_thread_mock.await_args.args[0].thread_id
    assert result == {"answer": "ok"}
    cleanup_mock.assert_awaited_once_with(
        thread_id=created_thread_id,
        workspace_id="workspace-1",
        request=request,
    )


@pytest.mark.anyio
async def test_stateless_stream_attaches_cleanup_for_temporary_thread() -> None:
    body = runs.RunCreateRequest(
        input={"messages": []},
    )
    request = _make_request(checkpoint=None)
    access_record = SimpleNamespace(
        thread=SimpleNamespace(thread_id="generated-thread", workspace_id="workspace-1"),
        store_record={},
    )

    with (
        patch("app.gateway.routers.runs.threads_router.create_thread", AsyncMock()) as create_thread_mock,
        patch("app.gateway.routers.runs.require_thread_access", AsyncMock(return_value=access_record)),
        patch("app.gateway.routers.runs.gateway_services.start_run", AsyncMock(return_value=_make_record())) as start_run_mock,
        patch("app.gateway.routers.runs.gateway_services.sse_consumer", return_value=iter(())),
        patch("app.gateway.routers.runs.get_run_manager", return_value=SimpleNamespace()),
        patch("app.gateway.routers.runs.get_stream_bridge", return_value=SimpleNamespace()),
    ):
        response = await runs.stateless_stream(
            body,
            request,
            current_user=SimpleNamespace(id=7),
            db=object(),
        )

    assert response.background is not None
    assert start_run_mock.await_args.args[1] == create_thread_mock.await_args.args[0].thread_id
