# SkillHub 作者与安装者 UI/UX 验收计划

日期：2026-05-07

状态：作者/安装者视角补充验收

## 文档目的

这份文档补充 `01-skills-user-flow-and-acceptance.md` 和 `02-skill-version-must-pass-user-test-cases.md` 中缺少的角色视角。

同一个 Skill 在不同用户眼里不是同一个产品任务。更准确地说，Skills 产品有两个空间：

1. 社区空间：负责展示官方和社区发布的 Skills，并提供下载到我的空间的入口。
2. 我的空间：负责展示我下载的 Skills 和我的 Skills，让它们可以被 Agent 选择和使用。

同一个 Skill 在不同空间和不同用户眼里承担不同任务：

1. 作者关心“我创建了什么、我发布了哪个版本、别人能否安装、我是否还有未发布改动”。
2. 下载者关心“这个 Skill 谁做的、我有没有下载到我的空间、我的 Agent 当前用哪个版本、是否有更新”。

页面不能把这两类用户都塞进同一套“已安装/未发布/当前版本”小徽标里。目标用户不理解内部机制，所以 UI 必须用自然语言把角色和下一步讲清楚。

## 角色定义

| 角色 | 说明 | 主要任务 |
| --- | --- | --- |
| 作者 / Publisher | 当前登录用户创建、上传或 fork 了 Skill，并可以发布到社区空间 | 迭代版本、发布、查看发布状态 |
| 下载者 / Downloader | 当前登录用户从社区空间下载别人或官方的 Skill 到我的空间 | 下载、绑定 Agent、手动更新 |
| 双重身份用户 | 当前登录用户既创建了某个 Skill，也可能从社区空间下载过同名或不同来源 Skill | 区分“我下载的”和“我的 Skill”，不能绑定错 |

## 用户可见状态词

推荐主文案：

| 场景 | 推荐表达 |
| --- | --- |
| 我上传/创建的 Skill | 我创建的 Skill |
| 我创建且已发布 | 已发布到 SkillHub |
| 我创建但还没发布 | 未发布 |
| 我的本地版本比已发布版本新 | 有未发布改动 |
| 别人发布的 Skill | 来自 `<作者>` |
| 官方预置 Skill | 官方 / official |
| 我从社区空间下载的 Skill | 已下载到我的空间 |
| 我安装的版本落后 | 有更新 |
| Agent 当前使用 | Agent 使用版本 `<n>` |
| fork 后的新 Skill | 基于 `<来源>` 创建 |

禁止让普通用户在主流程理解：

1. `public latest`
2. `custom`
3. `package version`
4. `artifact`
5. `Runtime Manifest`
6. `skill_definition_id`
7. `skill_install_id`
8. source namespace

## 流程 A：作者上传并发布自己的 Skill

### 前置条件

用户 A 已登录，准备“运行验收 Skill”版本 1 包。

### 步骤

1. 用户 A 打开 `/workspace/skills`。
2. 用户 A 在 My Skills 上传或创建“运行验收 Skill”版本 1。
3. 用户 A 查看该 Skill 卡片。
4. 用户 A 发布版本 1 到 SkillHub。
5. 用户 A 切换到 SkillHub 查看自己发布的 Skill。

### 预期

1. My Skills 中该 Skill 明确显示为“我创建的 Skill”。
2. 当前版本显示为平台版本，例如“版本 1”。
3. 发布前状态是“未发布”或“可发布”，不是“未安装”。
4. 发布确认说明“将版本 1 发布到 SkillHub，别人可以安装”，不出现 `public latest` 或 `SKILL.md version`。
5. 发布后状态是“已发布到 SkillHub”。
6. 作者在社区空间看到自己的 Skill 时，主操作应是“管理发布”或“查看详情”，不能让用户误以为需要下载自己的发布物才能继续管理。

### 失败信号

1. 作者自己的社区空间条目显示“下载”作为主操作，且没有解释这是自己的发布物。
2. 我的空间中作者创建的 Skill 和从社区空间下载的 Skill 无法区分。
3. 发布后作者不知道别人看到的是哪个版本。
4. 页面用内部字段解释版本或来源。

## 流程 B：下载者下载作者发布的 Skill

### 前置条件

用户 A 已发布“运行验收 Skill”版本 1。用户 B 已登录，尚未下载该 Skill。

### 步骤

