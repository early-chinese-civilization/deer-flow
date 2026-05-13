import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from deerflow.sandbox import skill_scope as skill_scope_module
from deerflow.sandbox.exceptions import SandboxRuntimeError
from deerflow.sandbox.skill_scope import derive_skill_scope_from_runtime
from deerflow.sandbox.tools import (
    VIRTUAL_PATH_PREFIX,
    _apply_cwd_prefix,
    _is_acp_workspace_path,
    _is_skills_path,
    _reject_path_traversal,
    _resolve_acp_workspace_path,
    _resolve_and_validate_user_data_path,
    _resolve_skills_path,
    bash_tool,
    ls_tool,
    mask_local_paths_in_output,
    replace_virtual_path,
    replace_virtual_paths_in_command,
    skill_load_tool,
    str_replace_tool,
    validate_local_bash_command_paths,
    validate_local_tool_path,
    write_file_tool,
)
from deerflow.skills.hashing import hash_skill_file_manifest

_THREAD_DATA = {
    "workspace_path": "/tmp/deer-flow/threads/t1/user-data/workspace",
    "uploads_path": "/tmp/deer-flow/threads/t1/user-data/uploads",
    "outputs_path": "/tmp/deer-flow/threads/t1/user-data/outputs",
}


# ---------- replace_virtual_path ----------


def test_replace_virtual_path_maps_virtual_root_and_subpaths() -> None:
    assert Path(replace_virtual_path("/mnt/user-data/workspace/a.txt", _THREAD_DATA)).as_posix() == "/tmp/deer-flow/threads/t1/user-data/workspace/a.txt"
    assert Path(replace_virtual_path("/mnt/user-data", _THREAD_DATA)).as_posix() == "/tmp/deer-flow/threads/t1/user-data"


# ---------- mask_local_paths_in_output ----------


def test_mask_local_paths_in_output_hides_host_paths() -> None:
    output = "Created: /tmp/deer-flow/threads/t1/user-data/workspace/result.txt"
    masked = mask_local_paths_in_output(output, _THREAD_DATA)

    assert "/tmp/deer-flow/threads/t1/user-data" not in masked
    assert "/mnt/user-data/workspace/result.txt" in masked


def test_mask_local_paths_in_output_hides_skills_host_paths() -> None:
    """Skills host paths in bash output should be masked to virtual paths."""
    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value="/home/user/deer-flow/skills"),
    ):
        output = "Reading: /home/user/deer-flow/skills/public/bootstrap/SKILL.md"
        masked = mask_local_paths_in_output(output, _THREAD_DATA)

        assert "/home/user/deer-flow/skills" not in masked
        assert "/mnt/skills/public/bootstrap/SKILL.md" in masked


# ---------- _reject_path_traversal ----------


def test_reject_path_traversal_blocks_dotdot() -> None:
    with pytest.raises(PermissionError, match="path traversal"):
        _reject_path_traversal("/mnt/user-data/workspace/../../etc/passwd")


def test_reject_path_traversal_blocks_dotdot_at_start() -> None:
    with pytest.raises(PermissionError, match="path traversal"):
        _reject_path_traversal("../etc/passwd")


def test_reject_path_traversal_blocks_backslash_dotdot() -> None:
    with pytest.raises(PermissionError, match="path traversal"):
        _reject_path_traversal("/mnt/user-data/workspace\\..\\..\\etc\\passwd")


def test_reject_path_traversal_allows_normal_paths() -> None:
    # Should not raise
    _reject_path_traversal("/mnt/user-data/workspace/file.txt")
    _reject_path_traversal("/mnt/skills/public/bootstrap/SKILL.md")
    _reject_path_traversal("/mnt/user-data/workspace/sub/dir/file.py")


# ---------- validate_local_tool_path ----------


def test_validate_local_tool_path_rejects_non_virtual_path() -> None:
    with pytest.raises(PermissionError, match="Only paths under"):
        validate_local_tool_path("/Users/someone/config.yaml", _THREAD_DATA)


def test_validate_local_tool_path_rejects_bare_virtual_root() -> None:
    """The bare /mnt/user-data root without trailing slash is not a valid sub-path."""
    with pytest.raises(PermissionError, match="Only paths under"):
        validate_local_tool_path(VIRTUAL_PATH_PREFIX, _THREAD_DATA)


def test_validate_local_tool_path_allows_user_data_paths() -> None:
    # Should not raise — user-data paths are always allowed
    validate_local_tool_path(f"{VIRTUAL_PATH_PREFIX}/workspace/file.txt", _THREAD_DATA)
    validate_local_tool_path(f"{VIRTUAL_PATH_PREFIX}/uploads/doc.pdf", _THREAD_DATA)
    validate_local_tool_path(f"{VIRTUAL_PATH_PREFIX}/outputs/result.csv", _THREAD_DATA)


def test_validate_local_tool_path_allows_user_data_write() -> None:
    # read_only=False (default) should still work for user-data paths
    validate_local_tool_path(f"{VIRTUAL_PATH_PREFIX}/workspace/file.txt", _THREAD_DATA, read_only=False)


def test_validate_local_tool_path_rejects_traversal_in_user_data() -> None:
    """Path traversal via .. in user-data paths must be rejected."""
    with pytest.raises(PermissionError, match="path traversal"):
        validate_local_tool_path(f"{VIRTUAL_PATH_PREFIX}/workspace/../../etc/passwd", _THREAD_DATA)


def test_validate_local_tool_path_rejects_traversal_in_skills() -> None:
    """Path traversal via .. in skills paths must be rejected."""
    with patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"):
        with pytest.raises(PermissionError, match="path traversal"):
            validate_local_tool_path("/mnt/skills/../../etc/passwd", _THREAD_DATA, read_only=True)


