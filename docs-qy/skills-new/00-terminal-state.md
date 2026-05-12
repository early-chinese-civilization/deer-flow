# Skill Version 新模式终态

日期：2026-05-12

状态：终态收口版，用于后续 task 拆分；当前仍处于设计捕获阶段，未进入实现。

## 文档定位

本文是 `feature/skill-version-new` 的新终态总览。

旧 `feature/skill-version` 方案、当前代码和旧文档只用于判断现状、迁移成本和清理边界；目标口径以 `docs-qy/skills-new` 为准。

## 目标用户语义

普通用户不需要理解目录层级、manifest、artifact、fork claim、默认 Agent 等工程对象。

用户侧稳定语义是：

1. 我能从平台发现别人发布的 Skill。
2. 我能把社区 Skill 安装到自己的可用范围。
3. 我能把可用 Skill 配置到自定义 Agent。
4. 我能上传和维护自己的 Skill。
5. 我能把自己的 Skill 版本发布给别人安装。
6. 作者发布新版不会静默改变安装者正在使用的版本。
7. 安装者可以看到更新，并显式更新。
8. 默认聊天可以使用平台预置的系统 Skill，但这不是用户安装，也不是默认 Agent 配置。

用户侧不再出现：

1. fork Skill。
2. 下载可编辑 Skill 包。
3. fork claim。
4. claim sidecar。
5. 隐藏 default Agent。
6. 用户级默认系统 Skill 开关。

## 已收口的终态决策

### 1. Skill 身份

`skill.id` 是 UUID，表达稳定 Skill 身份。

`skill` 表示“同一个 owner 下的同一个 Skill”。同名 Skill 冲突由 DB 中的 owner/identity 关系解决，不由目录层级、public/custom 路径或 name-only 扫描解决。

系统 Skill 和社区 Skill 使用同一套 `skill` 模型。系统 Skill 只是内部系统用户拥有的普通 Skill。

### 2. 版本身份

`skill_version` 不能独立于 `skill` 存在。

版本身份是复合键：

```text
(skill_id, version_number)
```

`version_number` 是同一 `skill` 下递增的不可变平台版本号。它不是 `SKILL.md` 包 metadata 的版本号，也不是独立全局 `skill_version_id`。

所有引用具体版本的业务关系必须同时携带：

```text
skill_id
version_number
```

### 3. OSS 内容目录

`.deer-flow/skills` 只保存不可变 Skill 版本内容。

终态目录结构是：

```text
.deer-flow/
  skills/
    {skill_id}/
      {version_number}/
        SKILL.md
        ...
```

目录不使用：

```text
{skill_version_id}
public/
custom/
user/
name-only
```

`content_hash` 用于同一 Skill 下的内容去重，`file_manifest_hash` 用于完整性校验。它们都不是物理目录主键。

表内不保存 `oss_path` / `storage_uri`。任何 runtime、sandbox、`skill_load` 或审计快照需要内容位置时，都必须从已解析的 `(skill_id, version_number)` 派生 `.deer-flow/skills/{skill_id}/{version_number}/`。

命名收口说明：旧口径 `skill_users` / `skill_agent` 名字不清晰，终态采用 `skill_installations` / `agent_skills`；旧字段 `skill_user_id` 终态采用 `skill_installation_id`。代码即文档，旧名只能出现在改名说明、历史问题或待删除语境。

### 4. Install-only

删除 fork 语义和下载相关产品语义，只留下平台内 install。

Install 是社区/用户 Skill 的平台内状态，不是文件下载。安装记录表达用户把某个发布 Skill 加入自己的可用范围，并选择当前使用的具体平台版本。

创建自己的 Skill 走上传/创建流程。未来如果需要“基于某个 Skill 创建自己的新 Skill”的体验，也应作为创建体验处理，不恢复 fork 业务对象。

### 5. 默认聊天不是 default Agent

默认聊天不是 Agent，不创建隐藏 default Agent，也不设计：

```text
agent.kind = "default" | "custom"
agents.kind = "default" | "custom"
```

终态 Thread 规则：

```text
thread.agent_id = null    -> 默认聊天
thread.agent_id != null   -> 绑定自定义 Agent
```

