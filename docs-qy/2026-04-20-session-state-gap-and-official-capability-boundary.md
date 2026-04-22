# DeerFlow 会话状态缺口与官方能力边界结论

日期：2026-04-20
状态：结论文档

## 1. 这份文档回答什么

这份文档专门回答这次讨论中的两个问题：

1. DeerFlow 当前“凭据过期后 401 没有被稳定捕获和正确处理”的真实问题到底是什么。
2. 这些状态和处理能力，Authlib / Keycloak / Better Auth 到底有没有原生提供；如果有，提供到哪一层；如果没有，为什么仍然需要 DeerFlow 或共享 SDK 自己定义契约。

这不是实现方案文档，也不是代码修改说明。

## 2. 先说结论

### 2.1 简明结论

- `Keycloak` 原生提供的是 IdP、SSO session 和标准 OIDC / logout 协议能力。
- `Authlib` 原生提供的是 OAuth / OIDC client 能力，包括授权跳转、code exchange、token refresh 等协议工具。
- `Better Auth` 原生提供的是更高一层的“应用级本地 session 框架”，包括 cookie session、session 续期、client hook、集成模式等。

因此：

- `ecc-west` 当前体验较好，不意味着 `Keycloak` 或 OIDC 标准天然把“401 后跳登录 / signed-out 页”全部处理好了。
- 更接近真实原因的是：`ecc-west` 受益于 Better Auth 自带的本地 session 生命周期和 client glue，再加上应用层补的 route guard / redirect glue。
- DeerFlow 当前问题不是“少用了一点 Keycloak 能力”，而是“当前自定义 auth 链路缺少稳定的应用会话层契约”。

### 2.2 对当前问题的直接判断

DeerFlow 当前更像是：

- 协议链路基本可用；
- 但会话状态没有被定义成消费方可稳定处理的协议；
- 导致 access token 过期、refresh 失败、显式 logout、未登录、上游不可用这些情况，最后都容易在产品层表现成“一个普通 401”。

这就是为什么用户感知会很差。

## 3. DeerFlow 当前真实问题

结合现有阶段文档，可以把 DeerFlow 当前问题拆成四层。

### 3.1 refresh 不是完全没有，而是链路不统一

`deerflow-auth-phase2-delta-matrix-and-code-audit.md` 已经确认：

- `/api/auth/me` 和 `/api/auth/refresh` 有 refresh 行为；
- 但普通业务依赖 `get_current_user()` 本身不会 refresh；
- 普通业务链路当前仍以 `kc_access_token -> /userinfo` 为主。

这意味着系统内部对“当前是否仍然算已登录”并没有统一答案：

- 某些入口会尝试恢复；
- 某些入口会直接 401；
- 前端收到的体验自然是不稳定的。

### 3.2 401 语义不够机器可读

当前真正缺的不是某一处 `redirect()`，而是稳定的会话失败协议。

消费方需要至少能区分：

- `not_authenticated`
- `session_expired`
- `logged_out`
- `auth_unavailable`

否则：

- 什么时候跳登录页
- 什么时候停在 signed-out 页
- 什么时候不要自动 refresh
- 什么时候要提示“认证服务不可用”

这些行为都只能靠散落的字符串判断和页面各自猜测。

### 3.3 DeerFlow 当前 auth core 还是“协议实现”，不是“会话框架”

阶段二代码审计已经说明：

- DeerFlow 当前有完整手写 `/api/auth/login|callback|me|refresh|logout`
- 前端登录态来源是 `/api/auth/me`
- middleware 主要看 `kc_access_token` / `kc_refresh_token`

这套实现更像是“项目级 OIDC 协议实现 + 若干前端补丁”，而不是像 Better Auth 那样有一层完整的应用 session runtime。

### 3.4 这不是 DeerFlow 单仓问题，而是共享契约问题

因为 ECC 已经明确：

- Python 服务长期要收敛到 `ecc-auth` 共享边界；
- DeerFlow 不应该再继续长出自己的长期私有 auth 语义；
- 但共享层也不应该直接硬编码某个项目的页面跳转 UX。

所以真正要补的是：

- 共享层定义稳定的 session failure contract；
- DeerFlow 消费这个 contract，把它映射成自己的登录页 / signed-out 页 / 提示交互。

## 4. 官方资料结论：Keycloak 提供到哪一层

### 4.1 Keycloak 确实提供 session / logout 标准能力

Keycloak 官方规格页明确列出了以下已支持能力：

