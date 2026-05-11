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

这张表的读法是：不要再把 Skill 当成一个会被原地改写的文件夹或一行 `skills` 记录。当前稳定模型把问题拆开：

1. `SkillDefinition` 回答“这是哪个 Skill 身份”。
2. `SkillVersion` 回答“这一版不可变内容是什么”。
3. `SkillRelease` 回答“哪一次 SkillHub 发布公开了哪一版”。
4. `SkillInstall` 回答“某个用户安装了哪个 Skill，并选择当前运行哪一版”。
5. `AgentSkill` 回答“某个 Agent 绑定的是用户安装态，还是系统 Skill 版本”。
6. `RuntimeManifest` 回答“某次 run 开始时实际授权加载了哪些具体版本和 artifact”。
7. `PendingSkillForkClaim` 回答“一个导出的可编辑包之后能否被服务端可信地认领为 fork”。

对象关系更精确地看是多条边，而不是单向链：

```text
SkillDefinition
  -> SkillVersion

SkillVersion
  -> SkillRelease

SkillDefinition
  -> SkillInstall
    -> installed_version_id / current_version_id -> SkillVersion

AgentSkill
  -> skill_install_id -> SkillInstall -> current_version_id -> SkillVersion
  -> system_skill_definition_id / system_skill_version_id -> SkillVersion

RuntimeManifest
  -> resolved AgentSkill bindings
  -> exact SkillVersion artifact/hash/virtual_path snapshot

PendingSkillForkClaim
  -> source_skill_definition_id
  -> source_skill_version_id
```

## SkillDefinition

`SkillDefinition` 表示“这是哪个 Skill”，不是某一次内容。

当前稳定规则：

1. Skill 身份由 `(source_type, source_identifier, name)` 约束。
2. System、Community、Personal/Fork 来源必须能区分。
3. 用户基于别人的 Skill fork/export 后再上传，应形成自己的 Skill 身份，而不是覆盖原 Skill。
4. 后续展示、发布、安装、运行都不应只依赖同名目录。

稳定身份的关键是 `source_type`、`source_identifier`、`name`。同一个名字可以来自不同来源，因此 `name` 只能作为人类可读标签或兼容路由上下文，不能作为唯一业务身份。

例如同名 `browser` 可以同时存在于：

```text
source_type="system", source_identifier="deerflow_builtin", name="browser"
source_type="user", source_identifier="<user-a-id>", name="browser"
source_type="user", source_identifier="<user-b-id>", name="browser"
```

这些是不同 `SkillDefinition`。上传、发布、安装、更新预览、Agent 绑定和运行解析都应该沿着 `skill_definition_id` / `skill_install_id` 继续走，不能在中途退回到“按 name 找最新一条”。

`owner_user_id` 是身份的归属/审计信息，不等同于“当前用户已经安装”。安装态属于 `SkillInstall`；发布态属于 `SkillRelease`；内容版本属于 `SkillVersion`。

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

`SkillVersion` 的稳定含义是“某个 SkillDefinition 下的一份内容快照”。创建后不要改写这些字段的语义：

1. `version_number`：DeerFlow 平台版本号，在同一个 `skill_definition_id` 下递增。
2. `artifact_uri`：运行时应该读取的不可变 artifact 位置。
3. `content_hash`：用于识别同一份规范化内容，避免重复平台版本。
4. `file_manifest_hash`：用于运行前校验 artifact 文件集合和原始内容没有漂移。
5. `source_package_version`：只记录来源包 metadata，不参与平台版本排序。

因此，包内 `SKILL.md` 的 `version` 变化但内容等价时，不应被当成新的平台运行版本；内容真正变化时，才创建新的 `SkillVersion`。运行时也不能因为目录里有一个同名较新文件夹，就跳过 `SkillVersion.artifact_uri`。

## SkillInstall

`SkillInstall` 表示“某个用户安装了某个 Skill，并选择当前运行哪个版本”。

当前稳定规则：

1. 安装 Community Skill 后创建或更新当前用户的 install row。
2. 发布者发布新版不会自动修改安装者的 `current_version_id`。
3. 安装者确认更新后，`current_version_id` 切换到目标 `SkillVersion`。
4. Agent 绑定非系统 Skill 时应绑定 `skill_install_id`，不要绑定 SkillHub latest、name 或目录。

`installed_version_id` 和 `current_version_id` 不是重复字段：

