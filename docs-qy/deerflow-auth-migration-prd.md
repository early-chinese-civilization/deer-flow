# DeerFlow 鉴权迁移 PRD

日期：2026-04-15

## 1. 背景

DeerFlow 当前已经有一套可工作的 Keycloak 鉴权链路，但它仍是 DeerFlow 自己维护的手写实现；同时，ECC 体系已经明确了统一目标：Python 服务应收敛到 `ecc-auth` 共享契约/SDK，而不是继续生长项目私有 OIDC 实现。

当前问题不是“DeerFlow 完全没有鉴权”，而是：

- 已有方向与共享契约部分重合
- 但核心 auth 实现仍未收敛到 `ecc-auth`
- 授权保护面仍不完整
- 因此不能把“当前能登录”误判成“已经完成统一鉴权”

本 PRD 用于定义 DeerFlow 从当前状态迁移到共享鉴权边界的正式方案。

## 2. 目标

### 2.1 主目标

将 DeerFlow 的认证核心从项目内手写 Keycloak/OIDC 实现，迁移为以 `ecc-auth` 共享契约/SDK 为中心的统一方案，同时保留 DeerFlow 自己的业务授权与资源归属逻辑。

### 2.2 具体目标

- 让 `/api/auth/*` 核心能力收敛到 `ecc-auth` 共享边界
- 让 DeerFlow 的共享身份语义与 ECC 统一契约一致
- 让 DeerFlow 的前端登录态继续以 Gateway `/api/auth/me` 为唯一真相来源
- 在迁移 auth core 的同时，补齐当前高风险未统一保护面
- 让“认证对齐”和“授权完整”分别被验证，不互相冒充

## 3. 非目标

以下内容不属于本次迁移目标：

- 重构 DeerFlow 全部用户资源模型
- 一次性把所有全局系统接口都改成普通用户接口
- 为 DeerFlow 引入新的本地 session authority
- 引入 Keycloak 前置的内部 OAuth Provider / auth-service
- 在本次迁移中改变 DeerFlow 的产品交互形态
- 把前端迁回 Better Auth

## 4. 成功标准

迁移完成后，应满足以下标准：

- DeerFlow 不再以手写 `/api/auth/*` 作为长期 auth core
- 共享身份主语义与 `ecc-auth` 契约一致
- `external_auth_id = sub`
- `kc_*` cookie 契约与共享规范一致
- `/me` 与依赖注入的 access token 校验路径收敛到共享目标
- 显式登出语义不再被自动 refresh 恢复
- `artifacts` / `suggestions` / `runs` 等高风险接口被纳入明确保护边界
- 迁移后不存在 DeerFlow 自己的并行 auth/session authority

## 5. 现状摘要

基于当前代码审计，DeerFlow 现状如下：

- 已有完整 `/api/auth/login|callback|me|refresh|logout`
- 浏览器侧已使用 `kc_access_token` / `kc_refresh_token` / `kc_id_token` / `kc_expires_at`
- 前端登录态来源已经切换到 Gateway `/api/auth/me`
- 普通业务依赖 `get_current_user()` 当前是 `kc_access_token -> /userinfo -> upsert local user`
- 目前未发现本地 `JWKS` 验签路径
- 当前未实现 `kc_logout_marker`
- 当前 state 缺少 `origin`
- 当前 callback 语义未显式表达为 `origin + return_to`
- 当前高风险未统一保护面仍包括 `artifacts`、`suggestions`、`runs`

## 6. 目标架构

### 6.1 边界划分

#### 共享 auth core

以下能力由 `ecc-auth` 负责：

- login
- callback
- me
- refresh
- logout
- token 交换、刷新、基础校验
- `kc_*` cookie 契约
- 共享身份对象
- 当前用户解析的共享部分

#### DeerFlow 业务层

以下能力保留在 DeerFlow：

