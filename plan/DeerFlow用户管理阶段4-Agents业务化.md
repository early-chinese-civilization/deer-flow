# DeerFlow用户管理阶段4-Agents业务化

## 1. 本阶段目标

- 将 agents 从全局文件目录迁到业务资源模型
- 建立 agent 与 skills / Knowledge Base 的实时资源关联
- 保留系统默认 agent 兼容

## 2. 前置依赖

- chat / workspace 闭环已建立
- 阶段 3 已能稳定创建用户级 chat

## 3. 主设计

- `agents` 成为用户级业务表
- 引入 `agent_skills / agent_knowledge_bases` 作为 agent 资源绑定表
- 系统默认 agent 继续兼容现有全局目录
- chat 仅保存当前 `agent_id`
- 运行时每次执行都按当前 agent 配置和当前资源引用实时解析
- 一个 chat 最多绑定一个 agent
- 不同 chat 可复用同一个 agent

## 4. 实时解析原则

- agent 本身后续会持续编辑，历史 chat 接受随当前 agent 配置变化而变化
- chat 不再保留 agent 配置快照，也不再保存 skill / Knowledge Base 的历史副本
- 每次 run 都重新解析当前 agent、当前 skill 引用、当前 Knowledge Base 引用
- 若引用的 skill 或 Knowledge Base 已删除、路径缺失或暂不可用，则记录 warning 后忽略对应配置

## 5. 运行时容错规则

- chat 创建或绑定 agent 时仅写入当前 `agent_id`
- 运行时按当前绑定实时解析 skill / Knowledge Base 资源
- 缺失引用按“忽略配置并继续执行模型”处理，不升级为阻断错误
- 历史 chat 允许跟随后续 agent 编辑而变化，这是已接受的产品 tradeoff

## 6. 涉及字段

- `agents.user_id`
- `agents.config_json`
- `agent_skills`
- `agent_knowledge_bases`
- `chats.agent_id`

## 7. 允许修改范围

- `backend/app/**`
- `frontend/src/**`
- `backend/tests/**`
- `plan/**`

## 8. 边界与不做事项

- 本阶段不处理 user skills 的运行时装载细节
- 本阶段不处理 KB 检索接入细节

## 9. 风险与注意事项

- 历史 chat 会随 agent 当前配置变化而变化，这是当前方案已接受的 tradeoff
- 若运行时不做好缺失引用的软失败处理，会把资源缺失放大成整条调用失败
- 若过早移除系统默认 agent 兼容层，会影响当前仓库级 agent 能力

## 10. 验收动作

- 用户可创建、编辑、查询自己的 agents
- chat 绑定 agent 后可按当前 `agent_id` 运行
- agent 修改后，后续 run 使用最新 agent 配置
- skill / Knowledge Base 引用缺失时会忽略对应配置并继续执行模型
- 同一个 agent 可被多个 chat 绑定
