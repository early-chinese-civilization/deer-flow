# DeerFlow用户管理阶段1-认证与当前用户解析

## 1. 本阶段目标

- 在 Python Gateway 中落地统一认证入口
- 接入 Keycloak `public client first`
- 建立 `users / current_user`
- 采用 `ecc_agent` 式浏览器 HttpOnly token cookie 认证
- 先完成 `/workspace/**` 登录保护

## 1.1 本阶段硬规则

- Gateway 是唯一认证真相
- Keycloak 是唯一登录态与失效真相
- `current_user` 的正式解析链路是：`kc_access_token -> /userinfo`，失败后 `kc_refresh_token -> refresh -> /userinfo`
- DeerFlow v1 不维护 `auth_sessions` 或 DeerFlow 自有服务端 session 作为正式认证模型
- 浏览器持有 `kc_access_token / kc_refresh_token / kc_id_token`，且必须是 `HttpOnly`
- 前端不得把 Keycloak token 持久化到 `localStorage / sessionStorage`
- `Secure / SameSite` 必须显式配置

## 2. 前置依赖

- 根目录 `.env` 已成为唯一配置源
- Keycloak 参数已确认
- PG 连接已确认使用 `5432`

## 3. 参考实现与 DeerFlow 落点

### 3.1 DeerFlow 正式采纳 `ecc_agent` 的部分

- `login`：推导 public origin、校验 `returnTo`、生成 `state`、设置 CSRF cookie
- `callback`：校验 `state / code / csrf`，换 token，读取 `userinfo`，完成本地用户落库
- `me`：优先用 `access_token` 调 `userinfo`，失效后再尝试 `refresh_token`
- `logout`：清理本地 cookie 并构造 Keycloak logout URL
- `get_current_user / get_user_id`：将当前用户解析能力沉淀为 Gateway 依赖
- `kc_* cookie` 的持有、清理与刷新回写

### 3.2 DeerFlow 与 `ecc_agent` 的差异点

- 仍按供应方要求保留 `Authorization Code(+PKCE，如供应方支持或要求)`
- DeerFlow 的业务目标是用户资源模型迁移，不迁 `ecc_agent` 的 `/profile`、crew/history 耦合
- frontend 仍然通过同源 `/api/auth/**` 使用 Gateway，不直接跨源访问 Keycloak
- 前端不把 token 复制到 `localStorage / sessionStorage`

### 3.3 阶段 1 不跟着迁的内容

- 不迁 `ecc_agent` 的 `/profile` 资料补全接口
- 不迁其 crew / history 业务耦合
- 不在阶段 1 就把所有业务路由切成全量 `Depends(get_user_id)` 模式

## 4. 涉及表与字段

- `users`
  - `id`
  - `external_auth_id`
  - `username`
  - `display_name`
  - `email`
  - `given_name`
  - `family_name`
  - `email_verified`
  - `created_at / updated_at`

阶段 1 不再引入 `auth_sessions`。

## 5. 接口定义

### `GET /api/auth/login`

- 参考 `ecc_agent` 的代理头 origin 推导与 `returnTo` 校验
- 生成 `state + nonce`，并在供应方支持或要求时补 `PKCE`
- 设置短期 CSRF 上下文 cookie
- 跳转到 Keycloak

### `GET /api/auth/callback`

- 校验 `state / code / csrf / pkce(如启用)`
- 向 Keycloak 交换 token
- 读取 `userinfo`
- upsert `users`
- 写入浏览器 `HttpOnly kc_access_token / kc_refresh_token / kc_id_token`
- 可选写入 `kc_expires_at`
- 清理临时 auth cookie

### `GET /api/auth/me`

- 优先读取 `kc_access_token`
- 用 `access_token` 调 Keycloak `/userinfo`
- access token 失效时，使用 `kc_refresh_token` 调 refresh
- refresh 成功则重写 `kc_* cookie` 并返回当前用户
- refresh 失败则清理 `kc_* cookie` 并返回 `401`

### `POST /api/auth/logout`

- 清理本地 `kc_* cookie`
- 返回或跳转 Keycloak logout URL

### `POST /api/auth/refresh`

- 推荐在阶段 1 落地
- 使用 `kc_refresh_token` 主动刷新并重写 `kc_* cookie`
- 前端初期可只依赖 `/api/auth/me` 懒刷新，不要求先做主动刷新调度

### `current_user`

- 作为 Gateway 统一依赖供后续阶段复用
- 负责把当前用户对象解析到请求上下文
- 业务路由不信任前端缓存用户态，只信任 Gateway 解析结果

## 6. 前端约束

- frontend 不再以 `better-auth` 作为主认证中心
- 前端登录态真相只能来自 Gateway `/api/auth/me`
- 前端不得把 Keycloak token 存入 `localStorage / sessionStorage`
- 浏览器中的 `kc_* cookie` 只作为 HttpOnly 认证载体，不作为前端可编程状态

## 7. 允许修改范围

- `backend/app/gateway/**`
- 认证相关 repository / migration 基座
- `backend/tests/**`
- `frontend/src/**`
- `plan/**`
- `scripts/**`

## 8. 禁止改动范围

- 不提前改 `chats / messages / workspaces / agents / skills / knowledge base`
- 不扩展 `frontend/src/server/better-auth/*` 成正式认证中心

## 9. 自动验证命令

```bash
make check
cd backend && uv run pytest tests/test_auth_routes.py tests/test_gateway_keycloak_tls.py -q
```

若阶段 1 新增了认证定向测试，验收时必须把新增测试一起纳入执行清单。

## 10. 失败即中断条件

- 回调地址或代理头逻辑无法稳定
- `kc_* cookie` 未显式配置 `HttpOnly / Secure / SameSite`
- `/api/auth/me` 不能完成“userinfo -> refresh -> 重写 cookie”闭环
- `current_user` 不能稳定按 `kc_access_token -> /userinfo`，失败后 `kc_refresh_token -> refresh -> /userinfo` 解析
- 前端仍把 Keycloak token 作为持久化主状态

## 11. 风险与注意事项

- 若 DeerFlow 实施时在回调地址、代理头、cookie 域、refresh 恢复、用户落库时序上出现疑问，先回查 `ecc_agent` 对应文件
- `ecc_agent` 的 token cookie 模型本轮是正式参考，不再写成“禁止照搬”
- 若供应方协议最终要求 `PKCE`，则在现有 cookie 架构上补齐，不改变本阶段认证真相

## 12. 验收动作

- 登录、回调、`/me`、退出链路跑通
- 登录回调后浏览器已收到 `HttpOnly kc_* cookie`
- `/workspace/**` 已受登录保护
- 前端登录态初始化已切到 `/api/auth/me`
- 前端未把 Keycloak token 持久化到浏览器存储
- `current_user` 已稳定走 Gateway + Keycloak 实时解析链路
