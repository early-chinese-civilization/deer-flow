from types import SimpleNamespace

from langchain_core.messages import HumanMessage, SystemMessage

from deerflow.agents.middlewares import file_reference_middleware as file_reference_middleware_module
from deerflow.agents.middlewares.file_reference_middleware import FileReferenceMiddleware
from deerflow.agents.middlewares.uploads_middleware import UploadsMiddleware


def test_uploads_middleware_persists_canonical_oss_file_identity(tmp_path):
    middleware = UploadsMiddleware(base_dir=str(tmp_path))
    workspace_id = "workspace-1"

    uploads_dir = tmp_path / "workspaces" / workspace_id / "user-data" / "uploads"
    uploads_dir.mkdir(parents=True)
    (uploads_dir / "report.md").write_text("hello")

    payload = {
        "filename": "report.md",
        "size": 123,
        "path": "oss://demo-bucket/workspaces/workspace-1/uploads/report.md",
        "virtual_path": "/mnt/user-data/uploads/report.md",
        "object_key": "workspaces/workspace-1/uploads/report.md",
        "oss_uri": "oss://demo-bucket/workspaces/workspace-1/uploads/report.md",
        "artifact_url": "/api/workspaces/workspace-1/uploads/content?object_key=workspaces%2Fworkspace-1%2Fuploads%2Freport.md",
        "signed_url": "https://signed.example/report.md",
        "extension": ".md",
    }

    state = {"messages": [HumanMessage(content="upload", additional_kwargs={"files": [payload]})]}
    runtime = SimpleNamespace(context={"workspace_id": workspace_id})

    result = middleware.before_agent(state, runtime)

    assert result is not None
    assert result["uploaded_files"] is not None

    file_entry = result["uploaded_files"][0]
    assert file_entry["oss_uri"] == payload["oss_uri"]
    assert file_entry["path"] == payload["path"]
    assert file_entry["virtual_path"] == payload["virtual_path"]
    assert file_entry["object_key"] == payload["object_key"]
    assert "artifact_url" not in file_entry
    assert "signed_url" not in file_entry


def test_uploads_middleware_accepts_path_only_virtual_payload(tmp_path, monkeypatch):
    middleware = UploadsMiddleware(base_dir=str(tmp_path))

    monkeypatch.setattr(
        "deerflow.agents.middlewares.uploads_middleware.get_app_config",
        lambda: SimpleNamespace(uploads=SimpleNamespace(oss=SimpleNamespace(bucket="demo-bucket"))),
    )

    payload = {
        "filename": "notes.txt",
        "size": 55,
        "path": "/mnt/user-data/uploads/notes.txt",
        "object_key": "workspaces/workspace-1/uploads/notes.txt",
    }

    state = {"messages": [HumanMessage(content="upload", additional_kwargs={"files": [payload]})]}
    runtime = SimpleNamespace(context={"workspace_id": "workspace-1"})

    result = middleware.before_agent(state, runtime)

    assert result is not None
    file_entry = result["uploaded_files"][0]
    assert file_entry["virtual_path"] == payload["path"]
    assert file_entry["oss_uri"].startswith("oss://")
    assert file_entry["object_key"] == payload["object_key"]


def test_uploads_middleware_sanitizes_existing_state_entries(tmp_path):
    middleware = UploadsMiddleware(base_dir=str(tmp_path))

    existing_entry = {
        "filename": "legacy.txt",
        "size": 9,
        "path": "oss://demo-bucket/workspaces/workspace-1/uploads/legacy.txt",
        "virtual_path": "/mnt/user-data/uploads/legacy.txt",
        "oss_uri": "oss://demo-bucket/workspaces/workspace-1/uploads/legacy.txt",
        "object_key": "workspaces/workspace-1/uploads/legacy.txt",
        "artifact_url": "/api/workspaces/workspace-1/uploads/content?object_key=workspaces%2Fworkspace-1%2Fuploads%2Flegacy.txt",
        "signed_url": "https://signed.example/legacy.txt",
        "extension": ".txt",
    }

    state = {
        "uploaded_files": [existing_entry],
        "messages": [HumanMessage(content="Show me the uploaded file list.")],
    }
    runtime = SimpleNamespace(context={"workspace_id": "workspace-1"})

    result = middleware.before_agent(state, runtime)

    assert result is not None
    file_entry = result["uploaded_files"][0]
    assert file_entry["oss_uri"] == existing_entry["oss_uri"]
    assert file_entry["virtual_path"] == existing_entry["virtual_path"]
    assert file_entry["path"] == existing_entry["path"]
    assert file_entry["object_key"] == existing_entry["object_key"]
    assert "artifact_url" not in file_entry
    assert "signed_url" not in file_entry


def test_file_reference_middleware_rewrites_all_oss_references(monkeypatch):
    middleware = FileReferenceMiddleware()

    def _fake_presign(oss_uri: str) -> str:
        return f"https://signed.example/{oss_uri.removeprefix('oss://')}"

    monkeypatch.setattr(file_reference_middleware_module, "_presign_oss_uri", _fake_presign)

    state = {
        "messages": [
            SystemMessage(content="Policy: review oss://demo-bucket/workspaces/ws/uploads/policy.md first."),
            HumanMessage(content="Then inspect oss://demo-bucket/workspaces/ws/uploads/report.md and answer."),
        ]
    }
    runtime = SimpleNamespace(context={"workspace_id": "workspace-1"})

    result = middleware.before_model(state, runtime)

    assert result is not None
    assert len(result["messages"]) == 2
    assert "https://signed.example/demo-bucket/workspaces/ws/uploads/policy.md" in result["messages"][0].content
    assert "https://signed.example/demo-bucket/workspaces/ws/uploads/report.md" in result["messages"][1].content
    assert "oss://" not in result["messages"][0].content
    assert "oss://" not in result["messages"][1].content
