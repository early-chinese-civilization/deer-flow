# Migration Plan

日期：2026-04-29

状态：历史分阶段迁移建议；2026-05-11 主体对象已落地

## 2026-05-11 当前代码校准

本文件是 2026-04-29 的迁移拆解，不是当前待办清单。当前代码已经有平台版本、不可变 artifact、安装态、Agent install/system binding、Runtime Manifest 和 run-level sandbox bundle。

继续工作时先读：

1. [../design/00-current-code-status.md](../design/00-current-code-status.md)
2. [../design/04-current-implementation-gap.md](../design/04-current-implementation-gap.md)
3. [12-user-flow-max-test-implementation-plan.md](12-user-flow-max-test-implementation-plan.md)

不要从“新增 SkillVersion / 新增 SkillInstall / 引入 Runtime Manifest”重新开始。当前剩余重点是修复 `.deer-flow` 存储阻塞、补完整 v2/update max-flow、清理 legacy route/name/copy 文案和补同名来源/失败路径测试。

## 文档目的

这份文档描述早期如何从旧实现迁移到目标模型。它不重复产品流程，不展开边界规则。

读完后应该能把工作拆成几轮可落地的实现任务。

具体执行时，以 [12-user-flow-max-test-implementation-plan.md](12-user-flow-max-test-implementation-plan.md) 作为最大验收闭环：每个迁移阶段都必须能说明它推进了“安装 Skill、绑定 Agent、Agent 真实调用、手动更新后再调用”这条流程中的哪一步。

## 迁移原则

不要一次性重构全部。当前实现已经有可用骨架，应该按能保留现有功能的顺序推进。

早期基本策略：

1. 先停止错误版本来源。
2. 再引入不可变版本快照。
3. 再引入安装态。
4. 最后重塑 SkillHub 和前端信息架构。

## 第一阶段：停止把 `SKILL.md` version 当平台版本

目标：

1. 保留现有上传、发布、下载能力。
2. 前端不再展示 `package version` 作为主版本。
3. 后端开始生成平台版本号。

建议动作：

1. 新增平台版本字段或版本表的最小形态。
2. 上传首次 Skill 时生成版本 1。
3. 同内容重复上传通过内容哈希判断，而不是通过 `SKILL.md version` 判断。
4. `SKILL.md version` 改名为 source/import metadata，只用于兼容。
5. 前端文案从“Package/Latest/public latest”改为“版本/发布到 SkillHub/安装”。

完成标准：

1. 用户看不到 package version 作为主版本。
2. 上传包内版本字段不能影响平台版本。
3. 旧上传/发布/下载主链路仍可用。

## 第二阶段：新增不可变 SkillVersion

目标：

1. 上传新内容创建版本 2。
2. 旧版本不被覆盖。
3. publish 指向具体版本。

建议动作：

1. 引入 `SkillVersion`。
2. custom Skill 当前内容迁移为版本 1。
3. upload 同名新内容创建新版本，不直接覆盖当前文件。
4. publish API 接收或默认选择一个 `skill_version_id`。
5. `skill_releases` 增加 `skill_version_id`。

完成标准：

1. 版本 1 artifact 在版本 2 创建后保持不变。
2. publish 明确发布某个版本。
3. 版本历史可以列出未发布和已发布版本。

## 第三阶段：新增安装态与不可变 Artifact Store

目标：

1. 用户从 SkillHub 安装某个版本。
2. 系统知道用户当前安装的是哪个版本。
3. 用户 B 能看到更新提示。
4. 每个 SkillVersion 都指向不可变 artifact。
5. 安装态记录 current SkillVersion，而不是复制后的目录状态。

建议动作：

1. 引入 `SkillInstall`。
2. download API 改名或新增 install API。
3. 旧 download 兼容为 install latest。
4. 前端“下载”改为“安装”。
5. 列表中展示“已安装 / 有更新”。
6. 安装官方或社区 Skill 时，记录 source skill 和 installed/current version。
7. 引入不可变 Artifact Store，保存 content hash、artifact URI、文件清单和校验状态。
8. 旧 download 复制目录能力只能作为兼容路径，不作为安装态真相。

完成标准：

1. 用户安装 SkillHub 当前发布版本后有安装记录。
2. 发布者发布新版后，安装旧版的用户出现更新提示。
3. 用户不确认更新时，安装态不变化。
4. SkillVersion artifact 创建后不能被原地替换。