def test_validate_local_tool_path_rejects_none_thread_data() -> None:
    """Missing thread_data should raise SandboxRuntimeError."""
    with pytest.raises(SandboxRuntimeError):
        validate_local_tool_path(f"{VIRTUAL_PATH_PREFIX}/workspace/file.txt", None)


# ---------- _resolve_skills_path ----------


def test_resolve_skills_path_resolves_correctly() -> None:
    """Skills virtual path should resolve to host path."""
    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value="/home/user/deer-flow/skills"),
    ):
        resolved = _resolve_skills_path("/mnt/skills/public/bootstrap/SKILL.md")
        assert resolved == "/home/user/deer-flow/skills/public/bootstrap/SKILL.md"


def test_resolve_skills_path_resolves_root() -> None:
    """Skills container root should resolve to host skills directory."""
    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value="/home/user/deer-flow/skills"),
    ):
        resolved = _resolve_skills_path("/mnt/skills")
        assert resolved == "/home/user/deer-flow/skills"


def test_resolve_skills_path_raises_when_not_configured() -> None:
    """Should raise FileNotFoundError when skills directory is not available."""
    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value=None),
    ):
        with pytest.raises(FileNotFoundError, match="Skills directory not available"):
            _resolve_skills_path("/mnt/skills/public/bootstrap/SKILL.md")


# ---------- _resolve_and_validate_user_data_path ----------


def test_resolve_and_validate_user_data_path_resolves_correctly(tmp_path: Path) -> None:
    """Resolved path should land inside the correct thread directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    thread_data = {
        "workspace_path": str(workspace),
        "uploads_path": str(tmp_path / "uploads"),
        "outputs_path": str(tmp_path / "outputs"),
    }
    resolved = _resolve_and_validate_user_data_path("/mnt/user-data/workspace/hello.txt", thread_data)
    assert resolved == str(workspace / "hello.txt")


def test_resolve_and_validate_user_data_path_blocks_traversal(tmp_path: Path) -> None:
    """Even after resolution, path must stay within allowed roots."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    thread_data = {
        "workspace_path": str(workspace),
        "uploads_path": str(tmp_path / "uploads"),
        "outputs_path": str(tmp_path / "outputs"),
    }
    # This path resolves outside the allowed roots
    with pytest.raises(PermissionError):
        _resolve_and_validate_user_data_path("/mnt/user-data/workspace/../../../etc/passwd", thread_data)


# ---------- replace_virtual_paths_in_command ----------


def test_replace_virtual_paths_in_command_replaces_skills_paths() -> None:
    """Skills virtual paths in commands should be resolved to host paths."""
    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value="/home/user/deer-flow/skills"),
    ):
        cmd = "cat /mnt/skills/public/bootstrap/SKILL.md"
        result = replace_virtual_paths_in_command(cmd, _THREAD_DATA)
        assert "/mnt/skills" not in result
        assert "/home/user/deer-flow/skills/public/bootstrap/SKILL.md" in result


def test_replace_virtual_paths_in_command_replaces_both() -> None:
    """Both user-data and skills paths should be replaced in the same command."""
    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value="/home/user/skills"),
    ):
        cmd = "cat /mnt/skills/public/SKILL.md > /mnt/user-data/workspace/out.txt"
        result = replace_virtual_paths_in_command(cmd, _THREAD_DATA)
        assert "/mnt/skills" not in result
        assert "/mnt/user-data" not in result
        assert "/home/user/skills/public/SKILL.md" in result
        assert "/tmp/deer-flow/threads/t1/user-data/workspace/out.txt" in result


# ---------- validate_local_bash_command_paths ----------


def test_validate_local_bash_command_paths_blocks_host_paths() -> None:
    with pytest.raises(PermissionError, match="Unsafe absolute paths"):
        validate_local_bash_command_paths("cat /etc/passwd", _THREAD_DATA)


def test_validate_local_bash_command_paths_allows_virtual_and_system_paths() -> None:
    validate_local_bash_command_paths(
        "/bin/echo ok > /mnt/user-data/workspace/out.txt && cat /dev/null",
        _THREAD_DATA,
    )


def test_validate_local_bash_command_paths_blocks_traversal_in_user_data() -> None:
    """Bash commands with traversal in user-data paths should be blocked."""
    with pytest.raises(PermissionError, match="path traversal"):
        validate_local_bash_command_paths(
            "cat /mnt/user-data/workspace/../../etc/passwd",
            _THREAD_DATA,
        )


def test_validate_local_bash_command_paths_blocks_traversal_in_skills() -> None:
    """Bash commands with traversal in skills paths should be blocked."""
    with patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"):
        with pytest.raises(PermissionError, match="path traversal"):
            validate_local_bash_command_paths(
                "cat /mnt/skills/../../etc/passwd",
                _THREAD_DATA,
            )


def test_bash_tool_rejects_host_bash_when_local_sandbox_default(monkeypatch) -> None:
    runtime = SimpleNamespace(
        state={"sandbox": {"sandbox_id": "local"}, "thread_data": _THREAD_DATA.copy()},
        context={"thread_id": "thread-1"},
    )

    monkeypatch.setattr(
        "deerflow.sandbox.tools.ensure_sandbox_initialized",
        lambda runtime: SimpleNamespace(execute_command=lambda command: pytest.fail("host bash should not execute")),
    )
    monkeypatch.setattr("deerflow.sandbox.tools.is_host_bash_allowed", lambda: False)

    result = bash_tool.func(
        runtime=runtime,
        description="run command",
        command="/bin/echo hello",
    )

    assert "Host bash execution is disabled" in result


