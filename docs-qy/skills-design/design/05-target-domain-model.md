# Target Domain Model

日期：2026-04-29

状态：目标领域模型；2026-05-11 主体已落地，字段名以代码为准

## 2026-05-11 当前代码校准

本文件描述目标对象边界。当前代码已经落地这些对象，但字段名和早期建议不完全一致：

- `SkillDefinition` 当前使用 `source_type`、`source_identifier`、`owner_user_id`，不是 `owner_type/source_namespace`。
- `SkillVersion` 当前使用 `skill_definition_id`、`version_number`、`artifact_uri`、`content_hash`、`file_manifest_hash`、`source_package_version`。
- `SkillInstall` 当前使用 `skill_definition_id`、`installed_version_id`、`current_version_id`。
- `AgentSkillBinding` 当前表名仍是 `agents_skills` / ORM `AgentSkill`，非系统绑定用 `skill_install_id`，System Skill 用 `system_skill_definition_id` / `system_skill_version_id`。
- Runtime Manifest 已持久化到 `runtime_manifests`。

如果本文件的“建议字段”和代码不同，以代码为准；本文件保留领域意图。

## 文档目的

这份文档只描述目标模型需要哪些领域对象，以及每个对象解决什么问题。它不描述迁移顺序，不列接口，不写测试计划。

读完后应该能判断：某个实现方案是否真的支持平台版本、安装态和手动更新。

## 总体方向

目标模型从当前的 `skills + skill_releases + agents_skills` 演进为：

1. `SkillDefinition`：Skill 的稳定身份。
2. `SkillVersion`：不可变内容快照。
3. `SkillRelease`：SkillHub 的公开发布记录。
4. `SkillInstall`：用户安装态。
5. `AgentSkillBinding`：Agent 绑定安装态，或绑定具体 System Skill 版本。

这几个对象分别回答：

1. 这是哪个 Skill？
2. 这是第几个内容版本？
3. 哪个版本被公开发布了？
4. 某个用户安装了哪个版本？
5. 某个 Agent 使用哪个已安装 Skill 或哪个系统 Skill 版本？

## SkillDefinition：Skill 的稳定身份

表示“这是哪个 Skill”，不直接表示某次内容。

建议字段：

1. `id`
2. `owner_user_id`
3. `source_type`：official、community、user
4. `name`
5. `display_name`
6. `description`
7. `created_at`
8. `updated_at`
9. `deleted_at`

它解决的问题：

1. 官方 Skill、社区 Skill、我的 Skill 有明确身份。
2. 用户基于别人 Skill 创建自己的版本时，会得到新的 Skill 身份。
3. SkillHub 可以围绕稳定身份展示详情和版本历史。

关键规则：

1. 官方 Skill 只能由平台维护。
2. 社区 Skill 来自用户发布。
3. 用户基于官方或社区 Skill 创建自己的版本时，生成新的 SkillDefinition。
4. 新 SkillDefinition 的版本从 1 开始。

## SkillVersion：不可变内容快照

表示“这个 Skill 的第几个平台版本”。

建议字段：

1. `id`
2. `skill_id`
3. `version_number`：1、2、3
4. `artifact_path`
5. `content_hash`
6. `description_snapshot`
7. `change_notes`
8. `source_package_version`：仅兼容记录，不作为平台版本
9. `created_by`
10. `created_at`
11. `status`：draft、active、disabled

它解决的问题：

1. 上传新内容不再覆盖旧内容。
2. 发布和安装都可以指向不可变版本。
3. 平台版本由系统递增生成。
4. 可以检测同内容重复上传。

关键规则：

1. 同一 SkillDefinition 下版本号单调递增。
2. 同内容重复上传不创建新版本。
3. 版本一旦创建，artifact 不被原地替换。
4. 导入包自带版本只能进入 `source_package_version`。
5. 普通用户主界面展示 `version_number`，不展示内部 id。

## SkillRelease：SkillHub 公开发布记录

当前 `skill_releases` 的方向是对的，但语义要升级。

目标语义：

1. release 指向 `skill_version_id`。
2. release 记录公开发布时间、发布者、公开说明、状态。
3. release 不再保存作为主版本的 `package_version`。
4. SkillHub 当前版本可以通过 latest published release 得到。

它解决的问题：

1. 发布的是某个版本，而不是当前目录。
2. 历史发布可以展示。
3. 下架某个 release 不会破坏私有版本历史。
4. SkillHub 页面可以区分“版本创建”和“版本公开发布”。

关键规则：

1. 发布记录不可变。
2. 再次发布创建新的 release。
3. 下架 release 不删除对应 SkillVersion。
4. 发布说明属于公开发布事件，可以和私有版本说明分开。

