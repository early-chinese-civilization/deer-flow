# 当前链路影响图

日期：2026-05-12

状态：当前代码链路记录，用于后续拆 task；旧词只表示当前代码待删除或历史问题。

## 用途

本文记录当前代码中的 Skill version / artifact / runtime 链路，作为新终态设计的影响面地图。

记录原则：宁愿多记，不为了节省上下文省略关键链路。后续每一个终态决策都要映射到这里，确认表结构、目录、API、默认聊天、Agent runtime、sandbox、`skill_load`、测试和迁移是否受影响。

## 新终态覆盖模型

这次 redesign 主要覆盖三条链路。

### 业务链路

业务链路包括：

1. `skill.id` UUID 稳定身份。
2. `skill_version(skill_id, version_number)` 复合身份。
3. `.deer-flow/skills/{skill_id}/{version_number}/` 不可变目录映射。
4. upload / install / update / publish。
5. release status / review placeholder。
6. `skill_installation.version_number`。
7. 自定义 Agent 的 `agent_skills` 写入。
8. fork/download/name-only/public/custom/user-dir 删除与迁移清理。
9. migration、schema preflight、业务测试。

### 默认聊天 runtime 链路

默认聊天不是 default Agent。

默认聊天链路包括：

1. `thread.agent_id = null`。
2. 平台级 `config.yaml` 的 `default_chat.system_skills`。
3. 配置项必须是内部系统用户拥有的 `(skill_id, version_number)`。
4. runtime descriptor 从配置项解析到 `.deer-flow/skills/{skill_id}/{version_number}/`。
5. prompt、sandbox、`skill_load` 只消费已校验 descriptor。

默认聊天不产生 `skill_installation`、`install_origin`、`agent_skills` 或隐藏 Agent。

### 自定义 Agent runtime 链路

自定义 Agent runtime 链路包括：

1. `thread.agent_id != null`。
2. Agent ownership 校验。
3. `agent_skills.skill_installation_id`。
4. `skill_installation.skill_id + version_number`。
5. runtime descriptor。
6. prompt 可用 Skill 注入。
7. sandbox allowlist。
8. `.runtime-skill-bundles` 或等价挂载/物化逻辑作为派生缓存。
9. `skill_load` 路径解析。
10. runtime / sandbox / `skill_load` 测试。

## 当前接近新方向的基础

当前代码已经有一部分接近“表结构 + 目录映射保证不可变性”的基础：

1. `SkillVersion` 已经是内容版本对象。
2. 当前 artifact 目录已经不是 public/latest 的简单覆盖。
3. `SkillVersion` 创建前会计算 `content_hash` 和 `file_manifest_hash`。
4. 同一个 `SkillDefinition` 下相同 `content_hash` 会复用已有 `SkillVersion`。
5. 新内容会创建新的 `version_number`。
6. `SkillInstall.current_version_id` 已经能表达“安装者当前选择哪个版本”的旧实现意图。
7. `SkillRelease.skill_version_id` 已经能表达“发布事件发布哪个版本”的旧实现意图。

这些是迁移参考，不是终态字段口径。终态要把版本引用收口为 `(skill_id, version_number)`，并把物理目录收口为 `.deer-flow/skills/{skill_id}/{version_number}/`。

## 表结构现状与终态差距

当前相关模型在 `backend/app/gateway/db/models.py`，其中多处是当前代码待删除或待迁移状态：

1. `SkillDefinition`：当前最接近终态 `skill`，但终态 `skill.id` 必须是 UUID。
2. `SkillVersion`：当前有独立 `id`、`artifact_uri`、`skill_definition_id`、`version_number`。终态版本身份改为 `(skill_id, version_number)`，不再以独立 `skill_version_id` 或 `artifact_uri` 作为事实来源。
3. `SkillInstall`：当前最接近终态 `skill_installation`，但终态不需要 `install_origin`，版本选择应表达为 `version_number`。
4. `SkillRelease`：当前有 `skill_version_id` 和 `artifact_path` 等旧字段。终态 release 指向 `(skill_id, version_number)`。
5. `AgentSkill`：当前仍同时存在旧 `skill_id`、新版 `skill_install_id`、system direct binding 字段。终态自定义 Agent 只需要 `agent_skills.skill_installation_id`。
6. `Thread.agent_id`：终态 nullable；null 表示默认聊天，非空表示自定义 Agent 聊天。
7. `RuntimeManifest`：当前有 `manifest_json` / `manifest_hash`，终态只能是非核心审计或删除对象。
8. `PendingSkillForkClaim`：fork/download 相关对象，终态删除。

## SkillVersion 创建和 artifact 映射

当前创建逻辑在 `backend/app/gateway/routers/skills.py` 的 `_ensure_skill_version_from_dir()`，当前 artifact URI 形态是：

```text
artifacts/skills/{definition_id}/v{version_number}-{content_hash[:12]}/{skill_name}
```

这是当前代码待迁移路径，不是终态。

终态写入原则：

1. 找到或创建 `skill(id UUID)`。
2. 计算 `content_hash` 和 `file_manifest_hash`。
3. 在同一 `skill_id` 下按 `(skill_id, content_hash)` 查找已有版本。
4. 没有可复用版本时生成下一个 `version_number`。
5. 写入 `.deer-flow/skills/{skill_id}/{version_number}/`。
6. 创建或确认 `skill_version(skill_id, version_number)`。

