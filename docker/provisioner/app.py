"""DeerFlow Sandbox Provisioner Service.

Dynamically creates and manages per-sandbox Pods in Kubernetes.
Each ``sandbox_id`` gets its own Pod + ClusterIP Service.  The backend
accesses sandboxes directly via the K8s internal DNS.

The provisioner runs inside the same K8s cluster and uses in-cluster config.

Endpoints:
    POST   /api/sandboxes              — Create a sandbox Pod + Service
    DELETE /api/sandboxes/{sandbox_id} — Destroy a sandbox Pod + Service
    GET    /api/sandboxes/{sandbox_id} — Get sandbox status & URL
    GET    /api/sandboxes              — List all sandboxes
    POST   /api/internal/sandboxes/{id}/exec — Execute cmd in sandbox
    GET    /health                     — Provisioner health check
"""

from __future__ import annotations

import logging
import os
import re
import time
from contextlib import asynccontextmanager

import urllib3
from fastapi import FastAPI, HTTPException
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream as k8s_stream
from pydantic import BaseModel, Field

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── Configuration ───────────────────────────────────────────────────────

K8S_NAMESPACE = os.environ.get("K8S_NAMESPACE", "bio-dev")
SANDBOX_IMAGE = os.environ.get(
    "SANDBOX_IMAGE",
    "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest",
)
SANDBOX_PORT = int(os.environ.get("SANDBOX_PORT", "8080"))
SAFE_THREAD_ID_PATTERN = r"^[A-Za-z0-9_\-]+$"
SAFE_WORKSPACE_ID_PATTERN = r"^[A-Za-z0-9._\-]+$"
SAFE_SKILL_SCOPE_PATTERN = r"^(public|[0-9]+)$"

# ── K8s client ──────────────────────────────────────────────────────────

core_v1: k8s_client.CoreV1Api | None = None


def _init_k8s_client() -> k8s_client.CoreV1Api:
    try:
        k8s_config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config")
    except Exception as exc:
        raise RuntimeError(
            f"Failed to initialize Kubernetes client (in-cluster config unavailable): {exc}"
        ) from exc
    return k8s_client.CoreV1Api()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global core_v1
    core_v1 = _init_k8s_client()
    logger.info("Provisioner is ready (K8s namespace: %s)", K8S_NAMESPACE)
    yield


app = FastAPI(title="DeerFlow Sandbox Provisioner", lifespan=lifespan)


# ── Request / Response models ───────────────────────────────────────────


class CreateSandboxRequest(BaseModel):
    sandbox_id: str
    thread_id: str = Field(pattern=SAFE_THREAD_ID_PATTERN)
    workspace_id: str = Field(pattern=SAFE_WORKSPACE_ID_PATTERN)
    skill_scope: str | None = Field(default=None, pattern=SAFE_SKILL_SCOPE_PATTERN)


class SandboxResponse(BaseModel):
    sandbox_id: str
    sandbox_url: str
    status: str


class ExecInSandboxRequest(BaseModel):
    command: str
    timeout_seconds: int = Field(default=120, ge=1, le=900)


class ExecInSandboxResponse(BaseModel):
    sandbox_id: str
    output: str


# ── K8s resource helpers ─────────────────────────────────────────────────


def _pod_name(sandbox_id: str) -> str:
    return f"sandbox-{sandbox_id}"


def _svc_name(sandbox_id: str) -> str:
    return f"sandbox-{sandbox_id}-svc"


def _container_name() -> str:
    return "sandbox"


def _sandbox_url(sandbox_id: str) -> str:
    return f"http://{_svc_name(sandbox_id)}.{K8S_NAMESPACE}.svc.cluster.local:{SANDBOX_PORT}"