def test_bash_tool_remote_reuses_initialized_sandbox(monkeypatch) -> None:
    executed_commands: list[str] = []
    runtime = SimpleNamespace(
        state={"sandbox": {"sandbox_id": "remote", "skill_scope": "public"}, "thread_data": _THREAD_DATA.copy()},
        context={"thread_id": "thread-1"},
    )

    monkeypatch.setattr(
        "deerflow.sandbox.tools.ensure_sandbox_initialized",
        lambda runtime: SimpleNamespace(execute_command=lambda command: executed_commands.append(command) or "remote ok"),
    )
    monkeypatch.setattr(
        "deerflow.sandbox.tools.get_sandbox_provider",
        lambda: SimpleNamespace(
            acquire_ephemeral=lambda **kwargs: pytest.fail("ephemeral acquire should not be used"),
            destroy=lambda _sandbox_id: pytest.fail("sandbox destroy should not be used"),
        ),
    )

    result = bash_tool.func(
        runtime=runtime,
        description="run command",
        command="cat /mnt/skills/sql-review/SKILL.md",
    )

    assert result == "remote ok"
    assert executed_commands == ["cat /mnt/skills/sql-review/SKILL.md"]


# ---------- Skills path tests ----------


def test_is_skills_path_recognises_default_prefix() -> None:
    with patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"):
        assert _is_skills_path("/mnt/skills") is True
        assert _is_skills_path("/mnt/skills/public/bootstrap/SKILL.md") is True
        assert _is_skills_path("/mnt/skills-extra/foo") is False
        assert _is_skills_path("/mnt/user-data/workspace") is False


def test_validate_local_tool_path_allows_skills_read_only() -> None:
    """read_file / ls should be able to access /mnt/skills paths."""
    with patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"):
        # Should not raise
        validate_local_tool_path(
            "/mnt/skills/public/bootstrap/SKILL.md",
            _THREAD_DATA,
            read_only=True,
        )


def test_validate_local_tool_path_blocks_skills_write() -> None:
    """write_file / str_replace must NOT write to skills paths."""
    with patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"):
        with pytest.raises(PermissionError, match="Write access to skills path is not allowed"):
            validate_local_tool_path(
                "/mnt/skills/public/bootstrap/SKILL.md",
                _THREAD_DATA,
                read_only=False,
            )


def test_validate_local_bash_command_paths_allows_skills_path() -> None:
    """bash commands referencing /mnt/skills should be allowed."""
    with patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"):
        validate_local_bash_command_paths(
            "cat /mnt/skills/public/bootstrap/SKILL.md",
            _THREAD_DATA,
        )


def test_local_bash_skills_paths_use_runtime_manifest_allowlist(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    artifact_dir = skills_root / "artifacts" / "skills" / "1" / "v1" / "probe-skill"
    public_dir = skills_root / "public" / "probe-skill"
    artifact_dir.mkdir(parents=True)
    public_dir.mkdir(parents=True)
    (artifact_dir / "SKILL.md").write_text("authorized", encoding="utf-8")
    file_manifest_hash = hash_skill_file_manifest(artifact_dir)
    (public_dir / "SKILL.md").write_text("public latest", encoding="utf-8")
    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "skills": [
                    {
                        "name": "probe-skill",
                        "artifact_uri": "artifacts/skills/1/v1/probe-skill",
                        "file_path": "artifacts/skills/1/v1/probe-skill",
                        "virtual_path": "/mnt/skills/probe-skill/SKILL.md",
                        "skill_version_id": 101,
                        "file_manifest_hash": file_manifest_hash,
                    }
                ]
            }
        },
        config={},
    )

    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value=str(skills_root)),
    ):
        validate_local_bash_command_paths(
            "cat /mnt/skills/probe-skill/SKILL.md",
            _THREAD_DATA,
            runtime,
        )
        resolved = replace_virtual_paths_in_command(
            "cat /mnt/skills/probe-skill/SKILL.md",
            _THREAD_DATA,
            runtime,
        )
        with pytest.raises(PermissionError, match="not available"):
            validate_local_bash_command_paths(
                "cat /mnt/skills/public/probe-skill/SKILL.md",
                _THREAD_DATA,
                runtime,
            )

    assert str(artifact_dir / "SKILL.md") in resolved
    assert "public" not in resolved


def test_skill_load_uses_runtime_virtual_mapping_for_manifest_artifact(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "artifacts" / "skills" / "1" / "v1" / "sql-review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("review sql", encoding="utf-8")
    file_manifest_hash = hash_skill_file_manifest(skill_dir)

    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "skills": [
                    {
                        "name": "sql-review",
                        "artifact_uri": "artifacts/skills/1/v1/sql-review",
                        "file_path": "artifacts/skills/1/v1/sql-review",
                        "virtual_path": "/mnt/skills/sql-review/SKILL.md",
                        "skill_version_id": 1,
                        "file_manifest_hash": file_manifest_hash,
                    }
                ]
            }
        },
        config={},
    )

    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value=str(skills_root)),
    ):
        result = skill_load_tool.func(
            runtime=runtime,
            description="load skill",
            path="/mnt/skills/sql-review/SKILL.md",
        )

    assert result == "review sql"


def test_skill_load_rejects_paths_not_in_runtime_allowlist(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "artifacts" / "skills" / "1" / "v1" / "sql-review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("review sql", encoding="utf-8")
    file_manifest_hash = hash_skill_file_manifest(skill_dir)

    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "skills": [
                    {
                        "name": "sql-review",
                        "artifact_uri": "artifacts/skills/1/v1/sql-review",
                        "file_path": "artifacts/skills/1/v1/sql-review",
                        "virtual_path": "/mnt/skills/sql-review/SKILL.md",
                        "skill_version_id": 1,
                        "file_manifest_hash": file_manifest_hash,
                    }
                ]
            }
        },
        config={},
    )

    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value=str(skills_root)),
    ):
        result = skill_load_tool.func(
            runtime=runtime,
            description="load missing skill",
            path="/mnt/skills/other-skill/SKILL.md",
        )

    assert "Permission denied" in result


