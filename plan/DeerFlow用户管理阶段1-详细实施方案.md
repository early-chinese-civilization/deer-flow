# DeerFlow 用户管理阶段1 - 详细实施方案

## 一、实施概览

### 1.1 目标

- 建立 Python Gateway 统一认证入口
- 接入 Keycloak `public client first`
- 建立 `users` 表和 `current_user` 解析
- 采用 `ecc_agent` 式浏览器 HttpOnly token cookie 模式
- 完成 `/workspace/**` 登录保护
- 前端切换到 Gateway 认证

### 1.2 技术栈

- **后端**: FastAPI + SQLAlchemy 2.0 (async) + psycopg + Alembic
- **认证**: Keycloak OpenID Connect
- **前端**: Next.js 16 + React 19

### 1.3 实施顺序

1. 更新依赖和环境配置
2. 创建数据库层（保留 `users`）
3. 创建认证模块（keycloak、cookie、current_user）
4. 创建认证路由（`/api/auth/*`）
5. 配置数据库迁移（`users`）
6. 扩展依赖注入（`get_current_user`）
7. 前端认证改造
8. 添加路由保护
9. 测试验证

## 二、后端实施

### 2.1 环境配置

`.env` 重点配置：

- `KEYCLOAK_URL`
- `KEYCLOAK_REALM`
- `KEYCLOAK_CLIENT_ID`
- `KEYCLOAK_CLIENT_SECRET`（如供应方配置需要）
- `KEYCLOAK_TLS_INSECURE`（仅本地调试时使用）
- `DATABASE_URL`

### 2.2 数据库模型

阶段 1 只保留 `users`：

- `id`
- `external_auth_id`
- `username`
- `display_name`
- `email`
- `given_name`
- `family_name`
- `email_verified`
- `created_at`
- `updated_at`

阶段 1 不引入 `auth_sessions`。

### 2.3 认证流程

#### 2.3.1 登录流程 (`GET /api/auth/login`)

1. 推导 public origin (`x-forwarded-proto`, `x-forwarded-host`, `referer`)
2. 校验 `returnTo`
3. 生成 `state / nonce`
4. 在供应方支持或要求时生成 `PKCE`
5. 设置临时 CSRF 上下文 cookie
6. 构造 Keycloak 授权 URL
7. 302 重定向到 Keycloak

#### 2.3.2 回调流程 (`GET /api/auth/callback`)

1. 校验 `state`
2. 校验 `code`
3. 校验 CSRF
4. 按当前 client 能力交换 token
5. 获取 `userinfo`
6. upsert `users`
7. 设置浏览器 `HttpOnly kc_access_token / kc_refresh_token / kc_id_token`
8. 可选设置 `kc_expires_at`
9. 清理临时 auth cookie
10. 302 重定向到 `returnTo`

#### 2.3.3 获取当前用户 (`GET /api/auth/me`)

1. 读取 `kc_access_token`
2. 调用 Keycloak `/userinfo`
3. 若 access token 失效，则读取 `kc_refresh_token`
4. 调用 Keycloak refresh 接口
5. refresh 成功后重写 `kc_* cookie`
6. 再次调用 `/userinfo`
7. 返回用户信息
8. refresh 失败则清空 `kc_* cookie` 并返回 `401`

#### 2.3.4 登出流程 (`POST /api/auth/logout`)

1. 读取 `kc_id_token`
2. 构造 Keycloak logout URL
3. 清理 `kc_* cookie`
4. 返回 `{ logoutUrl }`

#### 2.3.5 主动刷新 (`POST /api/auth/refresh`)

1. 读取 `kc_refresh_token`
2. 调用 Keycloak refresh 接口
3. 重写 `kc_* cookie`
4. 返回 `{ ok: true }`

### 2.4 `current_user` 依赖

- 从 `kc_access_token` 读取当前 access token
- 使用 Keycloak `/userinfo` 获取当前用户
- 必要时先 refresh 再 userinfo
- 把当前用户对象写入 `request.state.current_user`
- 供后续 user_id 校验和资源归属逻辑复用

### 2.5 Cookie 安全要求

- `kc_access_token / kc_refresh_token / kc_id_token` 必须是 `HttpOnly`
- `Secure` 在正式 HTTPS 环境中必须开启
- `SameSite` 必须显式配置
- 前端 JavaScript 不读取 token cookie

## 三、前端实施

### 3.1 认证入口

- 登录入口统一走 `/api/auth/login`
- 登录态初始化统一走 `/api/auth/me`
- 登出统一走 `/api/auth/logout`
- 前端不把 token 存入 `localStorage / sessionStorage`

### 3.2 路由保护

- `/workspace/**` 第一批纳入保护
- middleware 可以继续检查 cookie 是否存在
- 真正的用户鉴权仍以后端 `current_user` 为准

## 四、测试与验收

### 4.1 自动验证

```bash
make check
cd backend && uv run pytest tests/test_auth_routes.py tests/test_gateway_keycloak_tls.py -q
```

### 4.2 手工验证

1. 未登录访问 `/api/auth/me` 返回 `401`
2. 登录成功后浏览器收到 `HttpOnly kc_* cookie`
3. `/api/auth/me` 能返回当前用户
4. access token 失效后，`/api/auth/me` 能自动 refresh 并重写 cookie
5. refresh token 失效后，`/api/auth/me` 清空 cookie 并返回 `401`
6. `/api/auth/logout` 清理 cookie 并返回 Keycloak logout URL

## 五、与旧方案的差异

- 本文件已不再沿用早期服务端会话方案
- `ecc_agent` 的 token cookie 模型在 DeerFlow v1 中已被正式采纳
- 若未来要做多端会话管理、强制踢会话、会话审计，再重新评估是否引入服务端会话表