def _build_pod(
    sandbox_id: str,
    thread_id: str,
    workspace_id: str,
    skill_scope: str | None = None,
) -> k8s_client.V1Pod:
    return k8s_client.V1Pod(
        metadata=k8s_client.V1ObjectMeta(
            name=_pod_name(sandbox_id),
            namespace=K8S_NAMESPACE,
            labels={
                "app": "deer-flow-sandbox",
                "sandbox-id": sandbox_id,
                "app.kubernetes.io/name": "deer-flow",
                "app.kubernetes.io/component": "sandbox",
            },
        ),
        spec=k8s_client.V1PodSpec(
            containers=[
                k8s_client.V1Container(
                    name="sandbox",
                    image=SANDBOX_IMAGE,
                    image_pull_policy="IfNotPresent",
                    ports=[
                        k8s_client.V1ContainerPort(
                            name="http",
                            container_port=SANDBOX_PORT,
                            protocol="TCP",
                        )
                    ],
                    readiness_probe=k8s_client.V1Probe(
                        http_get=k8s_client.V1HTTPGetAction(
                            path="/v1/sandbox",
                            port=SANDBOX_PORT,
                        ),
                        initial_delay_seconds=5,
                        period_seconds=5,
                        timeout_seconds=3,
                        failure_threshold=3,
                    ),
                    liveness_probe=k8s_client.V1Probe(
                        http_get=k8s_client.V1HTTPGetAction(
                            path="/v1/sandbox",
                            port=SANDBOX_PORT,
                        ),
                        initial_delay_seconds=10,
                        period_seconds=10,
                        timeout_seconds=3,
                        failure_threshold=3,
                    ),
                    resources=k8s_client.V1ResourceRequirements(
                        requests={
                            "cpu": "100m",
                            "memory": "256Mi",
                            "ephemeral-storage": "500Mi",
                        },
                        limits={
                            "cpu": "1000m",
                            "memory": "1Gi",
                            "ephemeral-storage": "500Mi",
                        },
                    ),
                    security_context=k8s_client.V1SecurityContext(
                        privileged=True,
                        allow_privilege_escalation=True,
                        run_as_user=0,
                    ),
                )
            ],
            restart_policy="Always",
        ),
    )


def _build_service(sandbox_id: str) -> k8s_client.V1Service:
    return k8s_client.V1Service(
        metadata=k8s_client.V1ObjectMeta(
            name=_svc_name(sandbox_id),
            namespace=K8S_NAMESPACE,
            labels={
                "app": "deer-flow-sandbox",
                "sandbox-id": sandbox_id,
                "app.kubernetes.io/name": "deer-flow",
                "app.kubernetes.io/component": "sandbox",
            },
        ),
        spec=k8s_client.V1ServiceSpec(
            type="ClusterIP",
            ports=[
                k8s_client.V1ServicePort(
                    name="http",
                    port=SANDBOX_PORT,
                    target_port=SANDBOX_PORT,
                    protocol="TCP",
                )
            ],
            selector={
                "sandbox-id": sandbox_id,
            },
        ),
    )


def _get_pod_phase(sandbox_id: str) -> str:
    try:
        pod = core_v1.read_namespaced_pod(_pod_name(sandbox_id), K8S_NAMESPACE)
        return pod.status.phase or "Unknown"
    except ApiException:
        return "NotFound"


def _service_exists(sandbox_id: str) -> bool:
    try:
        core_v1.read_namespaced_service(_svc_name(sandbox_id), K8S_NAMESPACE)
        return True
    except ApiException:
        return False


def _exec_in_sandbox(sandbox_id: str, command: str, timeout_seconds: int = 120) -> str:
    try:
        return k8s_stream(
            core_v1.connect_get_namespaced_pod_exec,
            _pod_name(sandbox_id),
            K8S_NAMESPACE,
            container=_container_name(),
            command=["/bin/bash", "-lc", command],
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            _request_timeout=timeout_seconds,
        ) or ""
    except ApiException as exc:
        if exc.status == 404:
            raise HTTPException(status_code=404, detail=f"Sandbox '{sandbox_id}' not found") from exc
        raise HTTPException(status_code=500, detail=f"Sandbox exec failed: {exc.reason}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sandbox exec failed: {exc}") from exc


