# Workspace ID + 阿里云 OSS V2 上传链路重构方案

## 1. 背景

当前 DeerFlow 已经存在真实的 `workspace_id` 领域模型：

- 后端有 `Workspace` 表和 `Thread.workspace_id`
- 新建线程时会自动创建 workspace 并绑定到 thread
- 线程接口响应里已经带 `workspace_id`

但文件上传链路仍然是旧的 `thread_id` 语义：

- 上传路由仍是 `/api/threads/{thread_id}/uploads`
- 前端上传 hooks 仍以 `threadId` 为主参数
- 右侧工作区文件面板目前只是静态 mock UI
- 本地线程目录仍承担上传文件的持久化职责

这和当前产品语义不一致。目标是把“文件归属”统一提升到 `workspace_id`，并将持久化存储切到阿里云 OSS。

---

## 2. 本次已确认的关键决策

- 上传、列举、删除文件的主资源标识统一改为 `workspace_id`
- 不保留旧的 `/api/threads/{thread_id}/uploads` 兼容路由，直接切换
- 现有线程都已有 `workspace_id`，不做旧线程自动补建逻辑
- OSS SDK 使用 `alibabacloud-oss-v2`
- OSS 是工作区文件的唯一持久化真源
- 线程本地 `uploads` 目录继续保留，但只作为运行时镜像，不再是 canonical storage
- 右侧工作区文件面板只在普通线程页 `/workspace/chats/[thread_id]` 展示
- 本轮不做 i18n 接入，文案可继续硬编码中文
- 本轮不增加文件预览、下载、删除 UI，只完成真实数据接入

---

## 3. 目标

### 3.1 业务目标

- 工作区文件以 `workspace_id` 为唯一归属
- 文件上传后持久化到 OSS 对应 workspace 目录
- 普通线程页右侧文件面板展示该线程绑定 workspace 下的真实 OSS 文件
- agent 仍然可以继续通过 `/mnt/user-data/uploads/...` 访问上传文件
- 新线程首次发送且带附件时，上传流程也能正常工作

### 3.2 非目标

- 不改 artifact 主逻辑
- 不把 artifact 路由整体切到 workspace 维度
- 不把线程本地整个目录结构改造成 workspace 目录结构
- 不做文件面板的预览、下载、删除交互
- 不覆盖 `/workspace/chats/new` 和 agent 聊天页右侧面板

---

## 4. 总体设计

### 4.1 资源归属

采用“双层语义”：

- `workspace_id` 负责文件业务归属和 OSS 持久化目录
- `thread_id` 负责当前运行实例的本地沙箱镜像与 artifact 访问

也就是说：

- 文件“属于哪个工作区”由 `workspace_id` 决定
- 文件“当前运行时镜像到哪个线程本地目录”由 `thread_id` 决定

### 4.2 存储分层

- Canonical source：阿里云 OSS
- Runtime mirror：`threads/{thread_id}/user-data/uploads`

### 4.3 OSS 根目录规则

统一使用：

`workspaces/{workspace_id}`

并持久化到：

`Workspace.file_path`

---

## 5. 配置与环境变量

### 5.1 根目录 `.env`

在仓库根目录 `.env` 中新增以下变量：

- `ALIYUN_OSS_ENDPOINT`
- `ALIYUN_OSS_BUCKET`
- `ALIYUN_OSS_ACCESS_KEY_ID`
- `ALIYUN_OSS_ACCESS_KEY_SECRET`
- `ALIYUN_OSS_SIGNED_URL_EXPIRES_SECONDS`

`.env.example` 中增加对应占位符，但不写真实密钥。

### 5.2 `config.yaml`

新增 `uploads` 配置段，值通过 `$ENV_VAR` 解析：

