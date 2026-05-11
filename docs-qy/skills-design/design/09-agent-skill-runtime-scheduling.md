# Agent Skill Runtime Scheduling

日期：2026-05-11

状态：当前运行时实现说明

## 文档目的

这份文档把当前代码里的 Agent Skill 调度、Runtime Manifest、`skill_load` 和 sandbox bundle 关系说清楚。历史版本里关于 “public/user scope 是当前运行时主模型” 的描述已过时。

## 当前一句话

当前 Agent Skill runtime 已经以 Runtime Manifest 为授权真相：

```text
AgentSkill binding
  -> SkillVersion artifact
  -> RuntimeManifest
  -> prompt Skill section
  -> skill_load allowlist
  -> sandbox run-level readonly bundle
```

目录仍是存储实现，但目录不再决定业务身份、安装身份、版本身份或运行授权。

## 非系统 Skill 链路

非系统 Skill 包括用户从 Community 安装的 Skill，以及当前用户上传/创建/fork 后可绑定的 My Skills。

当前解析链路：

```text
AgentSkill.skill_install_id
  -> SkillInstall.id
  -> SkillInstall.current_version_id
  -> SkillVersion.id
  -> SkillVersion.artifact_uri
```

Resolver 生成的 runtime descriptor 至少包含：

- `name`
- `description`
- `file_path`
- `virtual_path`
- `skill_definition_id`
- `skill_version_id`
- `skill_install_id`
- `source_kind="install"`
- `binding_kind="install"`
- `version_number`
- `content_hash`
- `file_manifest_hash`
- `artifact_uri`
- `source_package_version`

模型可见路径带 install identity，避免同名 Skill 冲突：

```text
/mnt/skills/<skill_name>--install-<install_id>/SKILL.md
```

## System Skill 链路

System Skills 是平台预置能力，不要求每个用户安装。

当前解析链路：

```text
AgentSkill.system_skill_version_id
  -> SkillVersion.id
  -> SkillVersion.artifact_uri
```

System binding 也必须进入 Runtime Manifest。Descriptor 包含：

- `system_skill_definition_id`
- `system_skill_version_id`
- `skill_install_id=null`
- `source_kind="system"`
- `binding_kind="system"`

模型可见路径带 system identity：

```text
/mnt/skills/<skill_name>--system-<definition_id>-version-<version_id>/SKILL.md
```

## Runtime Manifest

每次 named Agent run 前，Gateway 会解析 Agent 的 active Skill bindings 并创建 `runtime_manifests` 行。

Manifest 记录：

- 当前用户和 Agent。
- 每个 Skill 的 definition/version/install 或 system binding identity。
- `artifact_uri`、`content_hash`、`file_manifest_hash`。
- prompt/skill_load 使用的 `virtual_path`。
- `manifest_hash`，用于 sandbox bundle scope 和审计。

Manifest 是 prompt、`skill_load` 和 sandbox 的共同输入。任一层都不应再按 name、public latest、用户目录或 filesystem scan 重新发现 Skill。

## sandbox 和 skill_load

当前 sandbox MVP 是 run-level readonly bundle：

```text
backend/.deer-flow/skills/.runtime-skill-bundles/<manifest-hash>/<virtual-root>/...
```

规则：

1. 只从 Manifest 中的 `artifact_uri` 精确读取。
2. 读取前校验 `file_manifest_hash`。
3. Artifact URI 必须在 immutable `artifacts/` scope。
4. 未授权 virtual path 读取失败。
5. `public/`、`<user_id>/`、`custom/`、same-name directory 和全局扫描都不是 fallback。

## 更新语义

当前代码是 follow-install-current：

```text
AgentSkill.skill_install_id -> SkillInstall.current_version_id
```

这意味着：

1. 发布者发布 v2，只创建新的 `SkillVersion` / `SkillRelease`，不会修改安装者的 `SkillInstall.current_version_id`。
2. 安装者未确认更新前，新 run 的 Manifest 仍指向 v1。
3. 安装者确认 `update-install` 后，`current_version_id` 切到 v2。
4. 绑定同一个 install 的 Agent 后续新 run 会生成 v2 Manifest。
5. 已经持久化的旧 Manifest 不会被改写，仍可审计为 v1。

如果产品要求“每个 Agent 绑定时固定版本，install 更新后 Agent 不跟随”，需要新增 Agent-level version pin 或等价确认模型。不要用“Manifest 是快照”来替代这个产品决策。

## 兼容残留

- `agents_skills.skill_id` 仍在表中，但 active legacy-only binding 在 manifest-era runtime 里应失败或显示 unavailable。
- `skills.file_path` 仍用于 catalog/user-visible materialized rows，不是 runtime 权威。
- `custom/<skill_name>` 是 legacy/local compatibility，不是新 Gateway runtime 入口。
- Name-only Agent create/update 仍可兼容旧调用，但同名多 install 时必须要求 `skill_install_ids`。

## 验收口径

运行成功必须同时证明：

1. Agent metadata 绑定了正确 `skill_install_id` 或 system version id。
2. Runtime Manifest 记录正确 `skill_version_id` 和 `artifact_uri`。
3. prompt 中暴露的是 Manifest `virtual_path`。
4. `skill_load` 读取的是 Manifest 授权路径。
5. sandbox bundle 来自 exact artifact，且 hash 校验通过。
6. Agent 回复体现对应版本行为，例如 `SKILL_RUNTIME_OK_V1` / `SKILL_RUNTIME_OK_V2`。

只看到 UI 显示“已安装”或 API 返回成功，不算 runtime 验收通过。
