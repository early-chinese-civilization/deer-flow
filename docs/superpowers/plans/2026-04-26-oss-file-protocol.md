# OSS File Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `oss://` the canonical internal file reference across gateway, LangGraph agent, frontend, and workspace-backed sandbox flows, while keeping sandbox execution on filesystem paths and generating `https://` only at the LLM or browser access boundary.

**Architecture:** Gateway owns OSS URI generation and presigned URL signing. Frontend stores and exchanges `oss://` plus workspace file metadata, but requests temporary upload/download URLs from gateway when it needs to touch OSS directly. LangGraph state and checkpoint persist `oss://` only; sandbox paths remain derived runtime data.

**Tech Stack:** FastAPI, LangGraph/LangChain middleware, Alibaba Cloud OSS SDK v2, Next.js, Node test runner, pytest, pnpm.

---

### Task 1: Canonicalize workspace file identity in gateway

**Files:**
- Modify: `backend/packages/harness/deerflow/uploads/storage.py`
- Modify: `backend/app/gateway/services/workspace_uploads.py`
- Modify: `backend/app/gateway/routers/uploads.py`
- Modify: `backend/tests/test_workspace_uploads_paths.py`
- Create: `backend/tests/test_workspace_uploads_protocol.py`

- [ ] **Step 1: Write the failing test**

```python
def test_workspace_file_response_exports_oss_uri():
    from app.gateway.services.workspace_uploads import build_workspace_file_response

    response = build_workspace_file_response(
        workspace_id="ws-123",
        filename="report.pdf",
        relative_path="uploads/report.pdf",
        size=42,
        object_key="workspaces/ws-123/uploads/report.pdf",
    )

    assert response["oss_uri"].startswith("oss://")
    assert response["oss_uri"].endswith("/workspaces/ws-123/uploads/report.pdf")
    assert response["markdown_oss_uri"] is None


def test_download_url_endpoint_returns_presigned_oss_url():
    from fastapi.testclient import TestClient

    from app.gateway.app import app

    with TestClient(app) as client:
        response = client.get(
            "/api/workspaces/ws-123/uploads/download-url",
            params={"object_key": "workspaces/ws-123/uploads/report.pdf"},
        )

    assert response.status_code == 200
    assert response.json()["download_url"].startswith("https://")
```

- [ ] **Step 2: Run the failing backend tests**

Run: `uv run pytest tests/test_workspace_uploads_protocol.py tests/test_workspace_uploads_paths.py -q`

Expected: fail because `oss_uri` fields and presigned metadata are not yet wired through the response builders.

- [ ] **Step 3: Implement the minimal OSS URI plumbing**

```python
from urllib.parse import urlsplit


def oss_uri_for_object(bucket: str, object_key: str) -> str:
    return f"oss://{bucket}/{object_key.lstrip('/')}"


def parse_oss_uri(oss_uri: str) -> tuple[str, str]:
    parsed = urlsplit(oss_uri)
    if parsed.scheme != "oss" or not parsed.netloc or not parsed.path:
        raise ValueError(f"Invalid OSS URI: {oss_uri!r}")
    return parsed.netloc, parsed.path.lstrip("/")


bucket = get_app_config().uploads.oss.bucket or ""
response["oss_uri"] = oss_uri_for_object(bucket, object_key)
response["markdown_oss_uri"] = None
if markdown_object_key:
    response["markdown_oss_uri"] = oss_uri_for_object(bucket, markdown_object_key)
```


```python
@router.get("/{workspace_id}/uploads/download-url")
async def get_workspace_download_url(workspace_id: str, object_key: str, current_user=Depends(get_current_user), db=Depends(get_db)):
    await _require_workspace_access(db=db, workspace_id=workspace_id, current_user=current_user)
    storage = OSSStorageBackend.from_app_config()
    download_url, _ = storage.presign_get_object(key=object_key)
    return {"download_url": download_url, "oss_uri": oss_uri_for_object(storage.bucket, object_key)}
```

- [ ] **Step 4: Run the backend tests again**

