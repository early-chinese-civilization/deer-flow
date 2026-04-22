# Gateway Auth Runtime Review Handoff

## Goal

这份 handoff 是给下一位继续做 review 的 agent，用来快速理解本轮在 `deer-flow` 里围绕“整个鉴权流程体系”已经做了什么、为什么这么做、哪些问题我故意没动，以及哪些代码路径已经探索过，不需要再从零开始读。

本轮工作的重点不是泛化清理整个仓库，而是收口这几个紧密相关的 auth/runtime 边界问题：

- Gateway run 启动时，哪些字段才算真正的 server-trusted runtime context
- `ecc_auth` 共享鉴权接入后，DeerFlow 自己的 Gateway 层有没有把共享契约重新削弱
- run 记录 / API 返回的数据里，是否还会回显伪造的 thread/user/auth 绑定
- 当前脏改动里有没有把 bootstrap / agent 选择能力错误地暴露给 HTTP 调用方

---

## 本轮结论摘要

### 已修复

#### 1. 收紧 Gateway 受信 runtime context 边界

我修改了：

- `backend/app/gateway/services/runtime.py`

核心变化：

- Gateway 现在只把 `thread_id` 和用户身份字段注入“受信 runtime context”
- 不再把 `agent_name` 提升成 trusted runtime context
- 请求侧传入的 runtime-only configurable 被过滤掉，当前明确挡住：
  - `is_bootstrap`
  - `__pregel_runtime`

原因：

- 之前当前脏改动的方向是对的：想把 runtime context 里的 thread/user 绑定变成 server-owned
- 但实现上把 `agent_name` 也一起视为 trusted 了，而它本质上仍然来自请求侧的 assistant/custom-agent 选择
- 更糟的是，`is_bootstrap` 没有被 Gateway 层阻断，和 `agent_name` 组合后会形成 bootstrap 写能力的边界风险

现在的边界是：

- `thread_id` / `user_id` / `external_auth_id` / `username` / `display_name` / `email`：由服务端覆盖
- `agent_name`：仍然允许合法选择，但不再通过 trusted runtime context 通道传播为 server-owned 身份绑定
- runtime-only 开关：不会从 Gateway 请求直接穿透

#### 2. run record 不再暴露未净化的伪造 config

我修改了：

- `backend/app/gateway/services/runtime.py`

新增行为：

- `start_run()` 不再把原始 `body.config` 直接塞进 run record 的 `kwargs["config"]`
- 改为保存“净化后的 public config”
- public config 会剥离 server-owned 的 thread/user/auth 绑定

原因：

- 之前即使实际执行时已经覆盖了伪造的 runtime context，run detail/list API 里仍然会回显调用方提交的假 `thread_id` / `user_id` / `external_auth_id`
- 这会污染审计面，误导后续消费 run record 的代码或 reviewer

#### 3. Keycloak 必填配置改成 fail-fast

我修改了：

- `backend/app/gateway/auth/routes.py`
- `backend/tests/test_auth_sdk_integration.py`

核心变化：

- `KEYCLOAK_URL`
- `KEYCLOAK_REALM`
- `KEYCLOAK_CLIENT_ID`

现在缺失时会在建 auth router 时直接失败，而不是被静默降成空字符串，等到 `/api/auth/login|callback|logout` 运行时再炸。

原因：

- `ecc_auth` 的共享契约本来就是 env-required
- DeerFlow 之前的 wrapper 把这个契约削弱了
- 这种错误应该是启动期配置错误，不应该变成运行期 auth 失败

#### 4. 修掉一个 assistant/context 兼容性缺口

我修改了：

- `backend/app/gateway/services/runtime.py`
- `backend/tests/test_gateway_services.py`

补的点：

- 当请求走 `config.context` 路径时，`assistant_id` 仍然会正常映射成 `configurable.agent_name`

原因：

- 我在收紧 trusted context 时发现一个旧兼容性缺口：
  - `build_run_config()` 以前只有在已有 `configurable` 时才会注入 `agent_name`
  - 如果请求使用 LangGraph 兼容的 `config.context` 形态，自定义 agent 选择会被吃掉
- 这个不是新引入的 auth 漏洞，但 reviewer 很容易把它误判成“我改坏了 custom agent”
- 所以顺手一起修了

---

## 本轮实际改动文件

### 代码

- `backend/app/gateway/services/runtime.py`
- `backend/app/gateway/auth/routes.py`
- `backend/app/gateway/deps.py`

### 测试

- `backend/tests/test_auth_sdk_integration.py`
- `backend/tests/test_gateway_services.py`
- `backend/tests/test_run_manager.py`

### 文档

