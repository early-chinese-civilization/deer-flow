# DeerFlow Checkpointer 切换 PG 与业务 PG 对齐方案

## Summary
本方案将当前文档从“方向正确的架构草案”重写为“可评审、可实施、可验收”的实施方案文档。

本轮保留以下总方向不变：

- `checkpointer/store` 是 runtime 真相，承接 `state/history`、checkpoint lineage、resume/interrupt、完整 `channel_values`
- `chats/messages` 是产品真相，承接 `user_id`、列表、标题、用户可见消息、产品查询
- 二者通过最新 root checkpoint 投影到 PG 对齐，而不是把 checkpointer 内部结构直接业务化

本轮固定决策如下：

- compat 详情读接口在返回前必须尝试一次 targeted reconciliation
- 若读前补齐失败，v1 采用“可用性优先”：返回 runtime 数据，PG 保持待补齐，并记录 lag / failure 指标
- 正式回滚目标是“回滚到上一套可用应用版本与配置”，不把“必须能切回 SQLite”写成长期硬要求
- 当前本地开发阶段允许从零开始，不迁移旧 SQLite `backend/.deer-flow/checkpoints.db`，仅人工备份后废弃

## 当前流程严格审查

### 1. 前端正式链路现状

- 前端当前默认将 LangGraph SDK 基地址指向 `/api/langgraph-compat`
- 详情页仍依赖 LangGraph runtime 语义，而不是单纯依赖 `messages` 表重建会话详情
- 当前主链依赖：
  - `useStream`
  - `threads.search`
  - `threads.getState`
  - `fetchStateHistory`
- 这意味着本轮不能把 `messages` 直接提升为详情页唯一真相

### 2. Gateway 当前运行链路

- Gateway 在 lifespan 中初始化 `checkpointer`、`store`、`stream_bridge`、`run_manager`
- `threads.search / get_thread / getState / history` 当前仍强依赖 checkpointer/store
- 运行中的 SSE 事件会在 Gateway 内消费 `values` 事件，并把最终用户可见消息投影到 PG
- 当前消息投影已经只从最终 `values.messages` 提取用户可见消息，不再把中间 `messages-tuple` 当作产品真相

### 3. LangGraph Server 当前运行链路

- `backend/langgraph.json` 已接入 custom checkpointer factory
- 但当前没有同步配置 custom `store.path`
- 这意味着 Gateway 的 store 已经跟随统一 provider，而 LangGraph Server 的 store 行为仍存在分叉风险

### 4. 当前最核心的不一致点

- checkpointer 仍落在 SQLite，本地文件路径是 `backend/.deer-flow/checkpoints.db`
- 业务 PG 已承接 `users/chats/messages`
- 当前列表、详情、历史、恢复分别读 PG 和 runtime 语义，天然存在“双真相短时漂移”
- `config.yaml` / `config.example.yaml` 里关于“checkpointer 不影响 LangGraph Server”的旧注释与真实实现冲突
- raw `/api/langgraph` 与 compat `/api/langgraph-compat` 的边界如果不锁死，后续 `user_id`、投影、列表一致性会再次分叉

## 一致性模型与核心定义

### 1. 一致性模型与保证

本轮将一致性分成三类，实施时不得混用：

- 强一致
  - `create_thread`
  - lazy takeover
  - user_id 绑定
  - 显式 `state/title` 更新
  - 这些流程只有在 chat 行、最新 root checkpoint 锚点、首轮 PG 投影全部完成后才算成功，否则请求直接失败
- 有界最终一致
  - SSE 过程中的消息投影
  - 运行不因投影失败中断，但 PG 允许短暂滞后
- 读前修复
  - `get_thread / getState / history` 返回前必须尝试一次 targeted reconciliation
  - 如果补齐成功，返回最新 runtime + 最新 PG 锚点对应结果
  - 如果补齐失败，返回 runtime 数据，不阻断详情读取，同时记录日志和指标

“对齐”在本方案中的正式含义是：

- PG 投影允许短暂滞后
- compat 详情读接口返回前必须尝试补齐最新 root checkpoint
- `create_thread / lazy takeover / user_id 绑定` 不允许以“稍后补齐”为理由绕过强一致要求

