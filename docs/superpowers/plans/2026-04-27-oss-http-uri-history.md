# OSS HTTP URI History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `oss://` as the canonical persisted file identity while deriving presigned `http_uri` values only at runtime and letting the frontend render those values safely.

**Architecture:** Add a small URI helper in the backend that can derive a presigned `http_uri` from an `oss_uri` without making it the source of truth. Then update the message/file middlewares so persisted history keeps `oss_uri` and `object_key`, while runtime payloads can carry `http_uri` for immediate browser use. The frontend will accept either `http_uri` or `oss_uri` and will always fall back to resolving `oss://` at render time.

**Tech Stack:** Python, FastAPI/LangGraph middleware, OSS SDK, Next.js 16, React 19, TanStack Query, TypeScript, `uv run pytest`, `pnpm exec node --test`, `pnpm typecheck`.

---

### Task 1: Add canonical URI helpers and runtime fields

**Files:**
- Create: `backend/packages/harness/deerflow/uploads/uri_resolution.py`
- Modify: `backend/packages/harness/deerflow/agents/thread_state.py:1-40`
- Test: `backend/tests/test_uri_resolution.py`

- [ ] **Step 1: Write the failing tests**

```py
from deerflow.uploads.uri_resolution import oss_uri_to_http_uri, split_oss_uri


def test_split_oss_uri_extracts_bucket_and_object_key() -> None:
    assert split_oss_uri("oss://demo-bucket/workspaces/ws-1/uploads/photo%20(1).png") == (
        "demo-bucket",
        "workspaces/ws-1/uploads/photo (1).png",
    )


def test_oss_uri_to_http_uri_returns_presigned_https(monkeypatch) -> None:
    class _FakeStorage:
        bucket = "demo-bucket"

        def presign_get_object(self, *, key: str, expires_seconds: int | None = None):
            return (f"https://signed.example/{key}", None)

    monkeypatch.setattr("deerflow.uploads.uri_resolution.OSSStorageBackend.from_app_config", lambda: _FakeStorage())

    assert oss_uri_to_http_uri("oss://demo-bucket/workspaces/ws-1/uploads/photo.png").startswith(
        "https://signed.example/"
    )
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `uv run pytest backend/tests/test_uri_resolution.py -q`

Expected: FAIL because `backend/packages/harness/deerflow/uploads/uri_resolution.py` does not exist yet.

- [ ] **Step 3: Implement the helper and runtime-only fields**

```py
# backend/packages/harness/deerflow/uploads/uri_resolution.py
def split_oss_uri(oss_uri: str) -> tuple[str, str] | None:
    ...


def oss_uri_to_http_uri(oss_uri: str) -> str:
    ...


def http_uri_to_oss_uri(http_uri: str) -> str | None:
    ...

# backend/packages/harness/deerflow/agents/thread_state.py
class WorkspaceFileState(TypedDict):
    ...
    http_uri: NotRequired[str | None]

class ViewedImageData(TypedDict):
    ...
    http_uri: NotRequired[str | None]
```

- [ ] **Step 4: Run the tests again and confirm they pass**

Run: `uv run pytest backend/tests/test_uri_resolution.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the helper and type updates**

```bash
git add backend/packages/harness/deerflow/uploads/uri_resolution.py backend/packages/harness/deerflow/agents/thread_state.py backend/tests/test_uri_resolution.py
git commit -m "feat: add runtime http uri helpers"
```

### Task 2: Keep backend history canonical and derive `http_uri` only at runtime

**Files:**
- Modify: `backend/packages/harness/deerflow/agents/middlewares/uploads_middleware.py:45-165`
- Modify: `backend/packages/harness/deerflow/agents/middlewares/file_reference_middleware.py:1-102`
- Modify: `backend/packages/harness/deerflow/agents/middlewares/view_image_middleware.py:97-142`
- Modify: `backend/packages/harness/deerflow/tools/builtins/view_image_tool.py:1-95`
- Modify: `backend/packages/harness/deerflow/agents/memory/prompt.py:330-363`
- Modify: `backend/packages/harness/deerflow/agents/memory/updater.py:253-287`
- Test: `backend/tests/test_uploads_state_and_file_reference_middleware.py`
- Test: `backend/tests/test_view_image_oss_uri_flow.py`

- [ ] **Step 1: Write the failing backend behavior tests**

