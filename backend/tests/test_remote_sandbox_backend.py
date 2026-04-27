import base64
import re
from types import SimpleNamespace

from deerflow.community.aio_sandbox import remote_backend


def _decode_mount_script(command: str) -> str:
    match = re.search(r"printf '%s' '?([A-Za-z0-9+/=]+)'? \| base64", command)
    assert match is not None
    return base64.b64decode(match.group(1)).decode("utf-8")


def test_remote_backend_mounts_workspace_root_prefix(monkeypatch):
    config = SimpleNamespace(
        uploads=SimpleNamespace(
            backend="oss",
            oss=SimpleNamespace(
                endpoint="oss-cn-test.aliyuncs.com",
                bucket="bucket",
                access_key_id="ak",
                access_key_secret="sk",
            ),
        )
    )
    monkeypatch.setattr(remote_backend, "get_app_config", lambda: config)

    backend = remote_backend.RemoteSandboxBackend("http://provisioner:8002")
    script = _decode_mount_script(
        backend._build_mount_command(workspace_id="workspace-1", skill_scope=None)
    )

    assert "workspaces/workspace-1/" in script
    assert "workspaces/workspace-1/user-data/" not in script
    assert "--close_to_open=true" in script
    assert "--oss_negative_cache_timeout=0" in script