### 2. 核心定义

- `root checkpoint`
  - 指 `checkpoint_ns == ""` 的 checkpoint
  - root namespace 是当前产品态可见状态的唯一投影源
  - 非 root namespace 视为执行内部状态，不进入产品投影
- `latest root checkpoint`
  - 指对 `thread_id + checkpoint_ns=""` 调用 `aget_tuple(...)` 且不显式指定 `checkpoint_id` 时，由 checkpointer 返回的当前最新 root checkpoint
  - 本轮不额外定义数据库侧排序规则，统一以 checkpointer 当前“最新返回值”为准
- `主分支`
  - 对产品投影而言，主分支就是当前 `aget_tuple(thread_id, checkpoint_ns="")` 返回的 latest root checkpoint 所在分支
  - fork/resume 产生的其他历史分支仍保留在 runtime 中，但不会单独投影到 PG；只有当它成为当前 latest root checkpoint 时，才会成为新的产品投影源
- `source_message_id`
  - 优先取上游消息 `id`
  - 若上游消息没有 `id`，使用 `fallback:{seq}:{role}:{content_hash}` 作为回退键
  - 回退键只保证同一线程、同一最终消息集合中的幂等，不承诺跨内容变化保持同一逻辑消息身份

### 3. 产品投影边界

- `messages` 只保存最终用户可见消息投影
- `messages` 不保存 checkpoint 全历史
- `messages` 不承接 resume/interrupt/runtime lineage 真相
- `history` 仍是 runtime 视图，不改成从 `messages` 逆向重建
- 详情页继续读 runtime 语义，列表与归属走 PG-first

## 目标方案与内部契约

### 1. 持久化后端统一

- backend 补齐 `langgraph-checkpoint-postgres`、`psycopg[binary]`、`psycopg-pool` 依赖
- `config.yaml` / `config.example.yaml` 的 `checkpointer` 段统一改为：
  - `type: postgres`
- `connection_string: $DATABASE_URL`
- v1 默认统一复用 `DATABASE_URL` 指向同一个物理 PG
- `backend/langgraph.json` 必须新增 `store.path`，使 LangGraph Server 与 Gateway 一起走统一 store provider

### 2. 真相分层与接口边界

- `thread_id` 继续作为唯一跨层主键，贯通：
  - checkpointer
  - store
  - `chats.thread_id`
  - `messages.thread_id`
- `checkpointer/store` 继续承接：
  - 最新 state
  - checkpoint 历史
  - interrupt / resume
  - 完整 `values.messages`
  - tool 过程与 channel values
- `chats/messages` 继续承接：
  - `user_id` / title / status / 列表排序
  - 用户可见消息投影
  - 产品查询与权限控制
- raw `/api/langgraph`
  - 仅调试入口
  - 不承诺 user_id / PG 产品投影 / 产品一致性语义
- compat `/api/langgraph-compat`
  - 正式产品入口
  - 负责 user_id 语义、PG 投影和读前修复

### 3. PG 投影与幂等规则

- `chats` 新增以下字段：
  - `latest_checkpoint_id`
  - `latest_checkpoint_at`
  - `projection_synced_at`
- 新增统一 projection service，输入为“当前 latest root checkpoint”，输出为：
  - `chats.title`
  - `chats.status`
  - `chats.latest_checkpoint_*`
  - `messages` 的最终用户可见消息集合
- 实施时必须遵守以下规则：
  - projection service 在真正落库前，必须重新读取一次当前 latest root checkpoint，不能直接使用触发事件携带的旧 checkpoint
  - `chats.latest_checkpoint_id`、`latest_checkpoint_at`、`projection_synced_at` 与 `messages` 必须在同一数据库事务内提交
  - `messages` 继续按 `(thread_id, source_message_id)` 做幂等 upsert
  - 当前投影结果之外的旧消息行必须在同一事务内删除
  - 旧 checkpoint 投影不能回退 `latest_checkpoint_id`
- 本轮不新增 `messages.checkpoint_id`
  - 如果后续要支持更细粒度审计或重建，再单开增强方案