1. 用户 B 打开社区空间。
2. 用户 B 找到用户 A 发布的“运行验收 Skill”。
3. 用户 B 点击“下载到我的空间”。
4. 用户 B 打开我的空间。
5. 用户 B 进入 Agent 配置页并绑定该 Skill。

### 预期

1. 社区空间卡片展示名称、描述、作者、来源、当前公开版本。
2. 官方 Skill 的作者/来源显示为 official/官方。
3. 未下载时主操作是“下载到我的空间”。
4. 下载后显示“已下载到我的空间”，并提供自然下一步“绑定到 Agent”。
5. 我的空间中该 Skill 明确显示“来自用户 A”或“从社区空间下载”。
6. Agent 绑定选项显示 Skill 名称、作者/来源、当前已下载版本。
7. 如果存在同名 Skill，用户 B 可以仅凭页面信息区分来源。

### 失败信号

1. 用户 B 只看到 Skill 名称，看不到作者或来源。
2. 下载成功后用户不知道是否还需要绑定 Agent。
3. Agent 绑定页按名称合并同名 Skill。
4. UI 显示“已下载”，但我的空间或 Agent 绑定页找不到该 Skill。

## 流程 C：作者发布 v2 后，作者和安装者看到不同状态

### 前置条件

用户 B 已安装用户 A 的版本 1，并绑定给 Agent。用户 A 准备版本 2。

### 步骤

1. 用户 A 上传或创建同名版本 2。
2. 用户 A 发布版本 2 到 SkillHub。
3. 用户 A 查看 My Skills 和 SkillHub。
4. 用户 B 刷新 SkillHub、My Skills、Agent 配置页。
5. 用户 B 不点击更新，直接用 Agent 对话。

### 预期

作者视角：

1. 用户 A 看到自己的当前创建版本和当前 SkillHub 发布版本。
2. 发布 v2 后，作者 UI 表达“SkillHub 当前发布版本是版本 2”。
3. 作者 UI 不暗示所有安装者已经自动更新。

安装者视角：

1. 用户 B 看到“有更新：当前使用版本 1，可更新版本 2”。
2. Agent Skills 区域仍显示版本 1。
3. 对话仍回复 `SKILL_RUNTIME_OK_V1`。
4. 页面解释更新需要用户 B 手动确认。

### 失败信号

1. 作者发布 v2 后，安装者 Agent 自动切到 v2。
2. 安装者页面只显示“最新版”或“当前版本”，看不出 Agent 实际仍用 v1。
3. 作者页面和安装者页面使用完全相同状态文案，导致“发布”和“安装更新”混淆。

## 流程 D：安装者手动更新并验证 Agent 切换

### 前置条件

用户 B 已安装版本 1，SkillHub 已有版本 2，用户 B 的 Agent 已绑定该安装态。

### 步骤

1. 用户 B 点击“查看更新”。
2. 用户 B 查看更新确认页。
3. 用户 B 确认更新。
4. 用户 B 回到 My Skills 和 Agent 配置页。
5. 用户 B 发起新对话，输入 `请执行 Skill 运行验收`。

### 预期

1. 更新确认页展示当前版本 1、可更新版本 2、发布者、更新说明和受影响 Agent。
2. 确认前不会切换版本。
3. 确认后 My Skills 显示版本 2。
4. Agent Skills 显示版本 2。
5. 新对话回复 `SKILL_RUNTIME_OK_V2`。

### 失败信号

1. 更新确认页没有受影响 Agent。
2. 更新后页面显示版本 2，但 Agent 仍运行版本 1。
3. 更新动作影响了错误来源的同名 Skill。

## 流程 E：同名不同来源必须可区分

### 前置条件

SkillHub 中存在两个同名或近似同名 Skill：

1. 用户 A 发布的“运行验收 Skill”。
2. 用户 C 发布的“运行验收 Skill”。

用户 B 至少下载其中一个。

### 步骤

1. 用户 B 打开 SkillHub。
2. 用户 B 比较两个同名 Skill。
3. 用户 B 下载用户 A 的版本。
4. 用户 B 打开 Agent 配置页并绑定该 Skill。
5. 用户 B 查看 chat/Agent Skill 展示。
6. 用户 B 运行验收。

### 预期