def test_skill_load_rejects_manifest_artifact_traversal_to_public_latest(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    public_dir = skills_root / "public" / "sql-review"
    public_dir.mkdir(parents=True)
    (public_dir / "SKILL.md").write_text("public latest", encoding="utf-8")

    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "skills": [
                    {
                        "name": "sql-review",
                        "artifact_uri": "artifacts/../public/sql-review",
                        "file_path": "artifacts/../public/sql-review",
                        "virtual_path": "/mnt/skills/sql-review/SKILL.md",
                        "skill_version_id": 1,
                        "file_manifest_hash": "expected-file-manifest-hash",
                    }
                ]
            }
        },
        config={},
    )

    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value=str(skills_root)),
    ):
        result = skill_load_tool.func(
            runtime=runtime,
            description="load skill",
            path="/mnt/skills/sql-review/SKILL.md",
        )

    assert "public latest" not in result
    assert "Error:" in result


def test_ls_uses_runtime_virtual_mapping_for_skill_directories(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "artifacts" / "skills" / "2" / "v1" / "table-tools"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("table skill", encoding="utf-8")
    (skill_dir / "notes.md").write_text("notes", encoding="utf-8")
    file_manifest_hash = hash_skill_file_manifest(skill_dir)

    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "skills": [
                    {
                        "name": "table-tools",
                        "artifact_uri": "artifacts/skills/2/v1/table-tools",
                        "file_path": "artifacts/skills/2/v1/table-tools",
                        "virtual_path": "/mnt/skills/table-tools/SKILL.md",
                        "skill_version_id": 1,
                        "file_manifest_hash": file_manifest_hash,
                    }
                ]
            }
        },
        config={},
    )

    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value=str(skills_root)),
    ):
        result = ls_tool.func(
            runtime=runtime,
            description="list skill files",
            path="/mnt/skills/table-tools",
        )

    assert "/mnt/skills/table-tools/SKILL.md" in result
    assert "/mnt/skills/table-tools/notes.md" in result


def test_ls_skills_root_lists_runtime_skill_directories() -> None:
    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "skills": [
                    {
                        "name": "chart-visualization",
                        "artifact_uri": "artifacts/skills/1/v1/chart-visualization",
                        "file_path": "artifacts/skills/1/v1/chart-visualization",
                        "virtual_path": "/mnt/skills/chart-visualization/SKILL.md",
                        "skill_version_id": 1,
                        "file_manifest_hash": "chart-hash",
                    },
                    {
                        "name": "table-tools",
                        "artifact_uri": "artifacts/skills/2/v1/table-tools",
                        "file_path": "artifacts/skills/2/v1/table-tools",
                        "virtual_path": "/mnt/skills/table-tools/SKILL.md",
                        "skill_version_id": 2,
                        "file_manifest_hash": "table-hash",
                    },
                ]
            }
        },
        config={},
    )

    with patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"):
        result = ls_tool.func(
            runtime=runtime,
            description="list skill roots",
            path="/mnt/skills",
        )

    assert "/mnt/skills/chart-visualization/" in result
    assert "/mnt/skills/table-tools/" in result


def test_derive_skill_scope_returns_none_when_runtime_skills_are_missing() -> None:
    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={"runtime_agent": {"user_id": 7, "skills": []}},
        config={},
    )

    assert derive_skill_scope_from_runtime(runtime) is None


def test_derive_skill_scope_materializes_bundle_for_manifest_artifacts(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    artifact_dir = skills_root / "artifacts" / "skills" / "1" / "v1" / "probe-skill"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "SKILL.md").write_text("authorized", encoding="utf-8")
    file_manifest_hash = hash_skill_file_manifest(artifact_dir)
    (skills_root / "public" / "probe-skill").mkdir(parents=True)
    (skills_root / "public" / "probe-skill" / "SKILL.md").write_text("public latest", encoding="utf-8")

    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "user_id": 7,
                "skills": [
                    {
                        "name": "probe-skill",
                        "artifact_uri": "artifacts/skills/1/v1/probe-skill",
                        "file_path": "artifacts/skills/1/v1/probe-skill",
                        "virtual_path": "/mnt/skills/probe-skill/SKILL.md",
                        "skill_version_id": 101,
                        "content_hash": "hash-v1",
                        "file_manifest_hash": file_manifest_hash,
                    }
                ],
            }
        },
        config={},
    )

    with patch(
        "deerflow.sandbox.skill_scope._get_skills_root_path",
        return_value=skills_root,
    ):
        scope = derive_skill_scope_from_runtime(runtime)

    assert scope is not None
    assert scope.startswith(".runtime-skill-bundles/")
    bundle_dir = skills_root / scope
    assert (bundle_dir / "probe-skill" / "SKILL.md").read_text(encoding="utf-8") == "authorized"
    assert not (bundle_dir / "public" / "probe-skill" / "SKILL.md").exists()


def test_derive_skill_scope_materializes_bundle_for_terminal_skill_version_path(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    artifact_uri = "12345678-1234-5678-1234-567812345678/1"
    artifact_dir = skills_root / artifact_uri
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "SKILL.md").write_text("terminal authorized", encoding="utf-8")
    file_manifest_hash = hash_skill_file_manifest(artifact_dir)

    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "user_id": 7,
                "skills": [
                    {
                        "name": "probe-skill",
                        "artifact_uri": artifact_uri,
                        "file_path": artifact_uri,
                        "virtual_path": "/mnt/skills/probe-skill/SKILL.md",
                        "skill_version_id": 101,
                        "content_hash": "hash-v1",
                        "file_manifest_hash": file_manifest_hash,
                    }
                ],
            }
        },
        config={},
    )

    with patch(
        "deerflow.sandbox.skill_scope._get_skills_root_path",
        return_value=skills_root,
    ):
        scope = derive_skill_scope_from_runtime(runtime)

    assert scope is not None
    assert (skills_root / scope / "probe-skill" / "SKILL.md").read_text(encoding="utf-8") == "terminal authorized"


