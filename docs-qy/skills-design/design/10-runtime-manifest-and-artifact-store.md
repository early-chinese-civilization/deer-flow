# Runtime Manifest And Artifact Store

日期：2026-04-30

状态：关键目标架构与调研入口

## 文档目的

这份文档把 Skills 的目标架构从“业务层安装成功”推进到“Agent 层确定能调到用户指定 Skill 版本”。

读者是即将继续调研或设计方案的 agent、后端、sandbox、运行时和测试同学。

读完后应该能做的事：

1. 判断一个方案是否真正解决 Agent 调度 Skill。
2. 判断目录复制、public latest、skill name 绑定为什么不能作为目标架构。
3. 围绕 Runtime Manifest 和不可变 Artifact Store 继续调研替代设计。
4. 给后续实现提出更具体的 resolver、sandbox、测试方案。

## 关键结论

【关键点】业务层显示“已安装”不等于完成。只有运行前生成的 Runtime Manifest 明确包含用户指定的 SkillVersion，并且 prompt、`skill_load`、sandbox allowlist 都只消费这份 Manifest，才算 Agent 层真正成功。

推荐目标架构是：

```text
Catalog
  -> SkillInstall
  -> AgentSkillBinding
  -> Runtime Resolver
  -> Runtime Manifest
  -> prompt / skill_load / sandbox allowlist
```

Skill 内容进入不可变 Artifact Store。Agent 不直接读 public latest，不直接按 skill name 猜目录，也不把复制后的目录当成安装态真相。

## 为什么要推翻目录驱动

当前 `public` 和 `user_id` 目录模型能跑通早期功能，但它把运行时调度建立在物理目录上。

这会带来几个根本问题：

1. 目录不能表达“用户安装了谁的哪个版本”。
2. 同名 Skill 无法可靠区分来源。
3. public latest 会诱导 Agent 跟随公共最新版。
4. 复制到用户目录后，来源关系和版本关系容易丢失。
5. 测试只能证明文件存在，不能证明 Agent 使用的是用户指定版本。

【关键点】目录可以是 artifact 存储实现，不能是业务身份、版本身份、安装身份或运行时授权身份。

## 目标对象边界

目标架构中，每层只回答一个问题。

1. Catalog 回答：平台上有哪些 Skill。
2. SkillDefinition 回答：这是哪个稳定 Skill 身份。
3. SkillVersion 回答：这是该 Skill 的哪个不可变内容版本。
4. SkillRelease 回答：哪个版本公开发布到了 SkillHub。
5. SkillInstall 回答：某个用户当前选择使用哪个版本。
6. AgentSkillBinding 回答：某个 Agent 使用哪个安装态。
7. Runtime Resolver 回答：本次运行实际能读取哪些 Skill artifact。
8. Runtime Manifest 回答：prompt、tool、sandbox 的共同授权真相。
9. Artifact Store 回答：不可变内容在哪里。

【关键点】AgentSkillBinding 不应该绑定 skill name，也不应该绑定 public Skill。它应该绑定当前用户空间里的 SkillInstall。

## Runtime Manifest 是唯一运行时真相

每次 Agent 运行前，系统必须生成一份 Runtime Manifest。

Manifest 至少要包含：

```json
{
  "user_id": 1755,
  "agent_id": 88,
  "skills": [
    {
      "binding_id": 1,
      "install_id": 42,
      "skill_id": 7,
      "skill_version_id": 19,
      "name": "weekly-report",
      "description": "...",
      "virtual_root": "/mnt/skills/weekly-report",
      "entrypoint": "/mnt/skills/weekly-report/SKILL.md",
      "artifact_uri": "oss://.../skills/artifacts/sha256-abc/",
      "content_hash": "sha256:abc"
    }
  ]
}
```

字段语义：

1. `binding_id` 用于解释这是哪个 Agent 绑定带来的 Skill。
2. `install_id` 用于解释这是用户选择的哪个安装态。
3. `skill_version_id` 用于解释这次运行实际使用哪个不可变版本。
4. `virtual_root` 和 `entrypoint` 是模型可见路径。
5. `artifact_uri` 和 `content_hash` 是运行时和审计使用的内容定位。

【关键点】prompt、`skill_load`、sandbox mount 都不能各自重新解析 Skill。它们必须消费同一份 Manifest。

## Runtime Resolver 的职责

Runtime Resolver 是这个设计里最重要的深模块。

它的外部接口应该很小：

```python
manifest = resolve_agent_skill_runtime(user_id, agent_id, run_context)
```

内部隐藏这些复杂度：

1. 校验 Agent 属于当前用户。
2. 读取 Agent active bindings。
3. 校验每个 SkillInstall 仍可用。
4. 解析 install 的 current SkillVersion。
5. 校验版本未被安全禁用。
6. 校验用户有权继续使用该版本。
7. 为每个 Skill 分配稳定 virtual path。
8. 处理同名 virtual path 冲突。
9. 生成 artifact allowlist。
10. 生成 prompt-facing descriptor。
11. 生成 run 级审计快照。

【关键点】Resolver 的输出是运行时契约，不是 UI 展示 DTO。它必须足够严格，宁可失败，也不能模糊地回退到 public latest 或同名目录。

## 不可变 Artifact Store

SkillVersion 应指向不可变 artifact。

推荐方向：