```yaml
uploads:
  backend: oss
  oss:
    endpoint: $ALIYUN_OSS_ENDPOINT
    bucket: $ALIYUN_OSS_BUCKET
    access_key_id: $ALIYUN_OSS_ACCESS_KEY_ID
    access_key_secret: $ALIYUN_OSS_ACCESS_KEY_SECRET
    signed_url_expires_seconds: $ALIYUN_OSS_SIGNED_URL_EXPIRES_SECONDS
```

说明：

- 仓库当前已经在后端启动时 `load_dotenv()`
- `config.yaml` 也已经支持 `$ENV_VAR` 解析
- 因此采用“根 `.env` + `config.yaml` 引用”的现有配置习惯即可

### 5.3 Python 依赖

backend harness 增加：

- `alibabacloud-oss-v2`

不引入 `oss2`。

---

## 6. 数据模型与数据修正

### 6.1 `Workspace.file_path` 语义固定

将 `Workspace.file_path` 统一定义为：

- 工作区在 OSS 中的根前缀
- 默认值为 `workspaces/{workspace_id}`

### 6.2 新建线程时的行为

当前线程创建流程已经会自动创建 workspace。需要补充：

- 创建 workspace 后立即写入默认 `file_path`
- 不再允许新 workspace 的 `file_path` 留空

### 6.3 历史数据修正

增加一次性修正逻辑：

- 对所有 `workspaces.file_path IS NULL` 的记录回填为 `workspaces/{id}`

这里不涉及 `workspace_id` 补建，因为当前业务前提是所有线程都已有 `workspace_id`。

---

## 7. 后端改造

## 7.1 OSS 存储封装

新增独立 OSS 存储层，基于 `alibabacloud-oss-v2` 提供以下能力：

- 生成 workspace object key
- 上传对象
- 列举 prefix 下对象
- 删除对象
- 生成签名 URL

推荐职责边界：

- 路由层只负责鉴权、参数解析、响应拼装
- OSS 客户端封装只负责存储操作
- 上传 manager 继续负责文件名规整、`virtual_path` 生成、本地镜像辅助逻辑

## 7.2 上传主路由

将主路由改为：

- `POST /api/workspaces/{workspace_id}/uploads`
- `GET /api/workspaces/{workspace_id}/uploads/list`
- `DELETE /api/workspaces/{workspace_id}/uploads/{filename}`

不保留旧 `/api/threads/{thread_id}/uploads`。

## 7.3 鉴权

新增 workspace 所有权校验：

- 调用方必须是该 workspace 所属用户
- 如果需要 `thread_id` 上下文，还需校验该 thread 属于当前用户，且其 `workspace_id` 与路径中的 `workspace_id` 一致

## 7.4 上传行为

`POST /api/workspaces/{workspace_id}/uploads` 的行为：

- 入参仍为 `multipart/form-data`
- 额外接收 `thread_id` 作为可选 query 参数
- 对每个文件先规范化文件名
- 上传原文件到 OSS
- 若文件类型支持转换，生成 markdown 伴生文件并上传到 OSS
- 若传入 `thread_id`，则把原文件和 markdown 文件同步写入该线程本地 `uploads` 目录
- 仍然返回 agent 需要的 `virtual_path`
- 若存在线程本地镜像，则返回 `artifact_url`

## 7.5 列表行为

`GET /api/workspaces/{workspace_id}/uploads/list` 的行为：

- 直接列举 `Workspace.file_path` 对应的 OSS prefix
- 结果按文件名或修改时间稳定排序
- 返回根路径信息和文件列表
- 不再以线程本地目录为准

返回建议结构：

```json
{
  "root_label": "workspace",
  "root_path": "oss://<bucket>/workspaces/<workspace_id>/",
  "count": 2,
  "files": [
    {
      "filename": "report.pdf",
      "size": 1024,
      "modified": 1776067200,
      "object_key": "workspaces/<workspace_id>/report.pdf",
      "virtual_path": "/mnt/user-data/uploads/report.pdf",
      "signed_url": "https://...",
      "artifact_url": null
    }
  ]
}
```

