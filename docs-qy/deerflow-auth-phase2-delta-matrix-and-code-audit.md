# DeerFlow 鉴权阶段二：差异矩阵与代码级核对

日期：2026-04-15

## 1. 范围

本文档基于 DeerFlow 当前代码实现做鉴权核对，并与 `ecc_auth` 稳定文档中的目标契约对照。

本轮核对覆盖：

- backend `app/gateway/auth/*`
- backend `app/gateway/deps.py`
- backend `app/gateway/services/ownership.py`
- backend 各 gateway router 的鉴权接入情况
- frontend `core/auth`、`middleware`、`/api/auth/[...all]`

本轮不包含：

- 真实登录联调
- 运行时抓包
- e2e 行为验证
- 迁移实现

## 2. 代码级现状摘要

### 2.1 后端认证主链

当前 DeerFlow 已经存在完整的后端认证路由：

- `GET /api/auth/login`
- `GET /api/auth/callback`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `POST /api/auth/refresh`

代码位置：

- `backend/app/gateway/auth/routes.py`

### 2.2 浏览器侧 cookie 契约

当前代码实际写入以下 cookie：

- `kc_access_token`
- `kc_refresh_token`
- `kc_id_token`
- `kc_expires_at`

其中前三者为 `HttpOnly`，`kc_expires_at` 为前端可读毫秒时间戳。

代码位置：

- `backend/app/gateway/auth/web.py`

### 2.3 当前用户解析方式

普通业务路由里的 `current_user` 通过 `get_current_user()` 解析，逻辑是：

1. 读取 `kc_access_token`
2. 用 access token 请求 Keycloak `/userinfo`
3. 把返回的 `sub` / claims upsert 到本地 `users`
4. 返回本地 `User`

注意：

- 普通业务依赖本身不会 refresh
- refresh 只发生在 `/api/auth/me` 与 `/api/auth/refresh`

代码位置：

- `backend/app/gateway/deps.py`
- `backend/app/gateway/auth/service.py`
- `backend/app/gateway/auth/keycloak.py`

### 2.4 当前前端登录态来源

前端当前活跃链路不是 `better-auth`，而是自定义 `core/auth`：

- Next middleware 只看 `kc_access_token` / `kc_refresh_token` 是否存在来保护 `/workspace/**`
- `AuthProvider` 初始化时调用 `/api/auth/me`
- `/api/auth/*` 由 Next route proxy 转发给 Gateway

代码位置：

- `frontend/src/middleware.ts`
- `frontend/src/core/auth/api.ts`
- `frontend/src/core/auth/context.tsx`
- `frontend/src/app/api/auth/[...all]/route.ts`

## 3. 与 ecc_auth 的契约差异矩阵

说明：

- `状态` 分为 `对齐`、`部分对齐`、`未对齐`
- `置信度` 指本轮代码阅读判断置信度，不代表真实联调结果

