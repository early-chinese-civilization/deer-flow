# Validation And Open Questions

日期：2026-04-29

状态：测试口径与待确认问题

## 文档目的

这份文档只描述测试口径、MVP 验收和仍需确认的问题。它不解释完整产品模型，不设计页面。

读完后应该能判断：现有测试哪些要保留，哪些要改写，哪些必须新增。

最高级验收以 [../user-test/01-skills-user-flow-and-acceptance.md](../user-test/01-skills-user-flow-and-acceptance.md) 和 [12-user-flow-max-test-implementation-plan.md](12-user-flow-max-test-implementation-plan.md) 为准。单元测试、接口测试、runtime 测试和前端测试都应该服务同一个最大测试：安装 Skill 后绑定 Agent，Agent 真实调用当前安装版本，发布新版后不自动变化，手动更新后才调用新版。

## 应保留的测试方向

这些测试方向仍然有价值：

1. 上传 zip 安全校验。
2. 缺少 `SKILL.md`、非法 YAML、非法 name/description 时拒绝。
3. 发布失败时数据库回滚、artifact 恢复。
4. public/自定义权限隔离。
5. 删除已绑定 Skill 前必须提示受影响 Agent。
6. publish 保存发布说明。
7. list/get/download 返回发布者和发布时间等展示元数据。

它们验证的是安全性、权限、失败回滚和展示元数据，不依赖旧版本口径。

## 应改写的测试方向

这些测试服务于旧模型，需要改写断言：

1. “同名不同 `package_version` 更新当前 custom row”应改为“同名新内容创建新 SkillVersion”。
2. “同名同 `package_version` 默认拒绝”应改为“同内容重复上传不创建新版本”。
3. “custom skill 展示 package_version”应改为“custom skill 展示平台当前版本”。
4. “release_version 作为 display version fallback”应改为“平台版本号作为主展示，release id 只做内部审计”。
5. “download public latest”应改为“install SkillHub 当前发布版本”。
6. “download overwrite 迁移 agent skill 绑定”应改为“更新安装态前展示受影响 Agent，确认后切换安装态当前版本”。

## 必须新增的测试方向

平台版本：

1. 首次上传生成版本 1，忽略导入包自带版本字段。
2. 第二次上传不同内容生成版本 2，版本 1 artifact 不变。
3. 第二次上传相同内容不生成版本。
4. 版本号由平台递增，用户请求体不能指定。

发布与安装：

1. 发布版本 1 后，其他用户安装的是版本 1。
2. 发布版本 2 后，已安装版本 1 的用户出现更新提示。
3. 发布版本 2 后，已安装版本 1 的用户 Agent 不自动变化。
4. 用户确认更新后，安装态 current version 变为版本 2。

魔改与来源：

1. 用户基于社区 Skill 创建自己的版本后，新 Skill 身份与原 Skill 解耦。
2. 官方 Skill 不能被普通用户直接发布新版。
3. 社区 Skill 不能覆盖官方 Skill 身份。

运行时：

1. 运行时解析的是 Agent 绑定安装态的 current version artifact。
2. 正在生成的回复不因 Skill 更新中途切换。
3. Skill 被安全禁用时，运行时停用并给出可解释状态。
4. 自定义 Agent 绑定官方、社区和用户自建 Skill 时，resolver 都能生成同一份 Runtime Manifest。
5. `skill_load` 不能读取当前 runtime resolver 未授权的 Skill 路径。
6. sandbox 不能读取 Manifest 未授权的 Skill artifact。
7. public latest 或同名目录不能作为 resolver 失败时的静默 fallback。

前端：

1. SkillHub 列表能区分官方、社区、已安装、有更新。
2. 发布弹窗展示平台版本，不展示 package version。
3. 更新确认页展示受影响 Agent。
4. 用户取消更新时不调用更新接口。

## MVP 必须做

第一版上线前，至少要满足：

1. 普通用户可以上传 Skill，并看到平台生成的版本 1。
2. 普通用户可以把自己的 Skill 绑定到 Agent，并在对话中生效。
3. 普通用户可以把自己的 Skill 发布到 SkillHub。
4. 另一个用户可以从 SkillHub 安装该 Skill。
5. 发布者上传新内容后，平台创建版本 2。
6. 发布者发布版本 2 后，安装版本 1 的用户不被自动升级。
7. 安装用户能看到更新提示，并手动升级。
8. 版本号由平台生成，用户无法通过 Skill 内容里的字段改写平台版本。
9. 官方 Skill、社区 Skill、我的 Skill、已安装 Skill 在页面和行为上不混淆。
10. 所有失败路径都不能留下用户可见的半成品。

## 第一版可以不做

1. 付费市场。
2. 评分评论。
3. 自动更新。
4. 多人协作编辑同一个 Skill。
5. 复杂 SemVer。
6. 自动合并用户魔改版本。
7. 每个 Agent 单独固定到不同历史版本的高级界面。
8. 复杂 diff 查看器。
9. 社区排行榜。
10. 组织级权限和审批流。

## 建议 P1

1. 回滚到旧版本。
2. 版本 diff。
3. 举报和下架流程。
4. 更完整的安全扫描。
5. 更新提醒偏好。
6. 作者主页。
7. 安装量、使用量等基础指标。

## 仍需产品确认的问题

这些问题不阻塞主方向，但会影响细节设计：

1. 是否允许用户查看社区 Skill 的完整源内容。
2. 发布到 SkillHub 是否需要人工审核，还是先自动校验后立即发布。
3. 我的空间中是否允许两个不同来源的同名 Skill 并存。
4. 更新已安装 Skill 后，是否需要提供立即回滚能力作为 MVP。
5. 官方 Skill 是否默认自动安装给所有用户，还是只在 SkillHub 推荐。
6. Agent 对话页是否要向最终用户展示当前启用的 Skill 名称和版本。
7. 安装 artifact 物化路径是否按 Skill 名称、install id，还是 version id 组织。
8. 用户空间是否允许安装两个不同来源但同名的 Skill。
9. Run 记录是否在 MVP 保存本次使用的 Skill 版本，作为后续审计和问题排查依据。
10. Runtime Manifest 是 run 前持久化，还是按需生成后随 run record 保存快照。
11. sandbox 采用多 artifact root allowlist，还是 run-level readonly bundle。

## 验证优先级

建议按这个顺序落测试：

1. 最大测试探针：准备 v1/v2 运行验收 Skill，固定触发输入和期望输出。
2. 平台版本来源：确保版本不再来自 Skill 内容。
3. 不可变版本：确保上传新内容不会覆盖旧版本。
4. 发布指定版本：确保 SkillHub 发布的是版本快照。
5. 安装态：确保用户安装的是明确版本。
6. Agent 绑定安装态：确保 Agent 不绑定 public latest、skill name 或同名目录。
7. 手动更新：确保新版本不会自动影响 Agent。
8. Runtime Manifest：确保 prompt、`skill_load`、sandbox allowlist 指向同一组 SkillVersion。
9. 前端状态：确保用户能看懂已安装、有更新、受影响 Agent。
10. 最大端到端：确保 v1 安装后回复 `SKILL_RUNTIME_OK_V1`，v2 发布但未更新仍回复 v1，手动更新后回复 `SKILL_RUNTIME_OK_V2`。
