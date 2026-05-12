# 统一发布 Skill 模型

日期：2026-05-12

状态：终态收口版

## 结论

System Skills 和 Community Skills 合并为一种模型。

System Skill 不再是独立业务分支。它只是统一发布模型中由受保护内部系统用户拥有或发布的普通 Skill。

终态不为 System Skill 单独引入 publisher/principal 表，也不回到 `source_type="system"` 分支。

## 统一模型

终态只有一种平台内发布 Skill：

```text
owner User
  -> skill(id UUID)
    -> skill_versions(skill_id, version_number)
      -> skill_releases
```

社区安装和自定义 Agent 使用：

```text
skill
  -> skill_installations
  -> agent_skills
  -> runtime descriptor
```

默认聊天使用：

```text
default_chat.system_skills
  -> skill_versions(skill_id, version_number)
  -> runtime descriptor
```

System Skill 与 Community Skill 的差异是权限和展示语义：

```text
is_official = skill.owner_user.external_auth_id == "system:deerflow"
```

不是：

```text
source_type == "system"
directory starts with system/
AgentSkill.system_skill_version_id 被设置
default Agent 绑定了系统 Skill
```

这些都是当前代码待删除或历史问题。

## 内部系统用户

终态维护一个受保护的内部系统用户：

```text
users.external_auth_id = "system:deerflow"
```

这个用户不是普通可登录用户，而是平台内部 owner/operator identity。

系统用户的展示名、头像或运营资料可由用户资料/配置层提供，不进入 Skill runtime 核心 ER。

它承担：

1. 拥有官方/System Skill。
2. 发布官方/System Skill。
3. 对自己的 release auto-publish。
4. 作为后续社区发布审核、下架、封禁、恢复等操作身份之一。

判断系统身份必须使用稳定 identity，例如 `external_auth_id`。不要依赖数字主键。

## 为什么不加新 publisher 表

当前终态只需要一个受保护系统作者身份。复用 `users` 可以获得：

1. 已有 owner/publisher 外键。
2. 已有展示名和审计字段。
3. 最少迁移面。
4. 不需要 publisher/principal 抽象。
5. 不需要把 system/community 分支重新带回业务代码。

如果未来明确要支持 organization/team publisher、多系统 publisher、非用户主体发布等，再单独设计 publisher/principal 表。那不是本轮终态的必要复杂度。

## 不采用的方案

### `source_type="system"`

这个方案会重新制造 system/community 分支。

它会把特殊逻辑扩散到：

1. 查询。
2. 权限判断。
3. Agent binding。
4. runtime descriptor。
5. 前端 selection helper。
6. 测试 fixture。

终态拒绝它。

### `owner_type = "system" | "user"`

这个方案比 `source_type` 稍简单，但仍然把系统身份作为枚举分支散落在业务代码里。

终态拒绝它。

### 新建 `skill_publishers`

这个方案扩展性更强，但对当前“一个系统作者 + 普通用户作者”的需求过重。

终态暂不采用。

### default Agent 承载系统 Skill

上一轮方案把默认聊天建模为 default Agent，再通过 `skill_installation` 或 `agent_skills` 承载系统 Skill。

这是历史问题，终态拒绝。默认聊天由 `thread.agent_id = null` 表达，系统 Skill 由平台级 `default_chat.system_skills` 配置表达。

## 权限规则

终态权限规则：

1. 普通用户不能登录为内部系统用户。
2. 普通用户不能把 Skill owner/publisher 改成内部系统用户。
3. 普通用户不能修改内部系统用户拥有的 Skill。
4. 内部系统用户自己发布的 release 可以直接 `published`。
5. 普通用户发布社区 Skill 时，第一轮可以仍然 `published`，二期改为 `pending_review`。
6. 官方/System 只是权限和展示语义，不是 runtime 分支。
7. 默认聊天 config 只能引用内部系统用户拥有的 Skill 版本。

## Gateway 业务影响

Gateway 需要收口为统一业务流程：

1. list/discovery 查询同一种 Skill/Release 模型。
2. 官方 badge 由 owner identity 推导。
3. install/update/publish 使用同一套 release/version 语义。
4. `skill_releases` / release 语义保留；删除的是 public latest copy、`artifact_uri` / `oss_path` / `storage_uri` 作为事实来源、独立 `skill_version_id` 版本身份，以及 fork/download 等旧语义。
5. 发现、install、update 只选择 `status="published"` 的 release；runtime 已经拿到具体 `(skill_id, version_number)` 后不通过 release 找目录。
4. 自定义 Agent config 使用同一套 Skill selection 模型。
5. 默认聊天系统 Skill 不经过 install，也不经过自定义 Agent selection。
6. system-specific request fields 删除，并迁移调用方到统一终态字段。
7. 普通用户创建/发布时禁止冒充内部系统用户。

需要重点清理当前代码中的：

1. `AgentSkill.system_skill_definition_id`。
2. `AgentSkill.system_skill_version_id`。
3. `system_skill_definition_ids`。
4. `system_skill_version_ids`。
5. `binding_kind="system"`。
6. `source_kind="system"` 作为业务分支。
7. `install_origin="system_default"`。
8. frontend system-specific selection metadata。
9. default Agent / `agents.kind=default/custom` 相关设计。

## Agent 运行时影响

runtime 不应知道“system binding”这种模型。

默认聊天只需要拿到：

```text
default_chat.system_skills[]
  -> skill_id
  -> version_number
  -> .deer-flow/skills/{skill_id}/{version_number}
```

自定义 Agent 只需要拿到：

```text
agent_skills
  -> skill_installations
  -> skill_id + version_number
  -> .deer-flow/skills/{skill_id}/{version_number}
```

官方/System Skill 与社区 Skill 的内容加载方式一致；差异只在 Gateway 权限和默认聊天 config 校验。

## 前端影响

前端应跟随统一模型：

1. System 和 Community 共用列表项模型。
2. 官方 Skill 显示 badge。
3. 自定义 Agent Skill 选择器不再维护 system-specific id 字段。
4. install/update/publish 文案沿用统一语义。
5. 默认聊天不显示“默认 Agent Skill 配置”。
6. 默认聊天系统 Skill 若需要展示，只展示平台配置结果，不提供用户级开关。