# ── API endpoints ────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/internal/sandboxes/{sandbox_id}/exec", response_model=ExecInSandboxResponse)
async def exec_in_sandbox(sandbox_id: str, req: ExecInSandboxRequest):
    logger.info("Exec request for sandbox %s (timeout=%ss)", sandbox_id, req.timeout_seconds)
    output = _exec_in_sandbox(sandbox_id, req.command, req.timeout_seconds)
    return ExecInSandboxResponse(sandbox_id=sandbox_id, output=output)


@app.post("/api/sandboxes", response_model=SandboxResponse)
async def create_sandbox(req: CreateSandboxRequest):
    sandbox_id = req.sandbox_id
    thread_id = req.thread_id
    workspace_id = req.workspace_id
    skill_scope = req.skill_scope

    if _service_exists(sandbox_id):
        return SandboxResponse(
            sandbox_id=sandbox_id,
            sandbox_url=_sandbox_url(sandbox_id),
            status=_get_pod_phase(sandbox_id),
        )

    try:
        core_v1.create_namespaced_pod(K8S_NAMESPACE, _build_pod(sandbox_id, thread_id, workspace_id, skill_scope))
        logger.info("Created Pod %s", _pod_name(sandbox_id))
    except ApiException as exc:
        if exc.status != 409:
            raise HTTPException(status_code=500, detail=f"Pod creation failed: {exc.reason}")

    try:
        core_v1.create_namespaced_service(K8S_NAMESPACE, _build_service(sandbox_id))
        logger.info("Created Service %s", _svc_name(sandbox_id))
    except ApiException as exc:
        if exc.status != 409:
            try:
                core_v1.delete_namespaced_pod(_pod_name(sandbox_id), K8S_NAMESPACE)
            except ApiException:
                pass
            raise HTTPException(status_code=500, detail=f"Service creation failed: {exc.reason}")

    for _ in range(20):
        if _service_exists(sandbox_id):
            break
        time.sleep(0.5)

    return SandboxResponse(
        sandbox_id=sandbox_id,
        sandbox_url=_sandbox_url(sandbox_id),
        status="Pending",
    )


@app.delete("/api/sandboxes/{sandbox_id}")
async def destroy_sandbox(sandbox_id: str):
    errors: list[str] = []
    try:
        core_v1.delete_namespaced_service(_svc_name(sandbox_id), K8S_NAMESPACE)
    except ApiException as exc:
        if exc.status != 404:
            errors.append(f"service: {exc.reason}")
    try:
        core_v1.delete_namespaced_pod(_pod_name(sandbox_id), K8S_NAMESPACE)
    except ApiException as exc:
        if exc.status != 404:
            errors.append(f"pod: {exc.reason}")
    if errors:
        raise HTTPException(status_code=500, detail=f"Partial cleanup: {', '.join(errors)}")
    return {"ok": True, "sandbox_id": sandbox_id}


@app.get("/api/sandboxes/{sandbox_id}", response_model=SandboxResponse)
async def get_sandbox(sandbox_id: str):
    if not _service_exists(sandbox_id):
        raise HTTPException(status_code=404, detail=f"Sandbox '{sandbox_id}' not found")
    return SandboxResponse(
        sandbox_id=sandbox_id,
        sandbox_url=_sandbox_url(sandbox_id),
        status=_get_pod_phase(sandbox_id),
    )


@app.get("/api/sandboxes")
async def list_sandboxes():
    try:
        services = core_v1.list_namespaced_service(
            K8S_NAMESPACE,
            label_selector="app.kubernetes.io/component=sandbox",
        )
    except ApiException as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list services: {exc.reason}")

    return {
        "sandboxes": [
            SandboxResponse(
                sandbox_id=(svc.metadata.labels or {}).get("sandbox-id", ""),
                sandbox_url=f"http://{svc.metadata.name}.{K8S_NAMESPACE}.svc.cluster.local:{SANDBOX_PORT}",
                status=_get_pod_phase((svc.metadata.labels or {}).get("sandbox-id", "")),
            )
            for svc in services.items
            if (svc.metadata.labels or {}).get("sandbox-id")
        ],
        "count": 0,
    }
