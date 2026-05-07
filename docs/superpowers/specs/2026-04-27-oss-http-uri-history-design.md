# OSS HTTP URI History Design

## 背景

当前会话历史里有些图片/文件引用已经被写成 presigned `https://...`，这类链接会过期，导致后续回看历史时不可用。正确的持久化真相应该是 `oss://...`，而 `https://...` 只能是运行时派生值。

## 目标

1. 会话历史、消息历史、`uploaded_files`、`viewed_images` 的持久化内容统一保存 `oss://...`。
2. `http_uri` 作为派生字段，只在后端运行时生成，不作为持久化真相。
3. 前端渲染时按需把 `oss://...` 转成当前可用的 presigned `https://...`。
4. 模型上下文里不再长期保存过期的 presigned URL。
5. 过期后可以重新生成新的 `http_uri`，不污染业务历史。

## 非目标

1. 不改变 OSS 存储本身。
2. 不把 `http_uri` 作为唯一来源。
3. 不要求历史数据一次性全量迁移。
4. 不重做前端文件预览架构。

## 术语

- **oss_uri**: `oss://bucket/object-key`，持久化真相。
- **http_uri**: presigned `https://...`，仅用于展示或临时访问。
- **virtual_path**: sandbox 内路径，仅用于工具和执行侧。

## 设计原则

- `oss_uri` 永远是 canonical。
- `http_uri` 永远是派生值。
- 后端可以生成 `http_uri`，但不应把它写回历史真相。
- 前端只负责把 `oss_uri` 解析成可访问的浏览器 URL。

## 架构

### 1. 后端持久化层

持久化消息和线程状态时，只保存 `oss_uri`、`object_key`、`virtual_path` 这些稳定字段。任何需要直接给模型或浏览器访问的 `https://...`，都必须在写入历史之前还原成 `oss_uri`。

### 2. 后端运行时派生层

新增一个运行时派生 helper，输入 `oss_uri`，输出临时 `http_uri`。这个 helper 只能在以下场景使用：

- 给前端返回即时可访问链接
- 在模型上下文中临时展开可见内容
- 生成当前请求生命周期内的展示数据

### 3. 前端渲染层

前端组件继续以 `oss_uri` 作为数据源，渲染时通过现有 OSS resolver 转成 presigned `https://...`。如果 `http_uri` 已由后端提供，前端可以直接使用；否则按需解析 `oss_uri`。

## 数据流

### 上传后

1. 后端接收上传结果，保存 `oss_uri` / `object_key` / `virtual_path`。
2. 如果某个响应需要给浏览器立即打开，后端可生成 `http_uri`。
3. 写入会话历史前，丢弃 `http_uri`，只保留 `oss_uri`。

### 模型调用前

1. 中间件读取历史和附件。
2. 如果内容里存在 `http_uri`，在进入持久化前转换回 `oss_uri`。
3. 模型看到的上下文优先是 `oss_uri`，工具调用继续使用 `virtual_path`。

### 前端渲染时

1. 组件拿到 `oss_uri`。
2. 通过 OSS resolver 获取当前有效的 `http_uri`。
3. 浏览器只接触临时 URL，不接触持久化真相。

## 需要修改的模块

### 后端

- `backend/packages/harness/deerflow/agents/thread_state.py`
  - 明确 `WorkspaceFileState` / `ViewedImageData` 的 `oss_uri` 为主字段，`http_uri` 仅作运行态字段（如需要）。
- `backend/packages/harness/deerflow/agents/middlewares/uploads_middleware.py`
  - 注入历史时优先输出 `oss_uri`，不要把 presigned URL 写进持久化消息。
- `backend/packages/harness/deerflow/agents/middlewares/view_image_middleware.py`
  - 注入的图片描述优先引用 `oss_uri`。
- `backend/packages/harness/deerflow/tools/builtins/view_image_tool.py`
  - 读取图片时使用 `virtual_path`，但 state 中保留 `oss_uri` / `object_key`。

### 前端

- `frontend/src/core/oss/*`
  - 保持 `oss_uri -> http_uri` 的解析能力。
- `frontend/src/components/workspace/messages/message-list-item.tsx`
  - 让图片回显和消息附件优先走 `oss_uri`。
- `frontend/src/components/workspace/artifacts/artifact-file-detail.tsx`
  - 保持 `oss_uri` 解析预览的逻辑。

## 错误处理

- `oss_uri` 缺失：不生成 `http_uri`，UI 退化为不可点击展示。
- `http_uri` 过期：重新根据 `oss_uri` 生成，不修改持久化历史。
- 历史里已有 `https://...`：在下一次读取/重写时规范化回 `oss_uri`。

## 测试策略

1. 后端单测
   - 断言持久化状态里只保留 `oss_uri`。
   - 断言 `http_uri` 不会落入 history/state。
   - 断言图片注入消息优先引用 `oss_uri`。
2. 前端单测
   - `oss_uri` 能解析成当前 presigned URL。
   - 图片/文件回显不依赖长期保存的 `https://...`。
3. 回归测试
   - 上传图片 -> 让 agent 描述 -> 再回显图片
   - 刷新后历史仍可正常打开

## 验收标准

1. 会话历史里不再持久化 presigned `https://...` 作为主引用。
2. 所有持久化消息都以 `oss://...` 为 canonical。
3. 前端可以随时把 `oss://...` 转成可访问的 `http_uri`。
4. `http_uri` 过期后，历史和渲染都能重新生成。

## 结论

这套设计把链接生命周期拆成两层：

- **持久层**: `oss://...`
- **运行层**: `http_uri`

这样既保留了历史可恢复性，也避免把过期链接写进会话数据。