def test_derive_skill_scope_reuses_system_skill_bundle_for_repeated_direct_bindings(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    artifact_dir = skills_root / "artifacts" / "skills" / "1" / "v1" / "system-skill"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "SKILL.md").write_text("system authorized", encoding="utf-8")
    file_manifest_hash = hash_skill_file_manifest(artifact_dir)

    def runtime_for_user(user_id: int) -> SimpleNamespace:
        return SimpleNamespace(
            state={"thread_data": _THREAD_DATA.copy()},
            context={
                "runtime_agent": {
                    "user_id": user_id,
                    "skills": [
                        {
                            "name": "system-skill",
                            "artifact_uri": "artifacts/skills/1/v1/system-skill",
                            "file_path": "artifacts/skills/1/v1/system-skill",
                            "virtual_path": "/mnt/skills/system-skill/SKILL.md",
                            "skill_version_id": 101,
                            "system_skill_definition_id": 1,
                            "system_skill_version_id": 101,
                            "source_kind": "system",
                            "binding_kind": "system",
                            "content_hash": "hash-v1",
                            "file_manifest_hash": file_manifest_hash,
                        }
                    ],
                }
            },
            config={},
        )

    with patch(
        "deerflow.sandbox.skill_scope._get_skills_root_path",
        return_value=skills_root,
    ):
        first_scope = derive_skill_scope_from_runtime(runtime_for_user(7))
        second_scope = derive_skill_scope_from_runtime(runtime_for_user(9))

    assert first_scope == second_scope
    assert len([path for path in (skills_root / ".runtime-skill-bundles").iterdir() if path.is_dir()]) == 1
    assert (skills_root / first_scope / "system-skill" / "SKILL.md").read_text(encoding="utf-8") == "system authorized"


def test_derive_skill_scope_prunes_stale_runtime_skill_bundles(tmp_path, monkeypatch) -> None:
    skills_root = tmp_path / "skills"
    artifact_dir = skills_root / "artifacts" / "skills" / "1" / "v1" / "probe-skill"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "SKILL.md").write_text("authorized", encoding="utf-8")
    file_manifest_hash = hash_skill_file_manifest(artifact_dir)

    stale_bundle = skills_root / ".runtime-skill-bundles" / "stale-bundle"
    stale_bundle.mkdir(parents=True)
    (stale_bundle / ".deerflow-runtime-bundle.json").write_text("{}", encoding="utf-8")
    stale_time = time.time() - 10
    (stale_bundle / ".deerflow-runtime-bundle.json").touch()
    os.utime(stale_bundle / ".deerflow-runtime-bundle.json", (stale_time, stale_time))
    os.utime(stale_bundle, (stale_time, stale_time))

    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "user_id": 7,
                "skills": [
                    {
                        "name": "probe-skill",
                        "artifact_uri": "artifacts/skills/1/v1/probe-skill",
                        "file_path": "artifacts/skills/1/v1/probe-skill",
                        "virtual_path": "/mnt/skills/probe-skill/SKILL.md",
                        "skill_version_id": 101,
                        "content_hash": "hash-v1",
                        "file_manifest_hash": file_manifest_hash,
                    }
                ],
            }
        },
        config={},
    )

    monkeypatch.setattr(skill_scope_module, "_RUNTIME_BUNDLE_RETENTION_SECONDS", 1)
    with patch(
        "deerflow.sandbox.skill_scope._get_skills_root_path",
        return_value=skills_root,
    ):
        current_scope = derive_skill_scope_from_runtime(runtime)

    assert current_scope is not None
    assert not stale_bundle.exists()
    assert (skills_root / current_scope / "probe-skill" / "SKILL.md").exists()


def test_derive_skill_scope_rejects_missing_manifest_artifact(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "user_id": 7,
                "skills": [
                    {
                        "name": "probe-skill",
                        "artifact_uri": "artifacts/skills/1/missing/probe-skill",
                        "file_path": "artifacts/skills/1/missing/probe-skill",
                        "virtual_path": "/mnt/skills/probe-skill/SKILL.md",
                        "skill_version_id": 101,
                        "content_hash": "hash-v1",
                        "file_manifest_hash": "expected-file-manifest-hash",
                    }
                ],
            }
        },
        config={},
    )

    with patch(
        "deerflow.sandbox.skill_scope._get_skills_root_path",
        return_value=skills_root,
    ):
        with pytest.raises(SandboxRuntimeError, match="artifact is missing"):
            derive_skill_scope_from_runtime(runtime)


def test_derive_skill_scope_rejects_artifact_file_manifest_hash_mismatch(tmp_path) -> None:
    skills_root = tmp_path / "skills"
    artifact_dir = skills_root / "artifacts" / "skills" / "1" / "v1" / "probe-skill"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "SKILL.md").write_text("authorized", encoding="utf-8")

    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "user_id": 7,
                "skills": [
                    {
                        "name": "probe-skill",
                        "artifact_uri": "artifacts/skills/1/v1/probe-skill",
                        "file_path": "artifacts/skills/1/v1/probe-skill",
                        "virtual_path": "/mnt/skills/probe-skill/SKILL.md",
                        "skill_version_id": 101,
                        "content_hash": "hash-v1",
                        "file_manifest_hash": "wrong-file-manifest-hash",
                    }
                ],
            }
        },
        config={},
    )

    with patch(
        "deerflow.sandbox.skill_scope._get_skills_root_path",
        return_value=skills_root,
    ):
        with pytest.raises(SandboxRuntimeError, match="file manifest hash mismatch"):
            derive_skill_scope_from_runtime(runtime)


def test_derive_skill_scope_rejects_public_latest_artifact_uri() -> None:
    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "user_id": 9,
                "skills": [
                    {
                        "name": "chart-visualization",
                        "artifact_uri": "public/chart-visualization",
                        "file_path": "public/chart-visualization",
                        "virtual_path": "/mnt/skills/chart-visualization/SKILL.md",
                        "skill_version_id": 1,
                    }
                ],
            }
        },
        config={},
    )

    with pytest.raises(SandboxRuntimeError, match="immutable version storage scope"):
        derive_skill_scope_from_runtime(runtime)


