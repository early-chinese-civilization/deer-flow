from types import SimpleNamespace

from app.gateway.services import workspace_uploads
from deerflow.config.paths import Paths


def test_build_workspace_root_path_uses_workspace_root_without_user_data(tmp_path, monkeypatch):
    monkeypatch.setattr(
        workspace_uploads,
        "get_app_config",
        lambda: SimpleNamespace(uploads=SimpleNamespace(backend="local", oss=SimpleNamespace(bucket=""))),
    )
    monkeypatch.setattr(workspace_uploads, "get_paths", lambda: Paths(base_dir=tmp_path))

    path = workspace_uploads.build_workspace_root_path("workspaces/workspace-123")

    assert path.endswith("workspaces/workspace-123")
    assert "user-data" not in path
