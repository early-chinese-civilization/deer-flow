"""Regression tests for provisioner kubeconfig path handling."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock


def _load_provisioner_module():
    """Load docker/provisioner/app.py as an importable test module."""
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "docker" / "provisioner" / "app.py"
    spec = importlib.util.spec_from_file_location("provisioner_app_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wait_for_kubeconfig_rejects_directory(tmp_path):
    """Directory mount at kubeconfig path should fail fast with clear error."""
    provisioner_module = _load_provisioner_module()
    kubeconfig_dir = tmp_path / "config_dir"
    kubeconfig_dir.mkdir()

    provisioner_module.KUBECONFIG_PATH = str(kubeconfig_dir)

    try:
        provisioner_module._wait_for_kubeconfig(timeout=1)
        raise AssertionError("Expected RuntimeError for directory kubeconfig path")
    except RuntimeError as exc:
        assert "directory" in str(exc)


def test_wait_for_kubeconfig_accepts_file(tmp_path):
    """Regular file mount should pass readiness wait."""
    provisioner_module = _load_provisioner_module()
    kubeconfig_file = tmp_path / "config"
    kubeconfig_file.write_text("apiVersion: v1\n")

    provisioner_module.KUBECONFIG_PATH = str(kubeconfig_file)

    # Should return immediately without raising.
    provisioner_module._wait_for_kubeconfig(timeout=1)


def test_init_k8s_client_rejects_directory_path(tmp_path):
    """KUBECONFIG_PATH that resolves to a directory should be rejected."""
    provisioner_module = _load_provisioner_module()
    kubeconfig_dir = tmp_path / "config_dir"
    kubeconfig_dir.mkdir()

    provisioner_module.KUBECONFIG_PATH = str(kubeconfig_dir)

    try:
        provisioner_module._init_k8s_client()
        raise AssertionError("Expected RuntimeError for directory kubeconfig path")
    except RuntimeError as exc:
        assert "expected a file" in str(exc)


def test_init_k8s_client_uses_file_kubeconfig(tmp_path, monkeypatch):
    """When file exists, provisioner should load kubeconfig file path."""
    provisioner_module = _load_provisioner_module()
    kubeconfig_file = tmp_path / "config"
    kubeconfig_file.write_text("apiVersion: v1\n")

    called: dict[str, object] = {}

    def fake_load_kube_config(config_file: str):
        called["config_file"] = config_file

    monkeypatch.setattr(
        provisioner_module.k8s_config,
        "load_kube_config",
        fake_load_kube_config,
    )
    monkeypatch.setattr(
        provisioner_module.k8s_client,
        "CoreV1Api",
        lambda *args, **kwargs: "core-v1",
    )

    provisioner_module.KUBECONFIG_PATH = str(kubeconfig_file)

    result = provisioner_module._init_k8s_client()

    assert called["config_file"] == str(kubeconfig_file)
    assert result == "core-v1"


def test_init_k8s_client_falls_back_to_incluster_when_missing(tmp_path, monkeypatch):
    """When kubeconfig file is missing, in-cluster config should be attempted."""
    provisioner_module = _load_provisioner_module()
    missing_path = tmp_path / "missing-config"

    calls: dict[str, int] = {"incluster": 0}

    def fake_load_incluster_config():
        calls["incluster"] += 1

    monkeypatch.setattr(
        provisioner_module.k8s_config,
        "load_incluster_config",
        fake_load_incluster_config,
    )
    monkeypatch.setattr(
        provisioner_module.k8s_client,
        "CoreV1Api",
        lambda *args, **kwargs: "core-v1",
    )

    provisioner_module.KUBECONFIG_PATH = str(missing_path)

    result = provisioner_module._init_k8s_client()

    assert calls["incluster"] == 1
    assert result == "core-v1"


def test_join_host_path_preserves_windows_style_paths():
    """Windows host paths should stay in Windows form when segments are joined."""
    provisioner_module = _load_provisioner_module()

    result = provisioner_module.join_host_path(
        r"C:\shared-root",
        "workspaces",
        "workspace-1",
        "user-data",
    )

    assert result == r"C:\shared-root\workspaces\workspace-1\user-data"


def test_build_pod_uses_privileged_container_without_startup_mounts():
    """Sandbox pod should defer skills/user-data mounts until after readiness."""
    provisioner_module = _load_provisioner_module()

    pod = provisioner_module._build_pod("sandbox-1", "thread_1", "workspace.1")

    container = pod.spec.containers[0]

    assert pod.spec.volumes in (None, [])
    assert container.volume_mounts in (None, [])
    assert container.security_context.privileged is True
    assert container.security_context.run_as_user == 0


def test_build_pod_rejects_invalid_workspace_id():
    """Unsafe workspace IDs should be rejected before building hostPath mounts."""
    provisioner_module = _load_provisioner_module()

    try:
        provisioner_module._build_pod("sandbox-1", "thread_1", "../escape")
        raise AssertionError("Expected ValueError for invalid workspace_id")
    except ValueError as exc:
        assert "workspace_id" in str(exc)


def test_build_pod_rejects_invalid_skill_scope():
    provisioner_module = _load_provisioner_module()

    try:
        provisioner_module._build_pod("sandbox-1", "thread_1", "workspace.1", "../escape")
        raise AssertionError("Expected ValueError for invalid skill_scope")
    except ValueError as exc:
        assert "skill_scope" in str(exc)


def test_create_sandbox_request_validates_skill_scope():
    provisioner_module = _load_provisioner_module()

    request = provisioner_module.CreateSandboxRequest(
        sandbox_id="sandbox-1",
        thread_id="thread_1",
        workspace_id="workspace.1",
        skill_scope="public",
    )

    assert request.skill_scope == "public"


def test_exec_in_sandbox_runs_bash_in_target_pod(monkeypatch):
    provisioner_module = _load_provisioner_module()
    provisioner_module.core_v1 = MagicMock()

    captured: dict[str, object] = {}

    def fake_stream(func, name, namespace, **kwargs):
        captured["func"] = func
        captured["name"] = name
        captured["namespace"] = namespace
        captured["kwargs"] = kwargs
        return "mounted"

    monkeypatch.setattr(provisioner_module, "k8s_stream", fake_stream)

    output = provisioner_module._exec_in_sandbox("sandbox-1", "echo hi", timeout_seconds=33)

    assert output == "mounted"
    assert captured["func"] == provisioner_module.core_v1.connect_get_namespaced_pod_exec
    assert captured["name"] == "sandbox-sandbox-1"
    assert captured["namespace"] == provisioner_module.K8S_NAMESPACE
    assert captured["kwargs"]["container"] == "sandbox"
    assert captured["kwargs"]["command"] == ["/bin/bash", "-lc", "echo hi"]
    assert captured["kwargs"]["_request_timeout"] == 33