Run: `uv run pytest tests/test_workspace_uploads_protocol.py tests/test_workspace_uploads_paths.py -q`

Expected: pass with `oss_uri` present in upload prepare/finalize/list payloads and in workspace file responses.

- [ ] **Step 5: Commit after this task**

```bash
git add backend/packages/harness/deerflow/uploads/storage.py backend/app/gateway/services/workspace_uploads.py backend/app/gateway/routers/uploads.py backend/tests/test_workspace_uploads_paths.py backend/tests/test_workspace_uploads_protocol.py
git commit -m "feat: canonicalize workspace file identities"
```

### Task 2: Switch the frontend to OSS-backed workspace file actions

**Files:**
- Modify: `frontend/src/core/uploads/api.ts`
- Modify: `frontend/src/core/uploads/cache.ts`
- Modify: `frontend/src/core/artifacts/utils.ts`
- Modify: `frontend/src/components/workspace/workspace-files-panel.tsx`
- Modify: `frontend/src/core/uploads/composer.ts`
- Create: `frontend/src/core/uploads/api.test.ts`
- Create: `frontend/src/core/artifacts/utils.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import assert from "node:assert/strict";
import test from "node:test";

import { addUploadedFilesToList } from "./cache";
import { urlOfArtifact } from "./utils";

void test("uploaded files keep oss uri through cache merges", () => {
  const current = {
    root_label: "workspace",
    root_path: "/mnt/user-data/workspace",
    files: [
      {
        filename: "report.pdf",
        size: 42,
        path: "/mnt/user-data/uploads/report.pdf",
        virtual_path: "/mnt/user-data/uploads/report.pdf",
        relative_path: "uploads/report.pdf",
        artifact_url: null,
        object_key: "workspaces/ws-123/uploads/report.pdf",
        oss_uri: "oss://deer-flow-test/workspaces/ws-123/uploads/report.pdf",
        signed_url: null,
      },
    ],
    tree: [],
    count: 1,
  };

  const next = [
    {
      filename: "report.pdf",
      size: 42,
      path: "/mnt/user-data/uploads/report.pdf",
      virtual_path: "/mnt/user-data/uploads/report.pdf",
      relative_path: "uploads/report.pdf",
      artifact_url: null,
      object_key: "workspaces/ws-123/uploads/report.pdf",
      oss_uri: "oss://deer-flow-test/workspaces/ws-123/uploads/report.pdf",
      signed_url: null,
    },
  ];

  const merged = addUploadedFilesToList(current, next)!;
  assert.equal(merged.files[0]!.oss_uri.startsWith("oss://"), true);
});

void test("artifact URL helper still targets gateway for thread artifacts", () => {
  assert.equal(
    urlOfArtifact({ filepath: "/mnt/user-data/workspace/example.md", threadId: "thread-1" }).includes(
      "/api/threads/thread-1/artifacts",
    ),
    true,
  );
});
```

- [ ] **Step 2: Run the failing frontend checks**

Run: `pnpm dlx tsx --test src/core/uploads/api.test.ts src/core/artifacts/utils.test.ts`

Expected: fail until the upload API returns `oss_uri`, the panel prefers presigned GET URLs, and the cache stops treating temporary URLs as persistent identity.

- [ ] **Step 3: Implement the frontend data model and action flow**

```ts
export interface UploadedFileInfo {
  filename: string;
  size: number;
  path: string;
  virtual_path: string;
  relative_path: string;
  artifact_url: string | null;
  object_key: string;
  oss_uri: string;
  signed_url?: string | null;
  extension?: string | null;
  modified?: number;
  markdown_file?: string | null;
  markdown_path?: string | null;
  markdown_virtual_path?: string | null;
  markdown_artifact_url?: string | null;
  markdown_object_key?: string | null;
  markdown_oss_uri?: string | null;
  markdown_signed_url?: string | null;
}
```