```text
Artifact Store
  content-addressed artifact
  version artifact reference
  release reference
```

核心规则：

1. 相同内容只存一份，可以由多个版本引用。
2. 已创建的 SkillVersion artifact 不允许原地替换。
3. 发布、安装、运行都指向 SkillVersion，而不是当前目录。
4. Artifact 可以有 OSS URI、content hash、大小、文件清单和校验状态。
5. Artifact Store 不关心用户是否安装，只关心内容是否存在且可读。

【关键点】版本不可变不是 UI 规则，而是运行时安全规则。只有 artifact 不可变，Agent 才能被审计为“本次确实使用版本 19”。

## Sandbox 和 tool 授权

目标设计不应该依赖“只能挂载 public 或某个 user scope”。

推荐让 sandbox 使用 Manifest 的 artifact allowlist：

1. 每个 manifest skill 对应一个只读 artifact root。
2. sandbox 可以挂载多个 artifact root，或挂载一个由 runtime 组装出的只读视图。
3. `skill_load` 只接受 Manifest 中出现的 `entrypoint` 或其子路径。
4. 未授权路径即使存在于底层存储，也必须读取失败。
5. sandbox 输出中的真实 artifact path 要被映射回 virtual path。

可以调研两种实现：

1. 多 artifact root allowlist：每个 SkillVersion 独立挂载或映射。
2. run-level readonly bundle：每次运行生成一个只读视图，`/mnt/skills` 只暴露这次 Manifest 中的 Skills。

【关键点】无论采用哪种实现，授权单位都必须是 Manifest 中的 SkillVersion artifact，而不是 public 目录或用户目录。

## Agent 更新语义

默认语义建议是：

```text
AgentSkillBinding -> SkillInstall -> current_version_id
```

用户更新 SkillInstall 时，所有绑定该 install 的 Agent 下一次运行使用新版。

发布者发布新版时：

1. SkillHub 显示新版本。
2. 已安装旧版的用户看到更新提示。
3. 用户不确认更新，SkillInstall 不变。
4. Runtime Resolver 仍输出旧 `skill_version_id`。
5. 用户确认更新后，Runtime Resolver 才输出新 `skill_version_id`。

未来可以扩展高级策略：

```text
version_policy = follow_install_current | pinned_version
```

第一版不需要把每个 Agent 固定到不同历史版本作为主路径，但数据模型和 Manifest 可以预留这个能力。

【关键点】“手动更新”必须在 Agent 层可验证：发布新版后，未确认更新的 Agent Manifest 仍然指向旧版本。

## 不推荐方案

### 不推荐：复制 public 目录后创建 custom Skill 行

这个方案会把安装态退化成文件副本。

问题：

1. 来源关系弱。
2. 版本关系弱。
3. 同名冲突难处理。
4. 更新语义容易变成覆盖目录。
5. Agent 使用哪个版本不够显式。

它可以作为短期兼容手段，但不能作为目标架构。

### 不推荐：Agent 直接绑定 public latest

这个方案会让发布者发布新版后，用户 Agent 行为可能在没有确认的情况下变化。

它违反手动更新模型。

### 不推荐：Agent 绑定 skill name

skill name 不是稳定身份。

它不能可靠表达：

1. 同名不同作者。
2. 同名不同来源。
3. 当前安装版本。
4. 用户是否有权使用。
5. 运行时应该读取哪个 artifact。

## 调研 agent 重点问题

后续调研 agent 可以优先围绕这些问题给方案。

1. Runtime Manifest 应该持久化还是只在 run 开始时生成？
2. Run record 是否必须保存完整 Manifest，还是只保存 skill version 快照？
3. Artifact Store 用 content hash 作为主键，还是用 version id 作为主路径？
4. 多 artifact root allowlist 和 run-level bundle 哪个更适合当前 sandbox？
5. 如何处理两个 Skill 的 virtual name 冲突？
6. `skill_load` 如何从 virtual path 严格映射到 Manifest artifact？
7. 下架、禁用、安全阻断应该发生在 resolver 前、resolver 中，还是 tool 调用时？
8. 官方默认 Skill 是否也需要显式 SkillInstall？
9. 自定义 Agent 是否允许混合 follow install 和 pinned version？
10. 旧 public/custom 数据如何迁移到 SkillDefinition、SkillVersion、SkillInstall？

## 验收标准

一个方案只有满足这些条件，才算解决核心 gap：

1. 用户安装 Skill v1 后，Agent Manifest 明确包含 v1 的 `skill_version_id`。
2. prompt 中只出现 Manifest 授权的 Skills。
3. `skill_load` 只能读取 Manifest 授权的 virtual path。
4. sandbox 只能读取 Manifest 授权的 artifact。
5. 发布者发布 v2 后，用户未确认更新前 Manifest 仍指向 v1。
6. 用户确认更新后，Manifest 才指向 v2。
7. run 记录能审计本次实际使用了哪些 SkillVersion。
8. 同名不同作者的 Skill 不会因为 name 冲突互相覆盖。
9. 安装成功但 resolver 失败时，Agent 运行必须失败或给出明确不可用状态，不能静默回退。

【关键点】最终验收要测 Agent 层，不只测业务 API。业务 API 返回安装成功，只是前置条件；Manifest、`skill_load` 和 sandbox allowlist 同时指向用户指定版本，才是完成条件。
