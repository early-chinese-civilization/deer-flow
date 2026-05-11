# Skills Runtime Lead Decision

日期：2026-04-30

状态：目标方案决策总纲；2026-05-11 主体已落地，字段名以代码为准

## 2026-05-11 当前代码校准

当前代码已实现本文件的主线：`SkillDefinition`、`SkillVersion`、`SkillRelease`、`SkillInstall`、Agent install/system binding、Runtime Manifest、manifest-backed `skill_load` 和 run-level sandbox bundle。

字段名和早期目标字段不同的地方，以代码为准：

- `SkillDefinition` 当前使用 `source_type` / `source_identifier` / `owner_user_id`，不是 `owner_type` / `source_namespace`。
- System Skill 当前不创建 per-user `SkillInstall`；Agent 通过 `system_skill_definition_id` / `system_skill_version_id` 绑定具体系统版本。
- 当前 Skills API `viewer_relation` 仍使用 `downloaded` 字面值表达 installed-from-Community personal row；用户文案必须渲染为“已安装”，不是下载。
- 当前 sandbox 方案已经选择 run-level readonly bundle。

仍未完成的是完整 v2/update/runtime-v2 max-flow，且被本地 `.deer-flow` 存储挂载阻塞。

## 文档目的

这份文档把已有 Skills 设计、`10-runtime-manifest-and-artifact-store.md` 和外部调研结论收束成一个决定性方案。

读者是后续要继续拆实现、写迁移、改 runtime、改 sandbox、改前端状态和补测试的同学。

读完后应该能做的事：

1. 判断后续设计是否偏离目标架构。
2. 按同一套对象边界拆后端、runtime、sandbox、前端和测试任务。
3. 在遇到旧实现兼容问题时知道哪些规则不能让步。
4. 把“用户安装成功”推进到“Agent 本次运行确实使用用户指定 SkillVersion”。

## Lead 决策

Skills 新方案以 Runtime Manifest 和不可变 Artifact Store 为中心。

最终链路确定为：

```text
SkillDefinition
  -> SkillVersion
  -> SkillRelease
  -> SkillInstall
  -> AgentSkillBinding
  -> Runtime Resolver
  -> Runtime Manifest
  -> prompt / skill_load / sandbox
```

核心规则：

1. `SkillDefinition` 是稳定身份。
2. `SkillVersion` 是不可变内容快照。
3. `SkillRelease` 是 SkillHub 公开发布事件。
4. `SkillInstall` 是用户当前选择使用哪个版本。
5. `AgentSkillBinding` 绑定用户自己的安装态；System Skill 例外，绑定具体 system SkillVersion，不绑定 public latest、skill name 或 latest release。
6. `Runtime Manifest` 是一次 Agent run 的唯一运行时授权真相。
7. prompt、`skill_load`、sandbox 都只能消费同一份 Runtime Manifest。
8. Artifact Store 保存不可变内容，目录物化只是运行时实现，不是产品身份。

【关键点】后续实现如果仍然让 Agent 从 public latest、skill name、用户目录 copy 或 filesystem scan 推断可用 Skill，就没有解决本轮核心问题。

## 方案不再讨论的事项

这些问题已经关闭，后续不再作为开放设计点反复摇摆。

| 问题 | 决策 |
| --- | --- |
| 平台版本是否来自 `SKILL.md` | 否。平台版本由 DeerFlow 生成，包内版本只保存为 source metadata。 |
| Agent 是否可以绑定 public latest | 否。非系统 Skill 绑定用户安装态；System Skill 绑定具体 system SkillVersion。 |
| 发布新版是否自动影响已安装用户 | 否。用户确认更新前 `SkillInstall.current_version_id` 不变。 |
| Runtime Manifest 是否只是 prompt 展示 DTO | 否。它是 prompt、tool、sandbox 的共同授权契约。 |
| Artifact 是否允许原地替换 | 否。`SkillVersion` 指向不可变 artifact。 |
| skill name 是否是稳定身份 | 否。外部可读身份是 namespace/name；内部不可变身份是 DeerFlow 平台 id。 |
| 包内是否必须有 version | 否。包内 version 可兼容读取，但不必填，也不参与平台版本。 |
| 如何判断上传包是不是 Skill | 通过包结构、`SKILL.md`、frontmatter 和文件安全校验判断，不通过 version 判断。 |
| official 和 community 是否都是稳定身份类型 | 否。official 是维护权威类型；community 是 SkillHub 展示/发布状态。 |
| name 和 display_name 是否都需要 | 需要，但第一版可以让 display_name 默认等于 name。name 是机器 slug，display_name 是用户可见名称。 |
| Resolver 失败时是否能 fallback 到 public 或同名目录 | 否。失败必须显式返回不可运行状态。 |
| Run record 是否保存完整 Manifest | 是。MVP 保存完整 Manifest JSON，并附带 manifest hash。 |
| sandbox 目标方案 | 优先采用 run-level readonly bundle。多 artifact root 仅作为底层实现或迁移兼容。 |

