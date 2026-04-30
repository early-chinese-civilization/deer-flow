# Skills Design Docs

日期：2026-04-30

状态：文档入口

## 目录说明

这组文档用于推进 DeerFlow Skills 从“public latest + custom copy + package_version”迁移到 SkillHub、平台版本、安装态、Runtime Manifest 和不可变 Artifact Store。

新的目录职责如下：

1. [plan](plan/roadmap.md)：当前 lead 决策、roadmap、迁移计划、最大测试实现计划和验收约束。后续执行和迁移以这里为入口。
2. [design](design/01-product-contract.md)：产品契约、边界、当前 gap、目标领域模型、前端面和运行时设计。
3. [user-test](user-test/01-skills-user-flow-and-acceptance.md)：Skills 用户交互与测试流程，用来验证安装、绑定、运行和手动更新主链路。
4. [explorer](explorer/skill-market-runtime-manifest-research.md)：外部机制调研和目标架构输入。

## 推荐入口

如果你要执行后续实现，先读：

1. [plan/11-runtime-manifest-lead-decision.md](plan/11-runtime-manifest-lead-decision.md)
2. [plan/12-user-flow-max-test-implementation-plan.md](plan/12-user-flow-max-test-implementation-plan.md)
3. [plan/roadmap.md](plan/roadmap.md)
4. [plan/06-migration-plan.md](plan/06-migration-plan.md)

如果你要做产品或前端迭代，先读：

1. [design/01-product-contract.md](design/01-product-contract.md)
2. [user-test/01-skills-user-flow-and-acceptance.md](user-test/01-skills-user-flow-and-acceptance.md)
3. [design/07-frontend-product-surface.md](design/07-frontend-product-surface.md)

如果你要继续 runtime / sandbox / tool 设计，先读：

1. [plan/11-runtime-manifest-lead-decision.md](plan/11-runtime-manifest-lead-decision.md)
2. [design/09-agent-skill-runtime-scheduling.md](design/09-agent-skill-runtime-scheduling.md)
3. [design/10-runtime-manifest-and-artifact-store.md](design/10-runtime-manifest-and-artifact-store.md)
4. [explorer/skill-market-runtime-manifest-research.md](explorer/skill-market-runtime-manifest-research.md)
