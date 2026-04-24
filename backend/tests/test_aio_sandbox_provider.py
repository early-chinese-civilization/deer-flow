"""Tests for AioSandboxProvider mount helpers."""

import hashlib
import importlib
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from deerflow.config.paths import Paths, join_host_path

# ── ensure_thread_dirs ───────────────────────────────────────────────────────


def test_ensure_thread_dirs_creates_acp_workspace(tmp_path):
    """ACP workspace directory must be created alongside user-data dirs."""
    paths = Paths(base_dir=tmp_path)
    paths.ensure_thread_dirs("thread-1")

    assert (tmp_path / "threads" / "thread-1" / "user-data" / "workspace").exists()
    assert (tmp_path / "threads" / "thread-1" / "user-data" / "uploads").exists()
    assert (tmp_path / "threads" / "thread-1" / "user-data" / "outputs").exists()
    assert (tmp_path / "threads" / "thread-1" / "acp-workspace").exists()


def test_ensure_thread_dirs_acp_workspace_is_world_writable(tmp_path):
    """ACP workspace must be chmod 0o777 so the ACP subprocess can write into it."""
    paths = Paths(base_dir=tmp_path)
    paths.ensure_thread_dirs("thread-2")

    acp_dir = tmp_path / "threads" / "thread-2" / "acp-workspace"
    mode = oct(acp_dir.stat().st_mode & 0o777)
    assert mode == oct(0o777)


def test_host_thread_dir_rejects_invalid_thread_id(tmp_path):
    paths = Paths(base_dir=tmp_path)

    with pytest.raises(ValueError, match="Invalid thread_id"):
        paths.host_thread_dir("../escape")


# ── _get_thread_mounts ───────────────────────────────────────────────────────


def _make_provider(tmp_path):
    """Build a minimal AioSandboxProvider instance without starting the idle checker."""
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    with patch.object(aio_mod.AioSandboxProvider, "_start_idle_checker"):
        provider = aio_mod.AioSandboxProvider.__new__(aio_mod.AioSandboxProvider)
        provider._config = {}
        provider._sandboxes = {}
        provider._lock = MagicMock()
        provider._idle_checker_stop = MagicMock()
    return provider


def test_get_thread_mounts_includes_acp_workspace(tmp_path, monkeypatch):
    """_get_thread_mounts must include /mnt/acp-workspace (read-only) for docker sandbox."""
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    monkeypatch.setattr(aio_mod, "get_paths", lambda: Paths(base_dir=tmp_path))

    mounts = aio_mod.AioSandboxProvider._get_thread_mounts("thread-3")

    container_paths = {m[1]: (m[0], m[2]) for m in mounts}

    assert "/mnt/acp-workspace" in container_paths, "ACP workspace mount is missing"
    expected_host = str(tmp_path / "threads" / "thread-3" / "acp-workspace")
    actual_host, read_only = container_paths["/mnt/acp-workspace"]
    assert actual_host == expected_host
    assert read_only is True, "ACP workspace should be read-only inside the sandbox"


def test_get_thread_mounts_includes_user_data_dirs(tmp_path, monkeypatch):
    """Baseline: user-data mounts must still be present after the ACP workspace change."""
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    monkeypatch.setattr(aio_mod, "get_paths", lambda: Paths(base_dir=tmp_path))

    mounts = aio_mod.AioSandboxProvider._get_thread_mounts("thread-4")
    container_paths = {m[1] for m in mounts}

    assert "/mnt/user-data/workspace" in container_paths
    assert "/mnt/user-data/uploads" in container_paths
    assert "/mnt/user-data/outputs" in container_paths


def test_join_host_path_preserves_windows_drive_letter_style():
    base = r"C:\Users\demo\deer-flow\backend\.deer-flow"

    joined = join_host_path(base, "threads", "thread-9", "user-data", "outputs")

    assert joined == r"C:\Users\demo\deer-flow\backend\.deer-flow\threads\thread-9\user-data\outputs"


def test_get_thread_mounts_preserves_windows_host_path_style(tmp_path, monkeypatch):
    """Docker bind mount sources must keep Windows-style paths intact."""
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    monkeypatch.setenv("DEER_FLOW_HOST_BASE_DIR", r"C:\Users\demo\deer-flow\backend\.deer-flow")
    monkeypatch.setattr(aio_mod, "get_paths", lambda: Paths(base_dir=tmp_path))

    mounts = aio_mod.AioSandboxProvider._get_thread_mounts("thread-10")

    container_paths = {container_path: host_path for host_path, container_path, _ in mounts}

    assert container_paths["/mnt/user-data/workspace"] == r"C:\Users\demo\deer-flow\backend\.deer-flow\threads\thread-10\user-data\workspace"
    assert container_paths["/mnt/user-data/uploads"] == r"C:\Users\demo\deer-flow\backend\.deer-flow\threads\thread-10\user-data\uploads"
    assert container_paths["/mnt/user-data/outputs"] == r"C:\Users\demo\deer-flow\backend\.deer-flow\threads\thread-10\user-data\outputs"
    assert container_paths["/mnt/acp-workspace"] == r"C:\Users\demo\deer-flow\backend\.deer-flow\threads\thread-10\acp-workspace"


