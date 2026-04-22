# Gateway Auth Runtime Custom-Agent Follow-up Handoff

## Goal

这份 handoff 是上一份

- `docs-qy/2026-04-22-gateway-auth-runtime-review-handoff.md`

的补充，不是替代。

上一份 handoff 已经把本轮 auth/runtime 主线、server-trusted runtime context 边界、sanitized public run config、Keycloak fail-fast 等背景讲清楚了。

我这次接着做的是一个更窄的 follow-up：

- 修复“Gateway 收紧 trusted runtime context 之后，把现有 custom-agent 选择链路一起误伤了”的回归
- 重点不是重做整个 custom agent authority model，而是恢复当前前端真实请求形态下的 agent 路由

---

## 先讲结论

### 已修复的回归

Gateway 现在能正确保留 custom-agent 选择，覆盖两条入口：

1. `body.config.context.agent_name`
2. `body.context.agent_name`

同时仍然保持这条边界：

- `thread_id` / user identity 仍然是 server-owned / trusted runtime context
- `agent_name` 不再被当成 trusted runtime identity
- `agent_name` 只作为普通选择参数保留在 `configurable.agent_name`

也就是说：

- 修复了 custom-agent 路由丢失
- 没有把 `agent_name` 放回 server-trusted runtime context

### 当前状态

- 代码已改
- 回归测试已补
- 目标测试通过
- 还没有提交 commit

---

## 为什么我会继续动这里

上一轮收紧 runtime context 的方向本身是对的：

- 不应该让客户端伪造 `thread_id`
- 不应该让客户端伪造 user/auth 绑定
- 不应该让 `agent_name` 通过 trusted runtime context 冒充服务端受信身份

但我 review 时发现，当前前端自定义 agent 页面并不是靠 `assistant_id=<custom-agent>` 选 agent，而是靠：

- frontend 固定发 `assistantId: "lead_agent"`
- 然后把真正目标 agent 放在 `context.agent_name`

证据：

- `frontend/src/core/threads/hooks.ts:118-121`
- `frontend/src/app/workspace/agents/[agent_name]/chats/[thread_id]/page.tsx:42-45`
- `frontend/src/app/workspace/agents/[agent_name]/chats/[thread_id]/page.tsx:72-75`

也就是说，如果 Gateway 收紧时直接把 `context.agent_name` 抹掉，又不把它转存到 `configurable.agent_name`，那 custom-agent chat 就会静默回退到默认 lead agent。

我做过最小复现，修复前这类请求最终会变成：

```python
{'recursion_limit': 100, 'context': {'model_name': 'gpt-4', 'thread_id': 'thread-1'}, 'configurable': {'thread_id': 'thread-1'}}
```

可以看到目标 agent 已经丢了。

---

## 我实际修改了哪些模块

### 1. `backend/app/gateway/services/runtime.py`

这是本次真正的代码修复点。

我处理了两层：

#### A. `build_run_config()` 里的 `request_config["context"]` 路径

位置：

- `backend/app/gateway/services/runtime.py:144-197`

新增行为：

- 如果请求使用 `config.context.agent_name`
- 且 `assistant_id` 为空或仍然是 `lead_agent`
- 就把这个值规范化后转存到 `configurable.agent_name`

保留的优先级：

- 显式非默认 `assistant_id` 仍然优先
- 不允许 `context.agent_name` 覆盖已经明确指定的自定义 `assistant_id`

原因：

- 这条路径兼容 LangGraph 风格 `config.context`
- 但不能重新把 `agent_name` 当成 trusted runtime context

#### B. `start_run()` 里的顶层 `body.context` 路径

位置：

- `backend/app/gateway/services/runtime.py:367-382`

这是我第二次补的地方。

因为我后来又确认到，前端真实更常走的是：

- 顶层 `body.context.agent_name`

而不是：

- `body.config.context.agent_name`

修复前这里的问题是：

- `start_run()` 只会把 `model_name` / `is_plan_mode` 这类键从 `body.context` 抄到 `configurable`
- 但不会处理 `body.context.agent_name`
- 后面 `_apply_trusted_run_context()` 又会把 `context` 里的 `agent_name` 清掉
- 所以前端真实路径还是会丢 agent 选择

我加的逻辑是：

- 当 `body.context.agent_name` 存在
- 且 `assistant_id` 为空或仍为 `lead_agent`
- 若 `configurable.agent_name` 还没被别处占用，就把它规范化后写入 `configurable.agent_name`
- 非法名称直接返回 400

#### C. 这次没有改变的边界

这些点我**没有**放松：

- `thread_id` 仍由服务端覆盖
- `user_id` / `external_auth_id` / `username` / `display_name` / `email` 仍由服务端覆盖
- `agent_name` 仍不会保留在最终 runtime `context`
- run record 返回给客户端的 config 仍是 sanitized public config

---

### 2. `backend/tests/test_gateway_services.py`

我补的是 gateway services 层的回归测试，不是 frontend 测试。

关键新增测试：

- `test_build_run_config_promotes_context_agent_name_for_lead_agent_requests`
- `test_start_run_keeps_custom_agent_selection_from_context`
- `test_start_run_keeps_custom_agent_selection_from_top_level_context`

其中最关键的是最后一个，它覆盖了当前前端真实负载形态：

- `assistant_id="lead_agent"`
- `config=None`
- `context={"agent_name": "VIP_AGENT", "model_name": "gpt-4", "is_plan_mode": True}`

验证点：

- 执行时 `configurable.agent_name == "vip-agent"`
- runtime `context` 里不再残留 `agent_name`
- `model_name` / `is_plan_mode` 继续保留
- run record 存的是 sanitized public config，不回显 server-owned context

