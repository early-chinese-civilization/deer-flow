"""Tests for workspace upload gateway responses."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.deps import get_current_user, get_db
from app.gateway.routers import uploads as uploads_router
from app.gateway.services import workspace_uploads
from deerflow.uploads import workspace_object_key, workspace_root_prefix

WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"


async def _db_dependency():
    yield SimpleNamespace()


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(uploads_router.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_db] = _db_dependency
    return TestClient(app)


def test_build_workspace_file_response_includes_oss_uris(monkeypatch) -> None:
    monkeypatch.setattr(
        workspace_uploads,
        "get_app_config",
        lambda: SimpleNamespace(
            uploads=SimpleNamespace(
                backend="oss",
                oss=SimpleNamespace(bucket="demo-bucket"),
            )
        ),
    )

    response = workspace_uploads.build_workspace_file_response(
        workspace_id=WORKSPACE_ID,
        filename="report.md",
        relative_path="uploads/report.md",
        size=123,
        object_key=f"workspaces/{WORKSPACE_ID}/uploads/report.md",
        markdown_file="report.txt",
        markdown_object_key=f"workspaces/{WORKSPACE_ID}/uploads/report.txt",
    )

    assert response["artifact_url"] == f"/api/workspaces/{WORKSPACE_ID}/uploads/content?object_key=workspaces%2F{WORKSPACE_ID}%2Fuploads%2Freport.md"
    assert response["path"] == "uploads/report.md"
    assert response["virtual_path"] == "/mnt/user-data/uploads/report.md"
    assert response["oss_uri"] == f"oss://demo-bucket/workspaces/{WORKSPACE_ID}/uploads/report.md"
    assert response["markdown_oss_uri"] == f"oss://demo-bucket/workspaces/{WORKSPACE_ID}/uploads/report.txt"
    assert response["markdown_path"] == "uploads/report.txt"
    assert response["markdown_virtual_path"] == "/mnt/user-data/uploads/report.txt"


def test_build_workspace_file_response_escapes_oss_uri_path_segments(monkeypatch) -> None:
    monkeypatch.setattr(
        workspace_uploads,
        "get_app_config",
        lambda: SimpleNamespace(
            uploads=SimpleNamespace(
                backend="oss",
                oss=SimpleNamespace(bucket="demo-bucket"),
            )
        ),
    )

    object_key = f"workspaces/{WORKSPACE_ID}/uploads/analysis (final) #1?.md"

    response = workspace_uploads.build_workspace_file_response(
        workspace_id=WORKSPACE_ID,
        filename="analysis (final) #1?.md",
        relative_path="uploads/analysis (final) #1?.md",
        size=123,
        object_key=object_key,
    )

    assert response["oss_uri"] == f"oss://demo-bucket/workspaces/{WORKSPACE_ID}/uploads/analysis%20%28final%29%20%231%3F.md"


def test_prepare_upload_includes_oss_uri(monkeypatch) -> None:
    monkeypatch.setattr(
        workspace_uploads,
        "get_app_config",
        lambda: SimpleNamespace(
            uploads=SimpleNamespace(
                backend="oss",
                oss=SimpleNamespace(bucket="demo-bucket"),
            )
        ),
    )

    with patch.object(
        uploads_router.WorkspaceRepository,
        "get_workspace_by_id",
        AsyncMock(return_value=None),
    ), patch(
        "app.gateway.routers.uploads.list_workspace_objects",
        AsyncMock(return_value=[]),
    ):
        with _build_client() as client:
            response = client.post(
                f"/api/workspaces/{WORKSPACE_ID}/uploads/prepare",
                json={"filename": "report.md", "size": 123},
            )

    assert response.status_code == 200
    file_response = response.json()["file"]
    assert file_response["path"] == "uploads/report.md"
    assert file_response["virtual_path"] == "/mnt/user-data/uploads/report.md"
    assert file_response["oss_uri"] == f"oss://demo-bucket/workspaces/{WORKSPACE_ID}/uploads/report.md"


def test_finalize_upload_includes_oss_uri(monkeypatch) -> None:
    monkeypatch.setattr(
        workspace_uploads,
        "get_app_config",
        lambda: SimpleNamespace(
            uploads=SimpleNamespace(
                backend="oss",
                oss=SimpleNamespace(bucket="demo-bucket"),
            )
        ),
    )

    root_prefix = workspace_root_prefix(WORKSPACE_ID)
    object_key = workspace_object_key(root_prefix, "report.md", subdir="uploads")
    uploaded_object = workspace_uploads.WorkspaceObjectInfo(
        key=object_key,
        size=123,
        last_modified=None,
        content_type="text/markdown",
    )

    with patch.object(
        uploads_router.WorkspaceRepository,
        "get_workspace_by_id",
        AsyncMock(return_value=SimpleNamespace(id="workspace-1", user_id=7, file_path=root_prefix, name="Workspace")),
    ), patch(
        "app.gateway.routers.uploads.list_workspace_objects",
        AsyncMock(return_value=[uploaded_object]),
    ), patch.object(
        uploads_router.WorkspaceRepository,
        "update_workspace_file_path",
        AsyncMock(),
    ):
        with _build_client() as client:
            response = client.post(
                f"/api/workspaces/{WORKSPACE_ID}/uploads/finalize",
                json={"filename": "report.md", "object_key": object_key, "size": 123},
            )

    assert response.status_code == 200
    assert response.json()["path"] == "uploads/report.md"
    assert response.json()["virtual_path"] == "/mnt/user-data/uploads/report.md"
    assert response.json()["oss_uri"] == f"oss://demo-bucket/workspaces/{WORKSPACE_ID}/uploads/report.md"


def test_list_uploaded_files_includes_oss_uri(monkeypatch) -> None:
    monkeypatch.setattr(
        workspace_uploads,
        "get_app_config",
        lambda: SimpleNamespace(
            uploads=SimpleNamespace(
                backend="oss",
                oss=SimpleNamespace(bucket="demo-bucket"),
            )
        ),
    )

    root_prefix = workspace_root_prefix(WORKSPACE_ID)
    object_key = workspace_object_key(root_prefix, "report.md", subdir="uploads")
    uploaded_object = workspace_uploads.WorkspaceObjectInfo(
        key=object_key,
        size=123,
        last_modified=None,
        content_type="text/markdown",
    )

    with patch.object(
        uploads_router.WorkspaceRepository,
        "get_workspace_by_id",
        AsyncMock(return_value=SimpleNamespace(id="workspace-1", user_id=7, file_path=root_prefix, name="Workspace")),
    ), patch(
        "app.gateway.routers.uploads.list_workspace_objects",
        AsyncMock(return_value=[uploaded_object]),
    ):
        with _build_client() as client:
            response = client.get(f"/api/workspaces/{WORKSPACE_ID}/uploads/list")

    assert response.status_code == 200
    file_response = response.json()["files"][0]
    assert file_response["path"] == "uploads/report.md"
    assert file_response["virtual_path"] == "/mnt/user-data/uploads/report.md"
    assert file_response["oss_uri"] == f"oss://demo-bucket/workspaces/{WORKSPACE_ID}/uploads/report.md"


def test_download_url_returns_presigned_url(monkeypatch) -> None:
    root_prefix = workspace_root_prefix(WORKSPACE_ID)
    object_key = workspace_object_key(root_prefix, "report.md", subdir="uploads")
    storage = SimpleNamespace(bucket="demo-bucket")
    storage.presign_get_object = lambda **kwargs: ("https://example.test/download", None)

    monkeypatch.setattr(uploads_router, "uses_oss_workspace_uploads", lambda: True)
    monkeypatch.setattr(uploads_router.OSSStorageBackend, "from_app_config", lambda: storage)

    with patch.object(
        uploads_router.WorkspaceRepository,
        "get_workspace_by_id",
        AsyncMock(return_value=SimpleNamespace(id="workspace-1", user_id=7, file_path=root_prefix, name="Workspace")),
    ), patch.object(
        uploads_router.WorkspaceRepository,
        "update_workspace_file_path",
        AsyncMock(),
    ):
        with _build_client() as client:
                response = client.get(
                    f"/api/workspaces/{WORKSPACE_ID}/uploads/download-url",
                    params={"object_key": object_key},
                )

    assert response.status_code == 200
    assert response.json() == {
        "download_url": "https://example.test/download",
        "oss_uri": f"oss://demo-bucket/workspaces/{WORKSPACE_ID}/uploads/report.md",
    }


def test_download_url_rejects_draft_workspace(monkeypatch) -> None:
    storage = SimpleNamespace(bucket="demo-bucket")
    storage.presign_get_object = lambda **kwargs: ("https://example.test/download", None)

    monkeypatch.setattr(uploads_router, "uses_oss_workspace_uploads", lambda: True)
    monkeypatch.setattr(uploads_router.OSSStorageBackend, "from_app_config", lambda: storage)

    with patch.object(
        uploads_router.WorkspaceRepository,
        "get_workspace_by_id",
        AsyncMock(return_value=None),
    ):
        with _build_client() as client:
            response = client.get(
                f"/api/workspaces/{WORKSPACE_ID}/uploads/download-url",
                params={"object_key": f"workspaces/{WORKSPACE_ID}/uploads/report.md"},
            )

    assert response.status_code == 404


def test_download_url_rejects_out_of_prefix_object_key(monkeypatch) -> None:
    root_prefix = workspace_root_prefix(WORKSPACE_ID)
    storage = SimpleNamespace(bucket="demo-bucket")
    storage.presign_get_object = lambda **kwargs: ("https://example.test/download", None)

    monkeypatch.setattr(uploads_router, "uses_oss_workspace_uploads", lambda: True)
    monkeypatch.setattr(uploads_router.OSSStorageBackend, "from_app_config", lambda: storage)

    with patch.object(
        uploads_router.WorkspaceRepository,
        "get_workspace_by_id",
        AsyncMock(return_value=SimpleNamespace(id="workspace-1", user_id=7, file_path=root_prefix, name="Workspace")),
    ):
        with _build_client() as client:
            response = client.get(
                f"/api/workspaces/{WORKSPACE_ID}/uploads/download-url",
                params={"object_key": "workspaces/other/uploads/report.md"},
            )

    assert response.status_code == 403


def test_upload_files_reports_claimed_filename_on_processing_failure(monkeypatch) -> None:
    root_prefix = workspace_root_prefix(WORKSPACE_ID)

    monkeypatch.setattr(
        uploads_router.WorkspaceRepository,
        "get_workspace_by_id",
        AsyncMock(return_value=SimpleNamespace(id="workspace-1", user_id=7, file_path=root_prefix, name="Workspace")),
    )
    monkeypatch.setattr(
        uploads_router,
        "list_workspace_objects",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        uploads_router,
        "_process_single_file",
        AsyncMock(side_effect=[None, RuntimeError("boom")]),
    )

    with _build_client() as client:
        response = client.post(
            f"/api/workspaces/{WORKSPACE_ID}/uploads",
            files=[
                ("files", ("report.md", b"one", "text/markdown")),
                ("files", ("report.md", b"two", "text/markdown")),
            ],
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to upload report_1.md: boom"