## SkillInstall：用户安装态

这是当前实现最缺的对象。

建议字段：

1. `id`
2. `user_id`
3. `source_skill_id`
4. `installed_version_id`
5. `current_version_id`
6. `display_name`
7. `created_at`
8. `updated_at`
9. `deleted_at`

它解决的问题：

1. 用户 B 安装了用户 A 的哪个版本可以被追踪。
2. 发布者发布新版后，可以判断用户 B 是否有更新。
3. 更新是修改用户 B 的安装态，而不是覆盖源 Skill。
4. Agent 可以绑定安装态，避免直接绑 SkillHub 对象。

关键规则：

1. 安装动作创建 SkillInstall。
2. 用户不更新时，`current_version_id` 不变。
3. 发布者发布新版本后，只产生可更新状态，不自动修改安装态。
4. 安全禁用可以让某个安装态不可运行，但必须可解释。

## AgentSkillBinding：Agent 绑定安装态

当前 `agents_skills` 可以演进，而不是丢弃。

推荐方向：

1. Agent 绑定 `skill_install_id`。
2. System Skill 绑定具体 system `SkillVersion`，不要求用户安装态。
3. 运行时通过 install 的 `current_version_id` 或 system version 找到 artifact。
4. 更新 install 的版本前，先查询受影响 Agent。
5. 对话历史可以记录当次运行用到的 `skill_version_id`，但不作为 MVP 必须。

它解决的问题：

1. SkillHub 新版本不会自动影响 Agent。
2. 用户确认更新后，绑定该安装态的 Agent 后续才变化。
3. System Skill 可直接进入 Agent binding，但 Manifest 中必须记录具体 system version。
4. 删除或禁用 Skill 时，可以准确提示受影响 Agent。

关键规则：

1. Agent 不直接绑定 SkillHub release。
2. Agent 不直接绑定别人发布的 SkillDefinition。
3. Agent 通过用户空间里的安装态获得非系统运行时内容。
4. Agent 通过 system binding 获得平台预置 Skill 的具体版本。
5. 正在进行中的回复不被中途切换版本。

## 来源关系

用户基于官方或社区 Skill 创建自己的版本时，需要保留来源关系。

来源关系用于：

1. 展示“基于某 Skill 创建”。
2. 未来做合并或更新提示。
3. 避免用户误以为自己拥有原 Skill 发布权。
4. 处理作者归属和信任提示。

第一版不需要自动合并来源 Skill 的新版本。

## 运行时解析目标

运行时不应该解析“当前 public latest 目录”或“当前 custom 文件路径”。

目标解析链路：

1. Run 请求带有 Agent。
2. Agent 找到 active AgentSkillBinding。
3. Binding 找到 SkillInstall。
4. SkillInstall 找到 current SkillVersion。
5. SkillVersion 提供 artifact。
6. Runtime Resolver 生成 Runtime Manifest。
7. 运行时根据 Manifest 注入 Skill 名称、描述和虚拟路径。
8. `skill_load` 和 sandbox 根据 Manifest 限制可读 artifact。

这个链路保证：没有用户确认更新时，Agent 行为不变。

## Runtime Manifest 与 Artifact Store

目标模型里，artifact 路径只是运行时读取实现，不是产品身份。

【关键点】目标架构应把 Runtime Manifest 作为 prompt、`skill_load`、sandbox allowlist 的共同真相。目录结构不能反向决定用户安装关系，也不能决定 Agent 实际使用哪个版本。

推荐目标：

1. SkillVersion 指向不可变 artifact。
2. SkillInstall 决定用户当前选择哪个 SkillVersion。
3. AgentSkillBinding 绑定 SkillInstall。
4. Runtime Resolver 在每次运行前生成 Runtime Manifest。
5. Manifest 明确列出本次运行允许读取的 SkillVersion artifact。
6. prompt 只展示 Manifest 中的 Skills。
7. `skill_load` 只读取 Manifest 授权的 virtual path。
8. sandbox 只挂载或映射 Manifest 授权的 artifact root。

旧的“安装后物化到当前用户 scope”只能作为兼容当前 sandbox 单 scope 约束的迁移备选，不是目标模型。

即使后续实现选择 run-level readonly bundle，而不是多 artifact root allowlist，领域关系也必须保持：

1. SkillInstall 决定用户当前使用哪个版本。
2. SkillVersion 决定不可变内容。
3. Runtime Manifest 决定本次运行能读哪些 artifact。
4. Run 记录能审计本次实际使用了哪些 SkillVersion。
