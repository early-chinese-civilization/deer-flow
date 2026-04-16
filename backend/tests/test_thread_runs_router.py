from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import StreamingResponse

from app.gateway.routers import thread_runs


def _make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/threads/thread-1/runs/run-1/stream",
            "headers": [],
            "query_string": b"",
            "app": SimpleNamespace(state=SimpleNamespace()),
        }
    )


@pytest.mark.anyio
async def test_stream_existing_run_passes_request_into_ownership_check() -> None:
    request = _make_request()
    record = SimpleNamespace(thread_id="thread-1", task=None)
    require_owned_thread = AsyncMock(return_value=object())
    run_manager = SimpleNamespace(get=lambda _run_id: record)
    stream_bridge = SimpleNamespace()

    with (
        patch("app.gateway.routers.thread_runs._require_owned_thread", require_owned_thread),
        patch("app.gateway.routers.thread_runs.get_run_manager", return_value=run_manager),
        patch("app.gateway.routers.thread_runs.get_stream_bridge", return_value=stream_bridge),
        patch(
            "app.gateway.routers.thread_runs.gateway_services.sse_consumer",
            return_value=iter(()),
        ),
    ):
        response = await thread_runs.stream_existing_run(
            "thread-1",
            "run-1",
            request,
            current_user=SimpleNamespace(id=7),
            db=object(),
            action=None,
            wait=0,
        )

    assert isinstance(response, StreamingResponse)
    assert require_owned_thread.await_args.kwargs["request"] is request