## 身份与包格式补充决策

本节是对早期文档中 `source_type = official/community/user` 建议的收口修正。后续实现以本节为准。

### 平台 id 是什么

平台 id 是 DeerFlow 在数据库里生成的内部不可变主键，不来自上传包，也不由用户填写。

常见平台 id 包括：

1. `SkillDefinition.id`
2. `SkillVersion.id`
3. `SkillRelease.id`
4. `SkillInstall.id`
5. `AgentSkillBinding.id`

这些 id 的用途是 join、授权、审计和 Manifest 固化。它们不负责给用户展示“这个 Skill 叫什么”，也不负责表达包作者想声明的版本。

因此同一个 Skill 在系统里有两层身份：

1. 人和外部系统能读懂的身份：`source_namespace/name`。
2. DeerFlow 内部永远不歧义的身份：平台 id。

【关键点】平台 id 不是“平台版本号”。平台版本号是 `SkillVersion.version_number`，用于用户理解 v1、v2。平台 id 是内部对象身份，用于避免改名、重名、迁移和审计时丢关系。

### 包内 version 不再是必填项

上传包不需要提供 version。

如果包内 `SKILL.md` 或其他 manifest 里有 version，DeerFlow 可以兼容读取并保存到 `source_package_version`，但它只表示“来源包自称的版本”。它不参与：

1. 平台版本递增。
2. 是否创建新 SkillVersion。
3. 是否允许发布。
4. 是否允许安装。
5. Agent runtime 选择哪个版本。

平台版本由 DeerFlow 根据 SkillDefinition 下的内容变更生成。首次有效内容是版本 1，后续不同内容生成版本 2、3。

### 如何判断上传包是不是 Skill

是否是 Skill 由 DeerFlow 校验包结构和入口文件决定，不由 version 决定。

MVP 校验规则：

1. 上传内容必须是安全 zip 或等价目录输入。
2. 路径不能包含目录穿越、绝对路径、非法软链或超限文件。
3. 根目录必须能解析出一个 `SKILL.md`。
4. `SKILL.md` 必须有合法 frontmatter。
5. frontmatter 至少提供 `name` 和 `description`，或由创建接口提供并写入平台字段。
6. `name` 必须符合 slug 规则，用于机器身份和 virtual path。
7. 文件清单、大小和 hash 必须能生成。

只要这些规则通过，它就是一个可导入的 Skill package。version 字段即使不存在也不影响导入。

### official 和 community 的必要性

需要区分官方和非官方，但不建议把 `official/community/user` 都做成 SkillDefinition 的稳定互斥类型。

更清楚的模型是：

1. `owner_type = official`：平台维护的 Skill，普通用户不能发布它的新版本。
2. `owner_type = user`：用户拥有的 Skill，可以是私有的，也可以发布到 SkillHub。
3. `community`：用户 owned Skill 发布到 SkillHub 后的目录展示状态，不是稳定身份类型。

这样可以避免一个用户私有 Skill 发布后必须从 `user` 变成 `community` 的类型迁移问题。

产品上仍然可以展示：

1. 官方 Skill：`owner_type = official`。
2. 社区 Skill：`owner_type = user` 且存在 published release。
3. 我的 Skill：当前用户拥有的 SkillDefinition。
4. 已安装 Skill：当前用户的 SkillInstall。

运行时仍然必须解析到具体 SkillVersion 和 Manifest。社区 Skill 通过 SkillInstall 进入运行时；系统 Skill 是平台预置共享资源，允许直接绑定/选择，但 Manifest 中仍必须记录具体 SkillVersion 和系统来源。

### name 和 display_name 的必要性

需要保留 `name` 和 `display_name`，但第一版 UI 可以弱化 `display_name`。

`name` 是机器 slug：

1. 用于 `source_namespace/name`。
2. 用于默认 virtual path。
3. 用于包校验和导入。
4. 应稳定、短、可读、低风险。

`display_name` 是用户可见名称：