另外我也保留了一个重要 precedence 检查：

- 非默认 `assistant_id` 仍然应该压过 `context.agent_name`

这是为了避免把“修复前端兼容性”变成“削弱明确指定 assistant_id 的语义”。

---

### 3. 文档

我顺手同步了：

- `backend/README.md`
- `backend/CLAUDE.md`

更新点是把运行时边界描述改准确：

- trusted runtime context 保护的是 `thread_id` 和 user identity
- custom-agent routing 通过 `configurable.agent_name` 保留
- 不是把 `agent_name` 当成 trusted runtime binding

---

## 我明确没有做的事情

### 1. 我没有处理 custom agent ownership / authorization model

我没有做这些：

- 没有让 Gateway 在 run 启动前通过 DB 验证 `agent_name` 所属权
- 没有把 `agent_name` 改成必须通过 `AgentRepository` 授权才能运行
- 没有统一 frontend / channels / on-disk agent config / DB agent 这几套 authority model

原因：

- 这会从“修复 Gateway 回归”扩成“重构整个 custom agent authority model”
- 超出当前 handoff / review 主线

这个问题依然值得 reviewer 继续盯。

### 2. 我没有把 `agent_name` 放回 trusted runtime context

这是故意的。

我修的不是“恢复旧行为”，而是：

- 恢复 custom-agent 选择能力
- 同时维持 trusted runtime context 收紧后的安全边界

### 3. 我没有扩 scope 去修其他已知 auth finding

仍然没动上一份 handoff 里提到的 open finding，例如：

- `/api/user-profile` 未鉴权问题
- broader custom agent ownership / bootstrap authority 问题

下一位 reviewer 不要把这些当成“这轮已经解决”。

---

## 我验证过什么

我实际跑过：

```bash
rtk proxy uv run python -m py_compile app/gateway/services/runtime.py tests/test_gateway_services.py
rtk proxy uv run ruff check app/gateway/services/runtime.py tests/test_gateway_services.py
rtk proxy uv run pytest tests/test_gateway_services.py -q
```

结果：

- `py_compile` 通过
- `ruff check` 通过
- `tests/test_gateway_services.py` 通过，最终是 `38 passed`

另外我做过两次最小复现：

### A. `config.context.agent_name` 路径

修复后会得到类似：

```python
{
  'recursion_limit': 100,
  'context': {'model_name': 'gpt-4', 'thread_id': 'thread-1'},
  'configurable': {'agent_name': 'vip-agent', 'thread_id': 'thread-1'}
}
```

### B. 顶层 `body.context.agent_name` 路径

修复后会得到类似：

```python
{
  'recursion_limit': 100,
  'configurable': {
    'thread_id': 'thread-1',
    'is_plan_mode': True,
    'model_name': 'gpt-4',
    'agent_name': 'vip-agent'
  },
  'context': {
    'email': 'alice@example.com',
    'user_id': '7',
    'username': 'alice',
    'external_auth_id': 'kc-sub',
    'thread_id': 'thread-1',
    'display_name': 'Alice'
  }
}
```

重点：

- `agent_name` 留在 `configurable`
- 不留在 trusted runtime `context`

---

## 当前 worktree / review 注意事项

仓库还是脏的，而且不只是我这次补的文件。

当前 `git status --short` 里和 auth/runtime 主线相关的脏文件包括：

- `backend/app/gateway/auth/routes.py`
- `backend/app/gateway/deps.py`
- `backend/app/gateway/routers/runs.py`
- `backend/app/gateway/routers/thread_runs.py`
- `backend/app/gateway/services/runtime.py`
- `backend/packages/harness/deerflow/runtime/runs/worker.py`
- `backend/tests/test_auth_sdk_integration.py`
- `backend/tests/test_gateway_services.py`
- `backend/tests/test_run_manager.py`
- `backend/README.md`
- `backend/CLAUDE.md`

以及一些无关或文档脏改动：

- `README.md`
- `backend/uv.lock`
- `docs-qy/2026-04-20-session-state-gap-and-official-capability-boundary.md`
- `docs-qy/2026-04-22-gateway-auth-runtime-review-handoff.md`

所以：

- 下一位 reviewer 不要默认整个 diff 都是我这次补出来的
- review 时应优先看 `runtime.py` / `test_gateway_services.py` 的 follow-up 部分

---

## 我建议下一位 reviewer 重点看什么

### 1. 这次修复是否刚好卡在正确边界

你要重点判断：

- 现在是不是既恢复了 custom-agent 路由
- 又没有把 `agent_name` 重新抬回 trusted runtime context

这才是这次修复的核心。

### 2. precedence 是否合理

目前规则是：

- 非默认 `assistant_id` 优先
- 否则允许 `context.agent_name` 补到 `configurable.agent_name`

请重点 review 这条 precedence 有没有漏洞或行为回归。

### 3. run record sanitized public config 是否仍然符合预期

这次 follow-up 不应该破坏上一轮 already-fixed 的点：

- 客户端不能通过 run record 回显伪造的 thread/user/auth 绑定

### 4. 是否还存在其他入口会继续丢 `agent_name`

我已经覆盖了：

- `body.config.context.agent_name`
- `body.context.agent_name`

但你可以继续检查：

- channels
- SDK client compatibility paths
- 其他特殊 run 创建入口

看看还有没有第三条同类路径。

---

## 当前进度一句话总结

auth/runtime 主线的 trusted-context 收紧还在，custom-agent 因此产生的 Gateway 回归已经补上两条真实入口并通过回归测试；下一位 reviewer 现在最应该做的是确认这次补丁没有重新削弱边界，也没有遗漏其他 agent 选择入口。
