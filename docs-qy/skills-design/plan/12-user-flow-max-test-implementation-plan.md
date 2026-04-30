# User Flow Max Test Implementation Plan

日期：2026-04-30

状态：实现拆解计划

## 文档目的

这份文档把 [Skills 用户交互与测试流程](../user-test/01-skills-user-flow-and-acceptance.md) 提升为实现工作的最大验收闭环。

读完后，接手同学应该能做四件事：

1. 知道本轮实现不是“做几个表或几个页面”，而是让最大用户流程真正跑通。
2. 知道当前项目里哪些代码路径要被改造。
3. 知道每个实现阶段要交付什么、测什么、不能偷懒到哪里。
4. 知道什么时候可以说“Skills 安装到 Agent 并运行成功”。

一句话原则：

```text
所有实现切片都必须服务最大测试：
安装 Skill -> 绑定 Agent -> Agent 真实调用 v1 -> 发布 v2 后不自动变化 -> 手动更新 -> Agent 真实调用 v2
```

如果一个切片不能推动这条链路，就先不要做。

## 最大测试定义

最大测试使用“运行验收 Skill”作为探针。

测试数据：

| 平台版本 | 触发输入 | 期望 Agent 回复 |
| --- | --- | --- |
| 版本 1 | `请执行 Skill 运行验收` | `SKILL_RUNTIME_OK_V1` |
| 版本 2 | `请执行 Skill 运行验收` | `SKILL_RUNTIME_OK_V2` |

完整验收顺序：

1. 用户 A 准备或发布运行验收 Skill 版本 1。
2. 用户 B 从 SkillHub 安装版本 1。
3. 用户 B 在我的 Skills 里看到已安装版本 1。
4. 用户 B 把该 Skill 绑定给自己的 Agent。
5. 用户 B 和 Agent 对话，Agent 回复 `SKILL_RUNTIME_OK_V1`。
6. 用户 A 发布版本 2。
7. 用户 B 不点击更新，再次对话仍回复 `SKILL_RUNTIME_OK_V1`。
8. 用户 B 看到更新提示和受影响 Agent，确认更新到版本 2。
9. 用户 B 再次对话，Agent 回复 `SKILL_RUNTIME_OK_V2`。
10. 如果运行时无法解析 Skill，Agent 明确报 Skill 不可用，不回退到 public latest、同名目录或默认能力。

这个测试是逻辑最大测试。早期可以先用后端集成测试和 runtime 单测模拟，等页面成熟后再补 Playwright 端到端测试。

## 当前项目落点

当前代码已经有可复用底座，但每层都缺一个关键对象或关键约束。

| 层 | 当前落点 | 当前能力 | 必须补齐 |
| --- | --- | --- | --- |
| 数据模型 | `skills`、`skill_releases`、`agents_skills` | 上传、发布、下载、Agent 绑定已有骨架 | `SkillVersion`、`SkillInstall`、Manifest/run 审计；`AgentSkillBinding` 绑定 install |
| Skills API | `upload_skills`、`publish_skill`、`download_skill` | 能上传、发布 public latest、复制 public 到用户目录 | 上传生成平台版本；发布指定版本；安装创建安装态；更新切换安装态 |
| Agent API | Agent 创建/编辑接收 skill name | 能把当前用户 Skill 行绑定给 Agent | 改为绑定安装态，返回 Skill 来源、版本、更新状态 |
| Runtime 注入 | `get_runtime_agent_bundle` 生成 `file_path` / `virtual_path` | 能把绑定 Skill 注入 prompt 和 tool runtime | 改为 Runtime Resolver 生成 Manifest，prompt/tool/sandbox 共用同一份 Manifest |
| skill_load | 当前按 runtime skill root map 解析 `/mnt/skills` | 能限制读取 Skills 虚拟路径 | 改为只读 Manifest 授权的 SkillVersion artifact |
| sandbox scope | 当前按 public 或单 user scope 推导 | 有基础安全边界 | 改为 run-level readonly bundle 或 Manifest allowlist，禁止 fallback |
| 前端 Skills | `SkillsGallery` public/custom tab | 有上传、下载、发布入口 | 拆成 SkillHub / 我的 Skills / 更新确认；文案从下载改安装 |
| 前端 Agent | Agent skills 是字符串列表 | 能选择 Skill 名称 | 展示并提交安装态；展示当前版本和不可用状态 |
| 测试 | publish/download/upload/runtime 有局部测试 | 能覆盖旧模型安全和回滚 | 以最大测试重写版本、安装、绑定、Manifest、skill_load、更新验收 |

## 实现阶段

