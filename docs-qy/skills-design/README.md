# Skills Design Docs

日期：2026-04-30

状态：文档入口；2026-05-11 已补当前代码状态索引

## 当前使用规则

发生冲突时按这个优先级判断：

1. 代码和测试。
2. `/Users/sayori/Desktop/work/docs` 下 sayoriqwq 最后整理的文档。
3. 本目录历史设计资料。

继续实现或 review 前，先读 [design/00-current-code-status.md](design/00-current-code-status.md)。2026-04-29/04-30 的计划文档中，“没有 SkillVersion / SkillInstall / Runtime Manifest” 等描述是当时的历史缺口，不再代表当前代码现实。

## 目录说明

这组文档用于维护 DeerFlow Skills 从早期“public latest + custom copy + package_version”迁移到系统空间、社区空间、我的空间、平台版本、安装态、Runtime Manifest 和不可变 Artifact Store 之后的设计上下文，并继续收口尚未完成的验收和兼容债。

新的目录职责如下：

1. [plan](plan/roadmap.md)：当前 lead 决策、roadmap、迁移计划、最大测试实现计划和验收约束。后续执行和迁移以这里为入口。
2. [design](design/01-product-contract.md)：产品契约、边界、当前 gap、目标领域模型、前端面和运行时设计。
3. [user-test](user-test/01-skills-user-flow-and-acceptance.md)：Skills 用户交互与测试流程，用来验证安装到我的空间、绑定、运行、手动更新，以及作者/安装者不同视角的 UI/UX 主链路。
4. [explorer](explorer/skill-market-runtime-manifest-research.md)：外部机制调研和目标架构输入。

## 推荐入口

如果你要执行后续实现，先读：

1. [design/00-current-code-status.md](design/00-current-code-status.md)
2. [plan/11-runtime-manifest-lead-decision.md](plan/11-runtime-manifest-lead-decision.md)
3. [plan/12-user-flow-max-test-implementation-plan.md](plan/12-user-flow-max-test-implementation-plan.md)
4. [plan/roadmap.md](plan/roadmap.md)
5. [plan/06-migration-plan.md](plan/06-migration-plan.md)

如果你要做产品或前端迭代，先读：

1. [design/00-current-code-status.md](design/00-current-code-status.md)
2. [design/01-product-contract.md](design/01-product-contract.md)
3. [user-test/01-skills-user-flow-and-acceptance.md](user-test/01-skills-user-flow-and-acceptance.md)
4. [user-test/03-skillhub-author-installer-ux.md](user-test/03-skillhub-author-installer-ux.md)
5. [design/07-frontend-product-surface.md](design/07-frontend-product-surface.md)

如果你要继续 runtime / sandbox / tool 设计，先读：

1. [design/00-current-code-status.md](design/00-current-code-status.md)
2. [plan/11-runtime-manifest-lead-decision.md](plan/11-runtime-manifest-lead-decision.md)
3. [design/09-agent-skill-runtime-scheduling.md](design/09-agent-skill-runtime-scheduling.md)
4. [design/10-runtime-manifest-and-artifact-store.md](design/10-runtime-manifest-and-artifact-store.md)
5. [explorer/skill-market-runtime-manifest-research.md](explorer/skill-market-runtime-manifest-research.md)
