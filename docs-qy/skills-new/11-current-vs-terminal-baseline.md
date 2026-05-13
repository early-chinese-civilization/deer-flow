# 当前代码与终态基线

日期：2026-05-13

状态：migration baseline。后续实现、review、验收 agent 必须先读本文，再进入具体代码。

## 用途

本文固定一个核心判断：

> 当前代码只代表现状和迁移输入，不代表终态；终态以 `docs-qy/skills-new/**` 和根目录 `DeerFlow数据库ER图.md` 为准。

这不是新的设计分支，而是把 2026-05-13 对当前代码的调研结果沉淀成后续实现基线。后续 agent 不应再把当前 `skill_definitions`、`skill_versions.id`、`artifact_uri`、`skill_installs.current_version_id`、`RuntimeManifest` 或 fork/download 代码理解为目标模型。

## 终态真源

1. `docs-qy/skills-new/README.md`
2. `docs-qy/skills-new/00-terminal-state.md`
3. `docs-qy/skills-new/flows/01-db-er-design.md`
4. `docs-qy/skills-new/flows/02-agent-runtime-design.md`
5. `docs-qy/skills-new/flows/03-core-relationship-diagrams.md`
6. `DeerFlow数据库ER图.md`

如果当前代码、旧测试、`.trellis/spec` 或旧 `docs-qy/skills-design` 与这些真源冲突，先按真源判断；再决定是否需要同步 spec、测试或实现。

## 当前代码现状

当前实现是一个 Skill version 中间态：

1. 当前稳定身份近似在 `skill_definitions.id BIGINT`。
2. 当前旧 `skills.id BIGINT` 仍混合用户 row、public latest row、catalog row、路径 row。
3. 当前 `skill_versions` 有独立 `id BIGINT`，并保存 `skill_definition_id`、`version_number`、`artifact_uri`。
4. 当前 `skill_installs` 通过 `installed_version_id` / `current_version_id` 指向 `skill_versions.id`。
5. 当前 `skill_releases` 仍保存 `release_version`、`artifact_path`、`source_skill_id`、`published_skill_id`、`skill_version_id`。
6. 当前 `agents_skills` 同时支持 legacy `skill_id`、install-backed `skill_install_id`、direct system `system_skill_definition_id` / `system_skill_version_id`。
7. 当前 fork/download 是真实行为：`pending_skill_fork_claims`、`/fork-package`、`/download`、fork metadata、public latest copy 都还存在。
8. 当前 runtime descriptor 仍携带 `skill_definition_id`、`skill_version_id`、`skill_install_id`、system IDs、`artifact_uri`。
9. 当前默认聊天没有从 `config.yaml default_chat.system_skills` 加载系统 Skill；no-agent runtime 当前是空 Skill 列表。
10. 当前 frontend/types/tests 仍编码 `skill_definition_id`、`skill_version_id`、`skill_install_id`、fork/download、`file_path`、`custom/*`、artifact 路径。

## 终态目标

1. `skills.id UUID` 是稳定 Skill 身份。
2. `skill_versions` 的版本身份是 `(skill_id, version_number)`，不是独立 `skill_version_id`。
3. Skill 内容目录只由 `(skill_id, version_number)` 派生为 `.deer-flow/skills/{skill_id}/{version_number}/`。
4. `skill_releases` 表示 exact `(skill_id, version_number)` 的发布、公开、审核可见性；discovery/install/update 只选择 `status="published"`。
5. `skill_installations` 是用户可用关系，保存当前 `skill_id + version_number`。
6. 自定义 Agent runtime 链路是 `Thread -> Agent -> agent_skills -> skill_installations -> skill_versions -> 派生目录`。
7. 默认聊天是 `thread.agent_id = null + config.yaml default_chat.system_skills`；不创建 Agent、`skill_installation` 或 `agent_skills`。
8. fork/download/public/custom/name-only/runtime-manifest-as-core-truth 都不是终态。

## 差距矩阵

