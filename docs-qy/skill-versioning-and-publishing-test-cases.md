# Skills 版本管理与发布功能测试用例设计

日期：2026-04-28

## 1. 文档目的

这份文档用于指导后续以 TDD 模式补齐 Skills 版本管理与发布能力的自动化测试。它不是实现说明，也不是简单罗列测试文件，而是把当前功能拆成可验证的行为契约。

读者：继续开发该功能的后端、前端或测试同学。

读完后应该能做的事：

1. 明确 Skills 版本管理与发布功能的核心行为边界。
2. 按优先级选择一个测试用例，先写失败测试，再补实现或修实现。
3. 判断某个自动化测试应该落在单元、接口、集成、前端组件还是端到端层。
4. 在代码改动后，用这份清单检查是否遗漏关键风险场景。

## 2. 当前业务契约摘要

### 2.1 核心概念

| 概念 | 含义 | 关键约束 |
| --- | --- | --- |
| custom skill | 某个用户自己的技能副本 | `skills.user_id` 有值；可上传、删除、发布 |
| public latest skill | 当前公共市场里可见的最新技能副本 | `skills.user_id` 为空；由发布流程产生；普通用户不可直接修改或删除 |
| package_version | skill 包自身版本 | 来自 `SKILL.md` frontmatter 的 `version` 字段；可为空；不强制 SemVer；必须是字符串 |
| release_version | 系统生成的发布记录版本 | 由发布流程生成；形如 `rel_xxx`；不可变；唯一 |
| skill_releases | 发布历史记录 | 记录每次 publish 事件，包含 package_version、release_notes、发布人、源 skill、public latest skill |
| release_notes | 发布说明 | 由 publish 请求传入；归属于发布事件，不修改 skill 包自身版本 |

### 2.2 公开入口

| 入口 | 行为 |
| --- | --- |
| `GET /api/skills` | 返回当前用户 custom skills 与 public latest skills，并携带版本/发布元数据 |
| `GET /api/skills/{skill_name}` | 返回单个可见 skill，优先当前用户 custom 副本，否则 public latest |
| `POST /api/skills/check-upload` | 解析上传包，判断同名同版本冲突、同名新版本更新 |
| `POST /api/skills/uploads` | 上传 custom skill；同名新版本更新现有 custom 行，同名同版本默认拒绝 |
| `POST /api/skills/{skill_name}/publish` | 将当前用户 custom skill 发布为 public latest，并创建 release 记录 |
| `POST /api/skills/{skill_name}/check-download` | 判断下载 public latest 是否会覆盖当前用户 custom skill |
| `POST /api/skills/{skill_name}/download` | 将 public latest 下载为当前用户 custom skill |
| 前端 Skills Gallery | 展示版本徽标、发布人、发布弹窗、release notes、上传/下载/发布操作 |

### 2.3 关键不变量

1. `package_version` 只来自 `SKILL.md`，发布请求不能修改它。
2. `release_version` 由系统生成，不能由客户端指定。
3. 发布成功后，对同一 `skill_name` 应只有一个 active public latest。
4. 历史 release 记录不可变；再次发布应新增 release 记录，而不是覆盖旧 release。
5. 同名 custom skill 上传时：
   - package_version 不同：更新当前 custom skill，不新增第二个 active 同名 custom row。
   - package_version 相同：默认拒绝，除非显式 overwrite。
6. 失败时不能留下半发布状态：
   - 数据库回滚。
   - public artifact 尽可能恢复到发布前状态。
   - 不创建无效 release 记录。
7. public skill 只读；用户只能下载成自己的 custom skill 后再修改/发布。

## 3. 测试分层策略

| 层级 | 适用内容 | 建议工具/方式 |
| --- | --- | --- |
| 单元测试 | frontmatter 解析、release notes 规范化、repository 创建 release、response shape 转换 | 直接调用函数或 repository，mock DB session |
| Router 级测试 | publish/upload/download 的业务流、状态码、rollback、文件副作用 | 直接调用 router handler，替换 repository 和文件路径 |
| 数据库集成测试 | migration、唯一约束、soft delete 后重复发布、release 查询排序 | 测试数据库或迁移 smoke test |
| API 集成测试 | HTTP 请求体校验、FastAPI/Pydantic 422、multipart 行为、鉴权依赖 | TestClient/AsyncClient |
| 前端单元测试 | API client 请求体、错误处理、类型契约 | fetch mock |
| 前端组件测试 | Skills Gallery 的按钮、弹窗、版本展示、confirm 分支 | React Testing Library |
| 端到端测试 | 上传、发布、列表展示、下载覆盖的真实用户流程 | Playwright 或后续 e2e harness |

TDD 优先顺序建议：