### 阶段 0：冻结最大测试和探针 Skill

目标：

1. 定义运行验收 Skill 的 v1/v2 测试包或测试 fixture。
2. 明确触发输入和期望输出。
3. 把最大测试拆成可自动化的检查点。

要做的事：

1. 准备两个内容不同、name 相同的 Skill 包：版本 1 回复 `SKILL_RUNTIME_OK_V1`，版本 2 回复 `SKILL_RUNTIME_OK_V2`。
2. 包内不要求 version 字段；即使有 version，也只作为 source metadata。
3. 在测试说明里固定触发语句：`请执行 Skill 运行验收`。
4. 先写后端层的最大测试草案：安装 v1、绑定 Agent、resolve Manifest、发布 v2、不更新仍 resolve v1、更新后 resolve v2。

完成标准：

1. 团队对“什么叫 Skill 真的生效”没有歧义。
2. 后续每个阶段都能引用同一个探针 Skill。
3. 不再用“API 返回成功”代替运行验收。

### 阶段 1：平台版本和不可变内容快照

目标：

1. 上传首次有效内容生成平台版本 1。
2. 上传不同内容生成平台版本 2。
3. 上传相同内容不生成新版本。
4. 包内 version 不再影响平台版本。

要做的事：

1. 新增 `SkillDefinition` / `SkillVersion` 的最小持久化结构，或在迁移期用现有 `skills` 承载 Definition，再新增 versions 表。
2. 为每个 SkillVersion 保存 `version_number`、`content_hash`、`artifact_uri`、`file_manifest`、`source_package_version`。
3. 改造上传逻辑：解析包、计算内容 hash、写入不可变 artifact、创建 SkillVersion。
4. 改写 upload/check-upload 响应：返回平台版本信息，不再返回“包版本是否相同”作为主判断。
5. 改写发布逻辑：发布的是某个 SkillVersion，不是当前目录。

测试锚点：

1. 探针 Skill v1 上传后是平台版本 1。
2. 探针 Skill v2 上传后是平台版本 2。
3. v1 artifact 在 v2 上传后内容不变。
4. 包内 version 不存在时仍能创建版本。
5. 包内 version 改变但内容相同，不创建新平台版本。

完成标准：

1. 用户看到的是版本 1/2/3。
2. 旧 `package_version` 测试全部改写为 source metadata 测试。
3. `publish_skill` 不再从当前文件目录推断“当前版本”。

### 阶段 2：SkillHub 安装态

目标：

1. 用户从 SkillHub 安装的是明确 SkillVersion。
2. 安装后有 `SkillInstall`，记录当前用户正在使用哪个版本。
3. 发布新版后，只产生“可更新”状态，不自动改用户安装态。

要做的事：

1. 新增 SkillInstall 持久化结构。
2. 新增或重命名安装接口，让旧 download 兼容为 install latest，但内部语义必须创建安装态。
3. 安装时记录 source SkillDefinition、installed version、current version。
4. 计算安装状态：未安装、已安装、可更新。
5. 更新接口只修改 SkillInstall 的 current version，并保留用户确认动作。
6. 复用现有“覆盖前查受影响 Agent”的思路，但语义改为“更新安装态前展示受影响 Agent”。

测试锚点：

1. 用户 B 安装探针 Skill v1 后，SkillInstall current version 是 v1。
2. 用户 A 发布 v2 后，用户 B 的 current version 仍是 v1。
3. 列表能返回“有更新”，但不自动更新。
4. 用户确认更新后，SkillInstall current version 变成 v2。

完成标准：

1. “安装成功”不再等于复制目录成功。
2. 系统能回答：这个用户安装了哪个 Skill 的哪个版本。
3. 更新提示来自安装态和发布版本比较，不来自文件名或目录时间。

### 阶段 3：Agent 绑定安装态

目标：

1. Agent 绑定用户自己的 SkillInstall。
2. Agent 不直接绑定 public latest、skill name 或复制后的 custom Skill 行。
3. Agent 配置页能展示绑定 Skill 的当前版本和更新状态。

要做的事：

1. 演进 `agents_skills`：新增 install 绑定能力，迁移期保留旧 skill_id 兼容。
2. Agent 创建/编辑接口从 skill name 逐步改为安装态 id 或稳定 Skill 引用。
3. Agent 响应从 `skills: string[]` 升级为可展示对象：名称、来源、当前版本、是否有更新、是否不可用。
4. 删除或禁用 install 前能查询受影响 Agent。
5. 旧数据迁移：用户自建 Skill 可以生成自有 SkillInstall，保证 custom Agent 也走同一条 resolver 链路。

