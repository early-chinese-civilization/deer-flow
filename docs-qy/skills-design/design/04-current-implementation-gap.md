# Current Implementation Gap

日期：2026-05-11

状态：当前代码差距说明。旧的 “public latest + custom copy + package_version” 描述已经不再代表当前主线；历史口径如需追溯，先读 [00-current-code-status.md](00-current-code-status.md)。

## 文档目的

这份文档只回答：2026-05-11 的代码已经实现了什么、哪些兼容路径仍会误导、哪些最大验收还没有完成。

当前事实优先级：代码和测试 > `/Users/sayori/Desktop/work/docs` > 本目录历史设计文档。

## 当前实现一句话

当前实现已经从旧的 `skills.id + file_path + package_version` 主模型，演进到：

```text
SkillDefinition
  -> SkillVersion
  -> SkillRelease
  -> SkillInstall
  -> AgentSkill install/system binding
  -> RuntimeManifest
  -> prompt / skill_load / sandbox bundle
```

新 runtime 真相是 `SkillVersion.artifact_uri` 和 Runtime Manifest，不是 `public latest`、用户目录 copy、`custom/`、Skill name 或文件系统扫描。

## 已经具备的能力

### 平台版本和 artifact

- 上传/安装会创建或复用 `SkillDefinition`。
- 不同内容在同一 definition 下生成递增 `SkillVersion.version_number`。
- 相同内容通过 `content_hash` 复用已有 `SkillVersion`。
- `SKILL.md` 的 `version` 只保存到 `source_package_version`，不是平台版本。
- `SkillVersion.artifact_uri` 指向 `artifacts/skills/<definition_id>/v<version>-<hash>/<skill_name>`。
- Runtime resolver 会校验 `file_manifest_hash`，不只信任路径。

### SkillHub install/update/publish

- Community install 使用兼容路由 `POST /api/skills/{name}/download`，但实际写 `SkillInstall`；用户文案应是“安装”。
- Install/check/update 路径都支持 `skill_definition_id` / `skill_install_id`，避免同名来源混淆。
- `update-install/preview` 能返回 target version、状态、发布信息和受影响 Agent。
- `update-install` 显式切换 `SkillInstall.current_version_id`。
- Publish 发布当前用户拥有或 fork 后拥有的 `SkillVersion`，并创建 `SkillRelease`；它不会改变其他用户已安装版本。
- 安装来的 Community Skill 不能直接作为原作者身份发布；必须先形成当前用户拥有的 fork/新 definition。

### System Skills

- System Skill 不要求创建 per-user `SkillInstall`。
- Agent 可通过 `system_skill_definition_id` / `system_skill_version_id` 直接绑定具体系统版本。
- System Skill 不应暴露 install 或 editable ZIP download/fork action。

### Fork/download editable package

- 真正的“下载”动作是 `POST /api/skills/{name}/fork-package`。
- 后端创建 `pending_skill_fork_claims`，ZIP 中写 `.deerflow/fork.json` sidecar。
- 上传时只有通过 server-side claim 校验才会分类为 `source_type="fork"`。
- 未修改 fork 的发布会按记录的 source version hash 被 hard-block。
- 当前 fork 是 claim + sidecar + anti-copy guard 的妥协态，不是完整 fork graph、merge、rebase 或 upstream update 模型。

### Agent 和 Runtime Manifest

- Agent create/update 兼容 `skills` name，但新路径应提交 `skill_install_ids` 或 system version/definition IDs。
- 非系统 Skill runtime descriptor 来自 `AgentSkill.skill_install_id -> SkillInstall.current_version -> SkillVersion.artifact_uri`。
- System Skill runtime descriptor 来自 `AgentSkill.system_skill_version_id -> SkillVersion.artifact_uri`。
- Runtime Manifest 持久化完整 JSON 和 deterministic `manifest_hash`。
- Prompt、`skill_load` 和 sandbox bundle 都应消费 manifest entry，不能各自重新解析。
- Sandbox 当前用 run-level readonly bundle 物化 manifest artifacts。

## 仍存在的兼容路径

这些路径存在，但不能作为新设计或新实现入口：

- `POST /api/skills/{name}/download` 的 route name 仍叫 download；产品语义是 install。
- `POST /api/skills/{name}/check-download` 的 route name 仍叫 download；产品语义是 install conflict check。
- `SkillResponse.viewer_relation` 当前仍有字面值 `downloaded`；UI 应渲染为“已安装”，不是下载。
- `skills.file_path` 仍存在，用于 catalog/user-visible/legacy materialized row。
- `agents_skills.skill_id` 仍存在，但 manifest-era runtime 不应通过 legacy skill row 解析。
- `custom/<skill_name>` 仍是 loader/client compatibility，新的 Gateway 写入不应把它当成一等路径。
- Name-only Agent binding、install 和 update 仍可兼容旧调用；同名多来源时必须报 ambiguous 并要求 identity-aware 请求。

## 当前真正缺口

1. **完整 v2/update max-flow 尚未通过浏览器验收**
   v1 install/bind/runtime 已有证据；v2 上传/发布和手动更新后 runtime-v2 被本地 `backend/.deer-flow` 挂载阻塞，不能标记为完成。

2. **存储挂载阻塞会污染 API 和 DB 事务**
   本地 `.deer-flow` 可能是 OSS/FUSE/NFS-backed mount。v2 上传曾卡在 `上传中...`，API pending，DB 出现 `idle in transaction`/lock 等症状。上传/发布路径需要 bounded storage IO 和清晰错误。

3. **follow-install-current 语义需要继续被明确接受或升级**
   当前 Agent 绑定 install。用户更新 install 后，绑定同一 install 的 Agent 后续新 run 会跟随新版。如果产品要求 existing Agent 永远 pin 到旧版本，需要新增 Agent-level version pin。

4. **前端仍需持续压低内部词泄漏**
   `download` route、`downloaded` relation、`package_version`、release metadata、definition/install IDs 都可能进入 UI。主流程文案必须保持 System/Community/My Skills、安装/已安装、平台版本、更新、下载 editable package 的用户心智。

5. **历史 docs 需要按当前入口阅读**
   2026-04-29/04-30 的阶段计划仍有参考价值，但其中“没有 SkillVersion/SkillInstall/Manifest”的陈述已经是历史，不是当前事实。

## 当前探索锚点

读代码时优先看：

- `backend/app/gateway/db/models.py`
- `backend/app/gateway/db/repository.py`
- `backend/app/gateway/routers/skills.py`
- `backend/app/gateway/routers/agents.py`
- `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`
- `backend/packages/harness/deerflow/sandbox/skill_scope.py`
- `backend/packages/harness/deerflow/sandbox/tools.py`
- `frontend/src/core/skills/type.ts`
- `frontend/src/core/skills/display.ts`
- `frontend/src/core/skills/api.ts`
- `frontend/src/core/agents/types.ts`
- `frontend/src/components/workspace/skills/skills-gallery.tsx`

相关测试：

- `backend/tests/test_runtime_manifest_versions.py`
- `backend/tests/test_agent_skill_visibility.py`
- `backend/tests/test_skills_upload_versions.py`
- `backend/tests/test_skills_api_versions.py`
- `backend/tests/test_skills_publish.py`
- `frontend/src/core/skills/display.test.ts`
- `frontend/src/core/skills/api.test.ts`
- `frontend/src/core/agents/skill-selection.test.ts`

## 一句话边界

可以说：当前代码已经有平台版本、安装态、system direct binding、Runtime Manifest 和 manifest-backed sandbox bundle。

不能说：完整 v1/v2/update 用户最大流程已经通过。