def test_derive_skill_scope_rejects_private_latest_artifact_uri() -> None:
    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "user_id": 7,
                "skills": [
                    {
                        "name": "table-tools",
                        "artifact_uri": "7/table-tools",
                        "file_path": "7/table-tools",
                        "virtual_path": "/mnt/skills/table-tools/SKILL.md",
                        "skill_version_id": 1,
                    }
                ],
            }
        },
        config={},
    )

    with pytest.raises(SandboxRuntimeError, match="immutable version storage scope"):
        derive_skill_scope_from_runtime(runtime)


@pytest.mark.parametrize(
    "artifact_uri",
    [
        "artifacts/../public/probe-skill",
        "artifacts/legacy/skills/legacy-id/probe-skill",
    ],
)
def test_derive_skill_scope_rejects_non_runtime_artifact_uri(artifact_uri) -> None:
    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "user_id": 7,
                "skills": [
                    {
                        "name": "probe-skill",
                        "artifact_uri": artifact_uri,
                        "file_path": artifact_uri,
                        "virtual_path": "/mnt/skills/probe-skill/SKILL.md",
                        "skill_version_id": 1,
                    },
                ],
            }
        },
        config={},
    )

    with pytest.raises(SandboxRuntimeError, match="immutable version storage scope"):
        derive_skill_scope_from_runtime(runtime)


def test_derive_skill_scope_rejects_missing_skill_version_id() -> None:
    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "user_id": 7,
                "skills": [
                    {
                        "name": "broken",
                        "artifact_uri": "artifacts/skills/1/v1/broken-skill",
                        "file_path": "artifacts/skills/1/v1/broken-skill",
                        "virtual_path": "/mnt/skills/broken/SKILL.md",
                    }
                ],
            }
        },
        config={},
    )

    with pytest.raises(SandboxRuntimeError, match="missing skill_version_id"):
        derive_skill_scope_from_runtime(runtime)


def test_derive_skill_scope_rejects_missing_artifact_uri() -> None:
    runtime = SimpleNamespace(
        state={"thread_data": _THREAD_DATA.copy()},
        context={
            "runtime_agent": {
                "user_id": 9,
                "skills": [
                    {
                        "name": "table-tools",
                        "file_path": "7/table-tools",
                        "virtual_path": "/mnt/skills/table-tools/SKILL.md",
                        "skill_version_id": 1,
                    }
                ],
            }
        },
        config={},
    )

    with pytest.raises(SandboxRuntimeError, match="missing artifact_uri"):
        derive_skill_scope_from_runtime(runtime)


def test_validate_local_bash_command_paths_allows_urls() -> None:
    """URLs in bash commands should not be mistaken for absolute paths (issue #1385)."""
    # HTTPS URLs
    validate_local_bash_command_paths(
        "curl -X POST https://example.com/api/v1/risk/check",
        _THREAD_DATA,
    )
    # HTTP URLs
    validate_local_bash_command_paths(
        "curl http://localhost:8080/health",
        _THREAD_DATA,
    )
    # URLs with query strings
    validate_local_bash_command_paths(
        "curl https://api.example.com/v2/search?q=test",
        _THREAD_DATA,
    )
    # FTP URLs
    validate_local_bash_command_paths(
        "curl ftp://ftp.example.com/pub/file.tar.gz",
        _THREAD_DATA,
    )
    # URL mixed with valid virtual path
    validate_local_bash_command_paths(
        "curl https://example.com/data -o /mnt/user-data/workspace/data.json",
        _THREAD_DATA,
    )


def test_validate_local_bash_command_paths_blocks_file_urls() -> None:
    """file:// URLs should be treated as unsafe and blocked."""
    with pytest.raises(PermissionError):
        validate_local_bash_command_paths("curl file:///etc/passwd", _THREAD_DATA)


def test_validate_local_bash_command_paths_blocks_file_urls_case_insensitive() -> None:
    """file:// URL detection should be case-insensitive."""
    with pytest.raises(PermissionError):
        validate_local_bash_command_paths("curl FILE:///etc/shadow", _THREAD_DATA)


def test_validate_local_bash_command_paths_blocks_file_urls_mixed_with_valid() -> None:
    """file:// URLs should be blocked even when mixed with valid paths."""
    with pytest.raises(PermissionError):
        validate_local_bash_command_paths(
            "curl file:///etc/passwd -o /mnt/user-data/workspace/out.txt",
            _THREAD_DATA,
        )


def test_validate_local_bash_command_paths_still_blocks_other_paths() -> None:
    """Paths outside virtual and system prefixes must still be blocked."""
    with patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"):
        with pytest.raises(PermissionError, match="Unsafe absolute paths"):
            validate_local_bash_command_paths("cat /etc/shadow", _THREAD_DATA)


def test_validate_local_tool_path_skills_custom_container_path() -> None:
    """Skills with a custom container_path in config should also work."""
    with patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/custom/skills"):
        # Should not raise
        validate_local_tool_path(
            "/custom/skills/public/my-skill/SKILL.md",
            _THREAD_DATA,
            read_only=True,
        )

        # The default /mnt/skills should not match since container path is /custom/skills
        with pytest.raises(PermissionError, match="Only paths under"):
            validate_local_tool_path(
                "/mnt/skills/public/bootstrap/SKILL.md",
                _THREAD_DATA,
                read_only=True,
            )


# ---------- ACP workspace path tests ----------


def test_is_acp_workspace_path_recognises_prefix() -> None:
    assert _is_acp_workspace_path("/mnt/acp-workspace") is True
    assert _is_acp_workspace_path("/mnt/acp-workspace/hello.py") is True
    assert _is_acp_workspace_path("/mnt/acp-workspace-extra/foo") is False
    assert _is_acp_workspace_path("/mnt/user-data/workspace") is False