- 本地 `users` 投影/落库策略
- `Thread` / `Workspace` / `Agent` 资源归属
- `require_thread_access` 等 ownership service
- 业务专属接口
- 前端 UI 登录体验与路由保护

### 6.2 权威边界

- `Keycloak` 是唯一外部身份与登录态权威
- `Gateway` 是 DeerFlow 请求级 auth enforcement 与当前用户解析权威
- DeerFlow 本地 `users` 只是业务投影，不是第二身份源
- 不引入 DeerFlow 自己的并行 session authority

## 7. 核心迁移原则

- 先定边界，再动 auth core
- 先补高风险保护面，再宣布“统一完成”
- 共享 auth core 与 DeerFlow 业务授权必须解耦
- 迁移过程中允许短期兼容层，但兼容层不能变成新常态
- 所有契约差异都必须有明确处理阶段，不能悬空

## 8. 关键差异清单

本次迁移至少需要处理以下差异：

- 手写 `/api/auth/*` vs `ecc-auth` 托管核心路由
- `/userinfo` 优先 vs `JWKS` 优先
- state 缺少 `origin`
- callback 未显式按 `origin + return_to`
- 缺少 `kc_logout_marker`
- `display_name` / `username` fallback 不完整
- Keycloak HTTP 客户端缺少 `trust_env=False`
- 高风险接口保护面未统一

## 9. 方案概览

### 阶段 A：迁移前收口

目标：

- 固定共享 auth core 与 DeerFlow 业务层边界
- 固定每个 router 的保护面归类
- 确认每个契约差异的处理阶段

产出：

- 边界清单
- 接口保护面清单
- 差异处理优先级

### 阶段 B：高风险保护面补齐

目标：

- 优先把 `artifacts`
- `suggestions`
- `runs`

纳入明确归属策略。

原因：

如果这些接口仍未统一 ownership，就算 auth core 已迁移，也不能视为安全闭环。

产出：

- 高风险接口保护面改造
- 对应测试补齐

### 阶段 C：共享 auth core 迁移

目标：

- 将 DeerFlow 当前核心 auth 路由与共享 auth 能力对齐
- 迁移当前用户解析路径
- 替换或收缩手写 Keycloak/OIDC 代码

这一阶段需要明确：

- 哪些 handler 被共享 SDK 直接替代
- 哪些 handler 仅保留 DeerFlow 业务包装职责
- 本地用户 upsert 如何接在共享身份回调上

### 阶段 D：契约补齐

目标：

- 引入 `origin`
- 补齐 `origin + return_to`
- 引入 `kc_logout_marker`
- 调整 fallback 规则
- 显式加入 `trust_env=False`
- 完成共享契约缺口收敛

### 阶段 E：残留清理

目标：

- 删除不再需要的手写 auth 逻辑
- 清理 Better Auth 历史残留
- 更新 DeerFlow 自己的文档与设计说明

## 10. 模块级改造范围

### 10.1 需要重点改造的 backend 模块

- `backend/app/gateway/auth/routes.py`
- `backend/app/gateway/auth/keycloak.py`
- `backend/app/gateway/auth/web.py`
- `backend/app/gateway/auth/service.py`
- `backend/app/gateway/deps.py`
- `backend/app/gateway/routers/artifacts.py`
- `backend/app/gateway/routers/suggestions.py`
- `backend/app/gateway/routers/runs.py`

### 10.2 需要重点改造的 frontend 模块

- `frontend/src/core/auth/api.ts`
- `frontend/src/core/auth/context.tsx`
- `frontend/src/middleware.ts`
- `frontend/src/app/api/auth/[...all]/route.ts`

### 10.3 需要重点核对的业务服务

- `backend/app/gateway/services/ownership.py`
- `ThreadRepository` / `WorkspaceRepository` / 用户投影相关 repository

## 11. 详细实施项

### 11.1 Auth Core 替换设计

必须回答：

- `ecc-auth` 如何接管 `/api/auth/*`
- DeerFlow 是否保留轻包装层
- 共享身份对象如何接入本地用户同步
- `get_current_user()` 如何切换到新的解析能力

