# 当前稳定现状：领域模型

日期：2026-05-11

状态：稳定事实说明

## 资料优先级

发生冲突时，判断顺序是：

1. 当前代码和测试。
2. `/Users/sayori/Desktop/work/docs`。
3. `docs-qy/skills-design` 下的历史设计和计划文档。

本文只描述当前稳定事实。早期文档里的 `public latest`、`custom copy`、包内版本即平台版本等说法，不再作为当前模型依据。

## 一句话模型

当前 Skills 模型已经从“目录里的一个 Skill 文件夹”稳定为这条链路：

```text
SkillDefinition
  -> SkillVersion
  -> SkillRelease / SkillInstall / AgentSkill
  -> RuntimeManifest
  -> sandbox readonly bundle
```

目录仍然存在，但目录只是存储实现，不再决定业务身份、平台版本、用户安装态或运行授权。

## 核心对象

| 对象 | 当前职责 | 稳定字段/关系 |
| --- | --- | --- |
| `SkillDefinition` | Skill 的稳定身份 | `source_type`、`source_identifier`、`name` 共同定义身份；可关联 `owner_user_id` |
| `SkillVersion` | 不可变内容版本 | `skill_definition_id`、`version_number`、`artifact_uri`、`content_hash`、`file_manifest_hash`、`source_package_version` |
| `SkillRelease` | SkillHub 发布事件 | 指向具体 `skill_version_id`，记录发布说明和发布状态 |
| `SkillInstall` | 某个用户的安装态 | `installed_version_id` 表示首次安装版本，`current_version_id` 表示当前运行选择 |
| `AgentSkill` | Agent 的 Skill 绑定 | 非系统 Skill 用 `skill_install_id`；System Skill 用 `system_skill_definition_id` / `system_skill_version_id` |
| `RuntimeManifest` | 单次 run 的授权快照 | 保存 `manifest_json` 和 `manifest_hash`，连接 prompt、`skill_load`、sandbox |
| `PendingSkillForkClaim` | 可编辑导出包的 server-side claim | 支撑 `fork-package` 导出的 `.deerflow/fork.json` 后续认领 |

## SkillDefinition

`SkillDefinition` 表示“这是哪个 Skill”，不是某一次内容。

当前稳定规则：

1. Skill 身份由 `(source_type, source_identifier, name)` 约束。
2. System、Community、Personal/Fork 来源必须能区分。
3. 用户基于别人的 Skill fork/export 后再上传，应形成自己的 Skill 身份，而不是覆盖原 Skill。
4. 后续展示、发布、安装、运行都不应只依赖同名目录。

## SkillVersion

`SkillVersion` 表示平台生成的不可变版本。

当前稳定规则：

1. `version_number` 是平台版本号，由系统生成。
2. 包内 metadata 里的版本只进入 `source_package_version`，不作为平台版本。
3. `artifact_uri` 指向不可变 artifact。
4. 新内容创建新版本；旧 artifact 不原地覆盖。
5. `content_hash` 和 `file_manifest_hash` 用于内容去重、校验和运行时审计。

当前 artifact 路径以不可变版本为核心，例如：

```text
backend/.deer-flow/skills/artifacts/skills/<definition_id>/v<version>-<hash>/<skill_name>/...
```

## SkillInstall

`SkillInstall` 表示“某个用户安装了某个 Skill，并选择当前运行哪个版本”。

当前稳定规则：

1. 安装 Community Skill 后创建或更新当前用户的 install row。
2. 发布者发布新版不会自动修改安装者的 `current_version_id`。
3. 安装者确认更新后，`current_version_id` 切换到目标 `SkillVersion`。
4. Agent 绑定非系统 Skill 时应绑定 `skill_install_id`，不要绑定 SkillHub latest、name 或目录。

## SkillRelease

`SkillRelease` 表示公开发布事件。

当前稳定规则：

1. 发布指向具体 `skill_version_id`。
2. 发布说明属于 release，不属于包内平台版本。
3. 再次发布新版会创建新的 release，不覆盖旧版本 artifact。
4. 安装者是否更新由自己的 `SkillInstall.current_version_id` 决定。

## AgentSkill

`AgentSkill` 是 Agent 到 Skill 的绑定表。

当前稳定规则：

1. 非系统 Skill 绑定 `skill_install_id`。
2. System Skill 不要求 per-user install，直接绑定 system definition/version 字段。
3. 运行前 resolver 必须把绑定解析为具体 `SkillVersion.artifact_uri`。
4. legacy 的 `skill_id`、name-only 绑定和同名目录都不是新版运行时权威入口。

## RuntimeManifest

`RuntimeManifest` 是单次 run 的运行授权快照。

当前稳定规则：

1. Manifest 在 run 前由 Gateway 解析并持久化。
2. Manifest 必须记录具体 SkillVersion、install/system binding identity、artifact、hash 和虚拟路径。
3. prompt、`skill_load`、sandbox 必须消费同一份 Manifest。
4. Manifest 已生成后不因后续 install 更新而被改写。

## 兼容面

当前代码仍保留一些历史路径和字段，但它们不再代表新模型：

1. `custom/<skill_name>` 是 legacy compatibility。
2. `skills.file_path` 可用于 catalog/materialized row，不是 runtime 权威。
3. `<user_id>/<skill_name>` 仍可能出现在 standalone/local client install 路径。
4. name-only Agent 请求仍可兼容旧调用，但同名或多来源场景必须走 ID 绑定。