- `README.md`
- `backend/README.md`
- `backend/CLAUDE.md`

### 本轮新增 handoff

- `docs-qy/2026-04-22-gateway-auth-runtime-review-handoff.md`

---

## 我明确没做的事情

### 1. 我没有处理 `/api/user-profile` 未鉴权问题

这是 review 过程中明确发现的 auth 面风险之一：

- 文件：`backend/app/gateway/routers/agents.py`
- 入口：
  - `GET /api/user-profile`
  - `PUT /api/user-profile`

问题性质：

- 这两个接口没有 `Depends(get_current_user)`
- 它们操作的是全局 `USER.md`
- `USER.md` 会被注入到 custom agents 的 prompt/运行时人格材料里

为什么这轮没动：

- 这不在当前 run/runtime 脏改动主路径上
- 改它会牵动 agents router 测试夹具和接口预期
- 当前用户让我先把 review 主线和这批修改“handoff 给下一个 reviewer”，不是继续扩 scope 大改

所以：

- 这项仍然应被视为 open finding
- 下一位 reviewer 不要把它当成“已修”

### 2. 我没有改已有的 custom agent ownership 模型

我没有做这些事情：

- 没有让 `assistant_id` 在 run 启动前去查 DB ownership
- 没有把 `agent_name` 改造成必须通过 `AgentRepository` 显式授权
- 没有改 frontend 的 custom-agent 路由发送形态

原因：

- 当前代码里 custom agent 运行路径本来就不是纯 DB-owned contract
- 运行时最终还是走 on-disk agent config / `load_agent_config(agent_name)`
- 如果这轮强行把它改成严格 DB ownership，需要同步梳理 frontend、channels、历史 agent 目录、bootstrap 流程
- 这会把任务从“修 auth/runtime trust boundary”扩大成“重构整个 custom agent authority model”

这件事值得 review，但我没有在本轮推进。

### 3. 我没有清理现有 worktree 里的其他脏改动

当前仓库本身还有未提交改动，不全是我这轮新增的。我没有去 reset/revert，也没有把 unrelated diff 洗干净。

特别是这些文件在本轮开始前就已经是脏的，且和本轮主题强相关，所以我只在必要处继续叠改，没有试图“还原到干净状态”：

- `backend/app/gateway/routers/runs.py`
- `backend/app/gateway/routers/thread_runs.py`
- `backend/packages/harness/deerflow/runtime/runs/worker.py`
- `backend/tests/test_gateway_services.py`
- `backend/tests/test_run_manager.py`

另外还存在与本轮无关的脏文件：

- `backend/uv.lock`
- `docs-qy/2026-04-20-session-state-gap-and-official-capability-boundary.md`

下一位 reviewer 需要按“当前 worktree 就是脏的”这个前提工作，不要默认所有 diff 都来自我这轮。

---

## 我探索过的路径

下一位 reviewer 可以直接复用这些探索结论。

### A. deer-flow 里的主路径

我已经读过这些核心代码：

- `backend/app/gateway/services/runtime.py`
- `backend/app/gateway/routers/runs.py`
- `backend/app/gateway/routers/thread_runs.py`
- `backend/packages/harness/deerflow/runtime/runs/worker.py`
- `backend/app/gateway/services/ownership.py`
- `backend/app/gateway/deps.py`
- `backend/app/gateway/app.py`
- `backend/app/gateway/auth/routes.py`
- `backend/app/gateway/auth/service.py`
- `backend/app/gateway/routers/agents.py`

### B. deer-flow 里的相关测试

我读过/用过这些测试：

- `backend/tests/test_auth_sdk_integration.py`
- `backend/tests/test_gateway_services.py`
- `backend/tests/test_run_manager.py`
- `backend/tests/test_runs_router.py`
- `backend/tests/test_thread_runs_router.py`
- `backend/tests/test_thread_ownership.py`
- `backend/tests/test_custom_agent.py`

### C. harness / runtime / bootstrap 相关

我重点看过这些会真正消费 runtime context 的地方：

- `backend/packages/harness/deerflow/agents/lead_agent/agent.py`
- `backend/packages/harness/deerflow/tools/builtins/setup_agent_tool.py`
- `backend/packages/harness/deerflow/config/agents_config.py`
- `backend/packages/harness/deerflow/config/paths.py`
- `backend/packages/harness/deerflow/tools/builtins/task_tool.py`
- `backend/packages/harness/deerflow/agents/middlewares/thread_data_middleware.py`

结论：

