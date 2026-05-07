# OSS 统一文件协议设计

## 背景

当前系统里，文件在 gateway、LangGraph agent、前端和 sandbox 之间存在多种表示方式：本地路径、HTTP artifact URL、临时下载链接和沙箱虚拟路径。这个方案会把这些表示统一收敛为一条规则：**系统内部只认 `oss://`，外部可访问链接只在边界层临时生成**。

## 目标

1. 工作空间内所有文件都以 `oss://<bucket>/<object-key>` 作为内部 canonical 标识。
2. 前端上传文件时，先向 gateway 请求 OSS presigned upload URL，再直接上传到 OSS。
3. 前端预览/下载文件时，向 gateway 请求 OSS presigned GET URL。
4. gateway、LangGraph agent、前端的业务状态和 checkpoint 统一保存 `oss://`。
5. sandbox 保持现有文件系统语义，只接收路径，不处理 `oss://`。
6. 仅在需要把文件内容交给 LLM 时，才把 `oss://` 转成临时 `https://` 链接。

## 非目标

1. 不做旧数据兼容迁移。
2. 不把 sandbox 改造成 URI 感知层。
3. 不通过 gateway 代理文件上传或文件下载流量。
4. 不把 presigned URL 作为持久状态保存。

## 核心原则

- `oss://` 是状态。
- `https://` 是派生物。
- checkpoint 保存可恢复信息，不保存临时访问态。
- sandbox 只处理路径，不处理对象存储协议。
- gateway 是唯一签名入口。

## 协议约定

### Canonical URI

统一使用：

```text
oss://<bucket>/<object-key>
```

约束：

- `<bucket>` 必须显式存在。
- `<object-key>` 表示对象在 bucket 内的完整 key。
- 同一个文件在业务层只能有一个 canonical `oss://`。

### Workspace 命名空间

工作空间对象建议放在统一前缀下，便于管理和权限控制：

```text
workspaces/<workspace_id>/workspace/...
workspaces/<workspace_id>/uploads/...
workspaces/<workspace_id>/outputs/...
```

其中：

- `workspace/` 用于工作区文件
- `uploads/` 用于前端上传文件
- `outputs/` 用于 agent/sandbox 产出文件

## 组件职责

### Frontend

- 向 gateway 请求 presigned upload URL。
- 直接把文件上传到 OSS。
- 上传完成后通知 gateway 生成并返回 `oss://`。
- 预览/下载时向 gateway 请求 presigned GET URL。
- 前端状态和 API 返回值优先保存 `oss://`。

### Gateway

- 校验 workspace 和用户权限。
- 签发 presigned PUT / GET URL。
- 维护文件元数据与 `oss://` 映射。
- 为 agent/LLM 边界提供临时可访问链接。
- 对外暴露统一的文件登记、查询和签名接口。

### LangGraph Agent

- 业务状态、tool 参数、checkpoint 统一使用 `oss://`。
- 仅在构造 LLM 输入时，将需要暴露给模型的文件临时转换为 `https://`。
- checkpoint 恢复后，重新从 `oss://` 生成新的临时访问链接。

### Sandbox

- 维持现有文件系统语义。
- 仅通过路径访问文件，不识别 `oss://`。
- 路径映射由 gateway 在下发任务参数前完成，或由 OSS 挂载层在宿主机侧预先完成。
- sandbox 产出的文件回落到 OSS 后，再生成新的 `oss://`。

## 数据流

### 1. 上传

1. 前端请求 gateway 获取 presigned PUT URL。
2. gateway 校验权限后返回 presigned PUT URL 和目标 object key。
3. 前端直接上传到 OSS。
4. 上传成功后，前端通知 gateway 完成登记。
5. gateway 返回对应的 `oss://`。

### 2. 预览 / 下载

1. 前端请求 gateway 获取 presigned GET URL。
2. gateway 校验权限后返回临时 `https://`。
3. 前端直接访问 OSS。

### 3. Agent / Checkpoint

1. agent 接收到的所有文件引用都使用 `oss://`。
2. checkpoint 只持久化 `oss://` 和必要的文件元数据。
3. 真正喂给 LLM 前，gateway 生成临时 `https://`。
4. LLM 只看到临时可访问链接，不接触内部协议。

### 4. Sandbox

1. gateway 或挂载层先把 `oss://` 映射成 sandbox 可见路径。
2. sandbox 继续按本地文件系统方式读写。
3. sandbox 产物重新落 OSS。
4. 系统返回新的 `oss://` 供后续状态使用。

## Checkpoint 规则

checkpoint 中保存：

- `oss://` 作为主引用
- `filename`
- `content_type`
- `size`
- `checksum`（如有）

checkpoint 中不保存：

- presigned PUT URL
- presigned GET URL
- 任何短期可访问的 `https://` 链接

恢复执行时，所有临时访问链接都必须重新签发。

## 错误处理

- `oss://` 格式非法：直接拒绝。
- 权限不足：gateway 不签发 URL。
- presigned URL 过期：重新向 gateway 请求签名。
- OSS 上传失败：前端重试上传，不污染业务状态。
- sandbox 路径缺失：任务失败并返回可重试错误。

## 迁移策略

本方案不考虑旧数据兼容，迁移采用一次性切换：

1. gateway 新增 presigned upload / GET 签名接口。
2. 前端改为直传 OSS，并使用 presigned GET。
3. agent checkpoint 和业务状态统一改为 `oss://`。
4. sandbox 保持路径模型不变，仅调整上游映射。
5. 清理旧的 URL 持久化路径。

## 验收标准

1. 前端上传文件不再经过 gateway 文件代理。
2. 前端预览/下载文件不再使用永久 HTTP artifact URL。
3. checkpoint 中不出现 presigned URL。
4. sandbox 中不出现 `oss://` 解析逻辑。
5. agent 处理文件时，持久状态里只保留 `oss://`。
6. LLM 输入中的外部链接均为临时签名 `https://`。

## 结论

这套设计把文件协议分成两层：

- 内部层：统一使用 `oss://`
- 外部访问层：只在边界处生成临时 `https://`

这样可以保证业务状态稳定、checkpoint 可恢复、sandbox 保持简单，同时满足上传、预览、下载和 LLM 访问的需要。
