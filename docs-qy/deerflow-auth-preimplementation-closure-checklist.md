# DeerFlow 鉴权实施前差异闭环清单

日期：2026-04-15

## 1. 目的

这份清单用于把 DeerFlow 当前鉴权实现推进到真正可实施迁移的状态。

它不直接定义代码方案细节，而是回答四个实施前必须明确的问题：

1. 哪些核心 auth 能力应该交给 `ecc-auth`
2. 哪些能力必须保留在 DeerFlow 自己的业务层
3. 哪些未完成保护面的接口必须纳入统一 ownership 体系
4. 迁移顺序应该如何安排，才能避免“auth 对齐了，但系统仍不安全”这种假完成

## 2. 输入依据

本清单基于以下两份前置文档：

- [阶段一初步结论](/Users/sayori/Desktop/work/deer-flow/docs-qy/deerflow-auth-phase1-initial-conclusion.md:1)
- [阶段二差异矩阵与代码级核对](/Users/sayori/Desktop/work/deer-flow/docs-qy/deerflow-auth-phase2-delta-matrix-and-code-audit.md:1)

## 3. 需要被 ecc-auth 接管的核心能力

以下能力应被视为共享 auth core，原则上不再继续在 DeerFlow 内扩展手写实现：

- `/api/auth/login`
- `/api/auth/callback`
- `/api/auth/me`
- `/api/auth/refresh`
- `/api/auth/logout`
- 登录状态 state 编码与校验
- Keycloak token exchange / refresh / userinfo / logout URL 交互
- `kc_*` cookie 写入、清理、刷新回写
- `current_user` / 当前身份解析的共享部分
- 共享身份对象与本地用户映射入参

实施前必须先明确：

- DeerFlow 现有哪些实现会被 `ecc-auth` 完整替代
- 哪些逻辑只是“看起来在 auth 目录里”，但本质仍属于 DeerFlow 业务层，不能直接删除
- DeerFlow 是否接受把 `/api/auth/*` 的核心路由边界正式交给共享 SDK

### 闭环条件

- 能列出将被 `ecc-auth` 接管的文件/模块范围
- 能列出不会被 `ecc-auth` 接管、而必须留在 DeerFlow 的逻辑清单
- 不再把 DeerFlow 当前手写 `/api/auth/*` 视为长期目标架构

## 4. 必须保留在 DeerFlow 的业务边界

以下内容不应混入共享 auth core，而应明确保留在 DeerFlow 应用层：

- 本地 `users` 表的业务落库策略
- `Thread` / `Workspace` / `Agent` 等资源的 ownership 规则
- `require_thread_access` 这类业务授权判断
- 业务专属路由
- 前端自己的应用登录态展示、导航、页面重定向体验

需要特别明确：

- 本地用户同步只是 projection / mapping，不是第二身份源
- DeerFlow 本地 `user.id` 只是业务主键，不应反向成为共享身份真相
- 授权逻辑不应继续寄生在手写 auth route 中，应该回到业务 service / ownership 层

### 闭环条件

- 每一类 DeerFlow-only 逻辑都能找到稳定归属层
- 不再把业务授权逻辑藏在共享 auth core 替换范围里
- 本地用户投影与共享身份源的边界清楚

## 5. 共享契约缺口清单

在真正切换到 `ecc-auth` 之前，以下缺口必须逐项确认处理路径：

### 5.1 高优先级缺口

- 当前 access token 校验是 `/userinfo` 优先，不是 `JWKS` 本地验签优先
- 当前 state 不包含 `origin`
- 当前 callback 语义不是显式 `origin + return_to`
- 当前未实现 `kc_logout_marker`
- 当前 `display_name` / `username` fallback 未完全符合共享契约
- 当前 Keycloak HTTP 客户端未显式 `trust_env=False`

### 5.2 中优先级缺口

- `KEYCLOAK_TLS_INSECURE` 目前只覆盖现有 HTTP 调用，未来若引入 JWKS 拉取还需补齐覆盖范围
- 前端仍有 Better Auth 依赖与文档残留
- 现有文档对 uploads 等保护面描述已过时，需要同步更新

### 闭环条件