- `thread_id` 的 runtime context 注入是必要的，很多 middleware/tool 都直接读它
- `user` 身份字段进入 runtime context 虽然暂时没被大量消费，但作为未来授权/审计上下文是合理的
- `agent_name` 一旦进入 trusted runtime context，就会影响：
  - lead agent prompt / SOUL 选择
  - bootstrap 创建路径
  - setup_agent 的落盘目录

所以它和 thread/user 不属于同一级别的“服务端受信绑定”

### D. frontend 自定义 agent 入口

我也看了 frontend 的 custom-agent chat 入口：

- `frontend/src/app/workspace/agents/[agent_name]/chats/[thread_id]/page.tsx`
- `frontend/src/core/threads/hooks.ts`
- `frontend/src/core/threads/types.ts`

结论：

- frontend 仍然会把 `agent_name` 放在 request `context` 里发给后端
- 但 Gateway 侧不应该因此把它升级成 trusted runtime context
- 合法 custom agent 选择目前主要还是通过 `assistant_id`/request shape 落到 `configurable.agent_name`

---

## 我用过的外部上下文

### 1. `ecc_auth` 共享 SDK

我专门对照了：

- `/Users/sayori/Desktop/work/ecc_auth/packages/python/ecc_auth/session.py`
- `/Users/sayori/Desktop/work/ecc_auth/packages/python/ecc_auth/middleware.py`
- `/Users/sayori/Desktop/work/ecc_auth/packages/python/ecc_auth/routes.py`
- `/Users/sayori/Desktop/work/ecc_auth/packages/python/ecc_auth/dependencies.py`
- `/Users/sayori/Desktop/work/ecc_auth/HANDOFF_auth_sdk_session_review.md`

这个对照主要用于确认：

- DeerFlow Gateway 的 auth wrapper 有没有把共享契约重新改歪
- `AuthSessionMiddleware` 安装后的业务依赖语义应该怎么描述
- 这轮 run/runtime review 应该把注意力放在 Gateway trust boundary，而不是再去重复 review `ecc_auth` middleware 本身

### 2. 并行 reviewer 子代理结论

我还让两个子代理做了并行 review，核心结论如下：

#### 子代理结论里，我已经处理的

- `agent_name` 被错误提升为 trusted runtime context
- run record 暴露未净化 config
- Keycloak 必填配置没有 fail-fast

#### 子代理结论里，我还没处理的

- `/api/user-profile` 未鉴权

---

## 当前建议给下一位 reviewer 的优先检查顺序

如果下一个 agent 继续做 review，我建议按这个顺序，不要重新从全仓库散读：

1. 先看 `backend/app/gateway/services/runtime.py`
   核对：
   - `build_run_config()`
   - `build_trusted_run_context()`
   - `_apply_trusted_run_context()`
   - `build_public_run_config()`
   - `start_run()`

2. 再看 `backend/tests/test_gateway_services.py`
   核对：
   - runtime-only configurable blocklist
   - context spoofing overwrite
   - sanitized public config 存储
   - `config.context` 形态下 `assistant_id -> agent_name` 的兼容性

3. 再看 `backend/app/gateway/auth/routes.py` 与 `backend/tests/test_auth_sdk_integration.py`
   核对：
   - required env fail-fast
   - 是否与 `ecc_auth.KeycloakConfig` 的共享契约一致

4. 最后单独决定要不要继续处理 `backend/app/gateway/routers/agents.py` 的 `/api/user-profile`

---

## 我做过的验证

我实际跑过：

```bash
cd /Users/sayori/Desktop/work/deer-flow/backend
rtk proxy uv run pytest tests/test_auth_sdk_integration.py tests/test_gateway_services.py tests/test_run_manager.py -q
```

结果：

- `55 passed`

以及：

```bash
cd /Users/sayori/Desktop/work/deer-flow/backend
rtk proxy uv run ruff check app/gateway/auth/routes.py app/gateway/deps.py app/gateway/services/runtime.py tests/test_auth_sdk_integration.py tests/test_gateway_services.py tests/test_run_manager.py
```

结果：

- `All checks passed!`

我没有跑更大的全量 backend test，也没有跑 frontend。

---

## 给下一位 reviewer 的一句话总结

你可以把这轮理解成：

- 我已经把“Gateway run 入口的 thread/user 受信绑定”和“run record 回显净化”这两条最核心的 auth/runtime trust boundary 收紧了
- 我也把 DeerFlow 对 `ecc_auth` 的一处配置契约削弱修回来了
- 但我没有继续扩到 `/api/user-profile` 未鉴权，也没有重构 custom agent ownership 模型

如果你是做 review，请优先验证我这轮对 `runtime.py` 的边界收口是否足够严格，以及是否还存在别的 caller-controlled configurable 可以越过 Gateway 直达 lead agent / bootstrap / filesystem。
