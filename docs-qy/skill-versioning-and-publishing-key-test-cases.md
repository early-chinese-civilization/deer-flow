# Skills 版本管理与发布关键测试用例

日期：2026-04-28

## 1. 目的

这份文档是完整测试用例设计的精简版，只保留 Skills 版本管理与发布功能必须优先覆盖的关键测试用例。后续走 TDD 时，可以按这里的顺序逐条落自动化测试。

## 2. 核心测试目标

需要优先验证四件事：

1. skill 包版本能被正确识别和展示。
2. custom skill 能正确发布为 public latest。
3. 发布失败时不会留下半发布状态。
4. 同名 skill 上传时能正确区分“同版本冲突”和“新版本更新”。

## 3. 关键业务不变量

1. `package_version` 来自 `SKILL.md` 的 `version` 字段，发布请求不能修改它。
2. `release_version` 由系统生成，用来标识一次不可变发布记录。
3. 同一个 `skill_name` 同时只能有一个 active public latest。
4. 每次成功发布都应该新增一条 `skill_releases` 记录。
5. 同名同版本上传默认拒绝；同名不同版本上传更新当前 custom skill。
6. 发布失败时数据库要 rollback，public artifact 要尽量恢复到发布前状态。

## 4. P0 关键测试用例

| ID | 场景 | 前置条件 | 操作 | 预期结果 |
| --- | --- | --- | --- | --- |
| K-001 | 读取 skill 包版本 | `SKILL.md` 中有 `version: v1.2.3` | 解析 skill 元数据 | 返回 `package_version = v1.2.3` |
| K-002 | 非字符串版本被拒绝 | `SKILL.md` 中有 `version: 1.2` | 上传或发布该 skill | 返回 400；不写 DB、不复制 artifact |
| K-003 | 首次发布 custom skill | 用户有 custom skill，public catalog 无同名 skill | `POST /api/skills/{name}/publish` | 创建 public latest；创建 release；响应包含 package_version、release_version、release_status |
| K-004 | 发布时保存 release notes | 请求体包含 `release_notes` | publish skill | release 记录保存 trim 后的 release_notes；package_version 仍来自 `SKILL.md` |
| K-005 | 发布无版本 skill | `SKILL.md` 没有 `version` | publish skill | 发布成功；package_version 为 null；release_version 正常生成 |
| K-006 | 覆盖旧 public latest | 已存在同名 public latest | publish 新 custom skill | 旧 public row 被 soft delete；新 public row 成为 latest；新增 release |
| K-007 | 发布不存在的 custom skill | 当前用户没有该 custom skill | publish skill | 返回 404；不复制文件、不创建 release |
| K-008 | 发布复制 artifact 失败 | copy public artifact 时抛错 | publish skill | 返回 500；rollback；旧 public artifact 保持不变；不创建 public row/release |
| K-009 | 创建 release 失败 | artifact 已复制，public row 已准备创建，release 创建失败 | publish skill | 返回 500；rollback；恢复旧 public artifact |
| K-010 | commit 失败 | release 已创建但事务提交失败 | publish skill | 返回 500；rollback；恢复旧 public artifact |
| K-011 | 列表返回 public release 元数据 | public latest 有 release record | `GET /api/skills` | 返回 package_version、release_version、release_status、release_notes、published_at、owner 信息 |
| K-012 | legacy public skill 兼容 | public skill 没有 release record | `GET /api/skills` | 版本和发布字段为 null，接口不报错 |
| K-013 | custom skill 展示 package version | custom skill 的 `SKILL.md` 有 version | `GET /api/skills` | custom skill 返回 package_version；release 字段为 null |
| K-014 | check-upload 同名新版本 | 用户已安装 v1，上传同名 v2 | `POST /api/skills/check-upload` | `same_version=false`，提示将更新 |
| K-015 | check-upload 同名同版本 | 用户已安装 v1，上传同名 v1 | `POST /api/skills/check-upload` | `same_version=true`，提示已存在 |
| K-016 | upload 同名新版本 | 用户已安装 v1，上传同名 v2 | `POST /api/skills/uploads` | 更新现有 custom row；不创建第二条 active 同名 row |
| K-017 | upload 同名同版本默认拒绝 | 用户已安装 v1，上传同名 v1 | `POST /api/skills/uploads` | result 为 skipped；不替换文件；不提交更新 |
| K-018 | 下载 public latest | public latest 存在，用户无同名 custom | `POST /api/skills/{name}/download` | 创建用户 custom skill；响应带源 release 元数据 |
| K-019 | 下载冲突不覆盖 | 用户已有同名 custom | download 且 `overwrite=false` | 返回 409；不替换文件 |
| K-020 | 用户隔离 | Alice 有 custom skill，Bob 没有 | Bob publish 同名 skill | 返回 404；Bob 不能发布 Alice 的 skill |

## 5. 前端关键测试用例

| ID | 场景 | 操作 | 预期结果 |
| --- | --- | --- | --- |
| FE-001 | publish API 请求体正确 | 调用 `publishSkill(name, { release_notes })` | 发送 POST；body 包含 `release_notes`；credentials 为 include |
| FE-002 | custom skill 展示发布入口 | custom tab 打开 skill 菜单 | 显示“发布”和“删除”；不显示“下载” |
| FE-003 | public skill 展示下载入口 | public tab 打开 skill 菜单 | 显示“下载”；不显示“发布”和“删除” |
| FE-004 | 发布弹窗展示元数据 | 点击 custom skill 的发布 | 弹窗显示 skill name、版本、description、release notes 输入框 |
| FE-005 | release notes 归一化 | 输入前后空格后确认发布 | 调用 mutation 时传入 trim 后内容；空白内容传 null |
| FE-006 | 发布失败不关闭弹窗 | publish mutation 失败 | 展示错误 toast；弹窗保留，用户输入不丢 |
| FE-007 | 版本 badge fallback | skill 有 package_version/release_version/无版本三种情况 | 分别显示 package_version、release_version、无版本文案 |
| FE-008 | 上传冲突用户取消 | check-upload 返回 exists=true，用户取消 confirm | 不调用 upload mutation |

## 6. 建议 TDD 落地顺序

第一轮先做后端 publish 主链路：

1. K-003：首次发布 custom skill。
2. K-004：发布时保存 release notes。
3. K-005：发布无版本 skill。
4. K-006：覆盖旧 public latest。
5. K-009：创建 release 失败恢复 artifact。
6. K-010：commit 失败恢复 artifact。

第二轮做上传版本判断：

1. K-014：check-upload 同名新版本。
2. K-015：check-upload 同名同版本。
3. K-016：upload 同名新版本更新现有 row。
4. K-017：upload 同名同版本默认拒绝。

第三轮做展示和下载：

1. K-011：public release metadata 展示。
2. K-012：legacy public skill 兼容。
3. K-013：custom package_version 展示。
4. K-018：下载 public latest。
5. K-019：下载冲突不覆盖。

第四轮做前端交互：

1. FE-001：publish API 请求体。
2. FE-004：发布弹窗展示元数据。
3. FE-005：release notes 归一化。
4. FE-006：发布失败不关闭弹窗。
5. FE-007：版本 badge fallback。

## 7. 最小验收标准

只看关键用例时，至少要满足：

1. K-001 到 K-020 全部有自动化测试。
2. FE-001、FE-004、FE-005、FE-006、FE-007 有前端自动化测试。
3. publish 成功和失败回滚都被测试覆盖。
4. 同名同版本与同名新版本上传都被测试覆盖。
5. public latest 与 release history 的关系被测试覆盖。
