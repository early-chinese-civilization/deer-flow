# Skills Design Roadmap

日期：2026-04-29

状态：历史 roadmap + 当前入口指引；2026-05-11 需先读当前代码状态

## 2026-05-11 状态校准

当前代码已经落地 `SkillDefinition`、`SkillVersion`、`SkillInstall`、`skill_releases.skill_version_id`、`agents_skills.skill_install_id`、System Skill direct binding、`runtime_manifests`、manifest-backed `skill_load` / sandbox bundle 和 fork claim 机制。

因此，本文件早期关于 SkillVersion、SkillInstall、Agent 版本绑定和 Runtime Manifest 尚未落地的判断是 2026-04-29 的历史 roadmap，不再是当前代码现实。

当前继续工作时按这个顺序：

1. 读 [../design/00-current-code-status.md](../design/00-current-code-status.md) 确认当前代码事实。
2. 用 [../design/04-current-implementation-gap.md](../design/04-current-implementation-gap.md) 看剩余缺口。
3. 用 [12-user-flow-max-test-implementation-plan.md](12-user-flow-max-test-implementation-plan.md) 继续补完整 v2/update max-flow。

## 这组文档解决什么

这组文档用于把 DeerFlow 的 Skills 功能从当前的“public latest + custom copy + package_version”雏形，推进到面向普通用户的 SkillHub、平台版本、安装态、手动更新模型。

读者是接下来探索或实现该功能的 agent、产品、设计、前端、后端和测试同学。

读完后应该能做的事：

1. 知道当前产品愿景是什么。
2. 知道当前代码已经实现了什么。
3. 知道愿景和实现之间的差距。
4. 知道下一步应该优先探索和改哪里。
5. 避免继续沿用“版本来自 Skill 内容字段”的旧口径。

## 核心结论

版本代表 Skill 内容版本，由平台生成、保存和展示。用户不能通过 Skill 内容里的 `version` 字段改写平台版本。

当前实现已经有 Skills API、`SkillDefinition`、`SkillVersion`、`SkillInstall`、`SkillRelease`、`AgentSkill` install/system binding、Runtime Manifest、上传、发布、安装、fork package、前端 Gallery 和部分 runtime/e2e 证据。这些是继续收口 v2/update max-flow 的底座。

2026-04-29 时记录的旧结构缺口中，平台版本、安装态、Agent install binding、System direct binding、Runtime Manifest 和 sandbox bundle 已经有主体实现。仍要继续收口的是 public/custom/name-only 兼容债、前端边角文案、同名来源测试和完整 v2/update 最大验收。

【关键点】当前代码已经按 Runtime Manifest 和不可变 Artifact Store 前进。后续重点不是重新设计这些对象，而是修复存储阻塞、补完整 v2/update 最大验收、继续清理 legacy route/name/copy 文案和兼容路径。

【决策入口】调研完成后的目标方案以 [11-runtime-manifest-lead-decision.md](11-runtime-manifest-lead-decision.md) 为准。10 号文档解释关键架构问题，explorer 文档解释外部调研输入，11 号文档负责拍板后续实现口径。

## 文档地图

| 文档 | 只回答什么问题 | 适合谁先读 |
| --- | --- | --- |
| [../design/00-current-code-status.md](../design/00-current-code-status.md) | 当前代码已经实现什么、哪些历史口径已过时、哪些 max-flow 证据未完成 | 所有人 |
| [11-runtime-manifest-lead-decision.md](11-runtime-manifest-lead-decision.md) | 调研后的目标方案决策总纲：哪些问题已拍板、实现必须服从哪些不变量 | 后端、调度、sandbox、前端、测试、接手 agent |
| [12-user-flow-max-test-implementation-plan.md](12-user-flow-max-test-implementation-plan.md) | 如何把用户交互流程当成最大测试，按安装、绑定、运行、手动更新拆具体实现任务 | 产品、设计、前端、后端、runtime、sandbox、测试 |
| [06-migration-plan.md](06-migration-plan.md) | 如何从当前实现分阶段迁移到目标模型 | 后端、前端、项目推进 |
| [08-validation-and-open-questions.md](08-validation-and-open-questions.md) | 哪些测试要保留、改写、新增，MVP 和待确认问题是什么 | 测试、产品、实现 agent |
| [../user-test/01-skills-user-flow-and-acceptance.md](../user-test/01-skills-user-flow-and-acceptance.md) | 普通用户如何安装、绑定、运行和手动更新 Skill，以及如何验收 Agent 真的调用到 Skill 本体 | 产品、设计、前端、后端、测试 |
| [../design/01-product-contract.md](../design/01-product-contract.md) | 普通用户视角下，Skill、SkillHub、平台版本、官方/社区/我的/已安装 Skill 分别是什么 | 所有人 |
| [../design/03-boundary-rules.md](../design/03-boundary-rules.md) | 上传、绑定、发布、安装、更新、回滚、安全等边界如何处理 | 产品、后端、测试 |
| [../design/04-current-implementation-gap.md](../design/04-current-implementation-gap.md) | 当前代码真实模型是什么，哪些能复用，哪些必须改 | 后端、测试、接手 agent |
| [../design/05-target-domain-model.md](../design/05-target-domain-model.md) | 目标领域模型需要哪些对象和关系 | 后端、架构、测试 |
| [../design/07-frontend-product-surface.md](../design/07-frontend-product-surface.md) | 前端信息架构和页面状态应如何改 | 前端、设计 |
| [../design/09-agent-skill-runtime-scheduling.md](../design/09-agent-skill-runtime-scheduling.md) | Agent 运行时如何从绑定解析到可读 Skill artifact，以及当前 OSS scope 模型缺什么 | 后端、调度、sandbox、实现 agent |
| [../design/10-runtime-manifest-and-artifact-store.md](../design/10-runtime-manifest-and-artifact-store.md) | Runtime Manifest、不可变 Artifact Store 和 Agent 层验收标准是什么 | 调研 agent、后端、调度、sandbox、测试 |
| [../explorer/skill-market-runtime-manifest-research.md](../explorer/skill-market-runtime-manifest-research.md) | 主流 Skill / Plugin / Agent marketplace 如何处理版本、安装态、hash、更新和运行时授权 | 调研 agent、架构、后端、sandbox、测试 |