## 第四阶段：Runtime Manifest 与 Agent 绑定安装态

目标：

1. Agent 绑定用户空间里的安装态。
2. 更新安装态前展示受影响 Agent。
3. 运行时解析安装态当前版本的 artifact。
4. prompt、`skill_load`、sandbox allowlist 消费同一份 Runtime Manifest。

建议动作：

1. `agents_skills` 从绑定 Skill 行演进为绑定 install 行。
2. 运行时 resolver 改为读取 install 当前版本，并生成 Runtime Manifest。
3. update install version 时复用当前 rebind/受影响 Agent 查询能力。
4. Run 记录保存本次实际使用的 SkillVersion 审计快照。
5. 改造 sandbox 和 `skill_load`，按 Manifest artifact allowlist 授权读取。
6. 调研并选择多 artifact root allowlist 或 run-level readonly bundle。

完成标准：

1. SkillHub 新版本发布不自动影响 Agent。
2. 用户更新安装态后，绑定该安装态的 Agent 后续使用新版。
3. 更新前能展示受影响 Agent。
4. 一个 Agent 同时绑定官方、社区和用户自建 Skill 时，Manifest 能明确列出每个 SkillVersion artifact。
5. 未在 Manifest 中授权的 Skill path 读取失败。

## 第五阶段：官方与社区来源拆分

目标：

1. SkillHub 清晰区分官方与社区。
2. 用户不能覆盖官方 Skill。
3. 用户可以基于符合条件的社区 Skill 下载可编辑包并创建自己的版本；系统 Skill 本轮不提供下载。

建议动作：

1. 给 Skill 身份增加来源类型。
2. 官方 Skill 由平台流程导入，不走普通用户 publish。
3. 社区 Skill 由用户 publish 生成。
4. “下载”生成可编辑包，用户上传后形成新的用户 Skill 身份，版本从 1 开始。

完成标准：

1. Skills UI 可以区分系统、社区和我的 Skills。
2. 普通用户不能发布官方 Skill 的新版。
3. 社区 Skill 下载后上传，得到独立的我的 Skill。

## 接口演进建议

当前接口可以兼容一段时间，但新产品语义建议逐步新增更明确的接口。

可兼容保留：

1. `GET /skills` 可以继续返回当前用户可见 Skills，但响应需要区分来源、安装态、平台版本、更新状态。
2. `POST /skills/uploads` 可以继续作为上传入口，但语义改为创建 Skill 或 SkillVersion。
3. `POST /skills/{name}/publish` 可以先兼容，但内部应发布指定平台版本。

建议新增或改名：

1. `GET /skillhub`：SkillHub 列表。
2. `GET /skills/mine`：我的 Skills，包括我创建和我安装的。
3. `POST /skills/{skill_id}/versions`：上传新版本。
4. `POST /skills/{skill_id}/versions/{version_id}/publish`：发布指定版本。
5. `POST /skillhub/{skill_id}/install`：安装 SkillHub 当前版本。
6. `POST /installs/{install_id}/update`：更新已安装 Skill 到指定版本。
7. `POST /skillhub/{skill_id}/fork-package`：下载可编辑包，用于后续上传成我的版本。
8. `GET /installs/{install_id}/affected-agents`：更新或删除前查看受影响 Agent。

接口命名可以后续再细化，但动作语义必须从“复制文件”升级为“安装、发布版本、更新安装态”。

## 当前实现辅助下的 MVP 调整

2026-05-11 的 MVP 调整是：

1. 不再把版本来源、SkillVersion、SkillInstall、Agent install binding 或 Runtime Manifest 当成待新增主体。
2. 继续修复本地/OSS/FUSE-backed `.deer-flow` 上传阻塞，避免 API pending 和 DB transaction/lock 污染。
3. 继续跑完整最大测试：v1 install/bind/runtime 已有证据；v2 upload/publish、未更新仍 v1、update-install 后 v2 仍待完成。
4. 继续清理 route/name 文案债：`download` route 是 install，`fork-package` 才是 editable ZIP 下载。
5. 继续补同名不同来源、System direct binding、legacy `skill_id`/`custom`/name-only fallback 的测试。

这样做的好处仍然成立：

1. 可以保留现有 API 和测试的大部分骨架。
2. 每一步都有用户可见收益。
3. 不会在一开始就把 Agent 运行时打碎。
4. 最终仍然能走向目标用户模型。
