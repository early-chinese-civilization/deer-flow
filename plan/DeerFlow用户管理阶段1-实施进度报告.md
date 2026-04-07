# DeerFlow 用户管理阶段1 - 实施进度报告

## 当前状态：本文件仅保留为阶段1历史记录说明

### 1. 口径变更说明

- 本文件早期记录基于旧服务端会话方案编写
- 当前 DeerFlow v1 认证正式口径已经切换为：
  - `Gateway + Keycloak + 浏览器 HttpOnly kc_* cookie`
  - `users` 保留
  - `auth_sessions` 不再作为正式目标
- 因此本文件不再作为阶段1实施真相

### 2. 当前应以哪些文档为准

- 总方案主文档：`plan/用户管理与资源模型接入方案.md`
- 执行总方案：`plan/DeerFlow用户管理执行方案.md`
- 阶段1正式文档：`plan/DeerFlow用户管理阶段1-认证与当前用户解析.md`
- 阶段1详细方案：`plan/DeerFlow用户管理阶段1-详细实施方案.md`

### 3. 历史内容中仍然可复用的部分

- 根目录 `.env` 单一配置源
- Keycloak 参数整理与代理头处理
- `users` 表及用户 upsert 思路
- `/api/auth/login / callback / me / logout / refresh` 的接口骨架
- `/workspace/**` 登录保护方向

### 4. 已过期、不可继续照着实施的内容

- 任何“DeerFlow 自己维护服务端会话真相”的旧设计
- 任何“本地 session 先于 Keycloak 成为有效性真相”的旧链路
- 任何与当前 `kc_*` HttpOnly token cookie 正式方案相冲突的旧约束

### 5. 当前正确的阶段1目标

- 采用 `ecc_agent` 式浏览器 HttpOnly token cookie 认证
- Keycloak 作为唯一登录态与失效真相
- `current_user` 以 `kc_access_token -> /userinfo`，失败后 `kc_refresh_token -> refresh -> /userinfo` 解析
- 仅保留 `users` 作为本地用户主映射

本文件后续仅作为历史背景说明保留，不再承担实施指导职责。