1. P0 后端行为：publish 成功、publish 失败回滚、upload 同名版本判断、list/get 版本元数据。
2. P0 API 契约：状态码、响应字段、错误 detail、release_notes 长度校验。
3. P1 数据库集成：migration、约束、历史 release 不可变。
4. P1 前端行为：发布弹窗、release_notes 请求体、版本显示。
5. P2 并发、端到端和可观测性。

## 4. 通用测试数据

### 4.1 用户

| 名称 | 字段 |
| --- | --- |
| Alice | `id=7`, `username=alice`, `display_name=Alice` |
| Bob | `id=8`, `username=bob`, `display_name=Bob` |
| Legacy publisher | `id=2`, `username=legacy`, `display_name=Legacy User` |

### 4.2 Skill 包

| 名称 | `SKILL.md` 元数据 | 用途 |
| --- | --- | --- |
| versioned demo v1 | `name: demo-skill`, `description: Demo skill`, `version: v1` | 基础版本 |
| versioned demo v2 | `name: demo-skill`, `description: Demo skill v2`, `version: v2` | 同名新版本 |
| unversioned demo | 无 `version` 字段 | 未声明包版本 |
| invalid numeric version | `version: 1.2` | 非字符串版本，应拒绝 |
| mismatched name | 请求路径是 `demo-skill`，frontmatter 是 `other-skill` | 发布元数据不匹配 |
| invalid name | `name: Demo Skill` 或 `name: -demo` | 名称格式非法 |
| long release notes | 超过 4000 字符 | 发布说明长度校验 |

### 4.3 初始数据库状态

| 状态 | 内容 |
| --- | --- |
| empty catalog | 无 public latest |
| legacy public | 有 active public skill，但没有对应 release record |
| versioned public latest | active public skill + 一条 published release |
| user custom only | Alice 有 custom skill，public catalog 无同名 skill |
| user custom + old public | Alice 有 custom skill，catalog 有旧 public latest |
| multi public duplicates | 同名 public rows 多条 active，用于验证 publish 后收敛为一个 latest |

## 5. 测试用例总览

优先级说明：

- P0：版本/发布主链路必须覆盖，缺失会影响功能可信度。
- P1：重要边界或回归风险，建议本轮补齐。
- P2：并发、可观测性、端到端体验，可在主链路稳定后补。

自动化状态说明：

- 已有：当前代码库已有相近自动化测试。
- 待补：建议新增。
- 扩展：已有覆盖，但需要增加断言或更贴近真实接口。

## 6. Frontmatter 与 package_version 用例

| ID | 优先级 | 层级 | 场景 | 前置条件 | 操作 | 预期结果 | 自动化状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SKV-001 | P0 | 单元 | 读取字符串 package_version | skill 目录含 `version: v1.2.3` | 解析 package_version | 返回 `v1.2.3` | 已有 |
| SKV-002 | P0 | 单元 | 未声明 package_version | skill 目录无 `version` | 解析 package_version | 返回 `None`，不报错 | 已有/扩展 |
| SKV-003 | P0 | 单元/Router | 非字符串 version 被拒绝 | `version: 1.2` | upload 或 publish | 返回 400；detail 提示 version 必须是 string | 已有 |
| SKV-004 | P0 | 单元 | 不强制 SemVer | `version: beta-2026-04-28` | 解析/发布 | 成功；原样作为 package_version | 待补 |
| SKV-005 | P1 | 单元 | 空字符串 version | `version: ""` | 解析/发布 | 若 YAML 解析为字符串，应允许并按空字符串处理；展示层应 fallback 到 release_version 或无版本 | 待补 |
| SKV-006 | P1 | 单元 | version 前后空格 | `version: " v1 "` | 解析/发布 | 需要明确是否保留原样；建议预期为保留原样，避免隐式修改包元数据 | 待补 |
| SKV-007 | P0 | 单元/Router | frontmatter 缺少 name | `SKILL.md` 无 name | upload/publish | 400；不写文件、不写 DB | 待补 |
| SKV-008 | P0 | 单元/Router | frontmatter 缺少 description | `SKILL.md` 无 description | upload/publish | 400；不写文件、不写 DB | 待补 |
| SKV-009 | P1 | 单元/Router | description 含 `<` 或 `>` | description 含 HTML-like 字符 | upload/publish | 400；detail 可读 | 待补 |
| SKV-010 | P1 | 单元/Router | compatibility 为非字符串 | `compatibility: [a]` | upload/publish | 400；detail 可读 | 待补 |
| SKV-011 | P1 | 单元/Router | 允许 author/compatibility 等可选字段 | frontmatter 含允许的可选字段 | upload/publish | 成功；不把这些字段误写为 release 元数据 | 待补 |
| SKV-012 | P1 | 单元/Router | 未知 frontmatter key | frontmatter 含 `unexpected: true` | upload/publish | 400；detail 列出允许字段 | 待补 |
| SKV-013 | P0 | Router | publish 路径 skill_name 与 SKILL.md name 不一致 | custom row 名为 `demo-skill`，文件内 name 为 `other-skill` | publish `demo-skill` | 400；不复制 public artifact，不创建 release | 待补 |