```py
def test_uploads_middleware_keeps_oss_uri_and_drops_http_uri(tmp_path):
    middleware = UploadsMiddleware(base_dir=str(tmp_path))
    payload = {
        "filename": "photo.png",
        "size": 123,
        "path": "oss://demo-bucket/workspaces/workspace-1/uploads/photo.png",
        "virtual_path": "/mnt/user-data/uploads/photo.png",
        "oss_uri": "oss://demo-bucket/workspaces/workspace-1/uploads/photo.png",
        "object_key": "workspaces/workspace-1/uploads/photo.png",
        "http_uri": "https://signed.example/workspaces/workspace-1/uploads/photo.png",
    }
    state = {"messages": [HumanMessage(content="upload", additional_kwargs={"files": [payload]})]}
    runtime = SimpleNamespace(context={"workspace_id": "workspace-1"})
    result = middleware.before_agent(state, runtime)
    assert result is not None
    file_entry = result["uploaded_files"][0]
    assert file_entry["oss_uri"] == payload["oss_uri"]
    assert file_entry["object_key"] == payload["object_key"]
    assert file_entry.get("http_uri") is None


def test_file_reference_middleware_does_not_persist_presigned_urls(monkeypatch):
    middleware = FileReferenceMiddleware()
    monkeypatch.setattr(
        file_reference_middleware_module,
        "_presign_oss_uri",
        lambda oss_uri: f"https://signed.example/{oss_uri.removeprefix('oss://')}",
    )
    state = {
        "messages": [
            HumanMessage(content="Open oss://demo-bucket/workspaces/ws/uploads/report.md now.")
        ]
    }
    result = middleware.before_model(state, SimpleNamespace(context={"workspace_id": "workspace-1"}))
    assert result is not None
    assert "https://signed.example" not in result["messages"][0].content
    assert "oss://demo-bucket/workspaces/ws/uploads/report.md" in result["messages"][0].content


def test_view_image_injected_message_prefers_oss_uri(tmp_path):
    middleware = ViewImageMiddleware()
    state = {
        "viewed_images": {
            "oss://demo-bucket/workspaces/ws-1/uploads/photo.png": {
                "base64": "ZmFrZS1pbWFnZS1kYXRh",
                "mime_type": "image/png",
                "virtual_path": "/mnt/user-data/uploads/photo.png",
                "oss_uri": "oss://demo-bucket/workspaces/ws-1/uploads/photo.png",
                "http_uri": "https://signed.example/workspaces/ws-1/uploads/photo.png",
                "object_key": "workspaces/ws-1/uploads/photo.png",
            }
        }
    }
    result = middleware.before_model(state, SimpleNamespace())
    assert result is not None
    message = result["messages"][0]
    assert "oss://demo-bucket/workspaces/ws-1/uploads/photo.png" in str(message.content)
    assert "https://signed.example" not in str(message.content)
    assert "oss://demo-bucket/workspaces/ws-1/uploads/photo.png" in str(message.content)
    assert "https://signed.example" not in str(message.content)
```

- [ ] **Step 2: Run the tests to confirm current behavior is wrong**

Run: `uv run pytest backend/tests/test_uploads_state_and_file_reference_middleware.py backend/tests/test_view_image_oss_uri_flow.py -q`

Expected: FAIL because the current middlewares still allow presigned URLs into message/state paths.

- [ ] **Step 3: Rewrite the middlewares to keep `oss_uri` canonical**

```py
# uploads_middleware.py
# - keep `oss_uri` / `object_key` in file state
# - attach `http_uri` only to runtime payloads, never to persisted history text

# file_reference_middleware.py
# - stop replacing message content with presigned URLs
# - preserve `oss_uri` in content/history
# - derive `http_uri` only for transient browser/model-facing metadata

# view_image_tool.py
# - resolve uploaded images back to `oss_uri` / `object_key`
# - store `http_uri` as transient metadata if needed

# view_image_middleware.py
# - display `oss_uri` in the injected human message text
# - keep `virtual_path` only as a tool hint

# memory/prompt.py and memory/updater.py
# - strip any lingering `http_uri` or presigned `https://...` before long-term memory is stored
```

- [ ] **Step 4: Run the tests again and confirm they pass**

Run: `uv run pytest backend/tests/test_uploads_state_and_file_reference_middleware.py backend/tests/test_view_image_oss_uri_flow.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the backend normalization**

```bash
git add backend/packages/harness/deerflow/agents/middlewares/uploads_middleware.py backend/packages/harness/deerflow/agents/middlewares/file_reference_middleware.py backend/packages/harness/deerflow/agents/middlewares/view_image_middleware.py backend/packages/harness/deerflow/tools/builtins/view_image_tool.py backend/packages/harness/deerflow/agents/memory/prompt.py backend/packages/harness/deerflow/agents/memory/updater.py backend/tests/test_uploads_state_and_file_reference_middleware.py backend/tests/test_view_image_oss_uri_flow.py
git commit -m "fix: keep oss uris canonical in history"
```

