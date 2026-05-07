# Frontend OSS URL Resolution Design

## 背景

当前前端已经把工作空间文件的 canonical 身份切到 `oss://...`，但浏览器渲染层仍然存在多种链接来源：`artifact_url`、`virtual_path` 和直接拼接的下载地址。这个设计要把前端统一收敛成一条规则：**前端状态里只保存 `oss://`，真正给浏览器显示/打开/下载时，再通过一个统一 resolver hook 转成临时 `https://`**。

## 目标

1. 前端所有文件附件、图片预览、artifact 入口和下载入口都以 `oss://` 作为内部引用。
2. `virtual_path` 只保留给 sandbox、`read_file`、`view_image` 这类执行侧输入，不作为浏览器链接源。
3. 前端提供一个统一的 `useResolvedOssUrl()` resolver hook，把 `oss://` 转成临时 `https://`。
4. 所有浏览器可见的 `href` / `src` / 下载地址都从 resolver hook 获取，不直接拼接永久 URL。
5. 解析失败时，UI 提供明确的失败态，不把临时 `https://` 写回持久状态。

## 非目标

1. 不修改后端 OSS 存储模型。
2. 不把 `virtual_path` 引入浏览器展示链路。
3. 不为普通网页超链接引入 `oss://` 体系。
4. 不把临时 `https://` 作为任何前端持久状态。

## 术语

- **canonical identity**: `oss://bucket/object-key`
- **browser URL**: gateway 签发的临时 `https://...`
- **sandbox path**: `/mnt/user-data/...` 形式的 `virtual_path`

## 设计原则

- `oss://` 是前端业务状态的真相。
- `virtual_path` 只用于执行侧和 sandbox。
- 浏览器不直接消费 `oss://`，但浏览器可见的链接必须由 `oss://` 派生。
- 所有浏览器链接都通过同一个 resolver hook 获取，以便统一缓存、过期重取和错误处理。

## 架构

### 1. 前端文件数据模型

文件类型保留以下核心字段：

- `oss_uri`: canonical identity
- `virtual_path`: sandbox path
- `object_key`: workspace object key
- `filename`, `size`, `modified`, `extension`

前端不再把 `artifact_url` 或 `virtual_path` 当成浏览器链接的主要来源。`artifact_url` 只在旧数据兼容或调试层面出现，不作为新的 UI 入口。

### 2. 统一 Resolver Hook

新增 `useResolvedOssUrl(workspaceId, ossUri, options)`：

- 输入：`oss://bucket/object-key`
- 输出：临时 `https://...`
- 依赖：当前 `workspaceId` 上下文和 gateway 解析接口
- 行为：
  - 首次请求时向 gateway 获取 presigned URL
  - 结果按 `oss_uri` 缓存
  - 临时 URL 过期或解析失败时可重新请求

hook 的职责只限于“解析”，不负责文件上传、消息提交或 sandbox 路径处理。

### 3. 浏览器消费层

所有浏览器可见链接都改成下列模式：

- 文件下载按钮 -> `useResolvedOssUrl(workspaceId, file.oss_uri)`
- 图片预览 `img src` -> `useResolvedOssUrl(workspaceId, file.oss_uri)`
- artifact 详情页入口 -> `useResolvedOssUrl(workspaceId, artifact.oss_uri)`
- 消息里的附件链接 -> `useResolvedOssUrl(workspaceId, file.oss_uri)`

### 4. 执行侧保留

以下路径继续使用 `virtual_path`：

- sandbox `read_file` / `write_file`
- `view_image` tool 输入
- 任何需要让 agent 在文件系统里直接读写的调用

## 数据流

### 上传后

1. 前端从 gateway 获得上传结果，结果里包含 `oss_uri` 和 `virtual_path`。
2. 前端状态只把 `oss_uri` 作为 canonical file reference。
3. 当 UI 需要显示或打开文件时，调用 `useResolvedOssUrl(workspaceId, ossUri)`。
4. hook 向 gateway 请求临时 `https://`，浏览器只接触这个临时地址。

### artifact / image 显示

1. 文件卡片、消息附件、图片预览都从 `oss_uri` 出发。
2. 组件不直接使用 `virtual_path` 生成浏览器 URL。
3. `virtual_path` 仍然保留在数据模型中，供 sandbox / viewer 逻辑使用。
4. 如果解析失败，组件显示失败态并允许重试。

### 重新打开或刷新

1. 若临时 URL 过期，组件再次调用 `useResolvedOssUrl(workspaceId, ossUri)`。
2. resolver 重新向 gateway 取新 URL。
3. 前端无需刷新业务状态，也不修改 `oss_uri`。

## 组件边界

### 需要改的前端模块

- `frontend/src/core/uploads/api.ts`
  - 增加/统一文件类型中的 `oss_uri`
  - 补齐 resolver 请求所需的类型
- `frontend/src/core/uploads/cache.ts`
  - 保证缓存/观测文件都带 canonical `oss_uri`
- `frontend/src/core/uploads/composer-core.ts`
  - 提交消息时保持 canonical `oss_uri`，`virtual_path` 仅用于 sandbox
- `frontend/src/core/threads/hooks.ts`
  - 线程提交和乐观更新使用 `oss_uri`
- `frontend/src/components/workspace/workspace-files-panel.tsx`
  - 下载、预览入口统一走 resolver hook
- `frontend/src/components/workspace/messages/message-list-item.tsx`
  - 消息中的文件/图片链接统一走 resolver hook
- `frontend/src/core/artifacts/utils.ts`
  - 只保留非浏览器展示用途的路径工具，浏览器链接不再直接依赖它

### 新增模块

- `frontend/src/core/oss/use-resolved-oss-url.ts`
  - 统一 resolver hook
- `frontend/src/core/oss/api.ts`
  - 可选：封装 gateway 解析接口请求

## 错误处理

- `oss_uri` 缺失：组件不渲染可点击链接，显示不可用状态。
- resolver 请求失败：显示错误提示，并允许重试。
- 临时 URL 过期：下一次渲染或手动重试时重新请求。
- workspace 上下文缺失：resolver 直接返回失败，不生成假链接。

## 测试策略

1. `useResolvedOssUrl()` 单元测试
   - 输入 `oss://`，返回临时 `https://`
   - 缓存命中时不重复请求
   - 失败态返回可预测的错误结果
2. uploads/cache 相关测试
   - 验证文件状态始终保留 `oss_uri`
3. workspace files panel 测试
   - 下载/预览使用 resolver hook
   - 不再直接依赖 `virtual_path` 生成浏览器链接
4. message list item 测试
   - attachment/image 渲染从 `oss_uri` 出发
   - sandbox path 只保留在数据中，不作为浏览器链接

## 验收标准

1. 前端文件类 UI 不再直接把 `virtual_path` 作为浏览器链接源。
2. 所有文件附件、图片预览、artifact 入口都通过统一 resolver hook 获取临时 `https://`。
3. 前端状态中保留 `oss://`，不持久化临时 `https://`。
4. sandbox 仍然只使用 `virtual_path`。
5. 出错时前端可以明确地重试解析，不污染业务状态。

## 结论

这套设计把前端的链接处理拆成两层：

- **状态层**: `oss://` + `virtual_path`
- **浏览器层**: `useResolvedOssUrl()` 生成临时 `https://`

这样可以保证前端数据统一、链接可过期重取、sandbox 语义不变，同时避免把不同来源的 URL 混成一套。