## 7. Release 数据模型与仓储用例

| ID | 优先级 | 层级 | 场景 | 前置条件 | 操作 | 预期结果 | 自动化状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SKR-001 | P0 | 单元/模型 | SkillRelease 模型列完整 | ORM 已加载 | 检查模型字段 | 包含 release_version、package_version、release_notes、status、artifact_path、publisher/source/published 关联 | 已有 |
| SKR-002 | P0 | 单元 | create_release 生成 release_version | 未传 release_version | 创建 release | release_version 以 `rel_` 开头；状态默认 `published` | 已有 |
| SKR-003 | P0 | 单元 | create_release 可接受无 package_version | package_version 为 None | 创建 release | 成功；package_version 为 None | 已有 |
| SKR-004 | P0 | 单元 | create_release 保存 release_notes | release_notes 为字符串 | 创建 release | release_notes 原样保存 | 已有 |
| SKR-005 | P0 | 单元/集成 | release_version 唯一 | 已存在同 release_version | 再插入同 release_version | DB 报唯一约束错误；业务层不吞错 | 待补 |
| SKR-006 | P1 | 集成 | migration 创建 skill_releases 表 | 迁移从旧版本升级 | 执行迁移 | 表、索引、唯一约束存在 | 已有/扩展 |
| SKR-007 | P1 | 集成 | release_notes migration 可重复执行 | 已有 release_notes 列 | 执行 upgrade | 不重复加列、不失败 | 已有/扩展 |
| SKR-008 | P1 | 集成 | downgrade 移除 release_notes | migration downgrade | 执行 downgrade | release_notes 列被移除 | 待补 |
| SKR-009 | P0 | 单元/集成 | 查询 public skill 最新 release | public skill 有多条 published release | get_latest_release_for_public_skill | 返回 created_at 最新的 published release | 扩展 |
| SKR-010 | P1 | 单元/集成 | 忽略非 published release | 同一 public skill 有 draft/failed release | 查询 latest | 只返回 status=`published` 的 release | 待补 |
| SKR-011 | P1 | 集成 | source_skill 被删除后 release 保留 | source custom skill 被 soft delete 或物理 FK SET NULL | 查询 release | release 仍存在；source_skill_id 可为空或仍可审计 | 待补 |
| SKR-012 | P1 | 集成 | published_skill 被替换后旧 release 保留 | 连续发布两次 | 查询历史 release | 旧 release 仍指向旧 public row，新 release 指向新 public row | 待补 |

## 8. Publish 成功路径用例

| ID | 优先级 | 层级 | 场景 | 前置条件 | 操作 | 预期结果 | 自动化状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SKP-001 | P0 | Router | 首次发布 versioned custom skill | Alice 有 `demo-skill` custom v1，catalog 无同名 public | POST publish | 创建 public latest；创建 release；返回 package_version、release_version、release_status、published_at | 已有/扩展 |
| SKP-002 | P0 | Router | 发布时保留 package_version 来源 | 请求体传 release_notes，不传 version | POST publish | package_version 来自 `SKILL.md`，不受请求体影响 | 已有 |
| SKP-003 | P0 | Router | release_notes 去除首尾空白 | release_notes 为 `"  Fix bug  "` | POST publish | release 记录为 `"Fix bug"` | 已有 |
| SKP-004 | P0 | Router | 空 release_notes 归一为 None | release_notes 为 `""` 或空白 | POST publish | release_notes 为 None；响应中为 null | 待补 |
| SKP-005 | P0 | Router | 发布 unversioned skill | custom skill 无 version | POST publish | 发布成功；package_version 为 null；version fallback 到 release_version | 待补 |
| SKP-006 | P0 | Router/集成 | 覆盖旧 public latest | 已有旧 active public latest | POST publish | 旧 public row soft delete；新 public row active；release 指向新 row | 已有/扩展 |
| SKP-007 | P0 | Router/集成 | 多条旧 public duplicates 被收敛 | 同名 active public rows 多条 | POST publish | 所有旧 active public rows 被 soft delete；只剩新 public latest active | 待补 |
| SKP-008 | P1 | Router | 同 package_version 重复发布也创建新 release | Alice custom v1 已发布过一次 | 再次 POST publish | 新 public latest 和新 release 被创建；release_version 不同；package_version 可相同 | 待补 |
| SKP-009 | P1 | Router | 新 package_version 发布 | Alice 将 custom 从 v1 更新到 v2 | POST publish | public latest package_version 为 v2；旧 v1 release 保留 | 待补 |
| SKP-010 | P0 | Router | 发布响应 owner 信息正确 | 当前用户 display_name 为 Alice | POST publish | 返回 owner_user_id=7，owner_display_name=Alice | 待补 |
| SKP-011 | P1 | Router | owner_display_name fallback | display_name 为空，username 有值 | POST publish 后 list/get | owner_display_name 使用 username | 待补 |
| SKP-012 | P0 | Router | 发布只提交一次事务 | 成功 publish | 观察 fake db commit/rollback | commit 1 次，rollback 0 次；repository create 使用 commit=False | 已有 |
| SKP-013 | P1 | Router | public artifact 路径稳定 | publish demo-skill | 检查 created skill 与 release artifact_path | 两者使用同一个 public latest storage path | 已有/扩展 |
| SKP-014 | P1 | Router | description 使用 SKILL.md 当前描述 | custom row description 旧，SKILL.md description 新 | POST publish | public row 和 release description 使用 SKILL.md 新描述 | 已有 |