- 每一项缺口都能明确归类为：
  - 迁移前先补
  - 迁移时一起补
  - 迁移后跟进
- 不允许存在“知道不符合契约，但先忽略”的无主项

## 6. 授权保护面补齐清单

当前最需要纳入统一 ownership 的接口面不是 auth core 本身，而是这些仍未统一保护的区域：

- `artifacts`
- `suggestions`
- `runs`（stateless）

其余仍未接入 `current_user` 的全局接口需要分层判断：

- 明确属于公共只读接口，可保留非用户化：
  - `models`
- 明确属于全局系统管理接口，未来可能需要后台/管理员边界，而不是简单用户边界：
  - `channels`
  - `mcp`
  - `memory`
  - `skills`
  - `agents`
  - `assistants_compat`

实施前必须先决定：

- 哪些接口要纳入普通用户 ownership
- 哪些接口应保留公共只读
- 哪些接口未来需要单独的 admin/operator 边界

### 闭环条件

- 所有 `/api/*` 路由都能归入以下三类之一：
  - 用户级 ownership 接口
  - 公共只读接口
  - 系统管理接口
- `artifacts` / `suggestions` / `runs` 的归属策略被明确定义

## 7. 迁移顺序建议

建议按下面顺序推进，而不是一上来直接替换所有 auth 代码。

### 第一步：定边界

- 确认 shared auth core 与 DeerFlow-only 业务层边界
- 确认契约缺口优先级
- 确认每个 router 的保护面归类

### 第二步：先补高风险保护面

- 优先处理 `artifacts`
- 优先处理 `suggestions`
- 评估 `runs` 是继续允许 stateless 复用 `thread_id`，还是必须绑定 ownership

原因：

如果这些接口还游离在统一 ownership 之外，auth core 替换完成也无法构成有效安全闭环。

### 第三步：收敛共享 auth 契约

- 迁移 `/api/auth/*` 核心能力到 `ecc-auth`
- 把 `userinfo` 优先路径迁到共享目标要求的 `JWKS` 优先
- 补齐 `origin`、`kc_logout_marker`、fallback 规则、`trust_env=False`

### 第四步：清理残留

- 删除不再需要的手写 auth 逻辑
- 清理 Better Auth 残留依赖与文档表述
- 更新 DeerFlow 自己的 auth 设计文档

## 8. 实施前必须回答的具体问题

进入实现前，至少要把下面问题逐一答清楚：

1. DeerFlow 当前 `backend/app/gateway/auth/routes.py` 中，哪些 handler 最终会完全删除，哪些只会变成业务包装层？
2. 当前 `deps.get_current_user()` 将如何迁移到共享解析能力？
3. 本地 `User` upsert 将挂在哪个共享回调或适配层上？
4. `artifacts` 应该按 thread ownership 保护，还是要引入 workspace / resource 级保护？
5. `suggestions` 是否必须绑定 thread ownership，还是允许脱离 thread_id 做纯消息级建议？
6. `runs` 是否还允许传任意 `thread_id` 复用既有线程？如果允许，ownership 规则是什么？
7. `kc_logout_marker` 引入后，前端 logout / signed-out 状态机要不要同步升级？
8. `JWKS` 验签落地后，哪些当前依赖 `/userinfo` 的路径会改变错误语义或性能特征？

## 9. 实施前验收口径

只有当下面条件都满足时，才算可以正式进入迁移实现：

- 共享 auth core 与 DeerFlow-only 业务边界已定稿
- 契约缺口已经分配优先级与处理阶段
- 所有 `/api/*` 路由完成保护面分类
- `artifacts` / `suggestions` / `runs` 的归属策略已明确
- `userinfo` 到 `JWKS` 的迁移影响已经被识别
- 本地用户投影与共享身份层的衔接方案已明确
- 不再存在“先改了再看”的关键鉴权分歧点

## 10. 推荐的下一份文档

在此基础上，建议下一份直接产出：

`deerflow-auth-migration-prd.md`

至少包含：

- 迁移目标
- 非目标
- 模块边界
- 分阶段实施项
- 保护面改造计划
- 验证计划
- 回滚策略

