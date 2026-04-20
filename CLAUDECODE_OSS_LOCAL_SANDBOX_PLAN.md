# Claude Code 可执行方案：本地容器 OSS 直挂改造

> 适用范围：仅覆盖 `make dev` 的本地容器 sandbox。  
> 不在本次范围内：`make docker`、provisioner、K8s 远程 sandbox。

## Summary

- 去掉 `/api/workspaces/{workspace_id}/uploads` 对 `thread_id` 的依赖，workspace 上传接口回归纯 workspace 语义。
- 移除上传后同步到线程本地文件的逻辑；agent 读取上传文件改为直接读本机已挂载的 OSS 目录。
- 本地容器 sandbox 保持 `/mnt/user-data/uploads` 和 `/mnt/user-data/outputs` 这组虚拟路径不变，但底层挂载源改为 OSS 本地挂载目录。
- agent 生成的文件直接写入 `workspaces/{workspace_id}/outputs` 对应挂载目录，不再做 run 前后补同步。
- 前端不长期依赖会过期的 `signed_url`，workspace 文件访问改走稳定后端代理 URL。

## Public API / Interface Changes

- 移除 `POST /api/workspaces/{workspace_id}/uploads`、`GET /api/workspaces/{workspace_id}/uploads/list`、`DELETE /api/workspaces/{workspace_id}/uploads` 的 `thread_id` 参数。
- 新增稳定代理接口：`GET /api/workspaces/{workspace_id}/uploads/content?object_key=...&download=true|false`。
- 保留 `artifact_url` 和 `markdown_artifact_url` 字段，但其值改为 workspace 稳定代理 URL，而不是 thread artifact URL。
- 新增配置 `uploads.oss.local_mount_root`，约定目录结构为 `workspaces/{workspace_id}/uploads` 与 `workspaces/{workspace_id}/outputs`。
- 扩展 sandbox provider 获取上下文的能力，允许本地容器挂载逻辑在 acquire 阶段拿到 `workspace_id`。

## 执行步骤

### 阶段 0：预检与配置

- [ ] 先确认本地开发实际走的是 container 型 `AioSandboxProvider`，不是 provisioner 模式；如果当前本地配置仍指向 provisioner，只调整本地开发配置入口，不改远程代码路径。
- [ ] 在 `backend/packages/harness/deerflow/config/uploads_config.py` 增加 `local_mount_root: str | None`，仅在 `uploads.backend=oss` 时启用。
- [ ] 在 `backend/packages/harness/deerflow/uploads/storage.py` 或相邻 helper 中增加本地挂载路径解析函数，统一返回 `local_mount_root/workspaces/{workspace_id}/uploads|outputs`。
- [ ] 约定未绑定 workspace 或未配置 `local_mount_root` 时，继续回退到线程本地 `uploads/outputs` 目录，避免破坏非 workspace 线程。

### 阶段 1：把 `workspace_id` 带进运行时

- [ ] 修改 `backend/app/gateway/services/runtime.py`，在启动 run 前把 thread 绑定的 `workspace_id` 放入 run context。
- [ ] 修改 `backend/packages/harness/deerflow/runtime/runs/worker.py`，构造 `Runtime(context=...)` 时复用完整 context，而不是只塞 `thread_id`。
- [ ] 修改 `backend/packages/harness/deerflow/sandbox/sandbox_provider.py`、`backend/packages/harness/deerflow/sandbox/middleware.py`、`backend/packages/harness/deerflow/sandbox/local/local_sandbox_provider.py`，让 provider acquire 接口能接收上下文但对旧 provider 保持兼容。
- [ ] 修改 `backend/packages/harness/deerflow/subagents/executor.py`，让 subagent 运行时也能继承 `workspace_id`，避免子代理首次懒初始化 sandbox 时丢失挂载上下文。

### 阶段 2：线程路径模型改成“本地 workspace + OSS uploads/outputs”

- [ ] 修改 `backend/packages/harness/deerflow/agents/middlewares/thread_data_middleware.py`，在“已绑定 workspace + OSS 本地挂载已配置”时，返回线程本地 `workspace_path` 与 OSS 挂载的 `uploads_path`、`outputs_path`。
- [ ] 修改 `backend/packages/harness/deerflow/community/aio_sandbox/aio_sandbox_provider.py`，本地容器模式下将 `/mnt/user-data/workspace` 挂线程本地目录，将 `/mnt/user-data/uploads`、`/mnt/user-data/outputs` 挂到 OSS 本地挂载目录。
- [ ] 不修改 `backend/packages/harness/deerflow/community/aio_sandbox/remote_backend.py` 和 `docker/provisioner`；本次明确不处理远程 sandbox。
- [ ] 修改 `backend/packages/harness/deerflow/sandbox/tools.py`，确保路径替换、访问校验、mask 逻辑都基于新的 `thread_data` 三段路径工作。

### 阶段 3：移除 workspace uploads 的 `thread_id` 逻辑

- [ ] 修改 `backend/app/gateway/routers/uploads.py`，删除 `thread_id` 查询参数、`_require_thread_context()`、`_load_thread_context()`、上传后 mirror、本地删除清理。
- [ ] 修改 `backend/app/gateway/services/workspace_uploads.py`，移除 `mirror_uploaded_file_to_thread()`、`sync_workspace_uploads_to_thread()`、remote sandbox sync helpers，以及所有 thread-local mirror 依赖。
- [ ] 保留 `build_workspace_file_response()` 的返回结构，但将 `artifact_url` 与 `markdown_artifact_url` 改为新的 workspace 稳定代理地址。
- [ ] 删除 `backend/app/gateway/services/runtime.py` 中 run 前的 workspace-to-thread sync 调用；run 后同步继续保持 no-op。

