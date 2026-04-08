# DeerFlow用户管理阶段3-工作区与Chat闭环

## 1. 本阶段目标

- 落 `workspaces / workspace_files`
- 沿用 `/api/threads/**` 主链承载 chat 创建、列表与详情
- 建立 chat 与 workspace 的稳定绑定
- 实现 canonical workspace 到 thread workspace 的映射
- 保持 Workspace 在 v1 为隐藏式内部资源

## 2. 前置依赖

- 阶段 2 的 `chats.thread_id` 已建立
- owner 校验已具备基础能力

## 3. 最终产品目标与当前阶段启用能力

### 3.1 最终产品目标

- Workspace 是用户级正式资源
- Workspace 未来可见、可复用、可独立管理
- 新建 chat 未来可选择已有 workspace；若未选择，再自动创建默认 workspace

### 3.2 当前阶段启用能力

- Phase 3 先完成后端模型、`threads` 主链接口语义和映射骨架
- v1 不做 Workspace 独立管理菜单，不做用户可见列表
- v1 不做“新建 chat 时选择已有 workspace”入口
- v1 每次新建 chat 时由后端自动创建新的隐藏 workspace 并绑定

## 4. canonical workspace 与 thread workspace 主从规则

- canonical workspace 是唯一业务主真相
- thread workspace 只是运行时投影目录，不承担长期业务主真相职责
- run 前固定执行 `canonical workspace -> thread workspace` 同步
- run 后固定执行 `thread workspace -> canonical workspace` 回写
- v1 冲突策略固定为“后写覆盖”，不做自动合并、不做双向冲突决策、不做用户提示式冲突管理

## 5. chat 绑定规则

- 新建 chat 时不允许用户选择已有 workspace
- 每次新建 chat 时自动创建默认 workspace
- 用户重新打开该 chat 时，继续使用已绑定的 workspace
- 阶段 2 中遗留的 `workspace_id = null` chat，在首次打开或首次写入时补默认 workspace

## 6. 涉及 API

- `POST /api/threads`
- `POST /api/threads/search`
- `GET /api/threads/{thread_id}`
- Workspace 在 v1 不作为用户主流程接口面暴露

## 7. 允许修改范围

- `backend/app/gateway/**`
- `backend/app/**`
- `frontend/src/**`
- `backend/tests/**`
- `plan/**`

## 8. 边界与不做事项

- 本阶段不处理 skills / KB 运行时投影
- 本阶段不引入复杂的 workspace 冲突合并策略
- 本阶段不做 Workspace 可见菜单与跨 chat 复用入口

## 9. 风险与注意事项

- 若回写策略不明确，会导致多个会话共享 workspace 时的数据覆盖争议
- 若把隐藏式 Workspace v1 误写成长期产品定义，会导致后续开放 Workspace 复用时再次推翻接口语义
- 若在本阶段就引入复杂冲突合并，会显著拖慢落地速度

## 10. 验收动作

- chat 可稳定创建并绑定 workspace
- 默认 workspace 自动创建逻辑可用
- canonical workspace 与 thread workspace 的同步和回写闭环可跑通
- Workspace 在 v1 对用户保持隐藏
- 数据模型和接口语义已经为未来可见可复用 Workspace 预留扩展空间