def test_validate_local_tool_path_allows_acp_workspace_read_only() -> None:
    """read_file / ls should be able to access /mnt/acp-workspace paths."""
    validate_local_tool_path(
        "/mnt/acp-workspace/hello_world.py",
        _THREAD_DATA,
        read_only=True,
    )


def test_validate_local_tool_path_blocks_acp_workspace_write() -> None:
    """write_file / str_replace must NOT write to ACP workspace paths."""
    with pytest.raises(PermissionError, match="Write access to ACP workspace is not allowed"):
        validate_local_tool_path(
            "/mnt/acp-workspace/hello_world.py",
            _THREAD_DATA,
            read_only=False,
        )


def test_validate_local_bash_command_paths_allows_acp_workspace() -> None:
    """bash commands referencing /mnt/acp-workspace should be allowed."""
    validate_local_bash_command_paths(
        "cp /mnt/acp-workspace/hello_world.py /mnt/user-data/outputs/hello_world.py",
        _THREAD_DATA,
    )


def test_validate_local_bash_command_paths_blocks_traversal_in_acp_workspace() -> None:
    """Bash commands with traversal in ACP workspace paths should be blocked."""
    with pytest.raises(PermissionError, match="path traversal"):
        validate_local_bash_command_paths(
            "cat /mnt/acp-workspace/../../etc/passwd",
            _THREAD_DATA,
        )


def test_resolve_acp_workspace_path_resolves_correctly(tmp_path: Path) -> None:
    """ACP workspace virtual path should resolve to host path."""
    acp_dir = tmp_path / "acp-workspace"
    acp_dir.mkdir()
    with patch("deerflow.sandbox.tools._get_acp_workspace_host_path", return_value=str(acp_dir)):
        resolved = _resolve_acp_workspace_path("/mnt/acp-workspace/hello.py")
        assert resolved == str(acp_dir / "hello.py")


def test_resolve_acp_workspace_path_resolves_root(tmp_path: Path) -> None:
    """ACP workspace root should resolve to host directory."""
    acp_dir = tmp_path / "acp-workspace"
    acp_dir.mkdir()
    with patch("deerflow.sandbox.tools._get_acp_workspace_host_path", return_value=str(acp_dir)):
        resolved = _resolve_acp_workspace_path("/mnt/acp-workspace")
        assert resolved == str(acp_dir)


def test_resolve_acp_workspace_path_raises_when_not_available() -> None:
    """Should raise FileNotFoundError when ACP workspace does not exist."""
    with patch("deerflow.sandbox.tools._get_acp_workspace_host_path", return_value=None):
        with pytest.raises(FileNotFoundError, match="ACP workspace directory not available"):
            _resolve_acp_workspace_path("/mnt/acp-workspace/hello.py")


def test_resolve_acp_workspace_path_blocks_traversal(tmp_path: Path) -> None:
    """Path traversal in ACP workspace paths must be rejected."""
    acp_dir = tmp_path / "acp-workspace"
    acp_dir.mkdir()
    with patch("deerflow.sandbox.tools._get_acp_workspace_host_path", return_value=str(acp_dir)):
        with pytest.raises(PermissionError, match="path traversal"):
            _resolve_acp_workspace_path("/mnt/acp-workspace/../../etc/passwd")


def test_replace_virtual_paths_in_command_replaces_acp_workspace() -> None:
    """ACP workspace virtual paths in commands should be resolved to host paths."""
    acp_host = "/home/user/.deer-flow/acp-workspace"
    with patch("deerflow.sandbox.tools._get_acp_workspace_host_path", return_value=acp_host):
        cmd = "cp /mnt/acp-workspace/hello.py /mnt/user-data/outputs/hello.py"
        result = replace_virtual_paths_in_command(cmd, _THREAD_DATA)
        assert "/mnt/acp-workspace" not in result
        assert f"{acp_host}/hello.py" in result
        assert "/tmp/deer-flow/threads/t1/user-data/outputs/hello.py" in result


def test_mask_local_paths_in_output_hides_acp_workspace_host_paths() -> None:
    """ACP workspace host paths in bash output should be masked to virtual paths."""
    acp_host = "/home/user/.deer-flow/acp-workspace"
    with patch("deerflow.sandbox.tools._get_acp_workspace_host_path", return_value=acp_host):
        output = f"Copied: {acp_host}/hello.py"
        masked = mask_local_paths_in_output(output, _THREAD_DATA)

        assert acp_host not in masked
        assert "/mnt/acp-workspace/hello.py" in masked


# ---------- _apply_cwd_prefix ----------


def test_apply_cwd_prefix_prepends_workspace() -> None:
    """Command is prefixed with cd <workspace> && when workspace_path is set."""
    result = _apply_cwd_prefix("ls -la", _THREAD_DATA)
    assert result.startswith("cd ")
    assert "ls -la" in result
    assert "/tmp/deer-flow/threads/t1/user-data/workspace" in result


def test_apply_cwd_prefix_no_thread_data() -> None:
    """Command is returned unchanged when thread_data is None."""
    assert _apply_cwd_prefix("ls -la", None) == "ls -la"


def test_apply_cwd_prefix_missing_workspace_path() -> None:
    """Command is returned unchanged when workspace_path is absent from thread_data."""
    assert _apply_cwd_prefix("ls -la", {}) == "ls -la"


def test_apply_cwd_prefix_quotes_path_with_spaces() -> None:
    """Workspace path containing spaces is properly shell-quoted."""
    thread_data = {**_THREAD_DATA, "workspace_path": "/tmp/my workspace/t1"}
    result = _apply_cwd_prefix("echo hello", thread_data)
    assert result == "cd '/tmp/my workspace/t1' && echo hello"