### 11.2 当前用户与本地用户投影

必须回答：

- 本地用户 upsert 的唯一主键是否继续固定为 `sub`
- 本地 `user.id` 如何继续服务业务 ownership，而不回流为身份真相
- fallback 规则如何与共享契约一致

### 11.3 保护面改造

必须回答：

- `artifacts` 的归属判断按什么粒度做
- `suggestions` 是否保留 thread 语义，还是降级为无状态建议
- `runs` 是否继续允许 stateless 复用既有 `thread_id`

### 11.4 Logout 行为

必须回答：

- 是否引入 `kc_logout_marker`
- 前端显式登出后，如何阻断自动恢复
- 何时重新允许显式登录

### 11.5 HTTP 客户端与运行时细节

必须回答：

- 何处设置 `trust_env=False`
- `KEYCLOAK_TLS_INSECURE` 未来如何覆盖 JWKS 拉取
- `JWKS` 优先后，错误映射是否仍保持稳定

## 12. 验证计划

### 12.1 单元验证

- `external_auth_id = sub`
- `display_name` / `username` fallback
- state 编码/解码
- `origin + return_to`
- cookie 写入/清理
- `kc_logout_marker`
- `503` 与 `401` 错误映射

### 12.2 集成验证

- login / callback / me / refresh / logout 闭环
- proxy header 场景
- TLS 配置场景
- refresh 失败场景
- logout 后禁止自动恢复
- `JWKS` 验签路径

### 12.3 端到端验证

- 浏览器登录
- workspace 进入保护
- 登出后保持 signed-out
- 高风险接口的 ownership 行为

### 12.4 保护面验证

- `artifacts`
- `suggestions`
- `runs`

都必须有明确的授权行为测试，不允许只验证 `/api/auth/*`

## 13. 回滚策略

迁移需要保留阶段性回滚能力：

- auth core 替换前保留兼容入口
- 高风险接口保护面变更要能独立回滚
- shared auth core 接入若阻断登录主链，应能临时回退到旧实现

但回滚只作为短期保障，不应长期维持双实现。

## 14. 风险

### 14.1 结构风险

- DeerFlow 业务副作用可能混在当前手写 auth 路径中
- `userinfo` -> `JWKS` 切换可能影响既有错误语义与性能特征

### 14.2 安全风险

- auth core 对齐后，若保护面未补齐，会出现“看似统一，实则可绕过”的状态
- `runs` / `artifacts` / `suggestions` 若处理不当，仍可能绕开 ownership

### 14.3 迁移风险

- 前端当前依赖 `/api/auth/me` 的恢复逻辑，若后端行为变化不兼容，会直接影响 workspace 入口体验

## 15. 里程碑建议

### 里程碑 1

完成边界定稿与保护面分类

### 里程碑 2

完成 `artifacts` / `suggestions` / `runs` 保护面方案与改造

### 里程碑 3

完成 `ecc-auth` 接入与 hand-written auth core 替换

### 里程碑 4

完成契约缺口补齐与前端显式登出行为稳定

### 里程碑 5

完成残留代码与文档清理

## 16. 参考文档

- [阶段一初步结论](/Users/sayori/Desktop/work/deer-flow/docs-qy/deerflow-auth-phase1-initial-conclusion.md:1)
- [阶段二差异矩阵与代码级核对](/Users/sayori/Desktop/work/deer-flow/docs-qy/deerflow-auth-phase2-delta-matrix-and-code-audit.md:1)
- [实施前差异闭环清单](/Users/sayori/Desktop/work/deer-flow/docs-qy/deerflow-auth-preimplementation-closure-checklist.md:1)
- `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth/ecc-auth-runtime-contract.md`
- `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth/keycloak-is-the-unified-identity-layer.md`
- `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth/do-not-wrap-keycloak-with-an-internal-oauth-provider.md`

