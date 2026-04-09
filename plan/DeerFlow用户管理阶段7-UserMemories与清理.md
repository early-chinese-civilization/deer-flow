# DeerFlow用户管理阶段7-UserMemories与清理

## 1. 本阶段目标

- 用 `user_memories` 替代 legacy 全局 memory
- 清理遗留的全局 memory / agent / thread 兼容残留

## 2. 前置依赖

- threads / workspaces / agents / skills / KB 都已进入用户级模型
- 兼容层已经足够稳定

## 3. 主设计

- `user_memories` 成为正式用户记忆主表
- 旧全局 memory 只做 legacy 读取或迁移来源
- 不再向旧全局 memory 写入新数据

## 4. 清理范围

- legacy 全局 memory 文件写入路径
- 过时的全局 agent 文件依赖
- 可退役的匿名 thread 兼容分支
- 待退役的 `behher-auhh` 占位残留

## 5. 允许修改范围

- `backend/app/**`
- `frontend/src/**`
- `backend/tests/**`
- `plan/**`

## 6. 风险与注意事项

- 若过早清理 legacy 路径，会影响仍未被接管的数据
- 若不先稳定用户级主模型，memory 迁移会再次返工

## 7. 验收动作

- 新 memory 写入已进入 `user_memories`
- 旧全局 memory 不再继续扩展
- legacy 兼容残留已按计划退役