def test_validate_local_bash_command_paths_allows_mcp_filesystem_paths() -> None:
    """Bash commands referencing MCP filesystem server paths should be allowed."""
    from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig

    mock_config = ExtensionsConfig(
        mcp_servers={
            "filesystem": McpServerConfig(
                enabled=True,
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/mnt/d/workspace"],
            )
        }
    )
    with patch("deerflow.config.extensions_config.get_extensions_config", return_value=mock_config):
        # Should not raise - MCP filesystem paths are allowed
        validate_local_bash_command_paths("ls /mnt/d/workspace", _THREAD_DATA)
        validate_local_bash_command_paths("cat /mnt/d/workspace/subdir/file.txt", _THREAD_DATA)

        # Path traversal should still be blocked
        with pytest.raises(PermissionError, match="path traversal"):
            validate_local_bash_command_paths("cat /mnt/d/workspace/../../etc/passwd", _THREAD_DATA)

        # Disabled servers should not expose paths
        disabled_config = ExtensionsConfig(
            mcp_servers={
                "filesystem": McpServerConfig(
                    enabled=False,
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", "/mnt/d/workspace"],
                )
            }
        )
        with patch("deerflow.config.extensions_config.get_extensions_config", return_value=disabled_config):
            with pytest.raises(PermissionError, match="Unsafe absolute paths"):
                validate_local_bash_command_paths("ls /mnt/d/workspace", _THREAD_DATA)


def _thread_runtime_with_paths(base_dir: Path, thread_id: str = "thread-1") -> SimpleNamespace:
    workspace_dir = base_dir / "workspace"
    uploads_dir = base_dir / "uploads"
    outputs_dir = base_dir / "outputs"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        state={
            "thread_data": {
                "thread_id": thread_id,
                "workspace_id": thread_id,
                "workspace_path": str(workspace_dir),
                "uploads_path": str(uploads_dir),
                "outputs_path": str(outputs_dir),
            }
        },
        context={"thread_id": thread_id, "workspace_id": thread_id},
        config={},
    )


def test_str_replace_parallel_updates_should_preserve_both_edits(tmp_path: Path) -> None:
    runtimes = [
        _thread_runtime_with_paths(tmp_path / "shared", "thread-1"),
        _thread_runtime_with_paths(tmp_path / "shared", "thread-1"),
    ]
    shared_file = tmp_path / "shared" / "workspace" / "shared.txt"
    shared_file.write_text("alpha\nbeta\n", encoding="utf-8")
    failures: list[BaseException] = []

    def worker(runtime: SimpleNamespace, old_str: str, new_str: str) -> None:
        try:
            result = str_replace_tool.func(
                runtime=runtime,
                description="并发替换同一文件",
                path="/mnt/user-data/workspace/shared.txt",
                old_str=old_str,
                new_str=new_str,
            )
            assert result == "OK"
        except BaseException as exc:  # pragma: no cover - failure is asserted below
            failures.append(exc)

    threads = [
        threading.Thread(target=worker, args=(runtimes[0], "alpha", "ALPHA")),
        threading.Thread(target=worker, args=(runtimes[1], "beta", "BETA")),
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    content = shared_file.read_text(encoding="utf-8")
    assert "ALPHA" in content
    assert "BETA" in content


def test_str_replace_parallel_updates_across_runtimes_should_share_path_lock(tmp_path: Path) -> None:
    runtimes = [
        _thread_runtime_with_paths(tmp_path / "shared", "thread-1"),
        _thread_runtime_with_paths(tmp_path / "shared", "thread-2"),
    ]
    shared_file = tmp_path / "shared" / "workspace" / "shared.txt"
    shared_file.write_text("alpha\nbeta\n", encoding="utf-8")
    failures: list[BaseException] = []

    def worker(runtime: SimpleNamespace, old_str: str, new_str: str) -> None:
        try:
            result = str_replace_tool.func(
                runtime=runtime,
                description="跨运行时并发替换同一路径",
                path="/mnt/user-data/workspace/shared.txt",
                old_str=old_str,
                new_str=new_str,
            )
            assert result == "OK"
        except BaseException as exc:  # pragma: no cover - failure is asserted below
            failures.append(exc)

    threads = [
        threading.Thread(target=worker, args=(runtimes[0], "alpha", "ALPHA")),
        threading.Thread(target=worker, args=(runtimes[1], "beta", "BETA")),
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    content = shared_file.read_text(encoding="utf-8")
    assert "ALPHA" in content
    assert "BETA" in content


def test_str_replace_and_append_on_same_path_should_preserve_both_updates(tmp_path: Path) -> None:
    runtimes = [
        _thread_runtime_with_paths(tmp_path / "shared", "thread-1"),
        _thread_runtime_with_paths(tmp_path / "shared", "thread-1"),
    ]
    shared_file = tmp_path / "shared" / "workspace" / "shared.txt"
    shared_file.write_text("alpha\n", encoding="utf-8")
    failures: list[BaseException] = []

    def replace_worker() -> None:
        try:
            result = str_replace_tool.func(
                runtime=runtimes[0],
                description="替换旧内容",
                path="/mnt/user-data/workspace/shared.txt",
                old_str="alpha",
                new_str="ALPHA",
            )
            assert result == "OK"
        except BaseException as exc:  # pragma: no cover - failure is asserted below
            failures.append(exc)

    def append_worker() -> None:
        try:
            result = write_file_tool.func(
                runtime=runtimes[1],
                description="追加新内容",
                path="/mnt/user-data/workspace/shared.txt",
                content="tail\n",
                append=True,
            )
            assert result == "OK"
        except BaseException as exc:  # pragma: no cover - failure is asserted below
            failures.append(exc)

    replace_thread = threading.Thread(target=replace_worker)
    append_thread = threading.Thread(target=append_worker)

    replace_thread.start()
    append_thread.start()
    replace_thread.join()
    append_thread.join()

    assert failures == []
    assert shared_file.read_text(encoding="utf-8") == "ALPHA\ntail\n"
