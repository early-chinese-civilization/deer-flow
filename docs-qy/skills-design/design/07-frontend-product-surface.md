# Frontend Product Surface

日期：2026-04-29

状态：前端信息架构；2026-05-11 主 Skills Gallery 已有三入口实现，本文作为剩余 UX/文案约束

## 2026-05-11 当前代码校准

`frontend/src/components/workspace/skills/skills-gallery.tsx` 当前已经有 System / Community / My Skills 三个入口，并通过 `src/core/skills/display.ts` 使用 `space`、`source_kind`、`viewer_relation`、platform version、install/update state 来派生卡片状态。

因此，下文记录的是早期两技术桶信息架构的历史问题，不再代表主 Skills Gallery。仍需继续关注的是：

1. settings/边角页面是否仍有 public/custom 兼容过滤。
2. 用户文案是否还把 install/add-to-My-Skills 叫 download。
3. `viewer_relation="downloaded"` 是否只作为 API legacy alias，被 UI 渲染成“已安装”。
4. Agent create/edit 是否优先提交 `skill_install_ids` / system IDs，而不是只提交 name。
5. 更新确认、受影响 Agent、不可用状态和鼠标点击提交流程是否都经过验收。

## 文档目的

这份文档只描述前端页面和用户可见状态应该如何调整。它不讨论后端表结构，不写迁移步骤。

读完后应该能设计 SkillHub、我的 Skills、Skill 详情页和 Agent 绑定区。

## 历史前端问题与剩余风险

早期 Skills Gallery 的旧模型问题是：

1. 早期 public/custom 两个技术桶不足以表达系统、社区、我创建的、我安装的。主 Skills Gallery 已修正为三入口；其他页面仍需检查。
2. “Download”不是普通用户心智中的安装。
3. 早期发布弹窗曾把版本来源描述成包内 metadata，与目标产品口径相反；当前和后续 UI 都必须只展示平台版本。
4. Badge 展示 package/release，暴露内部实现。
5. 没有 Skill 详情页、版本历史、更新确认页。
6. Agent 创建页只显示 Skill 名称列表，用户看不到版本、来源、更新状态。

## 目标页面结构

第一版至少需要：

1. System Skills：系统预置、直接可用、不可安装、不可下载。
2. Community Skills：社区、可安装、已安装、有更新。
3. 我的 Skills：我创建的、我安装的、已发布、有更新。
4. Skill 详情页：描述、来源、版本历史、安装/发布/下载。
5. Agent Skills 区域：已绑定 Skill、当前版本、是否有更新、解绑。
6. 更新确认页：当前版本、新版本、更新说明、受影响 Agent。

## System Skills 列表

每个系统 Skill 卡片至少展示：

1. 名称。
2. 简短描述。
3. 来源：系统。
4. 当前平台版本。
5. 直接可用状态。

主操作：

1. 用于 Agent / 选择到 Agent。
2. 查看。

禁止出现：

1. 安装。
2. 下载。
3. 已安装。
4. 加入我的 Skills。

## Community Skills 列表

每个 Skill 卡片至少展示：

1. 名称。
2. 简短描述。
3. 来源：社区。
4. 作者。
5. 当前公开版本。
6. 更新时间。
7. 安装状态：未安装、已安装、可更新。

主操作：

1. 未安装：安装。
2. 已安装且无更新：查看。
3. 已安装且有更新：查看更新。
4. 符合条件的社区 Skill：下载。

## Skill 详情页

详情页至少包含：

1. Skill 名称和描述。
2. 作者与来源。
3. 当前公开版本。
4. 更新说明。
5. 版本历史。
6. 安装按钮。
7. 下载按钮。
8. 权限或安全提示。

不要默认展示完整内部说明内容。是否允许查看源内容需要单独产品决策，尤其涉及社区 Skill 的安全和作者权益。

## 我的 Skills 页面

我的 Skills 至少展示：

1. 我上传的 Skill。
2. 我安装的 Skill。
3. 当前版本。
4. 是否已绑定 Agent。
5. 是否已发布。
6. 是否有更新。

过滤器建议：

1. 全部。
2. 我创建的。
3. 我安装的。
4. 已发布。
5. 有更新。

## 发布弹窗

发布弹窗必须说明：

1. 将发布哪个 Skill。
2. 将发布哪个平台版本。
3. 发布后别人可以安装。
4. 发布后的版本快照不可被原地修改。
5. 更新说明会展示给 SkillHub 用户。

发布弹窗不能再说：

1. 版本来自 `SKILL.md`。
2. 发布为 `public latest`。
3. 用户需要理解 package version。

## 更新确认页

更新确认页用于用户 B 手动更新已安装 Skill。

必须展示：

1. 当前已安装版本。
2. 可更新版本。
3. 更新说明。
4. 发布者。
5. 受影响 Agent 列表。

主操作：

1. 更新。
2. 暂不更新。

不做自动更新，不默认替用户决定。

## Agent Skills 区域

Agent 配置页需要有一个 Skills 区域：

1. 展示当前已绑定 Skills。
2. 展示每个 Skill 当前版本。
3. 展示来源：我创建、我安装、官方、社区。
4. 展示是否有更新。
5. 提供添加、解绑、查看更新。

如果 Skill 不可用，必须明确提示，不静默失败。

## 对话页可见性

普通用户应该知道 Agent 当前带了哪些 Skills，但不需要看运行细节。

建议：

1. 对话顶部或 Agent 信息里显示已启用 Skills 数量。
2. 可展开查看 Skill 名称和版本。
3. 如果某个 Skill 不可用，显示明确提醒。

不要把 Skill 的完整内容直接暴露在对话页。

## 可复用组件

可以从当前 Gallery 复用：

1. 列表卡片基础结构。
2. 上传入口。
3. 发布弹窗的更新说明输入。
4. dropdown 操作结构。
5. React Query hooks 的缓存失效模式。

但文案和状态模型需要重做。

## 文案替换方向

| 旧文案/概念 | 新文案/概念 |
| --- | --- |
| backend download route for adding to My Skills | 安装 |
| create-my-version / fork export | 下载 |
| Public | SkillHub |
| Custom | 我的 Skill |
| Package version | 版本 |
| Latest version | 当前版本 |
| Public latest | SkillHub 当前发布版本 |
| Version still comes from SKILL.md | 删除，不再出现 |