## 7.6 删除行为

`DELETE /api/workspaces/{workspace_id}/uploads/{filename}` 的行为：

- 删除 OSS 中对应对象
- 若文件存在 markdown 伴生文件，一并删除
- 若传入当前 `thread_id`，则同步清理该线程本地镜像
- 本轮只做后端能力，不要求前端面板立即暴露删除按钮

---

## 8. 运行时与本地镜像

## 8.1 保留线程本地 uploads 目录

当前线程本地目录仍然保留：

- agent sandbox 读取文件依赖 `/mnt/user-data/uploads/...`
- 现有 artifact 和消息文件展示逻辑依赖 `virtual_path`
- 因此本轮不移除本地镜像能力

## 8.2 运行前同步

在 run 启动前增加单向同步：

- 从当前 thread 绑定的 workspace OSS 目录
- 同步到当前 thread 的本地 `uploads` 目录

目标：

- 即使文件最初是由同 workspace 的其他线程上传
- 当前线程在运行时也能看到完整文件集

## 8.3 不做反向同步

保持以下约束：

- agent 在本地 `uploads` 目录中的任意修改，不自动回写 OSS
- OSS 始终是 canonical source
- 本轮只保证“上传产生的 canonical 文件”能被同步到线程本地

---

## 9. 前端改造

## 9.1 线程与 workspace 的获取方式

前端不能再假设只有 `threadId` 就足够。

需要补两类能力：

- `ensureThread(threadId)`：确保新线程已在后端创建成功，并能返回真实 `workspace_id`
- `getThread(threadId)`：查询线程详情并读取 `workspace_id`

原因：

- 当前新会话本地先生成 `threadId`
- 带附件的首条消息是“先上传，后 submit”
- 上传接口改成只认 `workspace_id` 后，必须先拿到真实线程绑定的 workspace

## 9.2 新线程首次带附件的时序

推荐时序：

1. 用户在 `/workspace/chats/new` 输入文本并选择附件
2. 前端先调用 `ensureThread(threadId)`
3. 后端创建 thread + workspace，并返回 `workspace_id`
4. 前端调用 `/api/workspaces/{workspace_id}/uploads`
5. 上传成功后，将 `virtual_path` 写入消息的 `additional_kwargs.files`
6. 再调用 thread submit / run

这样可以避免“新线程首条带附件时拿不到 workspace_id”的问题。

## 9.3 上传 hooks 改造

前端上传 API 与 hooks 统一改为 workspace 语义：

- `uploadFiles(workspaceId, files, { threadId? })`
- `listUploadedFiles(workspaceId)`
- `deleteUploadedFile(workspaceId, filename, { threadId? })`

query key 也改为 workspace 维度：

- `["uploads", "list", workspaceId]`

## 9.4 `useThreadStream` 改造

在提交带附件消息前：

- 若线程尚未落库，先 `ensureThread(threadId)`
- 拿到 `workspace_id`
- 再执行上传
- 再提交消息到 thread stream

普通无附件消息的原有流程可以保持最小改动。

---

## 10. 右侧工作区文件面板

## 10.1 展示范围

只在普通线程页展示：

- `/workspace/chats/[thread_id]`

不改：

- `/workspace/chats/new`
- `/workspace/agents/[agent_name]/chats/[thread_id]`

## 10.2 组件职责

`WorkspaceFilesPanel` 从静态 mock 改为真实数据组件。

建议接口：

```tsx
WorkspaceFilesPanel({ threadId, className? })
```

组件内部状态保留：

- `query`
- `selectedFile`

新增状态：

- `isLoading`
- `error`

## 10.3 数据获取流程

- 根据 `threadId` 获取 thread 详情
- 读取 `workspace_id`
- 再调用 workspace 文件列表接口

## 10.4 UI 行为

保留现有交互：