```text
首次安装 v1:
installed_version_id = v1
current_version_id = v1

安装者确认更新到 v2:
installed_version_id = v1
current_version_id = v2

安装者回滚到 v1:
installed_version_id = v1
current_version_id = v1
```

`installed_version_id` 是安装事件的历史锚点；`current_version_id` 是未来 run 解析时的当前选择。当前稳定实现是 follow-install-current：Agent 绑定 `skill_install_id` 后，后续新 run 会读取这个 install 当时的 `current_version_id`。已经生成的旧 Runtime Manifest 不会被改写。

同一个用户对同一个 active `SkillDefinition` 应只有一个 active install。若用户需要编辑别人的 Skill，不应直接修改这个 install 指向的源身份，而应通过 fork/export/upload 形成自己的 `SkillDefinition` 和 `SkillVersion`。

## SkillRelease

`SkillRelease` 表示公开发布事件。

当前稳定规则：

1. 发布指向具体 `skill_version_id`。
2. 发布说明属于 release，不属于包内平台版本。
3. 再次发布新版会创建新的 release，不覆盖旧版本 artifact。
4. 安装者是否更新由自己的 `SkillInstall.current_version_id` 决定。

`SkillRelease` 是“发布了哪一个不可变版本”的审计记录，不是 Skill 当前内容本身。发布应该落到具体 `skill_version_id`，这样 SkillHub 可以展示最新发布态，同时历史 release 仍然能回答：

1. 谁在什么时候发布。
2. 发布说明是什么。
3. 公开的是哪个 `SkillVersion`。
4. 后续新版发布前，安装者实际安装的是哪一版。

这层对象把“版本已经存在”和“版本已经公开发布”分开。一个 `SkillVersion` 可以先存在于作者的 My Skills 中，之后才发布；一个已发布版本也可以被下架或被新版取代，但旧 artifact 不因此被原地覆盖。

## AgentSkill

`AgentSkill` 是 Agent 到 Skill 的绑定表。

当前稳定规则：

1. 非系统 Skill 绑定 `skill_install_id`。
2. System Skill 不要求 per-user install，直接绑定 system definition/version 字段。
3. 运行前 resolver 必须把绑定解析为具体 `SkillVersion.artifact_uri`。
4. legacy 的 `skill_id`、name-only 绑定和同名目录都不是新版运行时权威入口。

`AgentSkill` 有两个稳定绑定模式：

```text
非系统 Skill:
AgentSkill.skill_install_id
  -> SkillInstall.current_version_id
  -> SkillVersion

System Skill:
AgentSkill.system_skill_definition_id
AgentSkill.system_skill_version_id
  -> SkillVersion
```

非系统 Skill 走安装态，是因为它属于某个用户的 My Skills 使用选择。System Skill 不走安装态，是因为它是平台预置共享能力，不应该为每个用户复制 install row 或私有内容。

实现和数据修复时要避免混合模式：同一条 active `AgentSkill` 不应既表示普通 install 绑定，又表示 system direct binding。兼容字段 `skill_id` 只能作为历史输入/迁移面，不能作为新版 runtime truth。

## RuntimeManifest

`RuntimeManifest` 是单次 run 的运行授权快照。

当前稳定规则：

1. Manifest 在 run 前由 Gateway 解析并持久化。
2. Manifest 必须记录具体 SkillVersion、install/system binding identity、artifact、hash 和虚拟路径。
3. prompt、`skill_load`、sandbox 必须消费同一份 Manifest。
4. Manifest 已生成后不因后续 install 更新而被改写。

Runtime Manifest 的价值是把“运行开始时的授权事实”固化下来。后续即使发布者发布 v2、安装者确认更新、或者 artifact 存储布局调整，这次 run 的 manifest 仍然说明当时到底允许加载什么。

Manifest 至少要能审计这些信息：

```json
{
  "skills": [
    {
      "skill_definition_id": 11,
      "skill_install_id": 13,
      "skill_version_id": 12,
      "version_number": 1,
      "artifact_uri": "artifacts/skills/11/v1-c8673db72c69/runtime-acceptance-skill",
      "content_hash": "sha256:...",
      "file_manifest_hash": "sha256:...",
      "virtual_path": "/mnt/skills/runtime-acceptance-skill--install-13",
      "source_kind": "community",
      "binding_kind": "install"
    }
  ]
}
```

