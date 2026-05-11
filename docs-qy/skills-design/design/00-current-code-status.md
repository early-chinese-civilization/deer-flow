# Current Skills Code Status

日期：2026-05-11

状态：当前代码事实入口

## 资料优先级

本目录是 `docs-qy/skills-design` 的设计资料。发生冲突时按下面顺序判断：

1. 代码和测试：当前项目现实。
2. `/Users/sayori/Desktop/work/docs`：sayoriqwq 最后整理的产品/架构口径。
3. `docs-qy/skills-design`：历史设计、计划和验收资料。

不要把 2026-04-29/2026-04-30 的“当前实现缺口”文字直接当成 2026-05-11 的代码现实。很多目标对象现在已经落地。

## 当前已落地

### 数据模型

当前代码已经有这些 Gateway 表和绑定字段：

- `skill_definitions`：稳定 Skill 身份，当前唯一身份是 `(source_type, source_identifier, name)`。
- `skill_versions`：平台生成的不可变内容版本，包含 `version_number`、`content_hash`、`file_manifest_hash`、`artifact_uri`、`source_package_version`。
- `skill_installs`：用户安装态，`current_version_id` 是用户当前运行选择。
- `skill_releases`：SkillHub 发布事件，指向具体 `skill_version_id`，发布说明在 release 上。
- `agents_skills.skill_install_id`：非系统 Skill 的 Agent 绑定入口。
- `agents_skills.system_skill_definition_id` / `system_skill_version_id`：System Skill 的直接绑定入口，不要求每个用户安装。
- `runtime_manifests.manifest_json` / `manifest_hash`：一次 run 的运行时授权快照和审计 hash。
- `pending_skill_fork_claims`：fork/export editable package 的 server-side claim。

### 文件和 artifact

当前文件层同时存在几种职责：

```text
backend/.deer-flow/skills/
  public/<skill_name>/...
  public/<owner_user_id>/<skill_name>/...
  <user_id>/<skill_name>/...
  <user_id>/definitions/<skill_definition_id>/<skill_name>/...
  artifacts/skills/<definition_id>/v<version>-<hash>/<skill_name>/...
  .runtime-skill-bundles/<manifest-hash>/<virtual-root>/...
  custom/<skill_name>/...                       # legacy compatibility only
```

当前 runtime 权威来源是 `SkillVersion.artifact_uri`，不是 `public/`、`<user_id>/`、`custom/` 或 `skills.file_path` 的 latest 语义。

### API 和产品语义

当前后端仍保留一些兼容路由名，但语义已经收敛：

- `POST /api/skills/{name}/download`：兼容路由名；实际语义是把非系统 Community Skill 安装进当前用户的 My Skills，写 `SkillInstall`，用户文案应叫“安装”。
- `POST /api/skills/{name}/check-download`：兼容路由名；实际是 SkillHub install conflict check。
- `POST /api/skills/{name}/fork-package`：真正的“下载”语义，导出带 `.deerflow/fork.json` claim sidecar 的可编辑 ZIP。
- `POST /api/skills/{name}/update-install/preview`：更新预览，返回目标版本和受影响 Agent。
- `POST /api/skills/{name}/update-install`：显式更新 `SkillInstall.current_version_id`。
- `POST /api/skills/{name}/publish`：发布当前用户拥有或 fork 后拥有的当前 `SkillVersion`，不会改变其他用户已安装版本。

System Skills 当前是直接可用/可绑定的系统资源；安装和 fork/download editable package 都会被拒绝或不应在 UI 暴露。

### Agent 和 runtime

当前非系统 Skill 的运行链路是：

```text
AgentSkill.skill_install_id
  -> SkillInstall.current_version_id
  -> SkillVersion.artifact_uri
  -> RuntimeManifest.manifest_json
  -> prompt skill section / skill_load / sandbox bundle
```

System Skill 的运行链路是：