| 主题 | DeerFlow 当前实际行为 | ecc_auth 目标契约 | 状态 | 置信度 | 迁移影响 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| Keycloak 是否为唯一外部身份源 | 当前 auth 实现直接对接 Keycloak，无内部 OAuth wrapper | Keycloak 是唯一统一身份层 | 对齐 | 高 | 低 | `backend/app/gateway/auth/keycloak.py` |
| Python 服务是否仍手写 OIDC | DeerFlow 当前 `/api/auth/*` 全部自行实现 | Python 服务应优先消费共享 `ecc-auth` SDK，而不是继续保留手写实现 | 未对齐 | 高 | 高 | 这是当前最核心结构差异 |
| 路由形态 | DeerFlow 自己维护 login/callback/me/logout/refresh 路由 | 这些核心路由应由共享 SDK 托管，应用只补业务专属路由 | 未对齐 | 高 | 高 | `backend/app/gateway/auth/routes.py` |
| cookie 名称 | 使用 `kc_access_token` / `kc_refresh_token` / `kc_id_token` / `kc_expires_at` | `kc_*` 契约固定 | 对齐 | 高 | 低 | `backend/app/gateway/auth/web.py` |
| `kc_expires_at` 语义 | JS 可读、毫秒时间戳 | JS 可读、毫秒时间戳 | 对齐 | 高 | 低 | `backend/app/gateway/auth/web.py` |
| `kc_logout_marker` | 当前未实现 | 显式登出后应存在 `kc_logout_marker`，并阻断 `/me`/`/refresh` 自动恢复 | 未对齐 | 高 | 中 | 当前 logout 只清 cookie，不建立 marker |
| 登录 state 结构 | 当前只有 `nonce + returnTo` | 应包含 `nonce + return_to + origin` | 未对齐 | 高 | 中 | `backend/app/gateway/auth/schemas.py` |
| callback 跳转语义 | callback 后 `RedirectResponse(url=normalize_return_to(...))`，只保留相对路径 | 应明确重定向到 `origin + return_to` | 部分对齐 | 高 | 中 | 在同源代理场景通常可工作，但不符合共享契约表达 |
| access token 校验方式 | `/userinfo` 优先；普通业务 `get_current_user` 只走 `/userinfo` | `/me` 和依赖注入优先做本地 `JWKS` 验签；access token 不可用时才 refresh | 未对齐 | 高 | 高 | 当前未发现本地 JWT/JWKS 验签实现 |
| refresh 行为 | `/api/auth/me` 在 access token 失败后使用 refresh token；`/api/auth/refresh` 主动刷新 | access token 不可用时才 refresh | 部分对齐 | 高 | 中 | `/me` 层面方向相近，但前置校验不是 JWKS |
| 普通业务依赖是否有副作用 | `get_current_user` 不刷新、不改 cookie，只做认证解析 | 依赖注入应稳定、可复用 | 对齐 | 高 | 低 | 这一点反而比较干净 |
| 上游 `5xx` 映射 | refresh/userinfo 失败时对外映射 `503 Authentication service unavailable` | 上游 `5xx` 不应伪装成 401 | 对齐 | 高 | 低 | `routes.py` 与 `deps.py` 都有映射 |
| `external_auth_id = sub` | 本地用户 upsert 使用 `user_info.sub` | 必须等于 Keycloak `sub` | 对齐 | 高 | 低 | `backend/app/gateway/auth/service.py` |
| `display_name` fallback | 当前为 `name or preferred_username` | 目标为 `name > preferred_username > email > sub` | 部分对齐 | 高 | 中 | 当前缺 `email > sub` fallback |
| `username` fallback | 当前直接使用 `preferred_username` | 目标为 `preferred_username > email > sub` | 未对齐 | 高 | 中 | 当前没有 fallback |
| `AuthIdentity` 共享身份层 | 当前只有 DeerFlow 自己的 `User` upsert + API payload | 共享层应以 `AuthIdentity` 为稳定接口 | 未对齐 | 中 | 中 | 需要后续结合 SDK 迁移确认 |
| Keycloak 端点使用方式 | 显式使用 `auth/token/userinfo/logout` 端点，不依赖 discovery | 共享契约要求避免把登录建立在动态 discovery 成功上 | 对齐 | 高 | 低 | `backend/app/gateway/auth/keycloak.py` |
| `KEYCLOAK_TLS_INSECURE` | 当前 `verify` 会随环境变量关闭 TLS 校验 | 应显式支持，并覆盖相关后端 HTTP 调用 | 部分对齐 | 高 | 中 | 目前覆盖 code exchange / refresh / userinfo，但因为没有 JWKS 拉取，无法覆盖 JWKS |
| `trust_env=False` | 当前 `httpx.AsyncClient` 未显式设置 `trust_env=False` | Keycloak HTTP 请求应禁用环境代理继承 | 未对齐 | 高 | 中 | `backend/app/gateway/auth/keycloak.py` |
| 前端是否依赖 Better Auth | 当前活跃路径不是 Better Auth；仅残留依赖和文档痕迹 | 可以保留项目内不同接入形态，但不应把 Better Auth 当 Python 服务统一中心 | 对齐 | 高 | 低 | 现状是自定义 `core/auth` |
| 是否存在 DeerFlow 自己的并行 auth session 权威 | 未发现 `auth_sessions` 表或 `request.session` 类正式鉴权权威 | 不应引入第二个签发源 / session authority | 对齐 | 中高 | 低 | 当前主要是本地 `users` 投影，不是本地 session authority |

## 4. Gateway 保护面代码核对

### 4.1 已接入 `current_user` / ownership 的区域

- `auth`：认证入口自身
- `threads`：已接入 `get_current_user`，多数接口再走 `require_thread_access`
- `thread_runs`：已接入 `get_current_user`，正常路径走 `require_thread_access`
- `uploads`：现在已接入 `get_current_user`，并校验 workspace / thread 归属

这说明旧文档里“uploads 未接入用户体系”的判断已经过时，代码现状比旧文档更靠前。

### 4.2 仍未接入 `current_user` / ownership 的区域