## 9. Publish 错误与回滚用例

| ID | 优先级 | 层级 | 场景 | 前置条件 | 操作 | 预期结果 | 自动化状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SKF-001 | P0 | Router | 发布不存在的 custom skill | 当前用户无此 custom skill | POST publish | 404；rollback；不复制文件、不创建 release | 已有 |
| SKF-002 | P0 | Router | 发布 public skill 不允许 | 只有 public latest，无当前用户 custom copy | POST publish | 404；不能把 public 直接当 source 发布 | 待补 |
| SKF-003 | P0 | Router | SKILL.md 缺失 | custom row 指向目录但无 SKILL.md | POST publish | 400；rollback；不复制 public artifact | 待补 |
| SKF-004 | P0 | Router | YAML frontmatter 非法 | SKILL.md frontmatter YAML 错误 | POST publish | 400；detail 可读；不复制 public artifact | 待补 |
| SKF-005 | P0 | Router | name 与请求路径不一致 | source metadata name 为 other-skill | POST publish demo-skill | 400；不复制 artifact；不创建 release | 待补 |
| SKF-006 | P0 | Router | package version 非字符串 | `version: 1.2` | POST publish | 400；不复制 artifact；不创建 release | 已有 |
| SKF-007 | P0 | API | release_notes 超过 4000 字符 | 请求体 release_notes 长度 4001 | POST publish | HTTP 422 或 400；不进入复制/DB 写入 | 待补 |
| SKF-008 | P0 | Router | 复制 public artifact 失败 | 文件系统 copy 抛错 | POST publish | 500 generic detail；rollback；旧 public artifact 不变；不 soft delete、不 create public、不 create release | 已有 |
| SKF-009 | P0 | Router | 创建 public row 失败后恢复 artifact | copy 成功，create_skill 抛错 | POST publish | 500；rollback；恢复旧 public artifact；不创建 release | 待补 |
| SKF-010 | P0 | Router | 创建 release 失败后恢复 artifact | copy 和 create public 成功，create_release 抛错 | POST publish | 500；rollback；恢复旧 public artifact；已调用的 DB 变更不提交 | 已有 |
| SKF-011 | P0 | Router | commit 失败后恢复 artifact | release 已创建但 commit 抛错 | POST publish | 500；rollback；恢复旧 public artifact；artifact_committed 不应置 true | 待补 |
| SKF-012 | P1 | Router | commit 后刷新 public skill 失败 | commit 成功，get_skill_by_id 返回 None | POST publish | 当前实现会返回 500；需要明确 artifact 已提交后不应恢复；建议补测试锁定行为 | 待补 |
| SKF-013 | P1 | Router | restore 过程中目标目录不存在 | 发布前无旧 artifact，copy 后 DB 失败 | POST publish | target_dir 被删除或保持不存在；不留下新 artifact | 待补 |
| SKF-014 | P1 | Router | restore 过程中自身失败 | restore 抛错 | POST publish | 最终仍返回 500；日志包含原 publish phase；需要评估是否吞掉 restore error | 待补 |
| SKF-015 | P1 | 日志 | 失败日志包含阶段信息 | 任意系统异常 | POST publish | 日志含 phase、skill_name、publisher_user_id、error_type；不泄露敏感文件内容 | 已有/扩展 |
| SKF-016 | P1 | API | ValueError 映射为 400，系统错误映射为泛化 500 | 分别制造 metadata 错误和 DB 错误 | POST publish | metadata 错误 detail 具体；系统错误 detail 为 `Failed to publish skill` | 已有/扩展 |

## 10. Upload 与 check-upload 用例