1. 可以有空格、大小写和更自然的文案。
2. 可以随产品展示调整。
3. 可以默认从 `name` 生成。
4. 不参与身份判断，不参与 resolver，不参与路径映射。

如果只保留一个字段，要么路径和身份会被用户改名影响，要么 UI 永远只能展示 slug。两者都不理想。所以目标模型保留两个字段，MVP 可以让 `display_name = name`，等产品需要更友好的名称时再开放编辑。

## 目标对象边界

### SkillDefinition

回答“这是哪个 Skill”。

最小字段：

1. `id`
2. `owner_type`：official、user
3. `source_namespace`
4. `name`
5. `display_name`
6. `owner_user_id`
7. `description`
8. `status`

规则：

1. `display_name` 可以重复。
2. `source_namespace + name` 用于外部可读身份和冲突解释。
3. `id` 是 DeerFlow 内部不可变身份，所有绑定、版本和审计以 id 为准。
4. `community` 不作为稳定对象类型；用户 Skill 发布到 SkillHub 后，在产品展示上成为社区 Skill。
5. 普通用户基于官方或社区 Skill 创建自己的版本时，生成新的 SkillDefinition。
6. 官方 Skill 只能由平台维护。

### SkillVersion

回答“这是哪个不可变内容版本”。

最小字段：

1. `id`
2. `skill_id`
3. `version_number`
4. `artifact_uri`
5. `content_hash`
6. `artifact_size`
7. `file_manifest`
8. `file_manifest_hash`
9. `entrypoint`
10. `description_snapshot`
11. `source_package_version`
12. `status`：draft、active、disabled、security_blocked

规则：

1. 同一 SkillDefinition 下 `version_number` 单调递增。
2. 同内容重复上传不创建新版本。
3. 创建后 artifact 不允许原地替换。
4. `source_package_version` 可以为空。
5. `source_package_version` 不参与平台版本排序，不参与运行时版本选择。
6. `disabled` 和 `security_blocked` 在 resolver 阶段 hard fail。

### SkillRelease

回答“哪个版本公开发布到了 SkillHub”。

最小字段：

1. `id`
2. `skill_id`
3. `skill_version_id`
4. `publisher_user_id`
5. `release_notes`
6. `published_at`
7. `status`：published、delisted、blocked

规则：

1. release 指向具体 SkillVersion。
2. latest 只用于 SkillHub 展示和安装默认选择。
3. delist release 不删除 SkillVersion，也不静默改变已安装用户。
4. blocked release 不等于 blocked version；安全阻断要落到 version 或 policy。

### SkillInstall

回答“某个用户当前安装并选择使用哪个版本”。

最小字段：

1. `id`
2. `user_id`
3. `source_skill_id`
4. `installed_version_id`
5. `current_version_id`
6. `display_name`
7. `install_source`：skillhub、official_default、fork_source、legacy_migration
8. `status`：active、disabled、deleted

规则：

1. 安装创建 SkillInstall。
2. 更新只修改 `current_version_id`，不覆盖源 Skill，不覆盖旧版本 artifact。
3. 用户未确认更新时，`current_version_id` 不变。
4. 更新前必须能查询受影响 Agent。
5. 系统 Skill 不创建用户级 SkillInstall；如果绑定到 Agent，resolver 直接记录系统 SkillVersion 和系统来源。

### AgentSkillBinding

回答“某个 Agent 使用哪个安装态或系统 Skill 引用”。

最小字段：

1. `id`
2. `agent_id`
3. `skill_install_id` 或系统 Skill 引用字段
4. `enabled`
5. `version_policy`：第一版默认为 `follow_install_current`
6. `pinned_version_id`：第一版预留，不做主界面

规则：

1. MVP 主路径是 `follow_install_current`。
2. 更新 SkillInstall 后，绑定该 install 的 Agent 下一次运行使用新版。
3. 正在进行中的 run 不因安装态更新中途切换版本。
4. Binding 不直接指向 SkillRelease、public Skill、skill name 或文件目录。

## Runtime Manifest

Runtime Manifest 是一次 run 的 lock file。

生成时机：

1. Run 开始前由 Runtime Resolver 生成。
2. 生成后写入 run record。
3. runtime context 只传 Manifest id/hash 和必要内存对象。
4. run 内使用同一份 Manifest，不重新解析安装态。

MVP 保存完整 JSON。这样排查问题时可以直接回答：这次 run 读取了哪些 SkillVersion、哪些 artifact、哪些 virtual path、哪些 policy decision。

建议结构：

