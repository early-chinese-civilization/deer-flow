# DeerFlow用户管理阶段2.5-会话主链稳定化与运行时PG对齐

## 1. 本阶段定位

- 本阶段位于阶段 2 与阶段 3 之间
- 本阶段不是新增业务能力阶段，而是阶段 2 的稳定化收尾阶段
- 本阶段负责把 chat / thread / owner / messages 这些已落地的产品语义，与 runtime 真相正式收口
- 阶段 3 默认暂停，直到阶段 2.5 完成

## 2. 本阶段目标

- 将 LangGraph `checkpointer / store` 正式切换到 PG
- 收口 runtime 真相与业务 PG 的边界
- 将 compat 主链稳定为正式产品入口
- 让 `chats.thread_id` 不只是产品主键，也成为稳定的跨层锚点
- 让 `messages` 从“已可用镜像”提升为“与 latest root checkpoint 有明确对应关系的产品投影”

## 3. 前置依赖

- 阶段 1 的 `current_user` 已稳定可用
- 阶段 2 的 `chats / messages / owner / lazy takeover` 已基本完成
- `/api/threads/**` 兼容层当前仍可用
- 管理口径上已确认：阶段 2 进入封板收尾，不再继续扩业务范围

## 4. 关联技术方案

- 本阶段的详细技术设计文档是：
  - `plan/DeerFlow Checkpointer切换PG与业务PG对齐方案.md`
- 本文档只定义执行导向的阶段边界、顺序、完成标准与回滚口径
- 如本文档与详细技术方案出现冲突，以“阶段边界与执行顺序”按本文档为准，以“checkpointer / projection / reconciliation 技术细节”按详细技术方案为准

## 5. 固定范围

- `checkpointer` 切换到 PG
- `store` 与 `checkpointer` 一起切换到 PG
- 为 `chats` 引入：
  - `latest_checkpoint_id`
  - `latest_checkpoint_at`
  - `projection_synced_at`
- 引入统一 projection service
- 将 `threads.search` 改为 PG-first
- 为 `get_thread / getState / history` 增加 targeted reconciliation
- 将 `create_thread / lazy takeover` 收紧为强一致链路
- 补齐 rebuild / lag / failure 运维能力

## 6. 明确不做事项

- 不进入 workspace canonical 映射
- 不引入 `/api/chats`
- 不提前做阶段 3 的 workspace 绑定闭环
- 不做 agents / skills / knowledge base / user memories
- 不把 `messages` 提升为 runtime 真相
- 不把 raw `/api/langgraph` 提升为正式产品链路

## 7. 本阶段固定规则

- runtime 真相继续在 `checkpointer / store`
- 产品真相继续在 `chats / messages`
- compat 主链是正式产品入口，raw `/api/langgraph` 仅调试
- 读前补齐失败时采用“可用性优先”：
  - 返回 runtime 数据
  - PG 保持待补齐
  - 必须记录 lag / failure 指标
- 回滚口径固定为：
  - 回滚到上一套可用应用版本与配置
  - 不承诺 SQLite 是长期统一 fallback

## 8. 子阶段顺序

### 8.1 阶段 2.5A：PG checkpointer/store 基础设施切换

- 输入前提
  - 当前仓库已确认 Gateway 与 LangGraph Server 都依赖 custom checkpointer
- 实施内容
  - 补齐 PG 依赖
  - 新增 `DEER_FLOW_CHECKPOINTER_DATABASE_URL`
  - 修改 `config.yaml / config.example.yaml`
  - 为 `backend/langgraph.json` 新增 `store.path`
- 完成标准
  - Gateway 与 LangGraph Server 都能在 PG 模式启动
  - 启动日志明确显示使用 PG checkpointer 与 PG store
- smoke test
  - 服务冷启动可通过
  - 基础 thread 创建与读取不报持久化错误
- 回滚条件
  - 任一服务无法在 PG 模式稳定启动
  - Gateway 与 LangGraph Server 对 store backend 的行为不一致
- 回滚目标
  - 回滚到阶段 2 完成时的上一套可用版本与配置

### 8.2 阶段 2.5B：投影基座与 chats 锚点字段

- 输入前提
  - 阶段 2.5A 完成