## 推荐阅读路径

产品对齐：

1. [../design/00-current-code-status.md](../design/00-current-code-status.md)
2. [../design/01-product-contract.md](../design/01-product-contract.md)
3. [../user-test/01-skills-user-flow-and-acceptance.md](../user-test/01-skills-user-flow-and-acceptance.md)
4. [12-user-flow-max-test-implementation-plan.md](12-user-flow-max-test-implementation-plan.md)
5. [../design/03-boundary-rules.md](../design/03-boundary-rules.md)
6. [08-validation-and-open-questions.md](08-validation-and-open-questions.md)

后端探索：

1. [../design/00-current-code-status.md](../design/00-current-code-status.md)
2. [11-runtime-manifest-lead-decision.md](11-runtime-manifest-lead-decision.md)
3. [12-user-flow-max-test-implementation-plan.md](12-user-flow-max-test-implementation-plan.md)
4. [../design/04-current-implementation-gap.md](../design/04-current-implementation-gap.md)
5. [../design/05-target-domain-model.md](../design/05-target-domain-model.md)
6. [../design/09-agent-skill-runtime-scheduling.md](../design/09-agent-skill-runtime-scheduling.md)
7. [../design/10-runtime-manifest-and-artifact-store.md](../design/10-runtime-manifest-and-artifact-store.md)
8. [../explorer/skill-market-runtime-manifest-research.md](../explorer/skill-market-runtime-manifest-research.md)
9. [06-migration-plan.md](06-migration-plan.md)
10. [08-validation-and-open-questions.md](08-validation-and-open-questions.md)

前端探索：

1. [../design/00-current-code-status.md](../design/00-current-code-status.md)
2. [../design/01-product-contract.md](../design/01-product-contract.md)
3. [../user-test/01-skills-user-flow-and-acceptance.md](../user-test/01-skills-user-flow-and-acceptance.md)
4. [12-user-flow-max-test-implementation-plan.md](12-user-flow-max-test-implementation-plan.md)
5. [../design/07-frontend-product-surface.md](../design/07-frontend-product-surface.md)

测试改造：

1. [../user-test/01-skills-user-flow-and-acceptance.md](../user-test/01-skills-user-flow-and-acceptance.md)
2. [12-user-flow-max-test-implementation-plan.md](12-user-flow-max-test-implementation-plan.md)
3. [08-validation-and-open-questions.md](08-validation-and-open-questions.md)
4. [../design/04-current-implementation-gap.md](../design/04-current-implementation-gap.md)
5. [../design/09-agent-skill-runtime-scheduling.md](../design/09-agent-skill-runtime-scheduling.md)
6. [11-runtime-manifest-lead-decision.md](11-runtime-manifest-lead-decision.md)
7. [../design/10-runtime-manifest-and-artifact-store.md](../design/10-runtime-manifest-and-artifact-store.md)
7. [../explorer/skill-market-runtime-manifest-research.md](../explorer/skill-market-runtime-manifest-research.md)
8. [06-migration-plan.md](06-migration-plan.md)

## Agent 探索锚点

优先搜索这些符号和概念，而不是从全仓库漫游：

1. `publish_skill`
2. `download_skill`
3. `upload_skills`
4. `check_skill_upload`
5. `Skill`
6. `SkillRelease`
7. `SkillRepository`
8. `SkillReleaseRepository`
9. `AgentSkill`
10. `replace_agent_skills`
11. `get_runtime_agent_bundle`
12. `SkillsGallery`
13. `package_version`
14. `release_version`
15. `public latest`
16. `build_private_skill_file_path`
17. `build_public_skill_file_path`
18. `derive_skill_scope_from_runtime`
19. `skill_load`
20. `virtual_path`
21. `file_path`
22. `Runtime Manifest`
23. `Artifact Store`
24. `content_hash`
25. `skill_version_id`

旧测试文档仍有参考价值，但它们以 `SKILL.md version` 和 `package_version` 为核心，属于旧实现口径。后续实现应以本目录文档为准。