### 4. 路由与读取契约

- `threads.search`
  - 正式语义改为 PG-first
  - checkpointer 扫描只允许作为 legacy 补索引或迁移辅助，不再作为产品正式结果源
- `get_thread / getState / history`
  - 返回前固定执行一次 targeted reconciliation
  - targeted reconciliation 只以当前 latest root checkpoint 为锚点，不对 history 中每个历史 checkpoint 逐条重投影
  - 若补齐成功，返回最新结果
  - 若补齐失败，返回 runtime 数据，并记录 `projection_failure`、`targeted_reconciliation_failure`、`projection_lag`
- `create_thread`
  - 固定顺序：
    1. 创建 `chat`
    2. 创建空 root checkpoint
    3. 立即投影一次并写回 `latest_checkpoint_id`
    4. 返回线程已创建
- lazy takeover
  - 仅对“checkpointer 里有 thread、PG 里无 chat”的线程生效
  - takeover 后必须立即完成一次 checkpoint -> PG 投影，否则请求失败

## 实施顺序、Runbook 与回滚

### Phase A. PG checkpointer/store 基础设施切换

- 输入前提
  - 当前仓库已确认 Gateway 与 LangGraph Server 都依赖 custom checkpointer
  - 允许引入 PG 依赖包
- 实施内容
  - 补齐 PG checkpointer/store 依赖
- 统一复用 `DATABASE_URL`
  - 修改 `config.yaml` / `config.example.yaml`
  - 为 `backend/langgraph.json` 新增 `store.path`
- 完成标准
  - Gateway 与 LangGraph Server 都能在 PG 模式启动
  - 启动日志明确显示使用 PG checkpointer 与 PG store
- 失败信号
  - 任一服务无法在 PG 模式启动
  - Gateway 与 LangGraph Server 对 store backend 的行为不一致
- 回滚条件
  - 进入 PG 模式后主服务无法稳定启动
- 回滚目标
  - 回滚到上一套可用应用版本与上一套配置

### Phase B. projection 基座与 chats 新字段

- 输入前提
  - Phase A 完成
- 实施内容
  - 为 `chats` 增加 `latest_checkpoint_id`、`latest_checkpoint_at`、`projection_synced_at`
  - 引入统一 projection service
  - 将 `messages` 写入统一收口到 projection service
- 完成标准
  - 新建 thread 后 chat 行存在且 `latest_checkpoint_id` 非空
  - 单轮对话后 `messages` 与 latest root checkpoint 的最终可见消息集合一致
- 失败信号
  - 同一 thread 出现 chat 锚点与 message 集合不一致
  - 同一事务中只更新了 chat 或只更新了 messages
- 回滚条件
  - projection 基座导致新 thread 或新对话无法形成稳定锚点
- 回滚目标
  - 回滚到 Phase A 完成状态

### Phase C. Gateway PG-first + targeted reconciliation

- 输入前提
  - Phase B 完成
- 实施内容
  - `threads.search` 正式切到 PG-first
  - `get_thread / getState / history` 增加读前 targeted reconciliation
  - `create_thread / lazy takeover` 收紧为强一致链路
- 完成标准
  - compat 主链不再依赖“全量扫描 checkpointer”作为正式列表源
  - 详情读接口在 PG 滞后时能尝试自动补齐
- 失败信号
  - compat 主链详情不可用
  - user_id 校验、takeover、投影行为再次分叉
- 回滚条件
  - PG-first 或读前修复导致正式主链可用性下降
- 回滚目标
  - 回滚到 Phase B 完成状态

### Phase D. 运维脚本、诊断命令、部署文档

- 输入前提
  - Phase C 完成
- 实施内容
  - 提供 thread 级和批量级 projection rebuild 脚本
  - 提供 lag / failure 诊断命令
  - 更新部署文档，不再依赖本地 SQLite
- 完成标准
  - 可对指定 thread 手动重建 PG 投影
  - 可识别 PG 投影滞后线程
  - 部署文档明确 PG 是唯一正式运行后端
- 失败信号
  - 运维无法识别或修复投影滞后
- 回滚条件
  - 运维阶段能力无法支撑正式维护
