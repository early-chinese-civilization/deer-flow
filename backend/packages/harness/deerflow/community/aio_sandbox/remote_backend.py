"""Remote sandbox backend - delegates Pod lifecycle to the provisioner service."""

from __future__ import annotations

import logging

import requests

from deerflow.config import get_app_config

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
        """Skipped: Sandbox volumes are natively mounted via K8s PVCs by the provisioner."""
        logger.info(
            "Skipping remote sandbox mount initialization for %s (volumes are pre-mounted)",
            info.sandbox_id,
        )
        return

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