- `artifacts`
- `suggestions`
- `runs`（stateless run）
- `memory`
- `skills`
- `mcp`
- `agents`
- `channels`
- `assistants_compat`
- `models`

其中风险较高的不是 `models` 这类公共只读接口，而是：

- `artifacts`
- `suggestions`
- `runs`

因为这些接口都和 thread/path/runtime 有更强耦合，却还没有统一 ownership 边界。

### 4.3 已发现的代码问题

`thread_runs` 中 `stream_existing_run` 当前对 `_require_owned_thread(...)` 的调用缺少 `request` 参数，因此这个入口不是“安全接入”，而是“实现损坏”。

这不是本文重点，但应记录为后续修复项。

## 5. 前端接入代码核对

### 5.1 当前真实登录态来源

前端当前登录态来源已经不是 `better-auth` session，而是：

1. middleware 基于 `kc_access_token` / `kc_refresh_token` 判断是否允许进入 `/workspace/**`
2. `AuthProvider` 启动后调用 `/api/auth/me`
3. `/api/auth/me` 成为前端恢复登录态的唯一主入口

这与第一阶段的文档目标基本一致。

### 5.2 仍然存在的历史残留

- `better-auth` 依赖仍在 `frontend/package.json`
- `frontend/README.md` / `frontend/AGENTS.md` 仍有 “better-auth” 或 “server/better-auth” 的历史表述

这不构成运行时 auth authority，但会增加理解噪音，后续应清理。

## 6. 本轮代码核对后的结论更新

相较于第一阶段只看文档的初步结论，本轮代码核对后可以把判断更新为：

### 6.1 已经可以确认的事实

- DeerFlow 当前确实有一套完整的手写 Keycloak/OIDC 路由实现
- 当前主认证链路确实是 `kc_access_token -> /userinfo`，而不是共享契约偏好的本地 `JWKS` 验签优先
- 当前没有形成 DeerFlow 自己的正式 session authority
- 前端当前真实登录态来源已经切到 Gateway `/api/auth/me`
- `uploads` 已经完成用户化接入，旧文档已过时

### 6.2 已经可以确认的结构性差异

- DeerFlow 仍未收敛到 `ecc-auth` SDK 托管核心 auth 路由
- DeerFlow 当前 state / callback 语义未完全满足 `origin + return_to` 契约
- DeerFlow 当前未实现 `kc_logout_marker`
- DeerFlow 当前 identity mapping fallback 规则未完全满足共享契约
- DeerFlow 当前 Keycloak 校验路径与 `ecc-auth` 目标存在核心差异：`userinfo` 优先 vs `JWKS` 优先

### 6.3 已经可以确认的授权保护面风险

- auth alignment 还不能代表 authorization completeness
- `artifacts` / `suggestions` / `runs` 是当前最明显的未统一保护面

## 7. 下一步建议

建议进入真正的迁移拆解前，先基于本文档再补一份“实施前差异闭环清单”，至少包括：

1. 哪些核心 auth 路由将被 `ecc-auth` 取代
2. 哪些 DeerFlow 业务逻辑应保留为 app-specific 路由或回调
3. `userinfo` 优先迁到 `JWKS` 优先时，哪些调用链会受影响
4. 未完成保护面的 router 应如何纳入统一 ownership 体系
5. `kc_logout_marker`、`origin`、fallback 规则、`trust_env=False` 这些共享契约缺口应按什么顺序补齐

## 8. 参考代码与文档

核心代码：

- `backend/app/gateway/auth/routes.py`
- `backend/app/gateway/auth/keycloak.py`
- `backend/app/gateway/auth/web.py`
- `backend/app/gateway/auth/service.py`
- `backend/app/gateway/deps.py`
- `backend/app/gateway/services/ownership.py`
- `backend/app/gateway/routers/threads.py`
- `backend/app/gateway/routers/thread_runs.py`
- `backend/app/gateway/routers/uploads.py`
- `backend/app/gateway/routers/artifacts.py`
- `backend/app/gateway/routers/suggestions.py`
- `backend/app/gateway/routers/runs.py`
- `frontend/src/core/auth/api.ts`
- `frontend/src/core/auth/context.tsx`
- `frontend/src/middleware.ts`
- `frontend/src/app/api/auth/[...all]/route.ts`

目标文档：

- `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth/ecc-auth-runtime-contract.md`
- `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth/keycloak-is-the-unified-identity-layer.md`
- `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth/do-not-wrap-keycloak-with-an-internal-oauth-provider.md`