```json
{
  "manifest_version": 1,
  "run_id": "run_123",
  "user_id": 1755,
  "agent_id": 88,
  "generated_at": "2026-04-30T10:00:00Z",
  "resolver_version": "skills-runtime-v1",
  "skills": [
    {
      "binding_id": 1,
      "install_id": 42,
      "skill_id": 7,
      "skill_version_id": 19,
      "owner_type": "user",
      "catalog_channel": "community",
      "source_namespace": "alice",
      "name": "weekly-report",
      "display_name": "Weekly Report",
      "description": "Generate weekly summaries from uploaded files.",
      "virtual_name": "weekly-report",
      "virtual_root": "/mnt/skills/weekly-report",
      "entrypoint": "/mnt/skills/weekly-report/SKILL.md",
      "artifact_uri": "oss://skills/artifacts/sha256/abc...",
      "content_hash": "sha256:abc...",
      "file_manifest_hash": "sha256:def...",
      "allowed_paths": [
        "/mnt/skills/weekly-report/SKILL.md",
        "/mnt/skills/weekly-report/references/**",
        "/mnt/skills/weekly-report/scripts/**"
      ],
      "declared_tools": [],
      "policy_decisions": [
        "install_active",
        "version_active",
        "source_allowed"
      ]
    }
  ],
  "bundle": {
    "mode": "run_level_readonly_bundle",
    "virtual_root": "/mnt/skills",
    "bundle_manifest_hash": "sha256:..."
  }
}
```

必备不变量：

1. Manifest 中没有的 Skill 不得出现在 prompt。
2. Manifest 中没有的 virtual path，`skill_load` 必须拒绝。
3. Manifest 中没有的 artifact，sandbox 必须不可读。
4. Manifest 中的 `skill_version_id + content_hash + file_manifest_hash` 必须能审计到不可变 artifact。
5. Manifest 生成后，本次 run 不再读取 latest release 或 install current 重新决策。

## Runtime Resolver

Resolver 是一个深模块，外部接口保持小：

```python
manifest = resolve_agent_skill_runtime(user_id, agent_id, run_context)
```

Resolver 负责：

1. 校验 Agent 属于当前用户。
2. 读取 active AgentSkillBinding。
3. 校验每个 SkillInstall 属于当前用户且 active。
4. 根据 `version_policy` 选择具体 SkillVersion。
5. 校验 SkillVersion 状态、source policy、安全策略和 artifact 校验状态。
6. 为每个 Skill 分配 deterministic virtual name。
7. 生成 prompt descriptor、tool path map、sandbox allowlist。
8. 生成完整 Runtime Manifest 和 manifest hash。
9. 记录被拒绝的原因。

Resolver 不负责：

1. 从 filesystem scan 发现 Skill。
2. 从 SkillHub latest 推断当前版本。
3. 在失败时复制目录或自动安装。
4. 解析作者包内 version 作为平台版本。
5. 根据 display name 做唯一身份判断。

失败策略：

1. 缺少 install：run 不启动，并提示 Agent 绑定已失效。
2. install disabled：run 不启动，并提示安装态不可用。
3. version disabled/security_blocked：run 不启动，并提示哪个 SkillVersion 被阻断。
4. artifact hash mismatch：run 不启动，这是完整性错误。
5. virtual path 冲突无法分配：run 不启动，这是 resolver bug。
6. 任意失败都不能 fallback 到 public latest。

## Artifact Store

Artifact Store 采用 content-addressed 主路径。

推荐形态：

```text
skills/artifacts/sha256/<digest>/
  SKILL.md
  references/
  scripts/
  assets/
  .deerflow-artifact-manifest.json
```

数据库里的 SkillVersion 仍是业务版本身份；content-addressed path 是内容存储身份。

规则：

1. 上传或导入后先生成 file manifest，再计算 content hash。
2. 写入 Artifact Store 后校验 hash。
3. `SkillVersion.artifact_uri` 指向不可变 artifact。
4. 相同 content hash 可以复用同一份 artifact。
5. 删除 SkillVersion 不物理删除 artifact，清理由保留期和引用计数决定。
6. Artifact Store 不表达安装态，也不表达 Agent 绑定。

`.deerflow-artifact-manifest.json` 至少保存：

1. 文件相对路径。
2. 文件大小。
3. 文件 sha256。
4. 是否可执行。
5. entrypoint。
6. 生成时间。

## Sandbox 决策

目标方案采用 run-level readonly bundle。

运行链路：

```text
Runtime Manifest
  -> assemble readonly bundle
  -> /mnt/skills/<virtual_name>/...
  -> sandbox mounts one readonly skills root
```

