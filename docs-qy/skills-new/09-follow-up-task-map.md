# 后续任务拆分图

日期：2026-05-12

状态：后续 implementation task 拆分草案

## 用途

本文把终态设计拆成未来可执行任务。它不是实施顺序的最终排期，但每个任务都应该能从这里找到业务链路、默认聊天 runtime 链路、自定义 Agent runtime 链路、测试和迁移边界。

长期执行规则：

1. 真正创建 Trellis implementation task 时，每个 task 都必须先引用 `.trellis/spec/backend/skill-runtime-and-storage.md` 作为可执行合同。
2. 本文只负责拆分任务边界和依赖顺序，不覆盖 `00-terminal-state.md` 或 `.trellis/spec` 的终态规则。
3. `docs-qy/skills-design` 只能作为旧状态参考；不能从那里恢复 fork/download、default Agent、Runtime Manifest 核心真相、public/custom/name-only runtime scan 或独立 `skill_version_id` 口径。
4. 如果未来实现发现合同需要变更，先更新 `.trellis/spec` 和 `.trellis/user`，再回到本文调整任务拆分。

## 推荐执行分组

### A. 后端基础模型与内容链路

先做 Task 1、Task 2、Task 3。它们共同决定数据模型、迁移、内容目录、发布安装更新的最小闭环，是后续 runtime 和前端工作的前置条件。

交付边界：

- DB schema、migration、preflight、repository 和基础测试一起交付。
- 内容写入必须证明 `.deer-flow/skills/{skill_id}/{version_number}/` 是唯一运行目录事实。
- publish/install/update 只移动 DB 引用，不复制 public latest 或用户目录副本。

### B. 统一来源模型与 runtime 链路

再做 Task 4、Task 5、Task 6、Task 7。它们把 System/Community Skill、默认聊天、自定义 Agent、descriptor、sandbox 和 `skill_load` 接到同一套解析结果。

交付边界：

- 默认聊天必须从 `thread.agent_id = null` 和 `config.yaml default_chat.system_skills` 解析，不创建 default Agent 或用户安装关系。
- 自定义 Agent 必须通过 `agent_skills.skill_installation_id` 解析，不能回退到 name-only 或 system-specific 字段。
- prompt、sandbox allowlist 和 `skill_load` 必须消费同一个 exact Skill version descriptor。

### C. 旧入口清理、前端跟随和知识同步

最后做 Task 8、Task 9、Task 10。它们依赖前两组的后端合同稳定后，清理旧目录/route/UI，并把文档和测试基线改成新事实来源。

交付边界：

- 旧 route 在迁移窗口内只能返回明确移除错误或新入口指引；迁移完成后删除。
- 前端只暴露 install/update/publish/My Skills/Agent selection 等产品语义，不暴露 artifact、manifest、package version 或内部 ID。
- Trellis spec/user docs 与最终实现保持同步，避免后续任务重新引用旧设计。

## Trellis task 创建规则

后续真正拆 Trellis task 时，不要一次性创建所有任务。按上面的 A/B/C 分组推进：

1. 每次只创建当前分组里最小可验收的 implementation task。
2. 每个 task 的 PRD 都要写清楚它属于 Task 1-10 中的哪一项或哪几项。
3. 每个 task 的 `implement.jsonl` / `check.jsonl` 至少引用 `.trellis/spec/backend/skill-runtime-and-storage.md`；跨前端时再引用 `.trellis/spec/frontend/type-safety.md` 和 `.trellis/spec/frontend/component-guidelines.md`。
4. 如果某个实现 task 发现任务拆分不再准确，先更新本文，再继续拆下一项。

## Task 1：数据模型和迁移收口

目标：