自定义 Agent 是用户显式创建和选择的 Agent。默认聊天不通过 Agent、`agent_skills` 或 `skill_installation` 来配置系统 Skill。

### 6. 默认聊天系统 Skill 由平台配置决定

默认聊天启用系统 Skill 由平台级 `config.yaml` 决定：

```yaml
default_chat:
  system_skills:
    - skill_id: "00000000-0000-0000-0000-000000000000"
      version_number: 1
```

该 config 是平台全局配置，面向所有用户。

约束：

1. 只允许配置内部系统用户拥有的 Skill。
2. 每一项必须指向存在的 `(skill_id, version_number)`。
3. 不提供用户级开关。
4. 不产生 `skill_installation`。
5. 不需要 `install_origin`。
6. 不需要 `skill_binding`、启用关系表或默认聊天专用绑定表。

### 7. 自定义 Agent 仍走业务链路

自定义 Agent 的 Skill 仍通过业务链路进入 runtime：

```text
Thread(agent_id)
  -> Agent
  -> agent_skills
  -> skill_installations
  -> skill_versions(skill_id, version_number)
  -> .deer-flow/skills/{skill_id}/{version_number}
```

这条链路适用于用户显式安装的社区 Skill、用户自己拥有的 Skill，以及将来允许配置到自定义 Agent 的系统 Skill。系统来源不需要 runtime 分支。

### 8. 不可变性由 DB 关系和目录映射保证

终态不以 Runtime Manifest JSON 作为 Skill 版本不可变性的核心模型。

不可变性由两层保证：

1. DB 表结构只引用明确 `(skill_id, version_number)`，不引用 latest、name-only 或可变目录。
2. OSS 目录中每个 `(skill_id, version_number)` 对应一个不可原地覆盖的内容目录。

Runtime Manifest JSON 如果保留，只能是非核心审计或调试记录，不能决定哪个版本是事实来源，也不能作为 Agent 或默认聊天是否授权加载 Skill 的依据。

### 9. 社区发布审核是二期占位

第一轮不实现社区发布审核，但模型不能把 publish 固定为“立即公开”。

`skill_releases` / release 语义保留。删除的是 public latest copy、`artifact_uri` / `oss_path` / `storage_uri` 作为事实来源、独立 `skill_version_id` 版本身份，以及 fork/download 等旧语义，不是 release。

`skill_versions` 表示不可变内容版本；`skill_releases` 表示某个 `(skill_id, version_number)` 的发布、公开、审核可见性。只有 `status="published"` 的 release 可被社区发现、安装和作为更新目标。

publish 流程必须先确保或创建 `skill_version(skill_id, version_number)` 和 `.deer-flow/skills/{skill_id}/{version_number}/` 内容目录，再创建或更新 `skill_releases(skill_id, version_number, status)`。内部系统用户发布可以 auto-published；普通社区作者第一轮可以 `published`，二期再改为 `pending_review`。审核状态属于 release，不属于 `skill_version`，也不改变 runtime 目录解析。

默认聊天 config 是否必须引用 `published` 系统 release 可以作为策略，但至少必须引用系统用户拥有且存在的版本。

## 终态对象职责

### User

表示真实用户和受保护的内部系统用户。

内部系统用户是平台 owner/operator identity，不是普通登录用户。它用于拥有和发布官方/System Skill，也可作为后续审核、下架、封禁、恢复等运营动作的执行身份。

内部系统用户使用稳定 identity 查找：

```text
users.external_auth_id = "system:deerflow"
```

不要依赖自增数字 ID 判断系统身份。

### skill

表示稳定 Skill 身份。

终态要求：

1. `skill.id` 是 UUID。
2. `skill.owner_user_id` 指向 owner。
3. 同一 owner 下 `skill.name` 唯一。
4. 系统 Skill 只是 owner 为内部系统用户的普通 `skill`。

### skill_version

表示不可变内容版本。

终态要求：

1. 主身份是 `(skill_id, version_number)`。
2. `version_number` 在同一 `skill_id` 下递增且不可变。
3. 一个 `skill_version` 只对应一个不可变内容目录。
4. 已存在目录不能被覆盖来表达更新。
5. 新内容创建新 `version_number`；同一 `skill` 下相同 `content_hash` 可以复用已有版本。