采用它的原因：

1. 当前 sandbox 已有单 scope 心智，bundle 可以把多来源 artifact 收束成一个 run scope。
2. virtual path 冲突可以在 bundle 组装时解决。
3. sandbox 只需要理解本次 run 的只读视图，不需要理解 SkillHub、install 或 release。
4. prompt、`skill_load`、sandbox 看到的路径一致。
5. run record 可以保存 bundle manifest hash。

MVP 允许先用 copy 或 symlink 组装 bundle，但语义必须是只读。

后续优化可以使用 hardlink、reflink、overlay 或对象存储 lazy mount。优化不能改变授权模型。

## skill_load 决策

`skill_load` 只接受 Manifest virtual path。

规则：

1. 输入路径必须命中某个 Manifest `virtual_root`。
2. 解析后的相对路径必须存在于对应 `file_manifest`。
3. 真实读取必须落在 bundle 或 artifact allowlist 内。
4. 未命中 Manifest 的路径即使真实存在，也返回 unauthorized。
5. 返回给模型的路径统一使用 virtual path。
6. `skill_load` 不读取 public 目录，不扫描用户目录，不按 name 查数据库。

## prompt 注入决策

prompt 只注入 Manifest 中的 Skill descriptor。

第一版只注入：

1. display name。
2. description snapshot。
3. virtual entrypoint。
4. 必要的来源提示。

不把完整 `SKILL.md` 全量塞进系统提示词。模型需要内容时通过 `skill_load` 按需读取。

这保留 Agent Skills 的 progressive disclosure 优点，同时避免 filesystem discovery 成为运行时真相。

## 更新语义

MVP 更新语义确定为：

```text
AgentSkillBinding -> SkillInstall -> current_version_id
```

发布者发布 v2：

1. SkillHub latest 指向 v2。
2. 已安装 v1 的用户看到有更新。
3. 用户不确认更新，SkillInstall 仍指向 v1。
4. Agent 下一次 run 的 Manifest 仍指向 v1。

用户确认更新：

1. 展示 v1 -> v2 的 `SKILL.md` diff。
2. 展示 file list diff。
3. 展示受影响 Agent。
4. 用户确认后修改 `SkillInstall.current_version_id`。
5. Agent 下一次 run 的 Manifest 指向 v2。

第一版不做自动更新，不做复杂 SemVer，不做每个 Agent 主界面单独 pin 到不同历史版本。

但数据模型预留：

```text
version_policy = follow_install_current | pinned_version
```

## 同名冲突决策

稳定身份不使用 display name。

virtual name 分配规则：

1. 同一次 Manifest 内，`name` 唯一时使用 `<name>`。
2. `name` 冲突但 `source_namespace--name` 唯一时使用 `<source_namespace>--<name>`。
3. 仍冲突时使用 `install-<install_id>--<name>`。
4. Manifest 同时保存 `display_name`、`name`、`source_namespace`、`virtual_name`。

prompt 应在冲突时明确说明两个 Skill 来源不同。

安装时不通过覆盖目录解决冲突。目录冲突只能由 bundle virtual path 分配处理。

## 官方 Skill 决策

默认无自定义 Agent 的公共 Skills 可以在迁移期保留 legacy 注入。

目标模型中，社区 Skill 和用户自建 Skill 仍通过安装态进入 Agent 绑定；系统 Skill 作为平台预置共享资源直接绑定，不创建 per-user SkillInstall。

迁移完成后，系统 Skill 进入 Manifest 时必须能看到具体 SkillVersion 和系统来源，但不需要制造用户级安装记录。即使 UI 上看起来是默认能力，运行审计也必须能指向具体版本。

## MVP 切片

### Slice 1：平台版本和不可变 SkillVersion

目标：

1. 上传首次内容生成版本 1。
2. 上传不同内容生成版本 2。
3. 上传相同内容不生成新版本。
4. 包内 version 只进入 source metadata。
5. publish 指向具体 SkillVersion。

完成标准：

1. 旧版本 artifact 不被覆盖。
2. SkillHub 展示平台版本。
3. 测试不再断言 `SKILL.md` version 是平台版本。

### Slice 2：Artifact Store

目标：

1. SkillVersion 指向 content-addressed artifact。
2. artifact 保存 content hash、file manifest、file manifest hash。
3. hash mismatch hard fail。

完成标准：

1. 同一 artifact 可被多个版本引用。
2. artifact 创建后不能原地替换。
3. `skill_load` 后续有可校验的 file manifest 输入。