| ID | 优先级 | 层级 | 场景 | 前置条件 | 操作 | 预期结果 | 自动化状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SKU-001 | P0 | Router | check-upload 同名新版本 | Alice 已安装 demo v1，上传 demo v2 | POST check-upload | exists=false，same_version=false，message 提示 will be updated | 已有 |
| SKU-002 | P0 | Router | check-upload 同名同版本 | Alice 已安装 demo v1，上传 demo v1 | POST check-upload | exists=true，same_version=true，message 提示 already exists | 已有 |
| SKU-003 | P0 | Router | check-upload 新 skill | Alice 无同名 custom，目标目录也不存在 | POST check-upload | exists=false，same_version=false，message 提示 available | 待补 |
| SKU-004 | P1 | Router | check-upload orphaned target dir | DB 无 active row，但目标目录已存在 | POST check-upload | exists=true；防止覆盖孤儿目录 | 待补 |
| SKU-005 | P0 | Router | upload 同名新版本更新当前 row | Alice 已安装 demo v1，上传 demo v2 | POST uploads | action=updated；不 create 新 row；文件替换；description 更新 | 已有 |
| SKU-006 | P0 | Router | upload 同名同版本默认拒绝 | Alice 已安装 demo v1，上传 demo v1 | POST uploads | action=skipped；success=false；不 commit，不替换文件 | 已有/扩展 |
| SKU-007 | P0 | Router | upload 同名同版本 overwrite | Alice 已安装 demo v1，overwrite_names 包含 demo-skill | POST uploads | action=updated；文件重装；commit | 待补 |
| SKU-008 | P0 | Router | upload unversioned 到 unversioned 视为同版本 | 已安装无 version，上传无 version | POST check-upload/uploads | same_version=true；默认拒绝 | 待补 |
| SKU-009 | P1 | Router | upload versioned 到 unversioned | 已安装无 version，上传 v1 | POST uploads | 视为新版本更新；action=updated | 待补 |
| SKU-010 | P1 | Router | upload unversioned 到 versioned | 已安装 v1，上传无 version | POST uploads | 视为新版本更新；action=updated | 待补 |
| SKU-011 | P0 | Router | upload 新 skill 创建 custom row | Alice 无同名 custom | POST uploads | action=created；创建 DB row；写入 private artifact | 待补 |
| SKU-012 | P0 | Router | upload 多文件部分成功 | 一个合法包，一个非法包 | POST uploads | 返回两个 result；合法包成功，非法包失败；互不影响 | 待补 |
| SKU-013 | P0 | Router/API | upload 非 zip | 文件不是 zip | POST check-upload/uploads | check-upload 返回 400；uploads 返回单项失败 | 待补 |
| SKU-014 | P0 | Router/API | zip root 有多个 skill folder | archive 多根目录 | POST upload | 失败；message 指明必须 exactly one skill folder | 待补 |
| SKU-015 | P0 | Router/API | zip 包含 unsafe path | archive 有 `../` 或绝对路径 | POST upload | 失败；不解压到目标外 | 待补 |
| SKU-016 | P1 | Router | upload 更新时 DB flush 失败 | 文件已替换，flush 抛错 | POST uploads | rollback；需要明确是否恢复旧文件；建议补测试暴露当前风险 | 待补 |
| SKU-017 | P1 | Router | upload create row 失败 | 文件已复制，create_skill 抛错 | POST uploads | rollback；建议要求删除新 target 或恢复旧 target | 待补 |
| SKU-018 | P1 | API | multipart overwrite_names 多值 | overwrite_names 重复提交 | POST uploads | 后端按集合处理；重复值不影响结果 | 待补 |
| SKU-019 | P1 | 前端组件 | 同名同版本 check 返回 exists 后用户取消 | checkSkillUpload 返回 exists=true，confirm=false | 选择文件 | 不调用 uploadSkills；清空 input | 待补 |
| SKU-020 | P1 | 前端组件 | 同名新版本 check 返回 exists=false | checkSkillUpload 返回 exists=false | 选择文件 | 直接上传，不弹 overwrite confirm | 待补 |

## 11. List/Get/Download 版本展示用例

