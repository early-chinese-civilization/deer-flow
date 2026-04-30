# Current Implementation Gap

日期：2026-04-29

状态：代码探索结论

## 文档目的

这份文档只回答当前实现是什么、能复用什么、和目标模型差在哪里。它不设计新数据表，不写迁移顺序。

读完后，接手 agent 应该能有方向地探索代码，而不是重新从全仓库扫起。

## 当前实现一句话

当前实现是“public latest + custom copy + package_version”模型。

它能支持用户上传自定义 Skill、发布成公共最新版、其他用户下载一份，但还不能支持真正的 SkillHub 平台版本、安装态和手动更新体验。

## 已经具备的能力

当前实现已经有一条可运行的 Skills 管理雏形：

1. 后端已有 Skills API，能列出当前用户可见 Skill、上传自定义 Skill、下载 public Skill、发布自定义 Skill、删除自定义 Skill、检查上传和下载冲突。
2. 数据库已有统一的 `skills` 表，用 `user_id = null` 表示 public Skill，用 `user_id = 当前用户` 表示用户自定义 Skill。
3. 数据库已有 `skill_releases` 表，用于记录一次 publish 事件，并保存系统生成的 `release_version`、发布说明、发布者、源 Skill、发布后的 public Skill。
4. 数据库已有 `agents_skills` 绑定表，Agent 可以绑定某个用户的 Skill 行。
5. 后端 publish 流程已经有事务控制和文件目录回滚，发布失败时会尽量恢复旧 public artifact。
6. 后端 download 流程已经支持把 public Skill 复制到用户私有目录；如果覆盖同名自定义 Skill，会尝试迁移 Agent 绑定到新 Skill 行。
7. 前端已有 Skills Gallery，支持 public/custom 两个 tab、上传、下载、发布、删除、版本徽标和发布说明弹窗。
8. Agent 创建和编辑流程已经能选择 Skill 名称，并把这些名称保存到 Agent 绑定关系中。
9. 运行时已经能按 Agent 绑定关系解析 Skill，并把 Skill 名称、描述和虚拟路径注入到运行时上下文。
10. 测试已经覆盖一部分 publish、download、upload、release metadata、失败回滚和版本展示行为。

这些能力可以作为后续重构的底座，不需要从零开始。

## 当前实现的核心语义

当前行为可以概括为：

1. Skill 文件内容仍是权威来源之一，特别是 `SKILL.md` frontmatter 的 `version`。
2. 用户上传同名 Skill 时，系统比较新旧 `SKILL.md` 里的 `version`：
   - 相同版本：认为是重复上传，默认拒绝。
   - 不同版本：认为是更新当前 custom Skill，并原地替换文件内容。
3. 用户发布 custom Skill 时，系统复制当前 custom Skill 到 public 目录，创建新的 public latest 行，并创建一条 release 记录。
4. public 列表展示 latest 版本；历史 release 只作为记录，不作为用户可选择的安装版本。
5. 用户下载 public Skill 时，系统复制当前 public latest 到用户 custom 空间，生成一个新的 custom Skill 行。
6. Agent 绑定的是 custom Skill 行，不绑定 release，也不绑定某个不可变版本快照。
7. 运行时每次按当前 Skill 行的文件路径加载内容，因此当前 Skill 内容变化后，后续运行会跟随变化。

这个模型能支持“把东西传上去、发布成公共最新、别人下载一份”，但还不能支持真正的 SkillHub 版本体验。

## 当前运行时调度语义

当前 Agent 运行时不是从“安装关系”解析 Skill，而是从 Skill 行解析共享文件系统路径。

现状是：

1. public Skill 位于 `public` scope。
2. 用户 Skill 位于当前 `user_id` scope。
3. 自定义 Agent 创建和编辑时，只按名称解析当前用户自己的 Skill。
4. 未指定自定义 Agent 时，运行时回退到 public Skills。
5. 指定自定义 Agent 时，运行时使用该 Agent 绑定的用户 Skill。
6. prompt 只暴露 `/mnt/skills/<skill_name>/SKILL.md` 这种稳定虚拟路径。
7. `skill_load` 再根据运行时注入的 `file_path` 找到真实 artifact。
8. sandbox 要求同一次运行的 Skills 来自同一个 scope，不能混用 public 和用户目录。

这个约束解释了为什么当前“下载 public Skill 到我的空间”可以让自定义 Agent 使用 public Skill：下载后的 artifact 已经变成当前用户 scope 下的 Skill。

但这仍然只是文件复制，不是安装态。复制后系统无法稳定知道它来自谁、来自哪个版本、是否有新版、更新会影响哪些 Agent。

## 可复用资产

后续不应该全量推倒。以下部分值得保留或演进：

1. `skills` 表可以继续作为“用户空间里的 Skill 实例”和“SkillHub 当前可见条目”的过渡性资源表。
2. `skill_releases` 的发布审计思想是对的，可以升级为公开版本历史的一部分。
3. publish 流程中的文件复制、事务提交、失败回滚和日志阶段划分值得保留。
4. upload 流程中的 zip 安全解压、单根目录校验、frontmatter 基础校验值得保留。
5. download 的冲突检查、覆盖确认和 Agent 绑定迁移可以演进成“更新已安装版本前展示受影响 Agent”。
6. Agent 绑定表已经从字符串绑定走向资源绑定，这是正确方向。
7. 运行时通过 Agent 绑定解析 Skill 的路径是对的，但需要从“当前文件路径”升级为“当前安装版本的 artifact 路径”。
8. 前端 Gallery 可以演进为 SkillHub + 我的 Skills，不需要完全重做交互基础。
9. sandbox 的 scope 挂载和 `skill_load` allowlist 是安全边界，值得保留其“按授权清单读取”的思想，但目标架构应升级为 Runtime Manifest 驱动，而不是继续由 public/user 目录决定授权。

