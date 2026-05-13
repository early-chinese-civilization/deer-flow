# Skills 新设计

日期：2026-05-12

状态：`feature/skill-version-new` 终态收口入口；当前用于后续 task 拆分，未进入实现。

## 用途

本目录是 `feature/skill-version-new` 的新设计入口，用来沉淀新的业务语义、稳定终态和后续 task 拆分依据。

当前唯一终态口径是：

1. `skill.id` 是 UUID，表达稳定 Skill 身份。
2. `skill_version` 不能独立于 `skill` 存在；版本身份是复合键 `(skill_id, version_number)`。
3. OSS 内容目录是 `.deer-flow/skills/{skill_id}/{version_number}/`。
4. 默认聊天不是 default Agent；`thread.agent_id = null` 表示默认聊天。
5. `thread.agent_id` 非空表示绑定用户自定义 Agent。
6. 默认聊天启用的系统 Skill 由平台级 `config.yaml` 配置决定。
7. 该配置面向所有用户，只允许引用内部系统用户拥有的 Skill；不产生 `skill_installation`、`install_origin` 或启用关系表。
8. 自定义 Agent 仍走业务链路：`Thread(agent_id) -> Agent -> agent_skills -> skill_installations -> skill_versions -> 派生目录 .deer-flow/skills/{skill_id}/{version_number}/`。
9. 系统 Skill 和社区 Skill 是同一套 Skill 模型；系统 Skill 是内部系统用户拥有的普通 Skill。
10. fork、download、manifest JSON 核心真相、public/custom/name-only 扫描、default Agent、`agent.kind=default/custom` 都不是终态。
11. 表内不存 `oss_path` / `storage_uri`；Skill 内容路径只能由 `(skill_id, version_number)` 派生。
12. `skill_releases` / release 语义保留；`skill_versions` 是不可变内容版本，`skill_releases` 是某个 `(skill_id, version_number)` 的发布 / 公开 / 审核可见性。
13. 发现、install、update 只选择 `status="published"` 的 release；runtime 已解析出具体 `(skill_id, version_number)` 后不通过 release 找目录。

命名收口说明：旧口径 `skill_users` / `skill_agent` 名字不清晰，终态采用 `skill_installations` / `agent_skills`，旧字段 `skill_user_id` 终态采用 `skill_installation_id`。代码即文档；旧名只允许出现在改名说明、历史问题或待删除语境。

## 资料优先级

发生冲突时按下面顺序判断：

1. [00-terminal-state.md](00-terminal-state.md) 中的终态总览。
2. [flows/01-db-er-design.md](flows/01-db-er-design.md)、[flows/02-agent-runtime-design.md](flows/02-agent-runtime-design.md)、[flows/03-core-relationship-diagrams.md](flows/03-core-relationship-diagrams.md) 中的核心关系图。
3. [11-current-vs-terminal-baseline.md](11-current-vs-terminal-baseline.md) 中的当前代码现状与终态差距基线。
4. [08-open-decisions.md](08-open-decisions.md) 中尚未关闭的高影响决策。
5. 用户在当前 brainstorm 中补充的明确业务语义。
6. 当前代码和测试事实，只用于判断现状和迁移成本。
7. `/Users/sayori/Desktop/work/docs/skills-version` 下的高优先级整理资料。
8. `docs-qy/skills-design` 下的旧设计资料。

`docs-qy/skills-design` 视为归档和旧状态参考，不再作为 `feature/skill-version-new` 的目标口径。

## 工作规则

1. 在用户明确说“结束设计描述”之前，只做设计捕获和文档起草，不进入实现。
2. 用户每描述一个模块，就同步更新本目录文档。
3. 新文档只记录目标终态和必要迁移约束，不复述旧方案的历史过程。
4. 旧词如果必须出现，必须明确标成“当前代码待删除”或“历史问题”，不能看起来像终态。
5. 最终从本目录终态描述反推出 implementation tasks、test tasks、migration tasks 和 docs/spec sync tasks。
6. 每个核心变更都要覆盖两条主链路：业务链路和 Agent/runtime 链路。
7. 前端不是这次 redesign 的主轴，只作为业务状态展示、操作入口和必要文案/API contract 跟随调整。

## 文档索引

1. [00-terminal-state.md](00-terminal-state.md)：新终态总览和任务拆分依据。
2. [01-install-only.md](01-install-only.md)：移除 fork/download，只留下平台内 install 语义。
3. [02-immutability-without-manifest.md](02-immutability-without-manifest.md)：用表结构和目录映射保证不可变性，不以 manifest JSON 作为核心模型。
4. [03-current-chain-impact-map.md](03-current-chain-impact-map.md)：当前代码链路和受影响模块清单。
5. [04-oss-skill-storage.md](04-oss-skill-storage.md)：OSS `.deer-flow/skills` 目录职责和终态收口。
6. [05-unified-published-skill-model.md](05-unified-published-skill-model.md)：合并 System Skills 和 Community Skills，用内部系统用户表达官方来源。
7. [06-publish-review-placeholder.md](06-publish-review-placeholder.md)：二期社区发布审核占位设计。
8. [07-default-agent-conversation.md](07-default-agent-conversation.md)：默认聊天不再建模为 default Agent。
9. [08-open-decisions.md](08-open-decisions.md)：必须回到用户确认的高影响不确定项。
10. [09-follow-up-task-map.md](09-follow-up-task-map.md)：从终态反推的后续任务拆分草案。
11. [10-default-system-skill-install.md](10-default-system-skill-install.md)：默认聊天系统 Skill 平台配置；文件名沿用历史编号，正文不采用默认安装模型。
12. [11-current-vs-terminal-baseline.md](11-current-vs-terminal-baseline.md)：当前代码现状与终态差距基线；后续 migration/code agent 必读。
13. [flows/01-db-er-design.md](flows/01-db-er-design.md)：终态 DB ER 和平台配置边界。
14. [flows/02-agent-runtime-design.md](flows/02-agent-runtime-design.md)：默认聊天与自定义 Agent 的 runtime 解析。
15. [flows/03-core-relationship-diagrams.md](flows/03-core-relationship-diagrams.md)：核心关系图。
