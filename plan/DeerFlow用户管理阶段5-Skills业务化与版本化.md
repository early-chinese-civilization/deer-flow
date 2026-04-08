# DeerFlow用户管理阶段5-Skills业务化与实时同步

## 1. 本阶段目标

- 将 skills 从纯运行时目录扩展为用户级业务资源
- 建立 `skills`
- 打通 user skills 的 OSS 存储与运行时投影

## 2. 前置依赖

- agents 业务化已完成
- chat 已能稳定绑定 agent

## 3. 分层策略

### 5A 业务化

- `skills` 管理 skill 主资源
- `agent_skills` 管理 agent 到 skill 的资源绑定
- system skills 保持兼容仓库目录
- user skills 进入 PG 管理

### 5B 运行时

- user skills 同步到 OSS 顶级目录
- Gateway 在运行前按 agent 当前绑定实时组装运行时 skills 目录
- skill 内容更新后，后续 run 直接使用最新内容

## 4. 资源关系

- agent 绑定的是 skill 资源
- chat 不再保存 skill 的历史副本
- 运行时每次都按 agent 当前绑定实时解析 skill
- 历史 chat 会跟随 skill 当前内容变化而变化，这是已接受的 tradeoff

## 5. 运行时容错规则

- chat 创建或绑定 agent 时不再保存 skill 的历史副本
- 运行时缺失 skill 路径、OSS 尚未同步完成或 skill 已被删除时，跳过对应 skill
- 缺失单个 skill 不阻断整次模型调用

## 6. 允许修改范围

- `backend/app/**`
- `skills/**`
- `backend/tests/**`
- `plan/**`

## 7. 边界与不做事项

- 本阶段不处理 Knowledge Base 检索
- 本阶段不做复杂的跨 skill 依赖管理

## 8. 风险与注意事项

- 历史 chat 会随 skill 当前内容变化而变化，这是当前方案已接受的 tradeoff
- 若只做 OSS 存储，不保留 PG 主资源关系，前端无法做稳定管理和回显
- 若缺失 skill 不做软失败处理，会直接扩大运行时报错面

## 9. 验收动作

- user skills 可入库
- user skills 可同步到 OSS
- 运行时按 agent 当前绑定实时加载最新 skill 内容
- skill 路径缺失或资源被删除时，会忽略对应 skill 并继续执行模型