| ID | 优先级 | 层级 | 场景 | 前置条件 | 操作 | 预期结果 | 自动化状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SKG-001 | P0 | Router | list public latest 携带 release metadata | public skill 有 published release | GET /api/skills | 返回 package_version、release_version、release_status、release_notes、published_at、owner 信息 | 已有 |
| SKG-002 | P0 | Router | list legacy public skill | public skill 无 release record | GET /api/skills | version/package_version/release_version/release_status/release_notes/published_at 均为 null | 已有 |
| SKG-003 | P0 | Router | list custom skill 读取 package_version | custom skill SKILL.md 有 version | GET /api/skills | category=custom；package_version/version 为 SKILL.md version；release fields 为 null | 已有 |
| SKG-004 | P1 | Router | list custom skill 读取失败不炸接口 | custom skill 文件缺失或解析失败 | GET /api/skills | package_version 为 null；列表仍成功返回 | 待补 |
| SKG-005 | P0 | Router | get public latest 携带 release metadata | 无当前用户 custom，public 有 release | GET /api/skills/demo-skill | 返回 public release metadata | 已有 |
| SKG-006 | P0 | Router | get 优先 custom | 当前用户 custom 与 public 同名 | GET /api/skills/demo-skill | 返回 custom；不返回 public release metadata | 待补 |
| SKG-007 | P1 | Router | list_visible 去重 public duplicates | 多个 active public rows 同名 | GET /api/skills | 每个 public name 只返回一条，优先最新 row | 待补 |
| SKG-008 | P0 | Router | download public latest 带源 release metadata | public skill 有 release，Alice 无 custom | POST download | 创建 custom skill；响应 category=custom，但携带源 release metadata | 已有 |
| SKG-009 | P0 | Router | download existing custom without overwrite | Alice 已有同名 custom | POST download overwrite=false | 409；rollback；不替换文件 | 已有 |
| SKG-010 | P0 | Router | download existing custom with overwrite | Alice 已有同名 custom | POST download overwrite=true | 旧 custom soft delete，新 custom row 创建，agent skill 绑定迁移 | 待补 |
| SKG-011 | P1 | Router | check-download 忽略 owner_user_id 兼容字段 | public latest owner_user_id 与请求不同 | POST check-download | 仍按 skill_name 找 public latest | 待补 |
| SKG-012 | P1 | Router | download public latest 不存在 | catalog 无此 skill | POST download | 404；不写文件 | 待补 |

## 12. 前端 API 与组件用例

| ID | 优先级 | 层级 | 场景 | 前置条件 | 操作 | 预期结果 | 自动化状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SKFED-001 | P0 | 前端单元 | publishSkill 发送 release_notes | mock fetch | 调用 publishSkill(name, {release_notes}) | 请求 POST `/api/skills/{name}/publish`；JSON body 含 release_notes；credentials include | 待补 |
| SKFED-002 | P0 | 前端单元 | publishSkill 错误 detail 透传 | fetch 返回 400/500 detail | 调用 publishSkill | throw Error(detail) | 待补 |
| SKFED-003 | P1 | 前端单元 | Skill 类型包含版本字段 | TS 编译 | 使用 Skill.version/package_version/release_version | 类型通过 | 已有/隐式 |
| SKFED-004 | P0 | 组件 | custom skill 菜单展示 Publish | filter=custom，有 custom skill | 打开更多菜单 | 有删除和发布；无下载 | 待补 |
| SKFED-005 | P0 | 组件 | public skill 菜单展示 Download | filter=public，有 public skill | 打开更多菜单 | 有下载；无删除和发布 | 待补 |
| SKFED-006 | P0 | 组件 | 打开发布弹窗显示版本与描述 | custom skill 有 package_version 和 description | 点击 Publish | 弹窗显示 name、package version、description、release notes 输入框 | 待补 |
| SKFED-007 | P0 | 组件 | 确认发布 trimming release_notes | releaseNotes 输入前后空格 | 点击 confirm | mutateAsync 入参 releaseNotes 去空白；成功后关闭弹窗并清空输入 | 待补 |
| SKFED-008 | P0 | 组件 | 发布空 release_notes | releaseNotes 为空白 | 点击 confirm | mutateAsync 入参 releaseNotes 为 null | 待补 |
| SKFED-009 | P0 | 组件 | 发布中禁用关闭/按钮 | publish mutation pending | 渲染弹窗 | textarea 和按钮 disabled；按钮文案为 publishing | 待补 |
| SKFED-010 | P1 | 组件 | 发布失败不关闭弹窗 | publish mutation reject | 点击 confirm | toast error；弹窗仍保留，releaseNotes 不丢 | 待补 |
| SKFED-011 | P1 | 组件 | public skill 显示 publisher | public skill 有 owner_display_name | 渲染列表 | 显示发布者信息 | 待补 |
| SKFED-012 | P1 | 组件 | version badge fallback | skill 有 package_version | 渲染 | badge 显示 package_version；detail 为 Latest/Package 文案 | 待补 |
| SKFED-013 | P1 | 组件 | release_version fallback | public skill 无 package_version 但有 release_version | 渲染 | badge 显示 release_version | 待补 |
| SKFED-014 | P1 | 组件 | 无版本 fallback | skill 无 package_version/release_version | 渲染 | badge/detail 显示 no package version | 待补 |
| SKFED-015 | P1 | 组件 | 上传部分失败 toast | uploadSkills 返回 success 与 failed 混合 | 选择文件 | 成功 toast 一次；每个失败 result toast error | 待补 |
| SKFED-016 | P1 | 组件 | 下载冲突用户取消 | checkDownload exists=true，confirm=false | 点击 download | 不调用 download mutation | 待补 |