1. SkillHub 卡片用作者、来源、详情入口或其他稳定视觉线索区分同名 Skill。
2. Agent 绑定选项不按 name 合并。
3. 绑定后 Agent Skills 展示来源和当前版本。
4. Runtime 使用用户 B 安装的用户 A 来源版本，不会串到用户 C。

### 失败信号

1. 两个同名 Skill 在列表中无法区分。
2. 安装用户 A 的 Skill 后，Agent 绑定页显示用户 C 的来源。
3. 运行时读取另一个同名来源。
4. 页面要求用户理解内部 ID 才能判断选哪个。

## 流程 F：下载后 fork 成我的 Skill

### 前置条件

用户 B 已从社区空间下载一个官方或社区 Skill。

### 步骤

1. 用户 B 打开我的空间。
2. 用户 B 找到已下载的 Skill。
3. 用户 B 点击“基于此创建我的版本”。
4. 系统创建一个新的“我的 Skill”。
5. 用户 B 查看新 Skill 的来源归因和发布状态。

### 预期

1. fork 后生成的是新的我的 Skill，不是修改已下载 Skill。
2. 新 Skill 保留“基于 `<来源 Skill>` 创建”的可见归因。
3. 新 Skill 初始状态未发布。
4. 如果用户未做实质修改就发布，本版本必须 hard-block；本轮按来源版本文件/内容 hash 精确相等判断，复杂相似度留给后续审核机制。
5. 后续审核机制上线后，可以把 hard-block 扩展为审核/治理流程。

### 失败信号

1. fork 直接覆盖已下载 Skill。
2. fork 后来源归因消失。
3. 用户可以把未修改复制品直接发布成新的社区 Skill。
4. Agent 绑定页无法区分已下载原版和 fork 后的我的版本。

## 核心 UI 验收矩阵

| 场景 | 作者应该看到 | 下载者应该看到 | 必须验证 |
| --- | --- | --- | --- |
| 上传 v1 | 我的 Skill，版本 1，未发布/可发布 | 不可见或尚未下载 | 作者不被提示下载自己的未发布 Skill |
| 发布 v1 | 已发布到社区空间，社区版本 1 | 社区空间可下载，来自作者 A 或官方，版本 1 | 发布不等于下载者已拥有 |
| 下载 v1 | 可看到发布状态 | 已下载到我的空间，当前版本 1 | Personal Space install 指向 v1 |
| 绑定 Agent | 不影响作者除非作者也绑定 | Agent 使用版本 1 | Agent 绑定安装态，不绑定 SkillHub 公共对象 |
| 发布 v2 | 社区空间当前发布版本 2 | 有更新，当前使用版本 1，可更新版本 2 | 未手动更新前 runtime 仍是 v1 |
| 手动更新 | 作者无自动影响提示 | 当前版本变成 2，Agent 下一次用 v2 | Runtime Manifest / Agent display / chat display 一致 |
| 同名不同来源 | 作者身份清楚 | 安装来源清楚 | 不按 name 串线 |
| fork | 生成新的我的 Skill | 原下载 Skill 不被修改 | 本版本 hard-block 未修改 fork 发布；本轮只要求精确 hash 相等拦截 |

## 自动化建议

前端应补以下 focused tests：

1. Skill display helper 能区分 official-community、user-community、downloaded-to-personal、authored-by-me、published-by-me、forked-by-me。
2. Community Space self-authored row 不以“下载/安装”为主操作。
3. Installer row 显示 author/source/version/update state。
4. Personal Space filters 能区分我下载的、我的 Skill、已发布、有更新、fork。
5. Same-name different-source rows 保留独立 selection key。
6. Agent/chat Skill metadata copy 不出现内部 ID、artifact、Runtime Manifest 文案。

## 第二轮迭代：社区空间搜索

社区空间增长后必须支持搜索和筛选。本轮 UI/API 设计必须保留这些入口需要的字段和语义。

### 必须支持的搜索维度

1. 按 Skill 名称搜索。
2. 按作者搜索或筛选。
3. 后续可扩展 official/community、已下载、有更新等筛选。

### 本轮必须避免的设计阻塞

1. 不要只把作者显示成不可查询的拼接文案。
2. 不要只用内部 ID 区分来源，普通用户必须能看到作者/来源。
3. 不要让同名 Skill 在搜索结果中合并成一条。
4. 不要把官方 Skill 和社区 Skill 混成无法筛选的 public 状态。