## 必须修正的语义

这些不是简单 UI 文案问题，而是会影响用户心智和数据正确性的产品语义问题：

1. `version` 仍来自 `SKILL.md`，与“版本由平台管理”的目标冲突。
2. 上传新版本会更新当前 custom Skill 行和文件，而不是创建不可变版本快照。
3. publish 创建的是新的 public latest 行，不是真正的“发布某个平台版本”。
4. `skill_releases` 记录 publish 事件，但没有成为用户可安装、可更新、可回滚的版本实体。
5. public Skill 同时承担“官方预制”和“社区发布”语义，没有明确来源类型。
6. download 被称为下载，实际产品语义应该是“安装到我的空间”。
7. 安装后没有保留“我安装了哪个源 Skill 的哪个版本”的稳定关系。
8. 发布者发布新版后，系统无法判断用户 B 当前安装的是旧版还是新版，也无法给出可靠更新提示。
9. Agent 绑定 custom Skill 行，缺少版本维度；如果 custom Skill 被原地替换，Agent 后续行为会变化。
10. 前端文案仍直接暴露 `package version`、`public latest`、`version still comes from SKILL.md` 等内部实现词。
11. runtime scope 只能表达 public 或某个用户目录，不能表达“用户安装了别人 Skill 的某个版本”。
12. public Skill 按 name 取 latest，无法支撑同名不同作者的社区 Skill 选择。

## 差距矩阵

| 用户目标 | 当前实现 | 差距 | 产品结论 |
| --- | --- | --- | --- |
| 用户上传 Skill，平台生成版本 1 | 上传后创建或更新 custom Skill 行，版本来自 `SKILL.md` | 没有平台版本实体；同名不同版本会原地更新 | 需要新增平台版本快照，上传内容变化时创建新版本 |
| 用户在 Agent 页面绑定 Skill | Agent 绑定当前用户 custom Skill 行 | 已有绑定表，但绑定不含版本语义 | 绑定应指向“已安装 Skill 的当前版本”或由安装态间接解析 |
| 用户发布自己的 Skill 到 SkillHub | custom Skill 被复制成 public latest，并创建 release 记录 | release 是发布事件，不是可安装版本；public 语义混杂 | publish 应发布某个不可变平台版本到 SkillHub |
| 用户上传新内容成为版本 2 | 同名不同 `package_version` 时更新当前 custom Skill 行和文件 | 旧版本内容丢失或只能靠 release 追踪；未发布版本无历史 | 更新必须创建新的 SkillVersion，不原地覆盖旧版本 |
| 用户 B 安装 v1，发布者发布 v2 后手动更新 | 用户 B 下载 public latest 为 custom copy；后续无法知道源版本更新关系 | 缺少 SkillInstall/源版本关系，无法可靠提示更新 | 必须引入安装态，记录 installed version 与 available version |
| 用户基于官方/社区 Skill 魔改 | 现在只有 download/overwrite，下载后就是同名 custom Skill | 无来源关系，无 fork/remix 语义 | 需要“基于此创建我的版本”，生成新 Skill 身份 |
| 官方 Skill 与社区 Skill 区分 | 都可能表现为 public Skill | 来源、可信度、维护者和发布权限不清 | public 需要拆成官方来源与社区来源 |
| 用户看到易懂版本 | 前端展示 package/release 字段和英文内部文案 | 普通用户需要理解 package/release | 展示“版本 1/2/3”，高级字段只留后台 |
| 更新不自动影响 Agent | 目前 custom Skill 更新后 Agent 会跟随当前文件内容 | 缺少更新确认和受影响 Agent 预览 | 用户手动更新安装态后，才影响绑定该安装态的 Agent |
| 回滚旧版本 | 当前没有可选择历史安装版本 | release 不足以还原未发布版本和用户安装状态 | 版本快照和安装历史要先建模，回滚可作为 P1 |
| 自定义 Agent 同时使用官方、社区和自建 Skill | sandbox 只允许同一次运行来自 public 或单个 user scope | public 和用户目录不能混挂；目录 scope 无法表达多来源多版本授权 | 目标应引入 Runtime Manifest 和 artifact allowlist |

【关键点】当前实现的核心 gap 不是“缺少一个下载动作”，而是缺少 Agent 运行前的 Runtime Manifest。没有 Manifest，就无法证明 prompt、`skill_load`、sandbox 读到的是用户指定的 SkillVersion。

## Agent 探索锚点

优先搜索这些符号：

1. `publish_skill`
2. `download_skill`
3. `upload_skills`
4. `check_skill_upload`
5. `Skill`
6. `SkillRelease`
7. `SkillRepository`
8. `SkillReleaseRepository`
9. `AgentSkill`
10. `replace_agent_skills`
11. `get_runtime_agent_bundle`
12. `SkillsGallery`
13. `package_version`
14. `release_version`
15. `public latest`
16. `derive_skill_scope_from_runtime`
17. `build_private_skill_file_path`
18. `build_public_skill_file_path`
19. `skill_load`
20. `virtual_path`
21. `file_path`

探索时先确认这些点：

1. 版本展示从哪里来。
2. 上传同名 Skill 时如何判断冲突。
3. 发布时 public latest 如何被替换。
4. 下载时是否保留源 release 关系。
5. Agent 绑定运行时最终解析到哪个 artifact。
6. 前端哪些文案仍暴露旧口径。
7. sandbox 当前是否允许混用 public 和 user scope。
8. `download` 是否把源 Skill、源版本和安装关系持久化。