```ts
export async function downloadUploadedFile(url: string, filename: string): Promise<void> {
  const response = await fetch(url, { credentials: "include" });
  if (!response.ok) throw new Error(await readErrorDetail(response, "Failed to download file"));
  downloadBlobAsFile(await response.blob(), filename);
}

export async function getWorkspaceDownloadUrl(workspaceId: string, objectKey: string): Promise<string> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/workspaces/${encodeURIComponent(workspaceId)}/uploads/download-url?object_key=${encodeURIComponent(objectKey)}`,
    { credentials: "include" },
  );
  if (!response.ok) throw new Error(await readErrorDetail(response, "Failed to resolve download URL"));
  const payload = await response.json();
  return payload.download_url;
}
```

Update `workspace-files-panel.tsx` so download buttons resolve a fresh presigned GET URL with `getWorkspaceDownloadUrl(...)` and never derive a long-lived browser URL from `artifact_url` for workspace uploads.

- [ ] **Step 4: Run the frontend checks again**

Run: `pnpm dlx tsx --test src/core/uploads/api.test.ts src/core/artifacts/utils.test.ts && pnpm check`

Expected: pass with OSS metadata in the upload model and no remaining dependency on permanent workspace artifact URLs.

- [ ] **Step 5: Commit after this task**

```bash
git add frontend/src/core/uploads/api.ts frontend/src/core/uploads/cache.ts frontend/src/core/artifacts/utils.ts frontend/src/components/workspace/workspace-files-panel.tsx frontend/src/core/uploads/composer.ts frontend/src/core/uploads/api.test.ts frontend/src/core/artifacts/utils.test.ts
git commit -m "feat: route workspace file actions through oss metadata"
```

### Task 3: Persist `oss://` in LangGraph state and resolve it only at the model boundary

**Files:**
- Modify: `backend/packages/harness/deerflow/agents/thread_state.py`
- Modify: `backend/packages/harness/deerflow/agents/middlewares/uploads_middleware.py`
- Create: `backend/packages/harness/deerflow/agents/middlewares/file_reference_middleware.py`
- Modify: `backend/packages/harness/deerflow/agents/factory.py`
- Create: `backend/tests/test_uploads_middleware_oss_uri.py`
- Create: `backend/tests/test_file_reference_middleware.py`

- [ ] **Step 1: Write the failing test**

```python
import re
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from deerflow.agents.middlewares.file_reference_middleware import FileReferenceMiddleware
from deerflow.agents.middlewares.uploads_middleware import UploadsMiddleware


def _make_runtime(workspace_id: str = "ws-123") -> SimpleNamespace:
    return SimpleNamespace(context={"workspace_id": workspace_id})


def test_uploads_middleware_stores_oss_uri_and_sandbox_path():
    middleware = UploadsMiddleware()
    state = {
        "messages": [
            HumanMessage(
                content="upload context",
                additional_kwargs={
                    "files": [
                        {"filename": "report.pdf", "size": 42, "path": "/mnt/user-data/uploads/report.pdf"},
                    ]
                },
            )
        ]
    }

    update = middleware.before_agent(state, _make_runtime())
    assert update["uploaded_files"][0]["oss_uri"].startswith("oss://")
    assert update["uploaded_files"][0]["path"] == "/mnt/user-data/uploads/report.pdf"
```

```python
def test_file_reference_middleware_signs_oss_links_before_model():
    middleware = FileReferenceMiddleware()
    state = {
        "messages": [HumanMessage(content="See oss://bucket/workspaces/ws-123/uploads/report.pdf")]
    }

    update = middleware.before_model(state, _make_runtime())
    assert "https://" in update["messages"][0].content
```

- [ ] **Step 2: Run the failing backend tests**

Run: `uv run pytest tests/test_uploads_middleware_oss_uri.py tests/test_file_reference_middleware.py -q`

Expected: fail because the uploaded file payload still only carries sandbox paths and there is no middleware that turns `oss://` into a temporary LLM-facing URL.

- [ ] **Step 3: Implement the state shape and model-boundary resolver**