测试锚点：

1. 用户 B 的 Agent 绑定探针 SkillInstall，而不是 SkillHub public row。
2. 同名不同来源 Skill 不会因为 name 绑定错。
3. 更新 SkillInstall 后，绑定该 install 的 Agent 下一次运行使用新版。
4. 正在运行的 run 不会中途切换版本。

完成标准：

1. Agent 绑定层能解释“这个 Agent 当前用的是版本 1”。
2. Agent 绑定层能解释“更新会影响这些 Agent”。
3. 任何新 Agent 绑定 Skill 的路径都不再依赖 public latest。

### 阶段 4：Runtime Resolver 和 Manifest

目标：

1. run 开始前生成 Runtime Manifest。
2. Manifest 明确列出本次 Agent 可以读取哪些 SkillVersion artifact。
3. prompt、`skill_load`、sandbox 只消费这份 Manifest。
4. Resolver 失败时 hard fail，不 fallback。

要做的事：

1. 新增 Runtime Resolver：输入 user、agent、run context，输出 Manifest。
2. Resolver 读取 AgentSkillBinding -> SkillInstall -> SkillVersion。
3. Resolver 校验 SkillInstall 属于当前用户、SkillVersion 可用、artifact hash 可校验。
4. Manifest 保存完整 JSON 和 hash 到 run record。
5. Gateway runtime 注入从 `file_path` / `virtual_path` 列表升级为 Manifest。
6. prompt descriptor 从 Manifest 生成，不再重新查 Skills 表。

测试锚点：

1. 安装 v1 后，Manifest 中有 v1 的 SkillVersion id 和 artifact。
2. 发布 v2 但未更新时，Manifest 仍指向 v1。
3. 更新后，下一次 Manifest 指向 v2。
4. Resolver 找不到 artifact、install 或 version 时，run 明确失败。
5. Resolver 不会回退到 public latest 或同名目录。

完成标准：

1. 可以通过 run record 回答“这次 Agent 到底用了哪个 SkillVersion”。
2. 页面成功和运行成功之间有可审计证据。
3. 最大测试的 v1/v2 行为可以在 resolver 层解释清楚。

### 阶段 5：skill_load 和 sandbox 按 Manifest 授权

目标：

1. `skill_load` 只能读取 Manifest 授权的 virtual path。
2. sandbox 只能看到本次 run 授权的 artifact。
3. 同名 Skill 不靠覆盖目录解决冲突。

要做的事：

1. 将当前 runtime skill root map 改为 Manifest virtual root map。
2. `skill_load` 从 virtual path 严格映射到 Manifest artifact 或 run-level readonly bundle。
3. 选择并实现 run-level readonly bundle 作为 MVP 目标；迁移期可以先用受控 copy/symlink 组装，但 Manifest 是授权真相。
4. sandbox 挂载 bundle，而不是推导 public/user scope。
5. 错误信息保持用户可解释：Skill 不可用、版本被禁用、artifact 校验失败。

测试锚点：

1. `skill_load` 读取探针 Skill v1 返回 v1 内容。
2. 发布 v2 未更新时，`skill_load` 仍读取 v1 内容。
3. 更新后，`skill_load` 读取 v2 内容。
4. Manifest 外路径读取失败。
5. public latest 存在 v2 时，未更新用户仍不能读到 v2。

完成标准：

1. 最大测试不只在 API 层通过，也在工具和 sandbox 层通过。
2. 运行时失败不会被默认 Agent 能力掩盖。
3. 路径映射复杂性被 Resolver/Manifest/bundle 吸收，用户和页面不感知。

### 阶段 6：前端交互主链路

目标：

1. 零背景用户能按文档完成安装、绑定、运行、更新。
2. 页面不暴露旧概念。
3. 页面状态能支撑最大测试观察。

要做的事：

1. 将 Skills Gallery 拆成 SkillHub 和我的 Skills 的信息架构。
2. 文案从 Download 改为安装，从 public/custom 改为 SkillHub/我的 Skills。
3. Skill 卡片展示来源、当前平台版本、安装状态、更新状态。
4. 安装成功后提供“绑定到 Agent”入口。
5. Agent 配置页 Skills 区域展示名称、来源、当前版本、更新状态、不可用状态。
6. 更新确认页展示当前版本、可更新版本、更新说明和受影响 Agent。
7. 对话页展示当前 Agent 启用 Skills 的可见线索。

测试锚点：

