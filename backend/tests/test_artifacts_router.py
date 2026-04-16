import asyncio
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import FileResponse

import app.gateway.routers.artifacts as artifacts_router

ACTIVE_ARTIFACT_CASES = [
    ("poc.html", "<html><body><script>alert('xss')</script></body></html>"),
    ("page.xhtml", '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body>hello</body></html>'),
    ("image.svg", '<svg xmlns="http://www.w3.org/2000/svg"><script>alert("xss")</script></svg>'),
]


def _make_request(query_string: bytes = b"") -> Request:
    app = FastAPI()
    app.state.store = SimpleNamespace()
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": query_string,
            "app": app,
        }
    )


async def _db_dependency():
    yield SimpleNamespace()


def test_get_artifact_reads_utf8_text_file_on_windows_locale(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "note.txt"
    text = "Curly quotes: \u201cutf8\u201d"
    artifact_path.write_text(text, encoding="utf-8")

    original_read_text = Path.read_text

    def read_text_with_gbk_default(self, *args, **kwargs):
        kwargs.setdefault("encoding", "gbk")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text_with_gbk_default)
    monkeypatch.setattr(artifacts_router, "resolve_thread_virtual_path", lambda _thread_id, _path: artifact_path)

    request = _make_request()
    with patch("app.gateway.routers.artifacts.require_thread_access", AsyncMock(return_value=object())):
        response = asyncio.run(
            artifacts_router.get_artifact(
                "thread-1",
                "mnt/user-data/outputs/note.txt",
                request,
                current_user=SimpleNamespace(id=7),
                db=object(),
            )
        )

    assert bytes(response.body).decode("utf-8") == text
    assert response.media_type == "text/plain"


@pytest.mark.parametrize(("filename", "content"), ACTIVE_ARTIFACT_CASES)
def test_get_artifact_forces_download_for_active_content(tmp_path, monkeypatch, filename: str, content: str) -> None:
    artifact_path = tmp_path / filename
    artifact_path.write_text(content, encoding="utf-8")

    monkeypatch.setattr(artifacts_router, "resolve_thread_virtual_path", lambda _thread_id, _path: artifact_path)

    with patch("app.gateway.routers.artifacts.require_thread_access", AsyncMock(return_value=object())):
        response = asyncio.run(
            artifacts_router.get_artifact(
                "thread-1",
                f"mnt/user-data/outputs/{filename}",
                _make_request(),
                current_user=SimpleNamespace(id=7),
                db=object(),
            )
        )

    assert isinstance(response, FileResponse)
    assert response.headers.get("content-disposition", "").startswith("attachment;")


@pytest.mark.parametrize(("filename", "content"), ACTIVE_ARTIFACT_CASES)
def test_get_artifact_forces_download_for_active_content_in_skill_archive(tmp_path, monkeypatch, filename: str, content: str) -> None:
    skill_path = tmp_path / "sample.skill"
    with zipfile.ZipFile(skill_path, "w") as zip_ref:
        zip_ref.writestr(filename, content)

    monkeypatch.setattr(artifacts_router, "resolve_thread_virtual_path", lambda _thread_id, _path: skill_path)

    with patch("app.gateway.routers.artifacts.require_thread_access", AsyncMock(return_value=object())):
        response = asyncio.run(
            artifacts_router.get_artifact(
                "thread-1",
                f"mnt/user-data/outputs/sample.skill/{filename}",
                _make_request(),
                current_user=SimpleNamespace(id=7),
                db=object(),
            )
        )

    assert response.headers.get("content-disposition", "").startswith("attachment;")
    assert bytes(response.body) == content.encode("utf-8")


def test_get_artifact_download_false_does_not_force_attachment(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "note.txt"
    artifact_path.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(artifacts_router, "resolve_thread_virtual_path", lambda _thread_id, _path: artifact_path)

    app = FastAPI()
    app.include_router(artifacts_router.router)
    app.state.store = SimpleNamespace()
    app.dependency_overrides[artifacts_router.get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[artifacts_router.get_db] = _db_dependency

    with (
        patch("app.gateway.routers.artifacts.require_thread_access", AsyncMock(return_value=object())),
        TestClient(app) as client,
    ):
        response = client.get("/api/threads/thread-1/artifacts/mnt/user-data/outputs/note.txt?download=false")

    assert response.status_code == 200
    assert response.text == "hello"
    assert "content-disposition" not in response.headers


def test_get_artifact_download_true_forces_attachment_for_skill_archive(tmp_path, monkeypatch) -> None:
    skill_path = tmp_path / "sample.skill"
    with zipfile.ZipFile(skill_path, "w") as zip_ref:
        zip_ref.writestr("notes.txt", "hello")

    monkeypatch.setattr(artifacts_router, "resolve_thread_virtual_path", lambda _thread_id, _path: skill_path)

    app = FastAPI()
    app.include_router(artifacts_router.router)
    app.state.store = SimpleNamespace()
    app.dependency_overrides[artifacts_router.get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[artifacts_router.get_db] = _db_dependency

    with (
        patch("app.gateway.routers.artifacts.require_thread_access", AsyncMock(return_value=object())),
        TestClient(app) as client,
    ):
        response = client.get("/api/threads/thread-1/artifacts/mnt/user-data/outputs/sample.skill/notes.txt?download=true")

    assert response.status_code == 200
    assert response.text == "hello"
    assert response.headers.get("content-disposition", "").startswith("attachment;")


def test_get_artifact_requires_owned_thread(monkeypatch, tmp_path) -> None:
    artifact_path = tmp_path / "note.txt"
    artifact_path.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(artifacts_router, "resolve_thread_virtual_path", lambda _thread_id, _path: artifact_path)

    app = FastAPI()
    app.include_router(artifacts_router.router)
    app.state.store = SimpleNamespace()
    app.dependency_overrides[artifacts_router.get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[artifacts_router.get_db] = _db_dependency

    with (
        patch(
            "app.gateway.routers.artifacts.require_thread_access",
            AsyncMock(side_effect=artifacts_router.HTTPException(status_code=403, detail="forbidden")),
        ),
        TestClient(app) as client,
    ):
        response = client.get("/api/threads/thread-1/artifacts/mnt/user-data/outputs/note.txt")

    assert response.status_code == 403
