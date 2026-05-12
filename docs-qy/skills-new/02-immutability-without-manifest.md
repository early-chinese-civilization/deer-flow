# 不依赖 Manifest JSON 的不可变性

日期：2026-05-12

状态：终态收口版

## 结论

`feature/skill-version-new` 的终态不采用 manifest JSON 作为 Skill 版本不可变性的核心模型。

不可变性应由两层共同保证：

1. 表结构设计：业务对象之间只引用明确版本 `(skill_id, version_number)`，不引用 latest、name-only、`skill_version_id` 或可变目录。
2. 目录结构映射：每个内容版本落到确定的不可变版本目录 `.deer-flow/skills/{skill_id}/{version_number}/`，后续更新只能创建新版本目录。

## 为什么这是核心变更

当前代码和旧设计把 Runtime Manifest 当成 run-level lock file，用 JSON 记录一次 run 实际解析到哪些 SkillVersion、artifact、hash、virtual path。

新终态不沿用这个核心思路。

不可变性应该是业务模型和存储模型自然保证的结果，而不是靠额外生成一份 JSON 快照来补缺。若表结构仍允许 name-only/latest/可变目录，manifest JSON 只是在运行前补了一层复杂度；若表结构和目录映射已经正确，manifest JSON 就不应该成为核心事实来源。

## 目标模型

终态要让下面这些关系直接可查、可约束、可迁移：

1. 哪个 `skill.id` 稳定存在。
2. 哪个 `(skill_id, version_number)` 内容版本存在。
3. 哪个 `skill_releases(skill_id, version_number, status)` 表达发布、公开、审核可见性。
4. 某个用户可用的是哪个 `skill`，当前选择哪个 `version_number`。
5. 某个发布事件发布的是哪个 `(skill_id, version_number)`。
6. 某个自定义 Agent 绑定的是哪个用户可用 Skill。
7. 默认聊天启用哪些内部系统用户拥有的 `(skill_id, version_number)`。
8. 某次 run 根据 thread 类型解析到哪个具体版本目录。

这些关系优先用表字段、外键、唯一约束、状态字段、平台配置校验和确定性目录映射表达。

`skill_releases` 没有被删除。`skill_versions` 表示不可变内容版本；`skill_releases` 表示某个 `(skill_id, version_number)` 的发布、公开、审核可见性。发现、install、update 只选择 `status="published"` 的 release。审核状态属于 release，不属于 `skill_version`，也不改变 runtime 目录解析。

## 目录映射原则

目录路径应从不可变业务身份派生，而不是从可变名字或 latest 目录派生。

目标原则：

1. 同一个 `(skill_id, version_number)` 的目录创建后不原地覆盖。
2. 新内容生成同一 `skill_id` 下新的 `version_number` 和新目录。
3. 用户安装、更新、自定义 Agent 绑定只切换数据库引用，不复制或覆盖旧版本内容。
4. 默认聊天只读取平台 config 指定的版本目录。
5. 运行时读取的路径能从数据库关系或平台 config 确定性推导。
6. 目录不使用 name、latest、public、custom、user_id、author_id 或独立 `skill_version_id` 作为定位依据。

终态目录命名已经收口为：

```text
.deer-flow/skills/{skill_id}/{version_number}/
```

## Runtime 生效原则

Runtime 不能把 manifest JSON 当作授权和不可变性的核心来源。

默认聊天链路是：

```text
Thread(agent_id=null)
  -> default_chat.system_skills
  -> skill_versions(skill_id, version_number)
  -> .deer-flow/skills/{skill_id}/{version_number}
  -> runtime descriptor
```

自定义 Agent 链路是：

```text
Thread(agent_id)
  -> Agent
  -> agent_skills
  -> skill_installations
  -> skill_versions(skill_id, version_number)
  -> .deer-flow/skills/{skill_id}/{version_number}
  -> runtime descriptor
```

若还需要 JSON 类输出，它只能承担这些非核心职责：

1. 审计输出。
2. 调试快照。
3. 日志关联。

JSON 不应该决定：

1. 哪个版本是权威版本。
2. 目录是否不可变。
3. 默认聊天是否启用了某个系统 Skill。
4. 自定义 Agent 是否绑定了某个 Skill。
5. 更新是否影响后续 run。
6. release 是否可被发现、安装或更新；但 runtime 已经拿到具体 `(skill_id, version_number)` 后不通过 release 找目录，release 不参与路径授权。

## 对后续任务的影响

后续 task 需要重新检查和拆分：

1. `runtime_manifests` 表从核心业务模型中移除；如审计调试确有需要，另行设计非核心记录。
2. manifest JSON 生成代码删除、降级为非核心审计，或迁移到新的审计记录设计。
3. prompt、sandbox、`skill_load` 当前是否消费 manifest JSON；如果是，需要改为从平台 config / 表关系和目录映射解析。
4. `skill_version` 的复合键目录映射如何迁移、校验和回滚。
5. 自定义 Agent binding、install update、publish update 是否只切换数据库引用，不改写旧目录。
6. publish 是否先确保或创建 `skill_versions` 和派生目录，再创建或更新 `skill_releases`。
7. 默认聊天 config 校验是否阻止非系统 owner Skill 进入默认聊天。
8. 测试要证明旧版本目录不会被覆盖，新版本创建新目录，未更新用户仍指向旧版本。

## 记录要求

这条变更是核心设计变更，后续讨论不能只记结论。

每次补充需求时，都要同步覆盖：

1. 表结构如何表达。
2. 目录结构如何映射。
3. API 如何创建、切换或读取这些关系。
4. 默认聊天 config 如何校验和进入 runtime。
5. 自定义 Agent 绑定如何落到具体版本。
6. Runtime 如何解析版本目录。
7. prompt、sandbox、`skill_load` 是否受影响。
8. 旧 manifest JSON、name-only、public/custom/user 目录读取如何删除和迁移清理。
9. 验收测试如何证明不可变性。
