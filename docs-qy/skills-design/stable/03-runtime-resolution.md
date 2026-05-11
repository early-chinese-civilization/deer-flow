# 当前稳定现状：运行时解析

日期：2026-05-11

状态：稳定事实说明

## 资料优先级

发生冲突时，判断顺序是：

1. 当前代码和测试。
2. `/Users/sayori/Desktop/work/docs`。
3. `docs-qy/skills-design` 下的历史设计和计划文档。

本文只描述当前运行时稳定链路，不描述早期 public/custom 目录模型。

## 一句话链路

当前运行时以 Runtime Manifest 为授权真相：

```text
AgentSkill binding
  -> SkillVersion artifact
  -> RuntimeManifest
  -> prompt Skill section
  -> skill_load allowlist
  -> sandbox run-level readonly bundle
```

运行时不应从 `public`、用户目录、`custom`、同名目录或全局扫描里重新发现 Skill。

## 非系统 Skill 解析

非系统 Skill 包括用户安装的 Community Skill，以及用户自己创建/fork 后拥有的 Skill。

稳定解析链路：

```text
AgentSkill.skill_install_id
  -> SkillInstall.current_version_id
  -> SkillVersion.artifact_uri
  -> RuntimeManifest.manifest_json
```

Manifest 中至少要能追踪：

1. `skill_definition_id`
2. `skill_version_id`
3. `skill_install_id`
4. `artifact_uri`
5. `content_hash`
6. `file_manifest_hash`
7. `version_number`
8. `virtual_path`
9. `source_kind`
10. `binding_kind`

模型可见路径带 install identity，避免同名 Skill 混淆：

```text
/mnt/skills/<skill_name>--install-<install_id>/SKILL.md
```

## System Skill 解析

System Skill 不要求每个用户创建 install row。

稳定解析链路：

```text
AgentSkill.system_skill_version_id
  -> SkillVersion.artifact_uri
  -> RuntimeManifest.manifest_json
```

Manifest 中必须记录 system binding identity：

1. `system_skill_definition_id`
2. `system_skill_version_id`
3. `skill_install_id=null`
4. `source_kind="system"`
5. `binding_kind="system"`

模型可见路径带 system definition/version identity：

```text
/mnt/skills/<skill_name>--system-<definition_id>-version-<version_id>/SKILL.md
```

## Runtime Manifest

Runtime Manifest 是一次 run 的解析结果和授权快照。

稳定规则：

1. run 前由 Gateway 解析 Agent 的 active Skill bindings。
2. Manifest 持久化 `manifest_json` 和 `manifest_hash`。
3. prompt、`skill_load`、sandbox 都消费同一份 Manifest。
4. Manifest 记录的是具体 artifact 和 hash，不是 latest name。
5. 旧 Manifest 不因后续发布或更新而变化。

Manifest 的作用不是替代产品版本策略。它只能保证“这一 run 用了什么”可审计；它不能自动决定 Agent 是否要跟随 install 更新。

## Artifact 和 sandbox

当前 runtime 权威内容来自 immutable artifact：

```text
backend/.deer-flow/skills/artifacts/skills/<definition_id>/v<version>-<hash>/<skill_name>/...
```

sandbox 当前采用 run-level readonly bundle：

```text
backend/.deer-flow/skills/.runtime-skill-bundles/<manifest-hash>/<virtual-root>/...
```

稳定规则：

1. 只复制 Manifest 授权的 artifact。
2. 复制前校验 `file_manifest_hash`。
3. sandbox 中只暴露 Manifest 授权的虚拟路径。
4. 未授权路径读取失败。
5. `custom`、`public`、同名目录、用户目录都不是 fallback。

## skill_load

`skill_load` 必须遵循 Manifest allowlist。

稳定规则：

1. 只能读取 Manifest 中的 `virtual_path`。
2. 不能通过 skill name 自动寻找同名目录。
3. 不能因为 install 版本更新就改变已经生成的旧 Manifest。
4. 错误信息应能解释“未授权/不存在/不可用”，而不是静默 fallback。

## 当前更新语义

当前稳定实现是 follow-install-current：

```text
AgentSkill.skill_install_id
  -> SkillInstall.current_version_id
```

这意味着：

1. 发布 v2 不会自动影响安装者。
2. 安装者不确认更新时，新 run 仍解析到 v1。
3. 安装者确认更新后，`current_version_id` 切到 v2。
4. 绑定同一个 install 的 Agent 后续新 run 会解析到 v2。
5. 已持久化的旧 run Manifest 仍可审计为 v1。

如果未来产品要求“Agent 绑定时固定版本，install 更新后 Agent 不跟随”，需要新增 Agent-level version pin 或等价确认模型。

## 验收口径

运行时验收不能只看 UI 或安装接口成功。

至少要同时证明：

1. Agent metadata 绑定了正确 `skill_install_id` 或 system version id。
2. Runtime Manifest 记录了正确 `skill_version_id` 和 `artifact_uri`。
3. prompt 暴露的是 Manifest `virtual_path`。
4. `skill_load` 读取的是 Manifest 授权路径。
5. sandbox bundle 来自 exact artifact，且 hash 校验通过。
6. Agent 回复体现对应版本行为，例如 `SKILL_RUNTIME_OK_V1` / `SKILL_RUNTIME_OK_V2`。
