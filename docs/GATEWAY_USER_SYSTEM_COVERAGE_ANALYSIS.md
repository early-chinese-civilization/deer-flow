# Gateway 用户体系接入现状分析

## 结论

目前不是所有 Gateway 接口都已接入用户体系。

更准确地说，当前只有“认证接口 + 线程主链路”完成了用户接入；若干线程外围接口以及系统级全局接口，仍然没有统一接入 `get_current_user` / `require_thread_access`。

## 总体判断依据

Gateway 当前没有统一的全局鉴权中间件或全局 router 级用户依赖。应用启动时只是逐个注册路由：

- `auth`
- `models`
- `mcp`
- `memory`
- `skills`
- `artifacts`
- `uploads`
- `threads`
- `agents`
- `suggestions`
- `channels`
- `assistants_compat`
- `thread_runs`
- `runs`

代码位置：

- [`backend/app/gateway/app.py`](../backend/app/gateway/app.py)

当前用户解析入口在：

- [`backend/app/gateway/deps.py#L76`](../backend/app/gateway/deps.py#L76) 的 `get_current_user`

全局检索结果显示，`Depends(get_current_user)` 和 `require_thread_access` 目前只明显落在：

- [`backend/app/gateway/routers/threads.py`](../backend/app/gateway/routers/threads.py)
- [`backend/app/gateway/routers/thread_runs.py`](../backend/app/gateway/routers/thread_runs.py)

## 一、已接入用户体系的接口

### 1. 认证接口 `/api/auth/*`

这组接口本身就是用户体系入口，虽然不是业务接口里常见的 `Depends(get_current_user)` 形式，但它们会通过 token/cookie 流程解析并同步当前用户。

典型接口包括：

- `/api/auth/login`
- `/api/auth/callback`
- `/api/auth/me`
- `/api/auth/logout`
- `/api/auth/refresh`

关键代码：

- [`backend/app/gateway/auth/routes.py`](../backend/app/gateway/auth/routes.py)

### 2. 线程主接口 `/api/threads/*`

这一组已经接入用户体系：

- 创建线程
- 搜索线程
- 获取线程
- 更新线程
- 删除线程
- 获取 state
- 更新 state
- 获取 history

这些接口都会要求 `current_user`，并且搜索已按 `user_id=current_user.id` 查询业务表。

关键代码：

- [`backend/app/gateway/routers/threads.py#L480`](../backend/app/gateway/routers/threads.py#L480)

### 3. 线程运行主链路 `/api/threads/{thread_id}/runs/*`

这一组也已经接入用户体系：

- create run
- stream run
- wait run
- list runs
- get run
- cancel run
- join run
- stream existing run

这些接口统一先走 `require_thread_access`。

关键代码：

- [`backend/app/gateway/routers/thread_runs.py#L105`](../backend/app/gateway/routers/thread_runs.py#L105)

### 4. 当前 ownership 的真实判断方式

当前共享鉴权逻辑在：

- [`backend/app/gateway/services/ownership.py#L40`](../backend/app/gateway/services/ownership.py#L40)

核心逻辑是：

1. 先要求当前请求已经有认证用户
2. 再查业务库中的 thread
3. 校验 `thread.user_id == current_user.id`
4. 然后再要求 Store 中存在对应 thread record

也就是说：

- `flow.threads.user_id` 是归属判断真值
- Store 目前仍参与“线程是否完整存在”的校验
- 但 Store 本身不再是用户归属真值来源

## 二、线程相关但还没有完全接入用户体系的接口

### 1. `/api/runs/*`

这是当前最明显的缺口之一。

接口：

- `POST /api/runs/stream`
- `POST /api/runs/wait`

这组接口没有 `Depends(get_current_user)`。当请求体里传入已有 `thread_id` 时，会直接复用该 `thread_id` 发起 run，没有在这个 router 内执行 ownership 校验。

关键代码：

- [`backend/app/gateway/routers/runs.py#L38`](../backend/app/gateway/routers/runs.py#L38)

这意味着它不属于“严格用户化”的线程主链路。

### 2. `/api/threads/{thread_id}/uploads/*`

接口：

- 上传文件
- 列出文件
- 删除文件

这组接口没有用户依赖，也没有 `require_thread_access`，当前只是按 `thread_id` 直接操作文件系统路径。

关键代码：

- [`backend/app/gateway/routers/uploads.py#L56`](../backend/app/gateway/routers/uploads.py#L56)

### 3. `/api/threads/{thread_id}/artifacts/*`

这组接口也没有用户依赖。当前主要是根据 `thread_id + path` 解析并返回文件内容。

关键代码：

- [`backend/app/gateway/routers/artifacts.py#L79`](../backend/app/gateway/routers/artifacts.py#L79)

### 4. `/api/threads/{thread_id}/suggestions`

这组接口同样没有用户依赖。虽然 URL 上带了 `thread_id`，但当前主要只是拿传入消息生成建议，不做线程归属校验。

关键代码：

- [`backend/app/gateway/routers/suggestions.py#L94`](../backend/app/gateway/routers/suggestions.py#L94)

## 三、当前仍然是全局/公共接口的模块

以下路由当前都没有明显接入用户体系：

### 1. `/api/memory/*`

特点：

- 面向全局 memory 数据
- 不是按用户隔离

代码：

- [`backend/app/gateway/routers/memory.py`](../backend/app/gateway/routers/memory.py)

### 2. `/api/skills/*`

特点：

- 读写全局 skills 配置
- 安装 skill 时虽然带 `thread_id`，但没有线程 ownership 校验

代码：

- [`backend/app/gateway/routers/skills.py`](../backend/app/gateway/routers/skills.py)

### 3. `/api/mcp/*`

特点：

- 读写全局 MCP 配置

代码：

- [`backend/app/gateway/routers/mcp.py`](../backend/app/gateway/routers/mcp.py)

### 4. `/api/agents/*` 和 `/api/user-profile`

特点：

- 操作全局 agents 目录和全局 `USER.md`
- 不是按用户做隔离

代码：

- [`backend/app/gateway/routers/agents.py`](../backend/app/gateway/routers/agents.py)

### 5. `/api/channels/*`

特点：

- 管理全局 IM channel 状态

代码：

- [`backend/app/gateway/routers/channels.py`](../backend/app/gateway/routers/channels.py)

### 6. `/api/models/*`

特点：

- 查询全局模型能力
- 更偏公共只读接口

代码：

- [`backend/app/gateway/routers/models.py`](../backend/app/gateway/routers/models.py)

### 7. `/api/assistants/*`

特点：

- 当前更像兼容层/公共接口
- 未接入用户鉴权

代码：

- [`backend/app/gateway/routers/assistants_compat.py`](../backend/app/gateway/routers/assistants_compat.py)

## 四、结论与风险

### 结论

当前 Gateway 不能说“所有接口都已经使用用户体系”。

更准确的表述应该是：

- 认证接口已接入用户体系
- `/api/threads/*` 与 `/api/threads/{thread_id}/runs/*` 这条线程主链已经接入用户体系
- 但 uploads、artifacts、suggestions、stateless runs 以及 memory/skills/mcp/agents/channels 等全局接口，仍未全部完成用户化

### 当前高风险缺口

优先级最高的缺口包括：

- `/api/runs/*`
- `/api/threads/{thread_id}/uploads/*`
- `/api/threads/{thread_id}/artifacts/*`
- `/api/threads/{thread_id}/suggestions`

原因是：

- 这些接口路径上已经带有 `thread_id` 或可复用线程
- 但没有统一走线程归属校验
- 容易形成“线程主接口已用户化，但外围资源接口仍绕过用户校验”的不一致状态

### 建议

如果后续继续推进 Gateway 用户化，建议优先顺序为：

1. 先补齐所有 thread-adjacent 接口的 `require_thread_access`
2. 再评估全局接口是否需要真正业务化到 user 维度
3. 最后决定哪些接口应保持公共/系统级能力，哪些应改造成用户资源
