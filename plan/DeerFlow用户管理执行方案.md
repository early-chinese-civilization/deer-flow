# DeerFlow用户管理执行方案

## 1. 文档定位

本文档是执行总方案，回答的是“按什么顺序落地”。

与总方案主文档的关系如下：

- `用户管理与资源模型接入方案.md`
  - 定义系统设计、长期约束和最终目标模型
- `DeerFlow用户管理执行方案.md`
  - 定义阶段顺序、依赖关系、兼容策略和回滚点
- `DeerFlow用户管理阶段*.md`
  - 定义某一阶段的具体实施项与验收动作

## 2. 执行总原则

- 长期保护面不等于一次性启用顺序
- Gateway 是唯一认证真相
- Keycloak 是唯一登录态与失效真相
- `current_user` 的正式解析链路是：`kc_access_token -> /userinfo`，失败后 `kc_refresh_token -> refresh -> /userinfo`
- DeerFlow v1 不维护 `auth_sessions` 作为正式认证模型
- LangGraph `checkpointer / store` 本轮不强迁入 PG
- 所有 user_id 归属只能由服务端 `current_user` 写入
- chat 绑定 agent 后按当前资源实时解析，缺失引用按忽略处理，不阻断模型执行
- Phase 1-3 不开放 Workspace 前端复用入口，但模型必须预留最终可见可复用能力
- 优先保留 `/api/threads/**` 与 `/api/runs/**` 兼容层
- 前期先做 user_id 过滤与服务端归属，后期再逐步清理 legacy 全局实现
- 如阶段验证失败，必须立即中断，不允许继续推进到下一阶段

## 3. 总体执行顺序

### 阶段 1

`Auth + 根目录 .env + PG(users) + current_user`

### 阶段 2

`chats + messages + legacy thread 懒接管`

### 阶段 3

`隐藏式 workspaces + threads 主链绑定 + workspace 映射`

### 阶段 4

`agents + 实时资源关联`

### 阶段 5

`skills 5A/5B`

### 阶段 6

`knowledge base 6A/6B/6C`

### 阶段 7

`user_memories`

### 最后单列

`legacy 清理`

## 4. 各阶段依赖关系

- 阶段 2 依赖阶段 1 的 `current_user`
- 阶段 3 依赖阶段 2 的 `chats.thread_id`
- 阶段 4 依赖阶段 3 的 chat / workspace 闭环
- 阶段 5 依赖阶段 4 的 agent 业务化
- 阶段 6 依赖阶段 5 的 user skills / OSS 组织方式
- 阶段 7 放在最后，避免过早改动全局 memory 主链路

## 5. 阶段 1 详细执行口径

### 5.1 固定顺序

1. 根目录 `.env` 单一来源加载进入 Gateway 启动链路
2. 建立 Keycloak / OIDC client 封装
3. 新增 `/api/auth/login`、`/api/auth/callback`、`/api/auth/me`、`/api/auth/logout`、推荐实现 `/api/auth/refresh`
4. 建立 `users` 的 repository 与 migration 基座
5. 建立 `current_user` 依赖与 `request.state.current_user`
6. 先保护 `/workspace/**`，`threads / runs` 在后续阶段逐步接管

### 5.2 明确禁止项

- 不得提前进入 `chats / messages / workspaces / agents / skills / knowledge_bases / user_memories`
- 不得在阶段 1 就改造 LangGraph `checkpointer / store`
- 不得把 frontend `better-auth` 扩成正式认证中心
- 不得继续引入本地 `auth_sessions` 或 DeerFlow 自有服务端 session 方案作为 v1 正式目标

### 5.3 参考源码矩阵

- 登录 / 回调 / 登出跳转问题：优先查 `ecc_agent/auth_routes.py`
- token 交换 / refresh / userinfo / logout URL 拼装：优先查 `ecc_agent/keycloak.py`
- `current_user` 依赖与受保护路由注入：优先查 `ecc_agent/auth.py` 和 `ecc_agent/main.py`
- 用户首登落库与字段映射：优先查 `ecc_agent/user_repository.py`

### 5.4 完成条件

