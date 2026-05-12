# 默认聊天不是默认 Agent

日期：2026-05-12

状态：终态收口版；本文替代上一轮 default Agent 设计。文件名沿用历史编号，不表示终态采用 default Agent。

## 结论

默认聊天不是 default Agent。

终态不创建隐藏 default Agent，不设计 `agent.kind=default/custom` 或 `agents.kind=default/custom`。

Thread 规则固定为：

```text
thread.agent_id = null    -> 默认聊天
thread.agent_id != null   -> 绑定自定义 Agent
```

默认聊天启用系统 Skill 由平台级 `config.yaml` 配置决定，不由用户级 Agent 配置决定。

## 为什么不建 default Agent

上一轮方案把普通聊天统一成“绑定默认 Agent 的聊天”。这是历史问题，终态不采用。

不建 default Agent 的原因：

1. 默认聊天是平台提供的基础聊天入口，不需要为每个用户创建隐藏 Agent。
2. 默认聊天系统 Skill 是平台全局策略，不是用户自己的 Agent 配置。
3. 如果默认聊天走 `agent_skills` / `skill_installation`，会把平台默认能力误建模成用户安装或用户绑定。
4. `agent.kind=default/custom` 会让 Agent 表承担两个不同产品概念：默认聊天和用户自定义 Agent。
5. `thread.agent_id = null` 已经能清楚表达默认聊天入口。

## 业务链路终态

Thread 关系：

```text
Thread
  agent_id nullable
```

规则：

1. 创建普通聊天 thread 时，`agent_id` 保持 `null`。
2. 创建自定义 Agent 聊天 thread 时，`agent_id` 指向当前用户拥有的 Agent。
3. `agent_id=null` 永远表示默认聊天，不需要回填默认 Agent。
4. `agent_id` 非空时必须校验 Agent 属于当前用户。
5. 默认聊天和自定义 Agent 使用不同的 Skill 配置来源，但最终进入同一类 runtime descriptor。

## 默认聊天 Skill 配置

默认聊天只使用平台级系统 Skill 配置：

```yaml
default_chat:
  system_skills:
    - skill_id: "00000000-0000-0000-0000-000000000000"
      version_number: 1
```

约束：

1. 这是平台全局配置，面向所有用户。
2. 只允许配置内部系统用户拥有的 Skill。
3. 至少必须引用存在的 `(skill_id, version_number)`；是否要求引用 `status="published"` 的系统 release 是平台策略。
4. 不提供用户级开关。
5. 不产生 `skill_installation`。
6. 不需要 `install_origin`。
7. 不需要 `skill_binding`、启用关系表或默认聊天专用绑定表。

默认聊天 runtime 链路：

```text
Thread(agent_id=null)
  -> default_chat.system_skills
  -> validate owner is internal system User
  -> skill_versions(skill_id, version_number)
  -> .deer-flow/skills/{skill_id}/{version_number}
  -> runtime descriptor
  -> prompt / sandbox / skill_load
```

## 自定义 Agent Skill 配置

自定义 Agent 继续使用业务链路：

```text
Thread(agent_id)
  -> Agent
  -> agent_skills
  -> skill_installations
  -> skill_versions(skill_id, version_number)
  -> .deer-flow/skills/{skill_id}/{version_number}
  -> runtime descriptor
  -> prompt / sandbox / skill_load
```

自定义 Agent 的 Skill 配置属于用户业务数据。默认聊天的系统 Skill 配置属于平台全局配置。二者不能混成一张默认 Agent 配置表。

`skill_releases` 语义保留，用于发现、install、update 可见性。默认聊天 runtime 已经由 config 拿到具体 `(skill_id, version_number)` 后不通过 release 找目录，release 不参与路径授权。

## 当前代码现状

当前代码已有部分基础：

1. `threads.agent_id` 已存在且可为空。
2. runtime request 可以通过 Agent 加载配置。
3. `runtime_agent.skills` 可以注入 prompt / sandbox / `skill_load`。

当前需要收口的问题：

1. 如果代码中把无 Agent run 当作空 runtime agent，需要改为默认聊天 config 解析。
2. 如果文档或迁移任务设计了 default Agent，需要删除。
3. 如果 Agent 表引入或计划引入 `kind=default/custom`，需要回退。
4. 如果默认聊天系统 Skill 通过 `skill_installation`、`install_origin` 或 `agent_skills` 物化，需要删除该设计。

## 前端影响

前端不是主轴，但需要跟随：

1. 普通聊天入口仍然存在，底层 `thread.agent_id=null`。
2. 普通聊天不跳转到默认 Agent 配置。
3. 自定义 Agent 聊天继续使用 Agent 配置。
4. 默认聊天系统 Skill 若展示，只展示平台配置结果，不提供用户级增删开关。

## 验收标准占位

后续测试应证明：

1. 新普通聊天 thread 的 `agent_id` 为 `null`。
2. 普通聊天 runtime 加载 `default_chat.system_skills` 配置的系统 Skill。
3. 普通聊天不会创建 default Agent。
4. 普通聊天不会创建 `skill_installation` 或 `agent_skills`。
5. 自定义 Agent 仍能独立配置 Skill。
6. `agent.kind=default/custom` 不进入终态 schema。