- OpenID Connect Session Management
- RP-Initiated Logout
- Back-Channel Logout
- Front-Channel Logout

来源：

- [Keycloak specifications](https://www.keycloak.org/securing-apps/specifications)

这说明 Keycloak 不是“只会发 token，不会管 session”。

### 4.2 但 Keycloak 对 generic server-side client 提供的是协议能力，不是现成的应用会话模型

Keycloak Server Admin 文档对 generic client 的表述是：

- 对非 Keycloak adapter 的客户端，Keycloak 公开的是 OIDC 端点；
- 包括 `/auth`、`/token`、`/logout`、`/userinfo`、`/certs`、`backchannel-logout` 等；
- 当用户去 Keycloak logout endpoint 登出后，Keycloak 会向客户端发送 logout 请求，客户端需要失效自己的本地 session。

来源：

- [Keycloak Server Administration Guide](https://www.keycloak.org/docs/26.3.3/server_admin/)

这说明：

- Keycloak 负责的是协议和 SSO session；
- “你本地如何表达已登出、如何清 cookie、如何让前端进入 signed-out 状态”仍然是客户端应用自己的责任。

### 4.3 Keycloak 的高阶会话检测能力主要体现在 JS adapter，不会自动迁移到 DeerFlow 这种 generic client

Keycloak JavaScript adapter 官方文档明确提供了这些更高层能力：

- `login-required`
- `check-sso`
- Session Status iframe
- `updateToken()`
- `clearToken()`
- `onAuthLogout`
- `onTokenExpired`

来源：

- [Keycloak JavaScript adapter](https://www.keycloak.org/securing-apps/javascript-adapter)

但这点很关键：

- 这些能力属于 `keycloak-js` adapter；
- DeerFlow 当前不是在前端直接用这个 adapter；
- 因此不能把 JS adapter 的体验误认为 “Keycloak generic OIDC client 默认就会给”。

## 5. 官方资料结论：Authlib 提供到哪一层

### 5.1 Authlib 原生覆盖协议流程

Authlib 官方文档明确把自己的 Web Client 能力定义为：

- `authorize_redirect()`
- `authorize_access_token()`
- OIDC discovery / metadata
- token 获取
- token refresh
- RP-Initiated Logout 的 `logout_redirect()`

来源：

- [Authlib Client](https://docs.authlib.org/en/latest/oauth2/client/index.html)
- [Web OAuth Clients](https://docs.authlib.org/en/latest/client/frameworks.html)
- [Starlette OAuth Client](https://docs.authlib.org/en/stable/client/starlette.html)

### 5.2 Authlib 也支持自动 refresh，但这是 token 级能力，不是应用 session UX

Authlib 官方 `OAuth 2 Session` 文档明确写了：

- 如果 `OAuth2Session` 带有 `token_endpoint`，它可以在 token 过期时自动 refresh；
- 也支持手动 `refresh_token()`；
- 自动刷新后如何更新存储，需要应用提供 `update_token`。

来源：

- [OAuth 2 Session](https://docs.authlib.org/en/latest/client/oauth2.html)

这说明：

- Authlib 并不是完全没有“续签能力”；
- 但它解决的是 OAuth token 生命周期；
- 它不替应用定义“401 是 session_expired 还是 logged_out”、“refresh 失败后跳哪里”、“前端如何统一停在 signed-out 页面”。

### 5.3 Authlib 不原生提供 DeerFlow 当前最缺的那层能力

官方文档没有提供 DeerFlow 现在真正需要的这些东西：

- 统一的应用 session 状态枚举
- 任意业务 API 的 401 统一分类协议
- 自动登录页跳转策略
- signed-out 页面策略
- logout 后禁止自动恢复的统一状态机
- 前端和服务端共享的一致会话失败语义

因此，把“这件事交给 Authlib”本身就选错了层级。

## 6. 官方资料结论：Better Auth 提供到哪一层

### 6.1 Better Auth 原生就是应用级 session 框架

Better Auth 官方 Session Management 文档明确说明：

- 它管理传统 cookie-based session；
- 有 session table；
- 有 `expiresIn`、`updateAge`；
- 可配置 `disableSessionRefresh`；
- 可配置 `deferSessionRefresh`；
- 当需要 refresh 时可以通过 `needsRefresh` 和客户端自动 POST 完成续期。

来源：

- [Better Auth Session Management](https://better-auth.com/docs/concepts/session-management)

这和 Authlib 的层级明显不同。

### 6.2 Better Auth 还提供 client hook 和框架集成模式

官方文档提供：

- `useSession()`
- `getSession()`
- session revalidation 配置
- Next.js 集成方式
- `signOut()` 后在成功回调里决定前端跳转

来源：

- [Better Auth Basic Usage](https://better-auth.com/docs/basic-usage)
- [Better Auth Client](https://better-auth.com/docs/concepts/client)
- [Better Auth Next.js integration](https://better-auth.com/docs/integrations/next)

所以 `ecc-west` 当前的良好体验，更合理的解释是：

- Better Auth 给了“本地 session runtime”；
- `ecc-west` 再在应用层补了自己的 route guard 和 redirect glue。

### 6.3 但 Better Auth 也不是“所有 401 UX 全自动”

官方模式依然是：

- 应用自己决定未登录时跳哪个 `/sign-in`；
- 应用自己决定登出成功后 `router.push(...)` 去哪里；
- 业务 API 的 401 如何分类，仍然不是 Better Auth 自动替你定义。

这点同样重要，因为它说明：

- 就算以后要借鉴 Better Auth，也不等于 DeerFlow 能完全不定义自己的消费协议。

## 7. 这次问题为什么不能简单归因成“没用好框架”

因为真实边界是这样的：

- `Keycloak` 负责上游身份、SSO session、logout 标准协议；
- `Authlib` 负责协议客户端能力；
- `Better Auth` 负责本地应用 session runtime；
- DeerFlow 现在缺的是最后一层对接 glue 和稳定 contract。

所以这不是“某个成熟框架明明有，你却手写了”的简单问题。

更准确的说法是：

- DeerFlow 当前方案只把协议层建起来了；
- 但没有把“项目如何表达会话失败”收敛成一份稳定 contract；
- 这份 contract 既不是 Keycloak generic client 自动给的，也不是 Authlib 自动给的。

## 8. 对 DeerFlow 的直接影响

基于以上结论，DeerFlow 现在真正应该解决的是：

### 8.1 不要再把“普通 401”当成足够表达力的 auth 协议

至少要区分：

- 未登录
- 会话过期，需要重新登录
- 用户显式登出，必须停在 signed-out
- 上游认证服务故障，应提示重试而不是跳登录

### 8.2 不要把最终页面跳转硬写进共享层

共享层更适合输出：

- 状态
- 建议动作
- 可选 redirect target

DeerFlow 自己决定：

- 跳登录页
- 跳 signed-out 小页面
- 保留哪个 `return_to`
- 是否显示 toast / modal / 空态

### 8.3 需要一份共享 session failure contract

建议后续新增或补齐一份共享契约，至少回答：

- `session_expired`
- `logged_out`
- `not_authenticated`
- `auth_unavailable`

这些状态分别通过什么 body / header / action 暴露给消费方。

## 9. 推荐的后续文档动作

建议下一步在 ECC 共享层新增一份专门文档，而不是把所有结论继续散在 PRD 和 code audit 里：

建议文档名：

- `ecc-auth-session-failure-contract.md`

建议内容：

1. 状态枚举
2. body/header 契约
3. refresh 允许与禁止条件
4. logout marker / signed-out 语义
5. 503 与 401 的明确分界
6. 消费方职责 vs 共享层职责

## 10. 与现有文档的关系

这份文档是对以下材料的补充结论，不替代它们：

- [deerflow-auth-phase1-initial-conclusion.md](/Users/sayori/Desktop/work/deer-flow/docs-qy/deerflow-auth-phase1-initial-conclusion.md:1)
- [deerflow-auth-phase2-delta-matrix-and-code-audit.md](/Users/sayori/Desktop/work/deer-flow/docs-qy/deerflow-auth-phase2-delta-matrix-and-code-audit.md:1)
- [deerflow-auth-migration-prd.md](/Users/sayori/Desktop/work/deer-flow/docs-qy/deerflow-auth-migration-prd.md:1)
- `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth/ecc-auth-runtime-contract.md`
- `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth/ecc-west-better-auth-keycloak-integration.md`

## 11. 最终一句话

DeerFlow 当前遇到的不是“框架没选对”，而是“在 Keycloak + Authlib 这条以协议为中心的链路里，缺了应用会话层的稳定失败契约”；而 `ecc-west` 当前较好的体验，恰好说明 Better Auth 帮它补厚了这一层，但也没有厚到能替 DeerFlow 自动定义全部跨项目行为。