### 阶段 4：为 workspace 文件提供稳定后端代理

- [ ] 在 `backend/app/gateway/routers/uploads.py` 新增 `GET /content` 代理接口，按 `workspace_id + object_key` 校验文件归属后返回内容。
- [ ] 代理接口对 `html/xhtml/svg` 复用 `backend/app/gateway/routers/artifacts.py` 的主动下载策略，其余文本和二进制沿用现有 artifact 响应风格。
- [ ] workspace 文件面板默认用代理 URL 访问，不把 `signed_url` 当成长期主协议；`signed_url` 可以保留为辅助字段，但前端不依赖它做持久访问。
- [ ] thread artifact 路由继续保留，主要服务 agent 产物面板和现有 thread artifact UI。

### 阶段 5：让 artifact 与 agent 读取都走 OSS 挂载目录

- [ ] 修改 `backend/app/gateway/path_utils.py` 与 `backend/app/gateway/routers/artifacts.py`，让“thread 绑定 workspace”时，`/mnt/user-data/uploads` 和 `/mnt/user-data/outputs` 解析到 OSS 挂载目录，而 `/mnt/user-data/workspace` 仍解析到线程本地目录。
- [ ] 修改 `backend/packages/harness/deerflow/agents/middlewares/uploads_middleware.py`，新文件存在性检查和历史文件扫描都改读 workspace OSS 挂载目录，但发给模型的路径仍保持 `/mnt/user-data/uploads/<filename>`。
- [ ] 保持 `backend/packages/harness/deerflow/tools/builtins/present_file_tool.py` 的对外契约不变：只有 `/mnt/user-data/outputs/*` 能被展示；只是其底层 `outputs_path` 变成 OSS 挂载目录。
- [ ] 不改 agent prompt 中 `/mnt/user-data/uploads`、`/mnt/user-data/outputs` 的使用说明，确保模型侧无感迁移。

### 阶段 6：前端配套改造

- [ ] 修改 `frontend/src/core/uploads/api.ts`，移除 `threadId` 参数与 `thread_id` query 拼接。
- [ ] 修改 `frontend/src/core/threads/hooks.ts`，发送带附件消息时仍先 `ensureThread(threadId)` 取 `workspace_id`，但上传请求不再传 `threadId`。
- [ ] 修改 `frontend/src/components/workspace/workspace-files-panel.tsx`，list/delete 直接按 `workspaceId` 请求，预览/下载优先使用后端稳定代理 URL。
- [ ] 保持 thread artifact 详情页现有逻辑不变，避免把 agent outputs 的展示链路和 workspace 文件面板耦在一起。

## Verification

- [ ] 后端定向测试至少覆盖：

```bash
cd backend
uv run pytest tests/test_thread_data_middleware.py tests/test_uploads_middleware_core_logic.py tests/test_artifacts_router.py tests/test_aio_sandbox_provider.py
```

- [ ] 为 workspace 代理接口、runtime context 透传、无 `thread_id` 的 workspace uploads router、新 `thread_data` 路径模型补充或更新测试。
- [ ] 跑一组 artifact/附件兼容回归：

```bash
cd backend
uv run pytest tests/test_channels.py tests/test_channel_file_attachments.py
```

- [ ] 前端执行：

```bash
cd frontend
pnpm check
```

- [ ] 手工验证 1：在已绑定 workspace 的线程里上传文件，确认 OSS 挂载目录 `workspaces/{workspace_id}/uploads` 立即可见。
- [ ] 手工验证 2：agent 在 sandbox 中能直接读取 `/mnt/user-data/uploads/...`。
- [ ] 手工验证 3：agent 生成文件到 `/mnt/user-data/outputs/...` 后，宿主机挂载目录 `workspaces/{workspace_id}/outputs` 立即出现文件。
- [ ] 手工验证 4：workspace 文件面板在等待超过 signed URL 过期时间后，仍可通过稳定代理 URL 预览和下载。
- [ ] 手工验证 5：未绑定 workspace 的线程仍使用旧线程本地目录，不应被这次改造破坏。

## Acceptance Criteria

- `/api/workspaces/{workspace_id}/uploads` 全链路不再接收也不依赖 `thread_id`。
- 上传文件不再同步到线程本地 `uploads` 目录。
- 本地容器 sandbox 中的 `/mnt/user-data/uploads` 与 `/mnt/user-data/outputs` 实际读写的是 OSS 本地挂载目录。
- agent 生成文件会直接进入 `workspaces/{workspace_id}/outputs`。
- workspace 文件访问不受 `signed_url` 过期影响。
- `make docker`、provisioner、K8s 远程 sandbox 相关代码路径行为不变。

## Assumptions

- 宿主机已经有可读写的 OSS 挂载目录，本次只负责让 DeerFlow 使用它，不负责实现挂载器本身。
- `uploads.oss.local_mount_root` 指向 bucket 根目录，而不是某个单独 workspace 子目录。
- 当前执行目标是本地容器开发链路；远程 sandbox 的 mount 能力和 provisioner API 改造明确留到后续单独任务。
- `DeerFlowClient` 的线程本地上传 API 不在本次主范围；仅当共享类型或测试被本次接口变更影响时，才做最小兼容修正。
