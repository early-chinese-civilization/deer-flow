# DeerFlow用户管理阶段5-Skills业务化与版本化

## 1. 本阶段目标

- 将 skills 从纯运行时目录扩展为用户级业务资源
- 建立 `skills / skill_versions`
- 打通 user skills 的 OSS 存储与运行时投影

## 2. 前置依赖

- agents 业务化已完成
- chat 已能稳定绑定 agent

## 3. 分层策略

### 5A 业务化

- `skills` 管理 skill 主资源
- `skill_versions` 管理版本化内容
- `agent_skills` 管理 agent 到 skill 的资源绑定
- system skills 保持兼容仓库目录
- user skills 进入 PG 管理

### 5B 运行时

- user skills 同步到 OSS 顶级目录
- Gateway 在运行前按 chat 绑定的版本组装运行时 skills 目录
- chat 冻结 `skill_version_ids`

## 4. 资源关系

- agent 绑定的是 skill 资源
- chat 最终冻结的是 `skill_version_ids`
- `chat_skill_versions` 记录 chat 最终冻结后的 skill 版本集合，属于必须落库的冻结结果
- 这样 agent 后续继续编辑时，不会影响历史 chat

## 5. 冻结硬规则

- chat 创建或绑定 agent 时，Gateway 必须解析并冻结当时有效的 `skill_version_ids`
- 冻结结果必须写入 `agent_snapshot` 与 `chat_skill_versions`
- 历史 chat 不跟随后续 skill 发布新版本而漂移

## 6. 允许修改范围

- `backend/app/**`
- `skills/**`
- `backend/tests/**`
- `plan/**`

## 7. 边界与不做事项

- 本阶段不处理 Knowledge Base 检索
- 本阶段不做复杂的跨 skill 依赖管理

## 8. 风险与注意事项

- 若只做 PG 入库，不做版本冻结，历史 chat 的 skill 行为会漂移
- 若只做 OSS 存储，不保留 PG 版本关系，前端无法做稳定管理和回显

## 9. 验收动作

- user skills 可入库、可版本化
- user skills 可同步到 OSS
- 运行时可按 chat 绑定的版本稳定加载
- `chat_skill_versions` 已作为冻结结果稳定落库