### skill_releases

表示某个 `(skill_id, version_number)` 被发布或提交发布。

Release status 控制可见性、可安装性、可更新性。它不改变 `skill_version` 内容目录，也不参与 runtime 路径授权。runtime 已经拿到具体 `(skill_id, version_number)` 后，只由该复合身份派生 `.deer-flow/skills/{skill_id}/{version_number}/`。

### skill_installation

表示用户对某个 Skill 的可用关系，并保存当前选择版本。

核心字段是：

```text
user_id
skill_id
version_number
```

`version_number` 必须引用同一 `skill_id` 下存在的 `skill_version.version_number`。

默认聊天的系统 Skill 配置不产生 `skill_installation`。`install_origin` 不进入终态最小模型。

### Agent

Agent 只表示用户显式创建的自定义 Agent。

终态不创建 default Agent，也不使用 `agent.kind=default/custom` 区分默认聊天和自定义 Agent。

### agent_skills

表示自定义 Agent 配置中启用的 Skill。

终态链路是：

```text
agent_skills.skill_installation_id
  -> skill_installation.skill_id + skill_installation.version_number
  -> skill_versions(skill_id, version_number)
```

`agent_skills` 不直接绑定系统 Skill，不直接绑定 `skill_version`，也不服务默认聊天。

### Thread

Thread 的 `agent_id` 是 nullable：

```text
agent_id = null      默认聊天
agent_id != null     自定义 Agent 聊天
```

默认聊天从平台 config 解析系统 Skill；自定义 Agent 聊天从 `agent_skills` 解析 Skill。

## 两条必须覆盖的运行链路

### 默认聊天 runtime 链路

```text
Thread(agent_id=null)
  -> default_chat.system_skills in config.yaml
  -> validate skill owner is internal system User
  -> skill_versions(skill_id, version_number)
  -> .deer-flow/skills/{skill_id}/{version_number}
  -> runtime descriptor
  -> prompt / sandbox / skill_load
```

### 自定义 Agent runtime 链路

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

## 前端跟随范围

前端不承担不可变性，也不定义 runtime 事实来源。

它需要跟随：

1. 删除 fork/download 入口和文案。
2. 展示 install/update/publish/review-ready 状态。
3. Agent 配置页只为自定义 Agent 保存 `agent_skills` 关系。
4. 默认聊天不出现 default Agent 配置入口；默认聊天系统 Skill 来自平台配置。
5. API 请求不再依赖 name-only、`skill_version_id` 路径或 system-specific binding fields。

## 明确不再作为终态事实来源的旧东西

以下内容是当前代码待删除或历史问题，只作为迁移输入，不能作为新终态业务事实来源或 runtime 事实来源：

```text
.deer-flow/skills/{skill_version_id}/...
.deer-flow/skills/public/...
.deer-flow/skills/{user_id}/...
.deer-flow/skills/{author_id}/...
.deer-flow/skills/custom/...
.deer-flow/skills/local/...
.deer-flow/skills/artifacts/skills/...
.deer-flow/skills/.runtime-skill-bundles/...
.deer-flow/skills/workspaces/...
```

以下业务对象或接口需要删除、迁移或替换：

1. fork package。
2. download editable package。
3. PendingSkillForkClaim。
4. claim sidecar。
5. default Agent / hidden default Agent。
6. `agent.kind=default/custom` 或 `agents.kind=default/custom`。
7. `install_origin`。
8. system-specific `agent_skills` fields。
9. system-specific API request fields。
10. Runtime Manifest JSON 作为核心事实来源的 schema/test 绑定。
11. `public/latest`、`custom`、name-only 扫描作为 install/runtime source。

## 后续 task 生成原则

从本终态反推后续任务，而不是从旧计划继续排队。

每个实现任务都应明确：

1. 它改业务链路、默认聊天 runtime 链路、自定义 Agent runtime 链路，还是多个链路都改。
2. 它删除哪些旧语义。
3. 它需要哪些 migration。
4. 它需要更新哪些测试。
5. 它是否影响前端 API contract。
6. 它是否需要同步 `.trellis/spec` 或用户文档。

候选任务拆分见 `09-follow-up-task-map.md`。