| 领域 | 当前现状 | 终态目标 | 开始实现时的含义 |
| --- | --- | --- | --- |
| Skill identity | `skill_definitions.id BIGINT` 是当前稳定身份；旧 `skills.id BIGINT` 仍是路径/展示/安装输入 | `skills.id UUID` 是稳定身份 | 先确定 `skill_definitions -> skills` 的迁移方式；旧 `skills` 是迁移输入和删除对象 |
| Version identity | `skill_versions.id BIGINT` 被 install/release/runtime 引用 | `(skill_id, version_number)` 是版本身份 | 先添加并回填 `skill_versions.skill_id`，再改 FK 消费方 |
| Storage path | `skills.file_path`、`skill_versions.artifact_uri`、`skill_releases.artifact_path`、`public/*`、`{user_id}/*`、`artifacts/skills/*` | `.deer-flow/skills/{skill_id}/{version_number}/` 派生目录；DB 不保存路径事实 | 删除路径字段前必须有目录迁移/校验策略 |
| Install | `skill_installs.current_version_id -> skill_versions.id` | `skill_installations.version_number` 与同一 `skill_id` 组成当前版本选择 | 由 `current_version_id` 回填 `(skill_id, version_number)` 后再重连 Agent binding |
| Release | release 有 `release_version`、`artifact_path`、`published_skill_id`、`skill_version_id` | release 是 exact `(skill_id, version_number)` 的可见性状态 | 需要决定旧 release 事件历史是否另建 audit/history |
| Agent binding | `skill_id`、`skill_install_id`、direct system version 都可绑定 | 自定义 Agent 绑定 `skill_installation_id` | 先迁移 install-backed rows；system direct binding 迁到默认 config 或显式 install 路径 |
| Default chat | no-agent runtime 当前返回空 Skill | `thread.agent_id = null` 加载平台配置的系统 Skill | 需要先有系统用户和 terminal Skill identity |
| Runtime descriptor | descriptor 携带旧 IDs 和 `artifact_uri`；RuntimeManifest 持久化 | descriptor 最小为 `skill_id`、`version_number`、`file_manifest_hash`、`virtual_path` | runtime rewrite 依赖 schema 和 storage mapping |
| Fork/download | route/table/UI/test 都存在 | 终态删除 fork/download 产品语义 | 不先删 route；等 install/update 替代路径可用后迁移窗口内禁用或删除 |
| Frontend/tests | 仍按旧 numeric IDs、fork/download、artifact paths 断言 | 跟随 UUID `skill_id`、`version_number`、install/update 语义 | 后端 schema/API 稳定后统一改前端和测试 |

## 推荐起步顺序

不要从 runtime、frontend 或 route 删除开始。先做身份映射。

1. 决定物理表策略：把当前 `skill_definitions` 迁成终态 `skills`，旧 `skills` 作为迁移输入和待删除对象；或先 side-by-side 建 terminal `skills`，再切换。
2. 决定 UUID 策略：现有 stable Skill 如何得到 `skills.id UUID`。
3. 建立/保护内部系统用户：`users.external_auth_id = "system:deerflow"`。
4. 添加并回填 terminal identity：
   - terminal `skills.id UUID`
   - `skill_versions.skill_id`
   - `(skill_id, version_number)` 约束
5. 从 `skill_installs.current_version_id` 回填 `skill_installations.skill_id + version_number`。
6. 从 `skill_releases.skill_version_id` 回填 `skill_releases.skill_id + version_number`。
7. 只有这些稳定后，再改 Agent binding、runtime descriptor、storage path derivation、API、frontend 和测试。

## 编码前必须确认的决策

1. **物理表计划**：终态 `skills` 是否由当前 `skill_definitions` rename/rebuild 而来；旧 `skills` 如何迁移、归档或删除。
2. **UUID 生成策略**：现有 Skill identity 使用随机 UUID、namespace deterministic UUID，还是已知系统 Skill 固定 seed UUID。
3. **Release 历史策略**：终态 ER 是每个 `(skill_id, version_number)` 一条 release visibility；如果旧 release event history 要保留，需单独 audit/history 模型。
4. **Storage 迁移策略**：DB migration 是否同步移动对象目录，还是单独数据迁移/校验任务负责 `.deer-flow/skills/{skill_id}/{version_number}/`。
5. **迁移窗口 API 策略**：`/download`、`/check-download`、`/fork-package`、archive install、upload 等旧入口在替换期间是返回明确移除错误、转发到新入口，还是保留只读兼容。

## 后续 agent 执行规则

1. 开始任何 Skill migration/code task 前，先读本文。
2. 遇到当前代码与终态文档冲突时，当前代码只能解释“为什么要迁移”，不能反向证明终态错误。
3. 不要把 `skill_definitions`、`skill_versions.id`、`artifact_uri`、`skill_installs.current_version_id`、`system_skill_version_id` 或 RuntimeManifest 写成新实现目标。
4. 如果实现发现本文与 `docs-qy/skills-new/**` 或 `DeerFlow数据库ER图.md` 冲突，以后两者为准，并更新本文。