## 当前目录形态

当前代码同时存在多种目录职责：

```text
{user_id}/{skill_name}
{user_id}/definitions/{skill_definition_id}/{skill_name}
public/{owner_user_id}/{skill_name}
public/{skill_name}
artifacts/skills/{definition_id}/vN-hash/{skill_name}
artifacts/legacy/skills/{skill_id}/{skill_name}
local/{skill_name}
custom/{skill_name}
.runtime-skill-bundles/<hash>/...
```

这些都是当前代码待删除、待迁移或派生缓存语义。终态事实来源只有：

```text
.deer-flow/skills/{skill_id}/{version_number}/
```

## API 链路现状

### Upload

当前 `POST /skills/uploads` 会创建或复用 `SkillVersion`，并同时写 editable 目录。

终态需要明确区分：

1. 上传/创建 Skill 的工作区不放在 `.deer-flow/skills` 事实命名空间。
2. 进入版本体系后才写 `.deer-flow/skills/{skill_id}/{version_number}/`。
3. 包 metadata version 不决定平台 `version_number`。

### Install archive

当前 `POST /skills/install` 会把 archive 解包到用户目录再创建版本。

终态需要决定这个入口是“上传自己的 Skill 包”还是“从平台安装 Skill”。如果是上传，应纳入 upload/create；如果是 install，应不能混入本地解包/文件下载心智。

### 旧 download route

当前 `POST /skills/{name}/download` 是历史问题，终态删除。

迁移窗口内如果仍被调用，只能返回“已移除/请使用 install”的明确错误，不能执行安装、运行、复制或认领逻辑。

### Update install

当前 `POST /skills/{name}/update-install` 的方向接近终态：只更新安装者当前版本引用。

终态需要把引用从独立 version id 收口为同一 `skill_id` 下的 `version_number`。

### Publish

当前 publish 同时复制 public latest 目录。

终态删除 public latest copy 作为事实来源，不删除 release。Publish 必须先确保或创建 `skill_version(skill_id, version_number)` 和 `.deer-flow/skills/{skill_id}/{version_number}/` 内容目录，再创建或更新 `skill_releases(skill_id, version_number, status)`；发现、install、update 只选择 `status="published"` 的 release。Runtime 已经拿到具体 `(skill_id, version_number)` 后不通过 release 找目录，release 不参与路径授权。

## Agent 绑定现状

当前 `AgentSkill` 支持三种模式：

1. 旧 `skill_id`。
2. 非系统 Skill 的 `skill_install_id`。
3. System Skill 的 `system_skill_definition_id` / `system_skill_version_id`。

终态已经明确：

1. 默认聊天不走 Agent 绑定。
2. 自定义 Agent 通过 `agent_skills.skill_installation_id` 绑定用户可用 Skill。
3. system-specific direct binding 是当前代码待删除分支。
4. name-only Agent binding 不进入终态模型。
5. `skill_installation.version_number` 是自定义 Agent runtime 的版本选择来源。

## Runtime Manifest 现状

当前 Runtime Manifest 创建在 `backend/app/gateway/db/repository.py`。

生产代码中没有发现“从 DB 读取已持久化 `manifest_json` 再驱动运行时”的链路。强绑定 `manifest_json` 的主要是：

1. DB 持久化。
2. manifest hash。
3. schema preflight。
4. 测试断言。

终态应把它从核心链路移走；如保留，只能作为非核心审计记录。

## Runtime descriptor / prompt / sandbox / skill_load 现状

当前 prompt、sandbox、`skill_load` 主要依赖 gateway 注入的 `runtime_agent.skills`。

终态要把 descriptor 来源明确拆成两种：

1. 默认聊天：来自 `default_chat.system_skills` 平台配置。
2. 自定义 Agent：来自 `Thread -> Agent -> agent_skills -> skill_installations -> skill_versions`。

二者最终都解析到同一类 descriptor：

```text
skill_id
version_number
file_manifest_hash
virtual_path
```

## Name-only 和旧目录入口现状

当前仍有多个旧入口：

1. `load_skills()` 扫描 `public/`、旧 `custom/`、skills root 下其他用户/本地目录。
2. `normalize_skill_file_path()` 支持旧 path normalization。
3. Skills API 仍有按 name 兼容查找。
4. Agent create/update 仍接受 `skills: string[]`。
5. standalone client 仍用 `load_skills()` 后按 `s.name == name` 查找。

这些是当前代码待删除或迁移入口。终态不能把它们映射回新版 runtime 链路作为能力来源。

## 测试影响面

后续测试要证明：

1. `skill.id` 是 UUID。
2. 版本身份是 `(skill_id, version_number)`。
3. `.deer-flow/skills/{skill_id}/{version_number}/` 不被覆盖。
4. 同内容复用版本，新内容创建新版本号。
5. publish 指向具体 `(skill_id, version_number)`。
6. install current version 只通过 DB 引用切换。
7. 默认聊天只加载 config 中配置的系统 Skill。
8. 默认聊天不会创建 default Agent、`skill_installation` 或 `install_origin`。
9. 自定义 Agent run 解析到正确版本目录。
10. `skill_load` 只能读取授权版本路径。
11. public/custom/name-only 旧路径候补读取不会参与新版 runtime 事实来源。