### Task 3: Teach the frontend to prefer `http_uri` and fall back to `oss_uri`

**Files:**
- Modify: `frontend/src/core/messages/utils.ts:326-389`
- Modify: `frontend/src/core/uploads/composer-core.ts:34-53`
- Modify: `frontend/src/core/threads/hooks.ts:346-390`
- Modify: `frontend/src/components/workspace/messages/message-list-item.tsx:85-431`
- Modify: `frontend/src/core/oss/source.ts:1-22`
- Test: `frontend/src/core/oss/source.test.ts`
- Test: `frontend/src/core/uploads/composer-core.test.ts`

- [ ] **Step 1: Write the failing frontend tests**

```ts
import assert from "node:assert/strict";
import test from "node:test";

const { getBrowserOssSourceFromOssUri } = await import(
  new URL("./source.ts", import.meta.url).href,
);
const { buildMessageFilesFromAttachments } = await import(
  new URL("./composer-core.ts", import.meta.url).href,
);


void test("parses an oss uri into a browser source", () => {
  assert.deepEqual(
    getBrowserOssSourceFromOssUri("oss://demo-bucket/workspaces/ws-1/uploads/photo.png"),
    {
      ossUri: "oss://demo-bucket/workspaces/ws-1/uploads/photo.png",
      objectKey: "workspaces/ws-1/uploads/photo.png",
    },
  );
});


void test("preserves http_uri on message files built from uploads", () => {
  const files = buildMessageFilesFromAttachments([
    {
      uploadState: "uploaded",
      uploadedFile: {
        filename: "photo.png",
        size: 123,
        path: "oss://demo-bucket/workspaces/ws-1/uploads/photo.png",
        virtual_path: "/mnt/user-data/uploads/photo.png",
        oss_uri: "oss://demo-bucket/workspaces/ws-1/uploads/photo.png",
        object_key: "workspaces/ws-1/uploads/photo.png",
        signed_url: "https://signed.example/workspaces/ws-1/uploads/photo.png",
      },
    },
  ]);
  assert.equal(files[0]?.http_uri, "https://signed.example/workspaces/ws-1/uploads/photo.png");
});
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `pnpm exec node --test src/core/oss/source.test.ts src/core/uploads/composer-core.test.ts`

Expected: FAIL because the frontend file/message shapes still do not carry `http_uri`.

- [ ] **Step 3: Update the frontend data model and renderers**

```ts
// frontend/src/core/messages/utils.ts
export interface FileInMessage {
  filename: string;
  size: number;
  path: string;
  virtual_path?: string;
  oss_uri?: string | null;
  http_uri?: string | null;
  object_key?: string;
  status?: "uploading" | "uploaded";
}

// frontend/src/core/uploads/composer-core.ts and frontend/src/core/threads/hooks.ts
// - copy `signed_url` into `http_uri` when building FileInMessage
// - keep `oss_uri` and `object_key` intact

// frontend/src/components/workspace/messages/message-list-item.tsx
// - prefer `file.http_uri`
// - otherwise resolve `file.oss_uri` through the OSS helper
// - never render a long-lived presigned URL as the persisted source
```

- [ ] **Step 4: Run the tests and typecheck again**

Run: `pnpm exec node --test src/core/oss/source.test.ts src/core/uploads/composer-core.test.ts && pnpm typecheck`

Expected: PASS.

- [ ] **Step 5: Commit the frontend rendering changes**

```bash
git add frontend/src/core/messages/utils.ts frontend/src/core/uploads/composer-core.ts frontend/src/core/threads/hooks.ts frontend/src/components/workspace/messages/message-list-item.tsx frontend/src/core/oss/source.ts frontend/src/core/oss/source.test.ts frontend/src/core/uploads/composer-core.test.ts
git commit -m "feat: render oss backed message images safely"
```

### Task 4: Final verification and cleanup

**Files:**
- Modify: any file still emitting presigned URLs into persisted history

- [ ] **Step 1: Run the focused backend and frontend checks**

Run: `uv run pytest backend/tests/test_uri_resolution.py backend/tests/test_uploads_state_and_file_reference_middleware.py backend/tests/test_view_image_oss_uri_flow.py -q && pnpm exec node --test src/core/oss/source.test.ts src/core/uploads/composer-core.test.ts && pnpm typecheck`

Expected: PASS.

- [ ] **Step 2: Scan for lingering presigned URLs in persisted-history code paths**

Confirm there are no remaining code paths that write `https://signed...` into message history or thread state; only runtime/browser payloads may carry it.

- [ ] **Step 3: Commit the finished work**

```bash
git add .
git commit -m "fix: keep persisted oss history canonical"
```