```python
class WorkspaceFileState(TypedDict):
    filename: str
    size: int
    object_key: str
    oss_uri: str
    path: str
    extension: str | None


class ThreadState(AgentState):
    uploaded_files: NotRequired[list[WorkspaceFileState] | None]


_OSS_URI_RE = re.compile(r"oss://[^\s)\"']+")


def _rewrite_oss_uris_in_message(message, runtime):
    if not isinstance(message.content, str):
        return message

    storage = OSSStorageBackend.from_app_config()

    def replace(match: re.Match[str]) -> str:
        _, object_key = parse_oss_uri(match.group(0))
        download_url, _ = storage.presign_get_object(key=object_key)
        return download_url

    return message.__class__(
        content=_OSS_URI_RE.sub(replace, message.content),
        id=message.id,
        additional_kwargs=message.additional_kwargs,
    )


class FileReferenceMiddleware(AgentMiddleware[ThreadState]):
    def before_model(self, state: ThreadState, runtime: Runtime) -> dict | None:
        messages = list(state.get("messages", []))
        return {"messages": [_rewrite_oss_uris_in_message(message, runtime) for message in messages]}
```

Update `UploadsMiddleware` so each persisted entry includes `oss_uri`, `object_key`, and `path`, while the injected prompt still shows the sandbox path that `read_file` can consume.

Register `FileReferenceMiddleware` in `factory.py` immediately before model invocation so any OSS references in LLM-facing content are signed at the last possible moment.

- [ ] **Step 4: Run the backend tests again**

Run: `uv run pytest tests/test_uploads_middleware_oss_uri.py tests/test_file_reference_middleware.py tests/test_thread_data_middleware.py -q`

Expected: pass with checkpointed state carrying `oss://` and model-facing content using temporary `https://` only at the boundary.

- [ ] **Step 5: Commit after this task**

```bash
git add backend/packages/harness/deerflow/agents/thread_state.py backend/packages/harness/deerflow/agents/middlewares/uploads_middleware.py backend/packages/harness/deerflow/agents/middlewares/file_reference_middleware.py backend/packages/harness/deerflow/agents/factory.py backend/tests/test_uploads_middleware_oss_uri.py backend/tests/test_file_reference_middleware.py
git commit -m "feat: persist oss references in agent state"
```

### Task 4: Update docs and run end-to-end verification

**Files:**
- Modify: `backend/docs/FILE_UPLOAD.md`
- Modify: `backend/docs/ARCHITECTURE.md`
- Modify: `README.md`
- Modify: any file touched above that still documents `artifact_url` as the primary workspace-file access path

- [ ] **Step 1: Write the failing doc assertions in review notes**

```text
FILE_UPLOAD.md must describe:
- frontend requests presigned PUT/GET from gateway
- workspace records carry oss:// as the canonical identity
- sandbox continues to use /mnt/user-data/... paths

ARCHITECTURE.md must describe:
- gateway signs URLs
- LangGraph checkpoint stores oss:// only
- sandbox does not parse oss://
```

- [ ] **Step 2: Run the full backend and frontend verification set**

Run:
`uv run pytest tests/test_workspace_uploads_protocol.py tests/test_workspace_uploads_paths.py tests/test_uploads_middleware_oss_uri.py tests/test_file_reference_middleware.py tests/test_thread_data_middleware.py -q`

Run:
`pnpm dlx tsx --test src/core/uploads/api.test.ts src/core/artifacts/utils.test.ts && pnpm check`

Expected: all checks pass and the documentation matches the new `oss://` / presigned URL boundary.

- [ ] **Step 3: Update the docs text and finalize the branch**

```markdown
## Workspace file access

- Canonical identity: `oss://bucket/key`
- Upload: presigned PUT from gateway, direct to OSS
- Download/preview: presigned GET from gateway, direct to OSS
- Sandbox: filesystem paths only
- Checkpoint: persist `oss://`, regenerate `https://` on resume
```

- [ ] **Step 4: Commit the docs and verification cleanup**

```bash
git add backend/docs/FILE_UPLOAD.md backend/docs/ARCHITECTURE.md README.md
git commit -m "docs: describe the oss file protocol"
```