```text
AgentSkill.system_skill_version_id
  -> SkillVersion.artifact_uri
  -> RuntimeManifest.manifest_json
  -> prompt skill section / skill_load / sandbox bundle
```

Runtime Manifest 会记录 `skill_version_id`、`skill_install_id` 或 system binding fields、`artifact_uri`、`content_hash`、`file_manifest_hash`、`virtual_path`、`source_kind`、`binding_kind` 等字段。

虚拟路径不是纯 `skill_name`。当前 install-backed path 带 install identity，例如：

```text
/mnt/skills/<skill_name>--install-<install_id>/SKILL.md
```

System path 带 system definition/version identity，例如：

```text
/mnt/skills/<skill_name>--system-<definition_id>-version-<version_id>/SKILL.md
```

Sandbox 当前采用 run-level readonly bundle，把 manifest 中的 artifact 精确复制/物化到：

```text
backend/.deer-flow/skills/.runtime-skill-bundles/<manifest-hash>/...
```

`skill_load` 和 sandbox 都应该只消费 manifest 授权路径，不能从 `public`、用户目录、`custom`、同名目录或全局扫描 fallback。

### 前端显示契约

当前 Skills API 已返回：

- `space`: `system` / `community` / `personal`
- `source_kind`: `official` / `community` / `personal` / `fork`
- `viewer_relation`: `system_available` / `official_available` / `community_available` / `downloaded` / `authored` / `authored_published` / `authored_unpublished_changes` / `update_available` / `forked`

注意：当前 API 字面值仍使用 `downloaded` 表示“从 Community 安装到 My Skills 的个人空间行”。用户文案和 UI helper 必须把它渲染成“已安装/安装态”，不能把它解释成文件下载动作。如果未来要把字面值改成 `installed`，需要前后端 contract 和测试一起改。

Agent API 仍保留 `skills: string[] | null` 兼容字段；版本感知展示应优先用 `skill_metadata`。新 Agent create/update 在可用时提交 `skill_install_ids` 或 `system_skill_version_ids` / `system_skill_definition_ids`，不要只提交 name。

## 已验证和未验证

2026-05-09 的本地 e2e 验收已经证明：

- User A 可上传并发布 v1。
- User B 可从 Community Skills 安装 v1。
- My Skills、Agent API 和 Agent 列表可显示 install/version metadata。
- User B 的 Agent 绑定 `skill_install_id` 后，runtime manifest 指向 v1 artifact。
- `skill_load` 读取 `/mnt/skills/runtime-acceptance-skill--install-13/SKILL.md`，Agent 最终回复 `SKILL_RUNTIME_OK_V1`。

尚未证明：

- v2 上传/发布成功。
- User B 不更新时仍运行 v1 的完整浏览器链路。
- 更新确认页和 `update-install` 后运行 v2 的完整浏览器链路。

未完成原因不是产品语义未定，而是本地 `backend/.deer-flow` 存储挂载阻塞：v2 上传卡在 `上传中...`，直接 API 也超时，并出现 DB `idle in transaction` / lock 等症状。

## 当前仍需谨慎的缺口

- `custom/<skill_name>`、name-only lookup、`skills.file_path`、`agents_skills.skill_id` 仍是 compatibility surface，不是新实现入口。
- `POST /api/skills/install` 的 standalone/local client 路径仍会写 `<user_id>/<skill_name>`，需要和 definition-aware upload path 区分。
- `viewer_relation="downloaded"` 是当前 API 字面值和用户文案之间的历史债，文档和 UI 都要明确“下载只用于 editable ZIP/fork export”。
- Agent 当前实现是 follow-install-current：用户更新 `SkillInstall.current_version_id` 后，绑定同一 install 的 Agent 后续新 run 会使用新版。若产品要“每个 Agent 固定版本直到逐个确认”，需要新增 Agent-level version pin 或等价模型。
- 完整 v2/update/runtime-v2 max-flow 需要在修复/替换 `backend/.deer-flow` 挂载后继续跑，不能提前标记通过。