- 回滚目标
  - 回滚到 Phase C 完成状态

### 数据迁移 Runbook

- 当前本地开发阶段
  - 允许从零开始
  - 不迁移旧 SQLite
  - 仅人工备份后废弃 `backend/.deer-flow/checkpoints.db`
- 若未来共享环境已经承载真实用户历史
  - 本方案不默认允许直接废弃旧 SQLite 数据
  - 只有在 Product 与 SRE/DBA 明确确认“历史 runtime 状态允许丢弃或重新开始”时，才能直接切 PG
  - 若不能接受历史丢失，需要单开 SQLite -> PG 迁移项目，本方案不在实施中临时兜底

## 验收标准、可观测性与待确认项

### 1. 验收标准

- 新建 thread
  - 动作：调用 `create_thread`
  - 期望结果：`chats` 有记录，且 `latest_checkpoint_id` 已写入
  - 可观测证据：PG 查询结果与 `getState` 返回的 latest root checkpoint 一致
- 单轮对话
  - 动作：发送一轮消息并完成运行
  - 期望结果：`messages` 与 latest root checkpoint 的最终可见消息集合一致
  - 可观测证据：PG 消息集合与 runtime `values.messages` 对比一致
- 服务重启
  - 动作：重启 Gateway 与 LangGraph Server 后读取 `search / getState / history`
  - 期望结果：列表、详情、历史都能恢复
  - 可观测证据：服务启动成功，PG 锚点与 runtime 返回不冲突
- 投影滞后
  - 动作：人工制造 `latest_checkpoint_id` 落后
  - 期望结果：compat 详情读会尝试补齐
  - 可观测证据：`projection_synced_at` 更新，或 failure/lag 指标增加
- 补齐失败
  - 动作：故意让 projection service 在读前修复中失败
  - 期望结果：返回 runtime 数据，不阻断详情读取
  - 可观测证据：`projection_failure_total`、`targeted_reconciliation_failure_total`、`projection_lag_seconds` 增长
- 并发
  - 动作：同一 thread 连续多轮并发运行或重复触发投影
  - 期望结果：旧 checkpoint 不会覆盖新 checkpoint
  - 可观测证据：`latest_checkpoint_id` 只前进不回退，`messages` 不出现旧结果回写
- 回滚
  - 动作：回滚到上一套应用版本与配置
  - 期望结果：主服务恢复可启动且正式主链恢复可用
  - 可观测证据：启动日志、接口探活、主链 smoke test 均恢复正常

### 2. 可观测性

本轮至少提供以下指标或等价日志键：

- `projection_attempt_total`
- `projection_success_total`
- `projection_failure_total`
- `targeted_reconciliation_total`
- `targeted_reconciliation_failure_total`
- `projection_lag_seconds`

指标定义要求：

- `projection_lag_seconds`
  - 定义为当前时间减去 `projection_synced_at`
  - 仅对 `chats.latest_checkpoint_id` 落后于 latest root checkpoint 的线程计算

### 3. 已决策项

- 本地/当前阶段允许从零开始，不迁移旧 SQLite，仅人工备份后废弃
- raw `/api/langgraph` 仅调试，不纳入产品一致性验收
- compat `/api/langgraph-compat` 是正式产品入口
- 详情页继续读 runtime，列表与归属走 PG-first
- 读前补齐失败时采用可用性优先，不阻断详情读取
- 本轮不新增 `messages.checkpoint_id`

### 4. 待确认项与 Owner

- 同物理 PG、同 schema、不同表组的容量与连接池是否被接受
  - Owner：SRE/DBA
- root checkpoint 是否覆盖全部用户可见消息
  - Owner：Backend
- `source_message_id` 在当前 LangGraph 版本下是否足够稳定作为主幂等键
  - Owner：Backend
- 产品是否接受“SSE 投影失败时，列表和消息可短时滞后，但下次 compat 读取前会尝试补齐”
  - Owner：Product
- 未来是否需要给 `messages` 增加 `checkpoint_id` 作为审计增强
  - Owner：Backend / Product

以上待确认项在实施前若未关闭，视为阻塞条件，不留给实施者临场判断。