1. `skill.id` 迁移为 UUID，并作为稳定 Skill 身份。
2. `skill_version` 收口为复合身份 `(skill_id, version_number)`。
3. `version_number` 在同一 `skill_id` 下递增且不可变。
4. 删除独立 `skill_version_id` 路径口径。
5. 删除独立 `artifact_uri` 终态字段依赖，运行路径由 `(skill_id, version_number)` 推导为 `.deer-flow/skills/{skill_id}/{version_number}/`。
6. 建立或保护内部系统用户：`external_auth_id="system:deerflow"`。
7. release status 沿用 review-ready 语义。
8. `skill_installation` 保留用户可用关系和 `version_number`，不引入 `install_origin`。
9. 删除 fork/download 相关表和字段，并迁移历史数据引用。
10. 移除 system-specific `agent_skills` 字段的终态依赖。
11. 保持 `threads.agent_id` nullable；null 是默认聊天，不回填 default Agent。
12. 不引入 `agents.kind=default/custom`。

测试：

1. migration 或 preflight 覆盖 UUID `skill.id`。
2. `(skill_id, version_number)` 唯一且不可变。
3. `version_number` 必须属于同一 `skill_id`。
4. 系统用户不可被普通用户冒充。
5. 普通聊天 thread 允许 `agent_id=null`。
6. schema 不包含 default Agent 终态字段。

## Task 2：SkillVersion 内容写入链路

目标：

1. 上传/创建 Skill 时计算 `content_hash` 和 `file_manifest_hash`。
2. 同一 `skill_id` 下相同内容复用已有 `(skill_id, version_number)`。
3. 新内容分配下一个 `version_number`，并写入 `.deer-flow/skills/{skill_id}/{version_number}/`。
4. 失败时清理目录或回滚 row。
5. install/update/publish 不复制或覆盖内容目录。

测试：

1. 新内容创建新版本号目录。
2. 相同内容复用版本。
3. 更新只改 DB 引用。
4. 旧目录不会被覆盖。

## Task 3：发布、安装、更新语义收口

目标：

1. 删除用户可见 fork/download 语义。
2. install 作为平台内状态。
3. update 只切换 `skill_installation.version_number`。
4. publish 先确保或创建 `skill_version(skill_id, version_number)` 和 `.deer-flow/skills/{skill_id}/{version_number}/` 内容目录，再创建或更新 `skill_releases(skill_id, version_number, status)`，不复制 public latest 事实来源。
5. discovery/install/update 只选择 `published` release。
6. archive install / upload / create 的 API 语义重新命名、替换或删除。

测试：

1. install 不产生文件副本。
2. publish 后 `skill_releases` 指向 exact `(skill_id, version_number)`，且 release 不参与 runtime 路径授权。
3. 未更新用户仍使用旧版本。
4. download/fork route 不再执行安装、运行、复制或认领逻辑；迁移窗口内只返回“已移除/请使用 install”，迁移完成后删除。

## Task 4：统一 System/Community Skill 模型

目标：

1. System Skill 通过内部系统用户 owner/publisher 表达。
2. 移除 `source_type="system"` 业务分支。
3. 移除 system-specific `agent_skills` request/response 字段。
4. 官方 badge 由 owner identity 推导。
5. 普通用户不能修改或冒充系统 owner。
6. 默认聊天系统 Skill 只由平台 config 配置。
7. 默认聊天 config 校验 owner 必须是内部系统用户。

测试：

1. 官方 Skill 和社区 Skill 使用同一 release/version 查询模型。
2. 权限保护系统用户。
3. 默认聊天 config 拒绝非系统用户拥有的 Skill。
4. 前端/API 不再提交 system-specific ids。

## Task 5：默认聊天配置 runtime

目标：

1. 新增或收口 `config.yaml`：

```yaml
default_chat:
  system_skills:
    - skill_id: "00000000-0000-0000-0000-000000000000"
      version_number: 1
```

2. 默认聊天 `thread.agent_id=null`。
3. 默认聊天不创建 default Agent。
4. 默认聊天不创建 `skill_installation`。
5. 默认聊天不需要 `install_origin` 或启用关系表。
6. 默认聊天 runtime 从 config 解析 exact `(skill_id, version_number)`。
7. config 配置项必须指向内部系统用户拥有的 Skill 版本。

测试：

1. 普通聊天 thread 保持 `agent_id=null`。
2. 普通聊天 runtime 能加载 config 指定系统 Skill。
3. 普通聊天不会写入 Agent、`skill_installation`、`agent_skills`。
4. 配置非系统 Skill 时启动或解析失败。