1. 用户能从 SkillHub 安装探针 Skill。
2. 我的 Skills 中能看到版本 1。
3. Agent 配置页能绑定并显示版本 1。
4. 发布 v2 后页面提示有更新，但 Agent 状态仍是版本 1。
5. 更新确认后页面变成版本 2。

完成标准：

1. 零背景同学可以按 user-flow 文档独立操作。
2. 页面不会让用户填写或理解 Skill 包内 version。
3. 页面不会把“已安装”和“已绑定”混成一个状态。

### 阶段 7：最大测试自动化

目标：

1. 最大 user-flow 至少有一条自动化链路覆盖。
2. 每个关键层都有能定位问题的较小测试。
3. 失败时能看出是安装态、绑定、resolver、tool、sandbox 还是前端状态问题。

建议测试层次：

1. 数据层：SkillVersion、SkillInstall、AgentSkillBinding 的状态变化。
2. API 层：install、update、affected agents、Agent bind。
3. Runtime 层：Manifest v1/v2 切换和失败 hard fail。
4. Tool 层：`skill_load` 只读 Manifest 授权路径。
5. sandbox 层：Manifest 外 artifact 不可读。
6. 前端层：SkillHub/我的 Skills/Agent 配置/更新确认状态。
7. 端到端层：探针 Skill v1/v2 最大流程。

完成标准：

1. 最大测试失败时，不能只得到“Agent 没按预期回答”，还要能定位是哪一层断了。
2. 合并前必须至少证明：v1 安装后运行 v1，v2 发布后未更新仍运行 v1，更新后运行 v2。
3. 任何 fallback 到 public latest、同名目录或默认能力的行为都算 P0。

## 实施顺序建议

推荐按下面顺序推进：

1. 先做阶段 0，冻结探针 Skill 和最大测试。
2. 再做阶段 1 和阶段 2，确保版本和安装态是真数据。
3. 然后做阶段 3，把 Agent 绑定从 name/skill row 拉到 install。
4. 接着做阶段 4 和阶段 5，解决真正的 runtime 路径映射和授权。
5. 最后做阶段 6 的完整前端体验，并在阶段 7 补最大端到端测试。

不要先做漂亮页面再补 runtime。这个项目最大的风险是 UI 流程看起来成功，但 Agent 没有读取用户安装的 Skill 本体。

## 第一轮开工清单

第一轮不追求完整 UI，而是把最大测试的后端和 runtime 骨架立起来。

建议先开这些任务：

1. 新增探针 Skill fixture：准备同名 v1/v2 包，固定 `SKILL_RUNTIME_OK_V1` 和 `SKILL_RUNTIME_OK_V2`。
2. 新增平台版本测试：首次上传生成版本 1，上传不同内容生成版本 2，包内 version 不参与判断。
3. 新增 SkillVersion 迁移和仓储：先满足版本号、content hash、artifact URI、source package version。
4. 改造上传路径：从“同名同 package_version 冲突”改成“同内容不建版本，不同内容建新版本”。
5. 新增 SkillInstall 迁移和仓储：能记录用户安装了哪个 SkillVersion。
6. 新增 install latest API：先让旧 download 走 install 语义，避免前端马上大改。
7. 新增 Runtime Resolver 雏形：给定 user + agent，能从绑定解析到 SkillInstall current version。
8. 新增 Manifest 单测：v1 安装后 resolve v1，v2 发布但未更新仍 resolve v1。
9. 给 resolver 失败路径写 hard fail 测试：不能 fallback 到 public latest、同名目录或默认能力。

第一轮完成后，即使页面还没全改，也应该能在测试里证明：

```text
install v1 -> bind agent -> resolve manifest v1
publish v2 -> resolve manifest still v1
update install -> resolve manifest v2
```

这就是后续前端和 sandbox 改造的地基。

## 每阶段交付检查表

每个阶段提交前都要回答：

1. 这个阶段推进了最大测试的哪一步？
2. 是否还存在 public latest、skill name、同名目录或当前文件路径的隐式 fallback？
3. 用户看到的版本是否完全由平台维护？
4. Agent 下一次 run 能否审计到具体 SkillVersion？
5. 如果失败，用户能否看到明确不可用状态？
6. 测试失败时，研发能否定位到数据、API、resolver、tool、sandbox 或前端中的具体层？

## 不做清单

这些不要插入 MVP 实现路径：

1. 自动更新。
2. 用户手写版本号。
3. SemVer 兼容矩阵。
4. diff 和回滚 UI。
5. 评分、评论、排行榜。
6. 付费市场。
7. 复杂组织权限。
8. 多人协作编辑。
9. 自动合并用户 fork 后的魔改内容。

这些能力可以在最大测试稳定后再设计。