具体 JSON 字段可以随实现演进，但稳定原则不变：prompt、`skill_load`、sandbox bundle 必须消费同一个 resolved snapshot；运行时不能重新去 public latest、custom path、用户目录或同名目录里发现 Skill。

`manifest_hash` 是对规范化 `manifest_json` 的确定性 hash，用来做审计、日志关联和 bundle 路径隔离。它不能替代 manifest 内容本身；需要排查时仍应看 `manifest_json` 中的具体 version/artifact/hash。

## PendingSkillForkClaim

`PendingSkillForkClaim` 表示一次可编辑 fork package 导出的服务端待认领声明。

当前稳定规则：

1. `fork-package` 导出 `.deerflow/fork.json`，其中只携带 claim token/sidecar 信息。
2. 可信状态在服务端 `PendingSkillForkClaim`，不在客户端 ZIP 内。
3. claim 记录来源 `source_skill_definition_id` 和 `source_skill_version_id`。
4. 后续上传时，服务端校验 claim 是否属于当前用户、是否未过期、是否未被认领或撤销。
5. 认领成功后，上传内容应形成当前用户自己的 fork/个人 Skill 身份，不覆盖原作者或 System Skill 身份。

这个对象解决的是“可编辑包离开平台后还能安全回来”的问题。没有 server-side claim 时，`.deerflow/fork.json` 很容易被篡改，服务端也无法可靠判断导出包是否过期、是否重复认领、是否来自某个具体 `SkillVersion`。

典型生命周期：

```text
用户点击 fork-package
  -> 服务端创建 PendingSkillForkClaim
  -> ZIP 写入 .deerflow/fork.json claim token
  -> 用户本地编辑
  -> 用户重新上传
  -> 服务端校验 claim
  -> 创建/关联用户自己的 SkillDefinition 和 SkillVersion
  -> claim 标记为 claimed
```

## 必须守住的对象约束

这套模型最怕的是重新把身份、版本、安装态和运行事实混在一起。后续改动至少要守住这些约束：

1. `SkillVersion` 创建后是不可变内容版本，不要原地覆盖 artifact/hash。
2. `SkillRelease` 发布的是具体 `SkillVersion`，不是会漂移的 name/latest。
3. `SkillInstall.current_version_id` 必须属于同一个 `SkillDefinition`。
4. 普通/Community/My Skill 的 Agent 绑定走 `skill_install_id`。
5. System Skill 的 Agent 绑定走 `system_skill_definition_id` / `system_skill_version_id`，不创建 per-user install。
6. `RuntimeManifest` 必须保存 run 开始时解析出的 exact version/artifact/hash，不在 prompt、`skill_load` 或 sandbox 阶段重新发现。
7. `PendingSkillForkClaim` 的可信状态必须在服务端；`.deerflow/fork.json` 只是携带 token。

## 完整生命周期示例

以用户安装并运行 `runtime-acceptance-skill` 为例：

```text
作者上传 v1
  -> SkillDefinition(runtime-acceptance-skill)
  -> SkillVersion(version_number=1, artifact_uri=...)

作者发布 v1
  -> SkillRelease(skill_version_id=v1)

安装者从 Community 安装
  -> SkillInstall(installed_version_id=v1, current_version_id=v1)

安装者把 Skill 绑定到 Agent
  -> AgentSkill(skill_install_id=<install-id>)

Agent 发起 run
  -> RuntimeManifest 固化 v1 artifact/hash/virtual_path
  -> prompt、skill_load、sandbox 都只消费这个 Manifest

作者发布 v2
  -> 新 SkillVersion(version_number=2)
  -> 新 SkillRelease(skill_version_id=v2)
  -> 安装者的 current_version_id 仍是 v1

安装者确认 update-install
  -> SkillInstall.current_version_id = v2
  -> 后续新 run 的 RuntimeManifest 解析到 v2
  -> 旧 RuntimeManifest 仍审计为 v1
```

这个例子说明：发布不会污染安装态，安装更新不会改写历史 run，历史 run 也不会阻止未来升级。

## 兼容面

当前代码仍保留一些历史路径和字段，但它们不再代表新模型：

1. `custom/<skill_name>` 是 legacy compatibility。
2. `skills.file_path` 可用于 catalog/materialized row，不是 runtime 权威。
3. `<user_id>/<skill_name>` 仍可能出现在 standalone/local client install 路径。
4. name-only Agent 请求仍可兼容旧调用，但同名或多来源场景必须走 ID 绑定。