- 实施内容
  - 为 `chats` 增加 `latest_checkpoint_*`
  - 引入统一 projection service
  - 将 `messages` 写入统一收口到 projection service
- 完成标准
  - 新建 thread 后 `chats.latest_checkpoint_id` 非空
  - 单轮对话后 `messages` 与 latest root checkpoint 的最终可见消息集合一致
- smoke test
  - 新线程可完成首轮对话并写入 PG 锚点
  - 同一线程重复投影不会造成旧消息残留
- 回滚条件
  - chat 锚点与 message 集合无法形成稳定对应关系
  - 同一事务中只更新 chat 或只更新 messages
- 回滚目标
  - 回滚到阶段 2.5A 完成状态

### 8.3 阶段 2.5C：PG-first 读取链路与 targeted reconciliation

- 输入前提
  - 阶段 2.5B 完成
- 实施内容
  - `threads.search` 正式切到 PG-first
  - `get_thread / getState / history` 增加读前 targeted reconciliation
  - `create_thread / lazy takeover` 收紧为强一致链路
- 完成标准
  - compat 主链不再依赖全量扫描 checkpointer 作为正式列表源
  - PG 滞后时详情读接口可尝试自动补齐
- smoke test
  - 人工制造 `latest_checkpoint_id` 落后后，详情读会触发补齐尝试
  - 补齐失败时详情仍可读，并出现可观测 failure / lag
- 回滚条件
  - compat 主链详情不可用
  - owner / takeover / 投影行为再次分叉
- 回滚目标
  - 回滚到阶段 2.5B 完成状态

### 8.4 阶段 2.5D：运维能力与部署收口

- 输入前提
  - 阶段 2.5C 完成
- 实施内容
  - 提供 thread 级和批量级 projection rebuild 脚本
  - 提供 lag / failure 诊断命令
  - 更新部署文档，不再依赖本地 SQLite
- 完成标准
  - 可手动重建指定 thread 的 PG 投影
  - 可识别 PG 投影滞后线程
  - 部署文档明确 PG 是唯一正式运行后端
- smoke test
  - 指定 thread 的 rebuild 可成功执行
  - lag / failure 诊断命令能输出可用结果
- 回滚条件
  - 运维无法识别或修复投影滞后
- 回滚目标
  - 回滚到阶段 2.5C 完成状态

## 9. 允许修改范围

- `backend/app/gateway/**`
- `backend/app/**`
- `backend/langgraph.json`
- `config.yaml`
- `config.example.yaml`
- `backend/tests/**`
- `plan/**`

## 10. 禁止改动范围

- 不提前进入 `frontend` 的 workspace 菜单与 `/api/chats` 主流程
- 不提前做 canonical workspace 与 thread workspace 的闭环实现
- 不提前做 agents / skills / knowledge base / user memories 的业务化迁移
- 不把阶段 2.5 混成“顺手做阶段 3”的过渡大杂烩

## 11. 自动验证命令

```bash
make check
cd backend && uv run pytest tests/test_threads_router.py tests/test_gateway_services.py -q
```

若阶段 2.5 新增 checkpointer / projection / reconciliation 定向测试，验收时必须把新增测试一起纳入执行清单。

## 12. 风险与注意事项

- 若 `checkpointer / store` 不一起切 PG，会导致 Gateway 与 LangGraph Server 行为继续分叉
- 若不把阶段 2.5 明确卡在阶段 2 与阶段 3 之间，后续 workspace 闭环会建立在不稳定的 runtime/PG 边界之上
- 若 `threads.search` 仍把 checkpointer 全量扫描当作正式结果源，列表语义无法稳定收口
- 若 targeted reconciliation 失败策略不固定，会在一致性与可用性之间反复摇摆

## 13. 验收动作

- 阶段 2 已封板，不再往阶段 2 增加新能力
- Gateway 与 LangGraph Server 已统一跑在 PG checkpointer/store 上
- `threads.search` 已正式切换为 PG-first
- `get_thread / getState / history` 已具备 targeted reconciliation
- `create_thread / lazy takeover` 已具备强一致约束
- rebuild / lag / failure 运维能力已可用
- compat 主链可稳定工作
- 阶段 3 的启动条件已升级为“阶段 2.5 完成后再启动”