- Gateway 已统一读取根目录 `.env`
- `/api/auth/login -> callback -> me -> logout` 闭环跑通
- `/api/auth/refresh` 在后端可用
- 登录回调后浏览器已收到 `HttpOnly kc_* cookie`
- 前端登录态初始化以 `/api/auth/me` 为准
- 前端不以 Keycloak token 作为 JavaScript 主状态持久化
- `current_user` 已按 `kc_access_token -> /userinfo`，失败后 `kc_refresh_token -> refresh -> /userinfo` 稳定解析

## 6. 阶段 2 详细执行口径

### 6.1 目标

- 建立 `chats.thread_id` 作为产品会话主键
- 建立 `messages` 新会话镜像
- 建立 legacy thread 懒接管

### 6.2 固定规则

- `chats.user_id` 一律来源于 `current_user`
- 不允许前端传入 归属字段决定归属
- lazy takeover 首次接管后 user_id 默认不可变
- 被接管 thread 一旦进入 `chats`，即视为进入新用户体系

### 6.3 兼容策略

- 首批只记录新登录后创建或访问的新体系会话
- 历史消息不做全量回填
- `/api/threads/**` 继续保留
- user_id 校验按“已接管 thread 优先”逐步打开

### 6.4 预备分支

若 `messages` 镜像写入的幂等、SSE 时机或 tool 回调顺序复杂度超预期，则允许实施期临时拆成：

- `2A chats / user_id / lazy takeover`
- `2B messages 镜像`

管理层主编号仍保留为阶段 2。

## 7. 阶段 3 详细执行口径

- 模型和接口语义按“Workspace 最终可见、可复用、可独立管理”的终态设计
- Phase 1-3 仍不开放 Workspace 独立菜单、用户可见列表和“新建 chat 选择已有 workspace”入口
- 引入 `workspaces / workspace_files`
- 每次新建 chat 时由后端自动创建新的隐藏 workspace 并稳定绑定
- 旧 chat 在首次打开或首次写入时补默认 workspace
- 不新增独立 `/api/chats` 公共接口，继续沿用 `/api/threads/**` 兼容主链
- canonical workspace 是唯一业务主真相，thread workspace 只是运行时投影
- Gateway 负责 run 前 `canonical -> thread` 同步、run 后 `thread -> canonical` 回写
- v1 冲突策略固定为“后写覆盖”

## 8. 阶段 4 详细执行口径

- `agents` 从全局文件转为业务资源
- system default agent 继续兼容
- chat 仅绑定当前 `agent_id`
- 运行时按当前 agent 配置、当前 skill 引用、当前 Knowledge Base 引用实时解析
- 缺失 skill / Knowledge Base 引用时记录 warning 后继续执行模型
- 支持同一个 agent 被多个 chat 复用

## 9. 阶段 5 详细执行口径

### 5A 业务化

- `skills` 入库
- system skills 与 user skills 分层

### 5B 运行时

- user skills 同步到 OSS
- 运行时按 agent 当前绑定实时组装 skills 目录
- skill 路径缺失或同步未完成时跳过对应 skill，不阻断模型执行

## 10. 阶段 6 详细执行口径

### 6A 资源层

- `knowledge_bases / knowledge_base_files` 落库
- 原始文件上传到 OSS

### 6B 索引层

- 文档切分
- `knowledge_chunks` 写入 `pgvector`

### 6C 运行时接入

- chat / agent 能读取当前绑定的 Knowledge Base
- Gateway 在运行前按当前引用组装检索上下文
- Knowledge Base 引用缺失、文件缺失或路径不可达时跳过对应增强，不阻断模型执行

## 11. 阶段 7 详细执行口径

- `user_memories` 替代 legacy 全局 memory
- 老 memory 只读接管，不再继续扩展
- 完成后再清理全局 memory 路径和历史兼容逻辑

## 12. 全局风险与回滚点

### 12.1 认证风险

- 代理头推导错误会导致回调地址异常
- refresh 恢复失败会导致用户重新跳回第三方登录
- 解决顺序优先参考 `ecc_agent` 已验证行为，再做 DeerFlow 安全增强

### 12.2 user_id 归属风险

- 若阶段 2 未固定 user_id 来源，会导致 thread 归属争议和权限判断漂移

### 12.3 workspace 风险

- canonical workspace 与 thread workspace 的回写冲突，v1 先按后写覆盖处理

### 12.4 回滚原则

- 每阶段都必须保留兼容层
- 优先保证 `/api/threads/**` 与 `/api/runs/**` 不被一次性打挂
- 若新业务接口异常，允许回退到兼容层读取链路