## Task 6：自定义 Agent agent_skills 绑定

目标：

1. 自定义 Agent 仍用 `thread.agent_id` 绑定。
2. Agent ownership 必须校验当前用户。
3. `agent_skills` 统一绑定 `skill_installation_id`。
4. `skill_installation` 通过 `skill_id + version_number` 解析 exact `skill_version`。
5. name-only Agent binding 不进入终态。
6. system direct binding 字段迁移删除。

测试：

1. 自定义 Agent 配置独立生效。
2. 自定义 Agent 不能绑定其他用户的 `skill_installation`。
3. 更新 `skill_installation.version_number` 后，相关 Agent 使用新版。
4. name-only 和 system-specific binding 请求被拒绝或迁移。

## Task 7：Runtime descriptor / sandbox / skill_load 收口

目标：

1. runtime descriptor 从默认聊天 config 或自定义 Agent DB 关系生成。
2. descriptor 使用 `skill_id`、`version_number`、`file_manifest_hash`、`virtual_path`。
3. prompt 使用 descriptor 中的 exact Skill 版本。
4. sandbox allowlist 只授权版本目录或其派生只读 mount。
5. `skill_load` 禁止 name-only/public/custom/local/user-dir/`skill_version_id` 旧路径读取。
6. `.runtime-skill-bundles` 只能作为 descriptor 派生缓存，不能作为业务存储。
7. RuntimeManifest JSON 移出核心链路；审计/调试如需留痕，另行设计非核心记录，否则删除相关 schema/test 绑定。

测试：

1. `skill_load` 只能读授权版本。
2. public/custom/local/name-only 不能参与新版 runtime。
3. runtime descriptor 与 config 或 DB 当前版本一致。
4. audit manifest 不影响运行结果。

## Task 8：旧目录和旧入口删除迁移

目标：

1. 迁移或废弃 `public/*`。
2. 迁移或废弃 `{user_id}/*`。
3. 迁移或废弃 `custom/*` / `local/*`。
4. 迁移当前 `artifacts/skills/{definition}/vN-hash/{name}` 到 `skill_id/version_number` 目录。
5. 删除 `{skill_version_id}` 目录口径。
6. 删除 `workspaces` under skills 的设计。
7. 旧 route 不再执行旧逻辑；迁移窗口内只返回明确“已移除/请使用新入口”的错误，迁移完成后删除。

测试：

1. 新 runtime 不读取旧目录。
2. 旧数据迁移后目录与 `(skill_id, version_number)` 一致。
3. 旧 public latest 不影响 install/update 判断。

## Task 9：前端跟随改造

目标：

1. 删除 fork/download 按钮、toast、文案和测试。
2. Gallery / My Skills / Agent config 使用 install/update/publish 语义。
3. 官方 badge 由 unified model 字段驱动。
4. 普通聊天不出现默认 Agent Skill 配置入口。
5. 自定义 Agent Skill selection 不再提交 name-only、`skill_version_id` 或 system-specific ids。

测试：

1. 用户能安装、更新、发布。
2. 用户能把已安装 Skill、个人 Skill 配置到自定义 Agent。
3. fork/download UI 不再出现。
4. 默认聊天没有用户级系统 Skill 开关。

## Task 10：文档、spec、ER 图和测试基线同步

目标：

1. 将 `docs-qy/skills-design` 明确标为旧状态参考。
2. 将新终态同步到 `.trellis/spec` 或用户文档中需要长期沉淀的部分。
3. 更新需要更新的 ER 图，但不要再恢复根目录旧 ER 口径。
4. 更新 schema preflight 说明。
5. 将测试命名从 manifest / `skill_version_id` 事实来源改为 table/directory/runtime descriptor 事实来源。

验收：

1. 新开发者不会从旧文档恢复 fork/download/default-agent/system-branch/manifest/`skill_version_id` 路径设计。
2. 所有后续任务引用 `docs-qy/skills-new` 的终态口径。