def test_discover_or_create_only_unlocks_when_lock_succeeds(tmp_path, monkeypatch):
    """Unlock should not run if exclusive locking itself fails."""
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    provider = _make_provider(tmp_path)
    provider._discover_or_create_with_lock = aio_mod.AioSandboxProvider._discover_or_create_with_lock.__get__(
        provider,
        aio_mod.AioSandboxProvider,
    )

    monkeypatch.setattr(aio_mod, "get_paths", lambda: Paths(base_dir=tmp_path))
    monkeypatch.setattr(
        aio_mod,
        "_lock_file_exclusive",
        lambda _lock_file: (_ for _ in ()).throw(RuntimeError("lock failed")),
    )

    unlock_calls: list[object] = []
    monkeypatch.setattr(
        aio_mod,
        "_unlock_file",
        lambda lock_file: unlock_calls.append(lock_file),
    )

    with patch.object(provider, "_create_sandbox", return_value="sandbox-id"):
        with pytest.raises(RuntimeError, match="lock failed"):
            provider._discover_or_create_with_lock("thread-5", "sandbox-5")

    assert unlock_calls == []


def test_get_skills_mount_scopes_public_skills(tmp_path, monkeypatch):
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    monkeypatch.setattr(
        aio_mod,
        "get_app_config",
        lambda: SimpleNamespace(skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills")),
    )
    monkeypatch.delenv("DEER_FLOW_HOST_SHARED_FS_ROOT", raising=False)
    monkeypatch.delenv("DEER_FLOW_HOST_SKILLS_PATH", raising=False)

    mount = aio_mod.AioSandboxProvider._get_skills_mount("public")

    assert mount == (str(skills_root / "public"), "/mnt/skills", True)


def test_get_skills_mount_preserves_windows_private_scope_paths(tmp_path, monkeypatch):
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    monkeypatch.setattr(
        aio_mod,
        "get_app_config",
        lambda: SimpleNamespace(skills=SimpleNamespace(get_skills_path=lambda: skills_root, container_path="/mnt/skills")),
    )
    monkeypatch.setenv("DEER_FLOW_HOST_SHARED_FS_ROOT", r"C:\Users\demo\deer-flow\backend\.deer-flow")
    monkeypatch.setattr(aio_mod, "get_paths", lambda: Paths(base_dir=tmp_path))

    mount = aio_mod.AioSandboxProvider._get_skills_mount("7")

    assert mount == (r"C:\Users\demo\deer-flow\backend\.deer-flow\skills\7", "/mnt/skills", True)


def test_deterministic_sandbox_id_includes_skill_scope() -> None:
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")

    legacy_id = aio_mod.AioSandboxProvider._deterministic_sandbox_id("thread-1")
    public_id = aio_mod.AioSandboxProvider._deterministic_sandbox_id("thread-1", "public")
    private_id = aio_mod.AioSandboxProvider._deterministic_sandbox_id("thread-1", "7")

    assert legacy_id == hashlib.sha256("thread-1".encode()).hexdigest()[:8]
    assert public_id == hashlib.sha256("thread-1:public".encode()).hexdigest()[:8]
    assert private_id == hashlib.sha256("thread-1:7".encode()).hexdigest()[:8]
    assert legacy_id != public_id
    assert public_id != private_id


def test_acquire_internal_does_not_reclaim_warm_pool_sandbox_from_wrong_scope():
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    provider = aio_mod.AioSandboxProvider.__new__(aio_mod.AioSandboxProvider)
    provider._lock = threading.Lock()
    provider._sandboxes = {}
    provider._sandbox_infos = {}
    provider._thread_sandboxes = {}
    provider._thread_locks = {}
    provider._last_activity = {}
    provider._warm_pool = {}
    provider._config = {}
    provider._backend = MagicMock()
    provider._idle_checker_stop = MagicMock()
    provider._shutdown_called = False
    provider._idle_checker_thread = None

    public_id = aio_mod.AioSandboxProvider._deterministic_sandbox_id("thread-1", "public")
    private_id = aio_mod.AioSandboxProvider._deterministic_sandbox_id("thread-1", "7")
    provider._warm_pool[public_id] = (SimpleNamespace(sandbox_url="http://warm"), 0.0)
    provider._discover_or_create_with_lock = MagicMock(return_value=private_id)

    sandbox_id = provider._acquire_internal("thread-1", skill_scope="7")

    assert sandbox_id == private_id
    assert public_id in provider._warm_pool
    provider._discover_or_create_with_lock.assert_called_once_with(
        "thread-1",
        private_id,
        workspace_id=None,
        skill_scope="7",
    )


def test_create_sandbox_initializes_backend_after_ready(monkeypatch):
    aio_mod = importlib.import_module("deerflow.community.aio_sandbox.aio_sandbox_provider")
    provider = aio_mod.AioSandboxProvider.__new__(aio_mod.AioSandboxProvider)
    provider._lock = threading.Lock()
    provider._sandboxes = {}
    provider._sandbox_infos = {}
    provider._thread_sandboxes = {}
    provider._thread_locks = {}
    provider._last_activity = {}
    provider._warm_pool = {}
    provider._config = {"replicas": 3}
    provider._idle_checker_stop = MagicMock()
    provider._shutdown_called = False
    provider._idle_checker_thread = None
    provider._backend = MagicMock()
    provider._backend.create.return_value = SimpleNamespace(sandbox_id="sandbox-1", sandbox_url="http://sandbox")

    monkeypatch.setattr(aio_mod, "wait_for_sandbox_ready", lambda url, timeout=60: True)

    sandbox_id = provider._create_sandbox("thread-1", "sandbox-1", workspace_id="workspace-1", skill_scope="7")

    assert sandbox_id == "sandbox-1"
    provider._backend.initialize.assert_called_once()
    args, kwargs = provider._backend.initialize.call_args
    assert args[0].sandbox_id == "sandbox-1"
    assert args[1] == "thread-1"
    assert kwargs == {"workspace_id": "workspace-1", "skill_scope": "7"}