## 13. 权限、隔离与安全边界用例

| ID | 优先级 | 层级 | 场景 | 前置条件 | 操作 | 预期结果 | 自动化状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SKS-001 | P0 | Router/API | 用户只能发布自己的 custom skill | Bob 无 demo custom，Alice 有 demo custom | Bob POST publish demo | 404；不能发布 Alice 的 skill | 待补 |
| SKS-002 | P0 | Router/API | 用户上传同名 skill 不影响他人 custom | Alice 和 Bob 均有 demo custom | Alice 上传 v2 | 只更新 Alice row 和 artifact；Bob 不变 | 待补 |
| SKS-003 | P0 | Router/API | public skill 不可删除 | 存在 public latest | DELETE /api/skills/demo | 403 | 已有/扩展 |
| SKS-004 | P0 | Router/API | public skill 不可 update/touch | 存在 public latest | PUT /api/skills/demo | 403 | 待补 |
| SKS-005 | P1 | Router/API | 下载 public 到 custom 时 owner_user_id 不授权选择历史发布者 | 有多个发布历史 | POST download with owner_user_id | 只能下载 public latest，不按 owner_user_id 取旧版本 | 待补 |
| SKS-006 | P1 | Router/API | 上传 zip 路径穿越防护 | zip entry 为 `../x` | upload/check-upload | 400 或单项失败；目标外无文件产生 | 待补 |
| SKS-007 | P1 | API | 未登录访问 Skills 管理接口 | 无 current_user | 调用写接口 | 返回鉴权错误；不进入业务逻辑 | 待补 |
| SKS-008 | P2 | 集成 | 发布日志不包含 SKILL.md 正文 | publish 失败，SKILL.md 含敏感文本 | 查看日志 | 日志只含阶段、skill_name、publisher、error 类型，不打印全文 | 待补 |

## 14. 并发与一致性用例

| ID | 优先级 | 层级 | 场景 | 前置条件 | 操作 | 预期结果 | 自动化状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SKC-001 | P1 | 集成 | 两次连续发布同名 skill | Alice 先发布 v1，再发布 v2 | 顺序 POST publish | 最终 public latest 为 v2；v1 release 保留 | 待补 |
| SKC-002 | P2 | 集成 | 同用户并发发布同名 skill | Alice 同时发两个 publish | 并发 POST publish | 最终只应有一个 active public latest；至少一个请求成功或明确失败；不出现两个 active latest | 待补 |
| SKC-003 | P2 | 集成 | 不同用户并发发布同名 skill | Alice/Bob 都有 demo custom | 并发 publish | 业务需明确最后写入者胜出还是拒绝冲突；建议锁定“最终单 active latest” | 待补 |
| SKC-004 | P2 | 集成 | 发布和下载并发 | Alice 发布，Bob 同时 download | 并发操作 | Bob 下载到的是某个一致的 public latest；不会复制半成品 artifact | 待补 |
| SKC-005 | P2 | 集成 | 上传和发布同一 custom skill 并发 | Alice 上传 v2，同时 publish demo | 并发操作 | 需要明确锁策略；不能出现 DB package_version 与 public artifact 内容不一致 | 待补 |

## 15. 端到端验收用例

| ID | 优先级 | 层级 | 场景 | 步骤 | 预期结果 | 自动化状态 |
| --- | --- | --- | --- | --- | --- | --- |
| SKE2E-001 | P1 | E2E | 上传新 skill 后发布为 public latest | 登录 Alice；上传 demo v1；切到 custom；点击发布；填写 release_notes；确认；切到 public | public 列表出现 demo；显示版本 v1、发布者 Alice；刷新后仍存在 | 待补 |
| SKE2E-002 | P1 | E2E | 新版本上传后再次发布 | 在 SKE2E-001 基础上上传 demo v2；发布 | public latest 显示 v2；后端 release history 有两条 | 待补 |
| SKE2E-003 | P1 | E2E | Bob 下载 Alice 发布的 public skill | Alice 发布 demo；Bob 登录；下载 demo | Bob custom 列表出现 demo；public latest 不受影响 | 待补 |
| SKE2E-004 | P1 | E2E | 同名同版本上传冲突取消 | Alice 已有 demo v1；再次上传 v1；取消 confirm | 不更新 custom；无成功 toast；列表不变 | 待补 |
| SKE2E-005 | P2 | E2E | 发布失败恢复旧 public latest | 通过测试开关制造 release DB 失败 | publish 返回失败；public 列表仍显示旧版本 | 待补 |