- 标题
- 根目录路径
- 搜索框
- 刷新按钮
- 文件列表
- 空结果提示
- 选中高亮

本轮不增加：

- 文件预览
- 下载按钮
- 删除按钮
- 拖拽上传
- 目录树递归展开

---

## 11. API 与类型约定

## 11.1 后端接口

### 上传

`POST /api/workspaces/{workspace_id}/uploads?thread_id={thread_id}`

### 列表

`GET /api/workspaces/{workspace_id}/uploads/list`

### 删除

`DELETE /api/workspaces/{workspace_id}/uploads/{filename}?thread_id={thread_id}`

## 11.2 文件对象结构

建议统一文件响应对象字段：

- `filename`
- `size`
- `modified`
- `object_key`
- `virtual_path`
- `signed_url`
- `artifact_url`
- `markdown_file`
- `markdown_virtual_path`
- `markdown_artifact_url`

说明：

- `virtual_path` 继续服务于 agent 和消息元数据
- `artifact_url` 仅在当前线程已有本地镜像时可用，可为 `null`
- 右侧文件面板主要使用 `filename`、`modified`、`size`
- 后续如要支持直接预览，可优先用 `signed_url`

---

## 12. 测试方案

## 12.1 后端测试

需要补充或改造以下覆盖：

- workspace 上传路由的鉴权校验
- OSS V2 SDK 封装层的上传、列举、删除、签名 URL
- markdown 伴生文件上传与删除
- 上传时同步写入当前线程本地镜像
- run 前从 OSS 到线程本地 `uploads` 的同步
- `Workspace.file_path` 默认写入与空值回填

## 12.2 前端测试

需要验证：

- 普通线程页右侧面板始终展示
- 面板宽度仍为 `clamp(320px,22vw,420px)`
- 面板能展示真实 OSS 列表
- 搜索可本地过滤
- 点击文件存在稳定选中态
- 刷新能重新拉取数据
- 新线程首次带附件发送能正常完成
- 现有 artifact 展示不受影响

## 12.3 建议命令

- 后端：相关 pytest 用例
- 前端：`pnpm check`

---

## 13. 风险点

- 新线程首条带附件消息的时序最容易出问题，必须先确保线程已创建并拿到真实 `workspace_id`
- `alibabacloud-oss-v2` 的签名 URL、列举和异常处理接口需要确认具体 SDK 用法
- 本地线程镜像和 OSS canonical source 之间必须保持职责清晰，避免再次出现“双真源”
- `artifact_url` 现在仍是 thread 维度，接口返回必须允许它是可选字段
- 若同一 workspace 被多个线程并发使用，run 前同步策略需要保证幂等且不会污染当前线程其他输出内容

---

## 14. 建议 Claude 重点审查的点

请重点审查以下设计是否合理：

- `workspace_id` 作为上传主资源标识后，是否还有遗漏的 `thread_id` 依赖链路
- 新线程首次带附件时，`ensureThread -> upload -> submit` 时序是否足够稳妥
- “OSS 为真源、线程本地 uploads 为运行时镜像”的边界是否清晰
- `alibabacloud-oss-v2` 在当前 Python 版本和项目 async 边界下是否是合适选型
- `artifact_url` 继续保留为 thread 维度可选字段，是否足够支撑现有消息/文件展示逻辑
- 是否还需要补一个专门的 workspace repository/update API 来规范 `file_path` 的写入与读取

---

## 15. 最终结论

本次改造的核心不是“把文件面板接上真实数据”这么简单，而是把整条上传链路从旧的 `thread_id` 模型迁移到真实存在的 `workspace_id` 模型。

最终形态应当是：

- 文件业务归属以 `workspace_id` 为准
- 文件持久化存储以 OSS 为准
- 线程本地 uploads 仅作为运行时镜像
- 右侧工作区文件面板展示 workspace 真实 OSS 文件
- 现有 agent 读取文件和 artifact 逻辑在本轮保持兼容