### Slice 3：SkillInstall

目标：

1. SkillHub 安装创建 SkillInstall。
2. 安装记录保存 installed/current SkillVersion。
3. 发布新版后只产生 update available 状态。

完成标准：

1. 用户未确认更新时 current version 不变。
2. 前端可以展示已安装、有更新。
3. 旧 download 兼容为 install latest，但不再是目标语义。

### Slice 4：AgentSkillBinding 绑定安装态

目标：

1. Agent 绑定 SkillInstall。
2. 更新安装态前可查询受影响 Agent。
3. 正在运行的 run 不中途换版本。

完成标准：

1. Agent 不再绑定 public latest。
2. 删除或禁用 install 时能解释受影响 Agent。
3. custom Agent 绑定系统 Skill 不创建 per-user install，但 Manifest 能审计到具体系统 SkillVersion。

### Slice 5：Runtime Resolver 和 Manifest 持久化

目标：

1. run 开始前生成 Runtime Manifest。
2. Manifest 保存完整 JSON 和 hash。
3. prompt descriptor 来自 Manifest。

完成标准：

1. Manifest 明确列出本次使用的 SkillVersion。
2. 发布新版但未更新安装态时，Manifest 仍指向旧版本。
3. Resolver 失败不 fallback。

### Slice 6：skill_load 按 Manifest 授权

目标：

1. `skill_load` 从 Manifest virtual path 映射到 artifact/bundle。
2. 未授权路径读取失败。
3. 返回路径保持 virtual path。

完成标准：

1. Manifest 外的 Skill path 不可读。
2. 同名 Skill 能通过 virtual name 共存。
3. file manifest 控制子文件读取。

### Slice 7：run-level readonly bundle

目标：

1. 根据 Manifest 组装 `/mnt/skills` 只读视图。
2. sandbox 只挂载本次 run bundle。
3. bundle manifest hash 写入 run record。

完成标准：

1. sandbox 无法读取 Manifest 外 artifact。
2. prompt、`skill_load`、sandbox 路径一致。
3. 多来源 Skill 可以在同一次 custom Agent run 中共存。

## 验收标准

一个实现只有满足以下条件，才算完成新方案核心闭环：

1. 用户安装 Skill v1 后，Agent Manifest 明确包含 v1 的 `skill_version_id`。
2. prompt 中只出现 Manifest 授权的 Skills。
3. `skill_load` 只能读取 Manifest 授权的 virtual path。
4. sandbox 只能读取 Manifest 授权的 bundle/artifact。
5. 发布者发布 v2 后，用户未确认更新前 Manifest 仍指向 v1。
6. 用户确认更新后，下一次 Manifest 才指向 v2。
7. run record 能审计完整 Runtime Manifest。
8. 同名不同作者的 Skill 不会因为 name 冲突覆盖。
9. Artifact hash mismatch 会阻止 run，而不是降级读取目录。
10. Resolver 失败时没有 public latest、filesystem scan 或同名目录 fallback。

## 非目标

第一版不做：

1. 付费市场。
2. 评分评论。
3. 自动更新。
4. 复杂 SemVer。
5. 社区排行榜。
6. 多人协作编辑同一个 Skill。
7. 自动合并用户 fork 后的魔改版本。
8. 每个 Agent 主界面单独 pin 到不同历史版本。
9. 组织级审批流。
10. 远程 runner / MCP server 的完整权限模型。

## 后续文档拆分建议

这份文档是 lead 决策，不替代实现设计。下一步建议按以下文档继续拆：

1. 数据库迁移设计：表结构、backfill、兼容旧 `skills`/`skill_releases`/`agents_skills`。
2. Artifact Store 设计：写入流程、hash、file manifest、保留期、迁移。
3. Runtime Resolver 设计：接口、错误码、policy 状态机、Manifest schema 版本化。
4. sandbox bundle 设计：组装方式、只读保证、清理策略、路径映射。
5. 前端状态设计：安装、更新、受影响 Agent、冲突来源提示。
6. 测试计划：按 Slice 逐步改写旧测试和新增 runtime/security 测试。

## 参考输入

这份决策基于：

1. `../design/05-target-domain-model.md`
2. `06-migration-plan.md`
3. `08-validation-and-open-questions.md`
4. `../design/09-agent-skill-runtime-scheduling.md`
5. `../design/10-runtime-manifest-and-artifact-store.md`
6. `../explorer/skill-market-runtime-manifest-research.md`