## 16. 推荐 TDD 落地顺序

### 第一组：发布主链路

目标：先让最核心的 publish 行为被一条端到端业务路径 pin 住。

1. SKP-001：首次发布 versioned custom skill。
2. SKP-004：空 release_notes 归一为 None。
3. SKP-005：发布 unversioned skill。
4. SKP-006：覆盖旧 public latest。
5. SKF-010：release 创建失败恢复 artifact。
6. SKF-011：commit 失败恢复 artifact。

每个用例单独走 red-green-refactor。不要一次性把全部测试写完。

### 第二组：上传版本判断

目标：把同名同版本和同名新版本的产品语义固定下来。

1. SKU-003：check-upload 新 skill。
2. SKU-005：upload 同名新版本更新当前 row。
3. SKU-006：upload 同名同版本默认拒绝。
4. SKU-007：upload 同名同版本 overwrite。
5. SKU-008/SKU-009/SKU-010：unversioned 与 versioned 组合。

### 第三组：列表/下载展示

目标：确保发布后用户真正能看到、下载、复用版本元数据。

1. SKG-001：list public latest release metadata。
2. SKG-003：list custom package_version。
3. SKG-006：get 优先 custom。
4. SKG-008：download public latest 带源 release metadata。
5. SKG-010：download overwrite 迁移 agent skill 绑定。

### 第四组：前端交互

目标：确保用户触发的操作和后端契约一致。

1. SKFED-001：publishSkill 请求体。
2. SKFED-006：发布弹窗展示版本和描述。
3. SKFED-007/SKFED-008：release_notes trim/null。
4. SKFED-010：发布失败不关闭弹窗。
5. SKFED-012/SKFED-013/SKFED-014：版本 badge fallback。

## 17. 当前已有覆盖与明显缺口

### 17.1 已有覆盖较好的部分

1. release 模型基础字段、创建 release、无 package_version、release_notes 保存。
2. publish 成功创建 public latest 和 release，返回版本化响应。
3. publish 缺少 custom skill 返回 404。
4. publish copy failure 不进入 DB 更新。
5. publish release failure 恢复旧 public artifact。
6. publish invalid numeric version 返回 400。
7. list/get/download 的部分版本元数据响应。
8. check-upload 同名新版本和同名同版本。
9. upload 同名新版本更新当前 custom row。
10. upload 同名同版本默认 skipped。

### 17.2 建议优先补齐的缺口

1. unversioned skill 的发布、上传、展示全链路。
2. commit 失败后的 artifact restore 行为。
3. create public row 失败后的 artifact restore 行为。
4. release_notes 空白归一和超长请求的 API 层状态码。
5. 同名 public duplicates 发布后收敛为单 active latest。
6. get skill 时 custom 优先于 public，并且不混入 public release metadata。
7. download overwrite 时旧 custom soft delete、新 custom 创建、agent skill 绑定迁移。
8. zip 安全解压、非 zip、多根目录等上传安全边界。
9. 前端 publish 弹窗和 release_notes 请求体。
10. 用户隔离：Bob 不能发布 Alice 的 custom skill。

## 18. 后续自动化测试命名建议

命名原则：测试名直接读成业务句子，不暴露内部实现细节。

建议新增或扩展的测试名称：

```text
test_publish_unversioned_skill_returns_release_version_as_display_version
test_publish_blank_release_notes_are_stored_as_null
test_publish_create_public_row_failure_restores_previous_public_artifact
test_publish_commit_failure_restores_previous_public_artifact
test_publish_soft_deletes_all_previous_public_latest_rows_for_name
test_get_skill_prefers_current_users_custom_copy_over_public_latest
test_upload_same_name_same_version_with_overwrite_reinstalls_skill
test_upload_unversioned_skill_conflicts_with_existing_unversioned_skill
test_upload_rejects_zip_with_unsafe_paths
test_download_public_skill_with_overwrite_rebinds_agent_skills
test_publish_skill_api_rejects_release_notes_over_4000_characters
test_skills_gallery_sends_trimmed_release_notes_when_publishing
test_skills_gallery_keeps_publish_dialog_open_when_publish_fails
```

## 19. Definition of Done

本功能的测试设计被认为落地完成，需要满足：

1. P0 用例全部有自动化测试，且测试从公开入口验证行为。
2. 所有新增测试都经历过失败态，再通过最小实现修绿。
3. publish 成功、失败、回滚、展示四条主链路均有覆盖。
4. upload 同名同版本、同名新版本、unversioned 三类版本判断均有覆盖。
5. release history 不可变、public latest 单 active 的不变量有集成测试。
6. 前端能验证 publish 请求体、弹窗状态和版本展示。
7. 全量相关测试通过后，才标记该功能为完成。
