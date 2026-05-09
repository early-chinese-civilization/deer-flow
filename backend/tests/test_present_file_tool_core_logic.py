"""Core behavior tests for present_files path normalization."""

import importlib
from types import SimpleNamespace

present_file_tool_module = importlib.import_module("deerflow.tools.builtins.present_file_tool")


def _make_runtime(outputs_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        state={"thread_data": {"outputs_path": outputs_path}},
        context={"thread_id": "thread-1"},
    )


def _make_runtime_with_workspace(outputs_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        state={"thread_data": {"outputs_path": outputs_path, "workspace_id": "workspace-1"}},
        context={"thread_id": "thread-1", "workspace_id": "workspace-1"},
    )


def test_present_files_normalizes_host_outputs_path(tmp_path, monkeypatch):
    outputs_dir = tmp_path / "threads" / "thread-1" / "user-data" / "outputs"
    outputs_dir.mkdir(parents=True)
    artifact_path = outputs_dir / "report.md"
    artifact_path.write_text("ok")

    monkeypatch.setattr(
        present_file_tool_module,
        "get_paths",
        lambda: SimpleNamespace(resolve_workspace_virtual_path=lambda workspace_id, path: artifact_path),
    )
    monkeypatch.setattr(
        present_file_tool_module,
        "get_app_config",
        lambda: SimpleNamespace(uploads=SimpleNamespace(oss=SimpleNamespace(bucket="demo-bucket"))),
    )
    result = present_file_tool_module.present_file_tool.func(
        runtime=_make_runtime_with_workspace(str(outputs_dir)),
        filepaths=[str(artifact_path)],
        tool_call_id="tc-1",
    )

    assert result.update["artifacts"] == {"/mnt/user-data/outputs/report.md": "oss://demo-bucket/workspaces/workspace-1/outputs/report.md"}
    assert result.update["messages"][0].content == "Successfully presented files"


def test_present_files_returns_oss_uri_for_virtual_outputs_path(tmp_path, monkeypatch):
    outputs_dir = tmp_path / "threads" / "thread-1" / "user-data" / "outputs"
    outputs_dir.mkdir(parents=True)
    artifact_path = outputs_dir / "summary.json"
    artifact_path.write_text("{}")

    monkeypatch.setattr(
        present_file_tool_module,
        "get_paths",
        lambda: SimpleNamespace(resolve_workspace_virtual_path=lambda workspace_id, path: artifact_path),
    )
    monkeypatch.setattr(
        present_file_tool_module,
        "get_app_config",
        lambda: SimpleNamespace(uploads=SimpleNamespace(oss=SimpleNamespace(bucket="demo-bucket"))),
    )

    result = present_file_tool_module.present_file_tool.func(
        runtime=_make_runtime_with_workspace(str(outputs_dir)),
        filepaths=["/mnt/user-data/outputs/summary.json"],
        tool_call_id="tc-2",
    )

    assert result.update["artifacts"] == {"/mnt/user-data/outputs/summary.json": "oss://demo-bucket/workspaces/workspace-1/outputs/summary.json"}


def test_present_files_returns_oss_uri_for_workspace_outputs(tmp_path, monkeypatch):
    outputs_dir = tmp_path / "threads" / "thread-1" / "user-data" / "outputs"
    outputs_dir.mkdir(parents=True)
    artifact_path = outputs_dir / "chart.png"
    artifact_path.write_bytes(b"png")

    monkeypatch.setattr(
        present_file_tool_module,
        "get_paths",
        lambda: SimpleNamespace(resolve_workspace_virtual_path=lambda workspace_id, path: artifact_path),
    )
    monkeypatch.setattr(
        present_file_tool_module,
        "get_app_config",
        lambda: SimpleNamespace(uploads=SimpleNamespace(oss=SimpleNamespace(bucket="demo-bucket"))),
    )

    result = present_file_tool_module.present_file_tool.func(
        runtime=_make_runtime_with_workspace(str(outputs_dir)),
        filepaths=["/mnt/user-data/outputs/chart.png"],
        tool_call_id="tc-oss",
    )

    assert result.update["artifacts"] == {"/mnt/user-data/outputs/chart.png": "oss://demo-bucket/workspaces/workspace-1/outputs/chart.png"}


def test_present_files_rejects_paths_outside_outputs(tmp_path):
    outputs_dir = tmp_path / "threads" / "thread-1" / "user-data" / "outputs"
    workspace_dir = tmp_path / "threads" / "thread-1" / "user-data" / "workspace"
    outputs_dir.mkdir(parents=True)
    workspace_dir.mkdir(parents=True)
    leaked_path = workspace_dir / "notes.txt"
    leaked_path.write_text("leak")

    result = present_file_tool_module.present_file_tool.func(
        runtime=_make_runtime(str(outputs_dir)),
        filepaths=[str(leaked_path)],
        tool_call_id="tc-3",
    )

    assert "artifacts" not in result.update
    assert result.update["messages"][0].content == f"Error: Only files in /mnt/user-data/outputs can be presented: {leaked_path}"
