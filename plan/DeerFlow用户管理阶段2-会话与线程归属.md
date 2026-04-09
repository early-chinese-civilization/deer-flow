# DeerFlow用户管理阶段2-会话与线程归属

## 1. 本阶段目标

- 落 `chats`
- 落 `messages`
- 建立 legacy thread 懒接管
- 建立 thread user_id 服务端归属

## 2. 前置依赖

- 阶段 1 的 `current_user` 已可用
- Gateway 已有本地用户映射与基于 `kc_* cookie + Keycloak` 的用户解析能力

## 3. 涉及表与字段

- `chats`
  - `thread_id uuid pk`
  - `user_id`
  - `workspace_id nullable`
  - `agent_id nullable`
- `messages`
  - `thread_id`
  - `role`
  - `content`
  - `seq`

## 4. 关键锁定规则

- `chats.thread_id` 直接作为产品会话主键，同时也是 LangGraph `thread_id`
- 不新增独立 `chat_id`
- 一个 chat 最多绑定一个 agent
- 不同 chat 可以绑定同一个 agent
- `workspace_id` 在阶段 3 进入稳定绑定；v1 新 chat 默认自动分配新的隐藏 workspace

## 5. user_id 归属规则

- `chats.user_id` 一律来源于阶段 1 解析出的 `current_user`
- 不允许前端传入 `user_id` 或任何 归属字段决定归属
- lazy takeover 首次接管时写入的 user_id 默认不可变
- 后续权限判断只认服务端归属记录

## 6. Legacy Thread 接管策略

- 旧 thread 采用懒接管
- 用户首次登录访问某个历史 thread 时，Gateway 补建 `chats` 归属记录
- 不做上线前全量回填
- 未被接管的匿名历史 thread 不纳入新用户隔离体系
- 被接管 thread 一旦写入 `chats`，即视为进入新用户体系
- 懒接管只适用于当前兼容入口暴露出来的 legacy thread，不定义共享 user_id 模式

## 7. messages 实施口径

- 首批开始写入新会话消息镜像
- 历史 thread 不自动回填
- v1 只镜像用户可见消息，不强行并入底层 tool 事件和 checkpoint 细粒度状态
- 若幂等、SSE 时机、tool 回调顺序复杂度超预期，可实施期临时拆成 `2A / 2B`

## 8. 允许修改范围

- `backend/app/gateway/**`
- `backend/app/**`
- `backend/tests/**`
- `plan/**`

## 9. 禁止改动范围

- 不提前进入 workspace canonical 映射细节实现
- 不提前做 agents / skills / knowledge base 的业务化迁移

## 10. 自动验证命令

```bash
make check
cd backend && uv run pytest tests/test_threads_router.py tests/test_gateway_services.py -q
```

若阶段 2 新增 chats / messages / user_id 定向测试，验收时必须把新增测试一起纳入执行清单。

## 11. 风险与注意事项

- 若 user_id 归属规则不固定，会导致 thread 归属争议和权限判断不一致
- 若未把 `chats.thread_id = 产品 chat 主键 = LangGraph thread_id` 写成硬规则，后续 `/api/chats` 与 `/api/threads` 会出现双主键漂移
- 若过早关闭 `/api/threads/**` 兼容层，会直接打挂现有前端主链路

## 12. 验收动作

- `chats.thread_id` 主键已生效
- 新体系会话消息已开始镜像写入
- `messages` 只镜像用户可见消息，未强行并入底层 tool 事件和 checkpoint 状态
- 已接管 thread 的 user_id 归属规则稳定且不可二次漂移
- `/api/threads/**` 在兼容层下仍可用
