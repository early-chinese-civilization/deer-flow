# DeerFlow 鉴权阶段一初步结论

日期：2026-04-15

## 1. 这份结论的范围

本文档只基于现有规划文档与 `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth` 下的稳定文档做阶段一结论整理。

本阶段不下代码实现结论，不宣称运行时已经完成收敛，也不替代后续代码级核查。

## 2. 当前判断

`deer-flow` 不是“完全没有鉴权方向”，而是已经在文档层面选择了一条与 `ecc_auth` 明显接近的路线：

- `Gateway` 是 DeerFlow 的认证真相
- `Keycloak` 是唯一外部身份源与登录态真相
- 浏览器侧以 `HttpOnly kc_*` cookie 承载认证状态
- `users.external_auth_id` 应映射为 Keycloak `sub`
- 不再把 DeerFlow 自己的 `auth_sessions` 作为正式目标模型

这说明问题的核心不是“重新发明一套方案”，而是把现有 DeerFlow 文档方案与 `ecc_auth` 的共享契约正式收口。

## 3. 目标判断

从 `ecc_auth` 文档看，长期目标应是：

- 统一身份层放在 `Keycloak + OIDC + claims 契约`
- Python 服务应收敛到共享 `ecc-auth` 契约/SDK，而不是继续维持项目私有 OIDC 实现
- 统一发生在 `AuthIdentity + kc_* cookie + sub/claims`，而不是统一成一个新的内部 OAuth Provider
- DeerFlow 自身只保留业务边界逻辑：
  - 本地用户映射/投影
  - 资源归属校验
  - 业务专属路由

因此，方向上应把 `ecc-auth` 视为目标边界，而不是继续扩展 DeerFlow 自己手写的鉴权体系。

## 4. 阶段一正式结论

阶段一的目标不应定义为“现在直接替换成 `ecc-auth` SDK”，而应定义为：

1. 先澄清 DeerFlow 文档层面的现状
2. 先澄清 `ecc_auth` 定义的目标边界
3. 明确两者之间的契约差异
4. 明确 DeerFlow 当前认证对齐与授权保护面不是同一件事
5. 为后续代码级核查与迁移留出清晰入口

换句话说，阶段一是“对齐定义阶段”，不是“实现替换阶段”。

## 5. 当前已经明确的硬约束

- `Gateway` 是 DeerFlow 请求级认证判定与 `current_user` 解析权威
- `Keycloak` 是唯一外部身份与登录态权威
- 浏览器侧会话载体只能是 `HttpOnly kc_*` cookie
- DeerFlow 不应再引入并行 session 权威
- DeerFlow 不应把 `auth_sessions` 作为正式目标模型继续发展
- `external_auth_id` 必须等于 Keycloak `sub`
- 回调成功后的跳转语义应为 `origin + return_to`
- 上游鉴权服务 `5xx` 应返回 `503`，不应伪装成普通 `401`
- 长期共享目标更偏向本地 `JWKS` 验签优先，而不只是 `/userinfo` 优先
- 不应在 Keycloak 前面再包一层 DeerFlow 内部 OAuth Provider / auth service

## 6. 目前已识别的主要差距

### 6.1 文档方向已接近，但实现是否一致尚未验证

当前结论大多来自 DeerFlow 文档，而不是代码验证结果。

因此下面这句话目前只能算“高概率推断”，不能算事实：

> DeerFlow 现在仍保留了一套手写鉴权实现，并且它与 `ecc-auth` 共享契约尚未完全收敛。

### 6.2 认证对齐不等于授权完整

DeerFlow 现有文档已经明确提到：

- `auth`
- `threads`
- `thread_runs`

这几条主链相对更接近用户体系；

但 `runs`、`uploads`、`artifacts`、`suggestions`、`memory`、`skills`、`mcp`、`agents`、`channels` 等保护面并未全部完成用户化。

因此，后续即使 auth core 对齐了，也不能自动得出“整套系统已经安全对齐”的结论。

### 6.3 共享契约存在明确的潜在差异点

从文档看，至少要重点核对这些点：

- `current_user` 解析链路是否仍然以 `/userinfo -> refresh` 为主
- 是否已经满足 `ecc-auth` 倾向的本地 `JWKS` 验签优先
- cookie 命名、写入、清理、刷新回写是否完全符合 `kc_*` 契约
- 回调状态、`return_to`、`origin` 推导语义是否一致
- 上游 `5xx` 是否被正确保留为 `503`
- DeerFlow 是否仍保留了平行 session 语义或兼容逻辑

## 7. 阶段一产出物建议

为了让后续工作可执行，阶段一建议固定输出以下 artifact：

### 7.1 现状总结

仅基于 DeerFlow 文档，区分：

- documented fact
- unverified inference

### 7.2 目标总结

仅基于 `ecc_auth` 稳定文档，列出不可退让的目标契约。

### 7.3 契约差异矩阵

建议后续按以下列组织：

- current documented behavior
- target contract
- source
- confidence
- migration impact
- needs code inspection later

### 7.4 保护面清单

保护面清单应区分：

- userized
- non-userized
- unknown / not yet verified

### 7.5 开放问题列表

所有需要代码级核查的问题，都单独归档，不混在阶段一结论里冒充事实。

## 8. 目前建议的路线结论

当前更合理的路线是：

- 长期目标：收敛到 `ecc-auth` 共享契约/SDK
- 阶段一动作：先把边界、差异、保护面讲清楚
- 过渡期允许保留现有手写实现作为迁移控制带

但这个过渡期必须满足限制：

- 不新增长期手写 auth 表面
- 不新增 DeerFlow 自己的 session 抽象
- 不新增内部 OAuth wrapper
- 过渡实现只能服务于后续收敛，不应成为新的目标架构

## 9. 后续代码级核查时的重点

等允许代码级探索后，优先核查以下问题：

1. DeerFlow 当前 auth route 的真实运行时行为是否与文档一致
2. `current_user` 的真实解析逻辑是什么
3. 是否存在 DeerFlow 自己的并行 session 语义
4. 哪些接口已经接入用户化，哪些仍停留在 legacy/global 模式
5. 哪些 DeerFlow 业务副作用嵌在手写 auth 流程里，无法直接迁入共享 SDK

## 10. 参考文档

DeerFlow 侧：

- `plan/用户管理与资源模型接入方案.md`
- `plan/DeerFlow用户管理执行方案.md`
- `plan/DeerFlow用户管理阶段1-认证与当前用户解析.md`
- `docs/GATEWAY_USER_SYSTEM_COVERAGE_ANALYSIS.md`

ecc_auth 侧：

- `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth/keycloak-is-the-unified-identity-layer.md`
- `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth/ecc-auth-runtime-contract.md`
- `/Users/sayori/Desktop/work/ecc_auth/docwarden/stable/auth/do-not-wrap-keycloak-with-an-internal-oauth-provider.md`
