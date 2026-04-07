# DeerFlow用户管理阶段4-Agents业务化

## 1. 本阶段目标

- 将 agents 从全局文件目录迁到业务资源模型
- 引入 `agent_snapshot`
- 保留系统默认 agent 兼容

## 2. 前置依赖

- chat / workspace 闭环已建立
- 阶段 3 已能稳定创建用户级 chat

## 3. 主设计

- `agents` 成为用户级业务表
- 引入 `agent_skills / agent_knowledge_bases` 作为 agent 资源绑定表
- 系统默认 agent 继续兼容现有全局目录
- chat 绑定 agent 时写入 `agent_snapshot`
- 一个 chat 最多绑定一个 agent
- 不同 chat 可复用同一个 agent

## 4. 为什么需要 `agent_snapshot`

- agent 本身后续会持续编辑
- 已存在的 chat 需要保留绑定时看到的 agent 配置快照
- 这样可以避免“修改 agent 后，历史 chat 行为被无意改变”
- `agent_snapshot` 至少包含 agent 核心配置、解析后的 `skill_version_ids`、`knowledge_base_version_ids`

## 5. 冻结硬规则

- chat 创建或绑定 agent 时，Gateway 必须解析当时有效的 skill / Knowledge Base 绑定
- 冻结结果必须写入 `agent_snapshot`
- 冻结结果必须同步落入 `chat_skill_versions` 与 `chat_knowledge_base_versions`
- 历史 chat 不得跟随后续 agent 编辑漂移

## 6. 涉及字段

- `agents.owner_user_id`
- `agents.config_json`
- `agent_skills`
- `agent_knowledge_bases`
- `chats.agent_id`
- `chats.agent_snapshot`

## 7. 允许修改范围

- `backend/app/**`
- `frontend/src/**`
- `backend/tests/**`
- `plan/**`

## 8. 边界与不做事项

- 本阶段不处理 user skills 的运行时装载
- 本阶段不处理 KB 检索接入

## 9. 风险与注意事项

- 如果只记录 `agent_id` 而不记录 snapshot，历史 chat 的运行效果会漂移
- 若过早移除系统默认 agent 兼容层，会影响当前仓库级 agent 能力

## 10. 验收动作

- 用户可创建、编辑、查询自己的 agents
- chat 绑定 agent 后会写入 `agent_snapshot`
- `agent_snapshot` 已冻结 agent 核心配置、`skill_version_ids`、`knowledge_base_version_ids`
- 同一个 agent 可被多个 chat 绑定
