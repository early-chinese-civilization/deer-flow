"""Remote sandbox backend - delegates Pod lifecycle to the provisioner service."""

from __future__ import annotations

import base64
import logging
import shlex
import textwrap

import requests

from deerflow.config import get_app_config
from deerflow.sandbox.skill_scope import CANONICAL_RUNTIME_SKILLS_SCOPE

from .backend import SandboxBackend
from .sandbox_info import SandboxInfo

logger = logging.getLogger(__name__)


class RemoteSandboxBackend(SandboxBackend):
    """Backend that delegates sandbox lifecycle to the provisioner service."""

    def __init__(self, provisioner_url: str):
        """Initialize with the provisioner service URL."""
        self._provisioner_url = provisioner_url.rstrip("/")

    @property
    def provisioner_url(self) -> str:
        return self._provisioner_url

    def create(
        self,
        thread_id: str,
        sandbox_id: str,
        extra_mounts: list[tuple[str, str, bool]] | None = None,
        workspace_id: str | None = None,
        skill_scope: str | None = None,
    ) -> SandboxInfo:
        """Create a sandbox Pod + Service via the provisioner."""
        return self._provisioner_create(
            thread_id,
            sandbox_id,
            extra_mounts,
            workspace_id=workspace_id,
            skill_scope=skill_scope,
        )

    def destroy(self, info: SandboxInfo) -> None:
        """Destroy a sandbox Pod + Service via the provisioner."""
        self._provisioner_destroy(info.sandbox_id)

    def is_alive(self, info: SandboxInfo) -> bool:
        """Check whether the sandbox Pod is running."""
        return self._provisioner_is_alive(info.sandbox_id)

    def discover(self, sandbox_id: str) -> SandboxInfo | None:
        """Discover an existing sandbox via the provisioner."""
        return self._provisioner_discover(sandbox_id)

    def initialize(
        self,
        info: SandboxInfo,
        thread_id: str | None,
        workspace_id: str | None = None,
        skill_scope: str | None = None,
    ) -> None:
        """Mount OSS-backed skills and workspace data after the pod is ready."""
        del thread_id
        resolved_workspace_id = workspace_id
        if not resolved_workspace_id:
            raise RuntimeError("workspace_id is required to initialize remote sandbox mounts")

        command = self._build_mount_command(
            workspace_id=resolved_workspace_id,
            skill_scope=skill_scope,
        )
        logger.info(
            "Initializing remote sandbox mounts for %s workspace=%s skill_scope=%s",
            info.sandbox_id,
            resolved_workspace_id,
            skill_scope,
        )
        self._provisioner_exec(info.sandbox_id, command)

    @staticmethod
    def _quote_shell(value: str) -> str:
        return shlex.quote(value)

    @staticmethod
    def _mount_prefix(path_suffix: str) -> str:
        return f"{path_suffix.strip('/')}/"

    def _build_mount_command(self, *, workspace_id: str, skill_scope: str | None) -> str:
        uploads_config = get_app_config().uploads
        if uploads_config.backend != "oss":
            raise RuntimeError("Remote sandbox OSS mounts require uploads.backend=oss")

        oss_config = uploads_config.oss
        missing = [name for name in ("endpoint", "bucket", "access_key_id", "access_key_secret") if not getattr(oss_config, name)]
        if missing:
            raise RuntimeError(f"OSS mount configuration is incomplete: missing {', '.join(missing)}")

        mount_specs: list[tuple[str, str, str, str]] = []
        if skill_scope:
            if skill_scope != CANONICAL_RUNTIME_SKILLS_SCOPE:
                raise RuntimeError(f"Unsupported remote sandbox skill_scope: {skill_scope}")
            mount_specs.append(
                (
                    "/mnt/skills",
                    "/tmp/ossfs2-skills.conf",
                    "/tmp/ossfs2-log/skills",
                    self._mount_prefix("skills"),
                )
            )
        mount_specs.append(
            (
                "/mnt/user-data",
                "/tmp/ossfs2-workspaces.conf",
                "/tmp/ossfs2-log/workspaces",
                self._mount_prefix(f"workspaces/{workspace_id}/user-data"),
            )
        )

        mount_commands = "\n".join(
            textwrap.dedent(
                f"""
                mount_ossfs \
                  {self._quote_shell(mount_path)} \
                  {self._quote_shell(config_path)} \
                  {self._quote_shell(log_dir)} \
                  {self._quote_shell(bucket_prefix)}
                """
            ).strip()
            for mount_path, config_path, log_dir, bucket_prefix in mount_specs
        )

        script = textwrap.dedent(
            f"""
            exec 2>&1
            set -euxo pipefail

            OSS_ENDPOINT={self._quote_shell(oss_config.endpoint)}
            OSS_BUCKET={self._quote_shell(oss_config.bucket)}
            OSS_ACCESS_KEY_ID={self._quote_shell(oss_config.access_key_id)}
            OSS_ACCESS_KEY_SECRET={self._quote_shell(oss_config.access_key_secret)}

            dump_debug_state() {{
              echo "=== debug: /dev/fuse ==="
              ls -l /dev/fuse || true
              echo "=== debug: mount table ==="
              grep -E '/mnt/skills|/mnt/user-data|fuse|ossfs' /proc/mounts || true
              echo "=== debug: ossfs logs ==="
              find /tmp/ossfs2-log -maxdepth 2 -type f -print -exec sh -c 'echo "--- $1 ---"; cat "$1"' _ {{}} \\; 2>/dev/null || true
            }}

            trap 'status=$?; echo "=== mount script failed with exit $status ==="; dump_debug_state; exit $status' ERR

            ensure_ossfs2() {{
              echo "=== ensure ossfs2 ==="
              if [ -x /usr/local/bin/ossfs2 ]; then
                /usr/local/bin/ossfs2 --version || true
                return 0
              fi

              cd /tmp
              wget -O ossfs2.deb https://gosspublic.alicdn.com/ossfs/ossfs2_2.0.7_linux_x86_64.deb
              dpkg -i ossfs2.deb
              /usr/local/bin/ossfs2 --version || true
            }}

            ensure_fuse_ready() {{
              echo "=== ensure fuse ==="
              if [ ! -e /dev/fuse ]; then
                echo "ERROR: /dev/fuse is missing"
                ls -l /dev || true
                exit 1
              fi
              printf 'user_allow_other\\n' > /etc/fuse.conf || true
              cat /etc/fuse.conf || true
            }}

            is_mounted() {{
              grep -qs " $1 " /proc/mounts
            }}

            mount_ossfs() {{
              mount_path="$1"
              config_path="$2"
              log_dir="$3"
              bucket_prefix="$4"

              echo "=== mount target: $mount_path prefix: $bucket_prefix ==="
              mkdir -p "$mount_path" "$log_dir"

              if is_mounted "$mount_path"; then
                echo "already mounted: $mount_path"
                return 0
              fi

              printf '%s\\n' \\
                "--oss_endpoint=$OSS_ENDPOINT" \\
                "--oss_bucket=$OSS_BUCKET" \\
                "--oss_access_key_id=$OSS_ACCESS_KEY_ID" \\
                "--oss_access_key_secret=$OSS_ACCESS_KEY_SECRET" \\
                "--oss_bucket_prefix=$bucket_prefix" \\
                "" \\
                "--uid=0" \\
                "--gid=0" \\
                "--file_mode=0777" \\
                "--dir_mode=0777" \\
                "--allow_other=true" \\
                "" \\
                "--log_level=info" \\
                "--log_dir=$log_dir" \\
                > "$config_path"

              chmod 600 "$config_path"
              echo "config written to $config_path"
              grep -v 'access_key' "$config_path" || true
              /usr/local/bin/ossfs2 mount "$mount_path" -c "$config_path"
              echo "mount command completed for $mount_path"

              is_mounted "$mount_path"
              ls -lah "$mount_path"
            }}

            ensure_ossfs2
            ensure_fuse_ready
            {mount_commands}
            echo "=== mount script completed successfully ==="
            dump_debug_state
            """
        ).strip()

        encoded_script = base64.b64encode(script.encode("utf-8")).decode("ascii")
        return f"printf '%s' {self._quote_shell(encoded_script)} | base64 -d | /bin/bash"

    def _provisioner_create(
        self,
        thread_id: str,
        sandbox_id: str,
        extra_mounts: list[tuple[str, str, bool]] | None = None,
        workspace_id: str | None = None,
        skill_scope: str | None = None,
    ) -> SandboxInfo:
        """POST /api/sandboxes -> create Pod + Service."""
        try:
            del extra_mounts
            payload = {
                "sandbox_id": sandbox_id,
                "thread_id": thread_id,
                "workspace_id": workspace_id or thread_id,
                "skill_scope": skill_scope,
            }
            logger.info("Provisioner create payload for sandbox %s: %s", sandbox_id, payload)
            resp = requests.post(
                f"{self._provisioner_url}/api/sandboxes",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("Provisioner created sandbox %s: sandbox_url=%s", sandbox_id, data["sandbox_url"])
            return SandboxInfo(
                sandbox_id=sandbox_id,
                sandbox_url=data["sandbox_url"],
            )
        except requests.RequestException as exc:
            logger.error("Provisioner create failed for %s: %s", sandbox_id, exc)
            raise RuntimeError(f"Provisioner create failed: {exc}") from exc

    def _provisioner_exec(self, sandbox_id: str, command: str) -> str:
        """POST an internal exec command to the provisioner."""
        try:
            logger.info(
                "Provisioner exec request for sandbox %s command:\n%s",
                sandbox_id,
                command,
            )
            resp = requests.post(
                f"{self._provisioner_url}/api/internal/sandboxes/{sandbox_id}/exec",
                json={"command": command},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            output = str(data.get("output", ""))
            logger.info(
                "Provisioner exec output for sandbox %s:\n%s",
                sandbox_id,
                output,
            )
            return output
        except requests.RequestException as exc:
            logger.error("Provisioner exec failed for %s: %s", sandbox_id, exc)
            raise RuntimeError(f"Provisioner exec failed: {exc}") from exc

    def _provisioner_destroy(self, sandbox_id: str) -> None:
        """DELETE /api/sandboxes/{sandbox_id} -> destroy Pod + Service."""
        try:
            resp = requests.delete(
                f"{self._provisioner_url}/api/sandboxes/{sandbox_id}",
                timeout=15,
            )
            if resp.ok:
                logger.info("Provisioner destroyed sandbox %s", sandbox_id)
            else:
                logger.warning("Provisioner destroy returned %s: %s", resp.status_code, resp.text)
        except requests.RequestException as exc:
            logger.warning("Provisioner destroy failed for %s: %s", sandbox_id, exc)

    def _provisioner_is_alive(self, sandbox_id: str) -> bool:
        """GET /api/sandboxes/{sandbox_id} -> check Pod phase."""
        try:
            resp = requests.get(
                f"{self._provisioner_url}/api/sandboxes/{sandbox_id}",
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                return data.get("status") == "Running"
            return False
        except requests.RequestException:
            return False

    def _provisioner_discover(self, sandbox_id: str) -> SandboxInfo | None:
        """GET /api/sandboxes/{sandbox_id} -> discover existing sandbox."""
        try:
            resp = requests.get(
                f"{self._provisioner_url}/api/sandboxes/{sandbox_id}",
                timeout=10,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return SandboxInfo(
                sandbox_id=sandbox_id,
                sandbox_url=data["sandbox_url"],
            )
        except requests.RequestException as exc:
            logger.debug("Provisioner discover failed for %s: %s", sandbox_id, exc)
            return None
