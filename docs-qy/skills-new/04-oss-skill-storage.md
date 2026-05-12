# OSS Skill 存储设计

日期：2026-05-12

状态：终态收口版

## 结论

`.deer-flow/skills` 的终态只承担一个职责：保存不可变 Skill 版本内容。

终态目录结构是：

```text
.deer-flow/
  skills/
    {skill_id}/
      {version_number}/
        SKILL.md
        ...
```

其中：

```text
skill_id = skill.id
skill.id terminal type = UUID
version_number = skill_version.version_number
runtime path = ".deer-flow/skills/{skill_id}/{version_number}"
```

不再使用 `{skill_version_id}`、`public`、`{user_id}`、`{author_id}`、`custom`、`local`、`artifacts/skills`、`workspaces` 等目录层级作为 Skill 内容事实来源。

## 为什么是 `skill_id/version_number`

`skill_version` 不能独立于 `skill` 存在。版本身份是：

```text
(skill_id, version_number)
```

因此物理目录也直接使用这组身份：

```text
.deer-flow/skills/{skill_id}/{version_number}/SKILL.md
```

这样可以同时表达：

1. 稳定 Skill identity。
2. 同一 Skill 下不可变版本号。
3. 运行时需要读取的确定内容根目录。

旧的 `.deer-flow/skills/{skill_version_id}` 是上一轮方案，当前终态删除。

## 同名 Skill 如何处理

不同用户发布同名 Skill，不靠目录名区分。

DB 中是不同 Skill：

```text
owner=A, name=data-analysis -> skill_id=8b4...
owner=B, name=data-analysis -> skill_id=f12...
```

它们生成不同物理目录：

```text
.deer-flow/skills/8b4.../1/SKILL.md
.deer-flow/skills/f12.../1/SKILL.md
```

runtime 从默认聊天 config 或自定义 Agent 绑定解析到具体 `(skill_id, version_number)`，不从目录反推出作者或 Skill name。

## UUID 而不是 content hash

目录中的 `skill_id` 使用 `skill.id`，终态类型为 UUID。

职责划分：

```text
Stable Skill identity: skill.id (UUID)
Version identity: (skill_id, version_number)
Dedup key: (skill_id, content_hash)
Integrity check: file_manifest_hash
```

不使用 `content_hash` 作为路径主键，原因：

1. hash 是内容身份，不是业务版本身份。
2. 两个不同 Skill 可能拥有完全相同内容。
3. 是否共享物理内容是存储优化问题，不应改变业务对象。
4. hash path 会诱导 runtime 从内容反推业务关系。

## 当前代码中的旧目录职责

当前代码中存在多类目录：

```text
public/{skill_name}
public/{owner_user_id}/{skill_name}
{user_id}/{skill_name}
{user_id}/definitions/{skill_definition_id}/{skill_name}
artifacts/skills/{definition_id}/v{version_number}-{hash}/{skill_name}
artifacts/legacy/skills/{skill_id}/{skill_name}
local/{skill_name}
custom/{skill_name}
.runtime-skill-bundles/{bundle_or_manifest_hash}/...
```

终态分类如下：

1. `public/*`：当前代码待删除的 catalog / public latest 心智；不能作为 install/runtime 事实来源。
2. `{user_id}/*`：当前代码待迁移的用户私有目录心智；不能作为 runtime 事实来源。
3. `{user_id}/definitions/*`：上传/编辑工作区；若继续需要，应移出 `.deer-flow/skills` 事实命名空间。
4. `artifacts/skills/*`：当前最接近不可变 artifact 的实现；迁移到 `skill_id/version_number` 目录。
5. `artifacts/legacy/*`：旧模式迁移来源；迁移完成后删除，不能作为新事实来源。
6. `local/*` / `custom/*`：旧 standalone 入口；迁移后不进入新 runtime 链路。
7. `.runtime-skill-bundles/*`：runtime 派生物；不能作为业务内容事实来源。

## `workspaces` 不属于 skills 目录

上传暂存、解包工作区、编辑工作区都不应放在 `.deer-flow/skills` 终态目录里。

原因：

1. `.deer-flow/skills` 应只保存已进入平台版本体系的不可变内容。
2. workspace 是过程文件，不是 Skill 版本内容事实来源。
3. 把 workspace 放进 `skills` 会让 loader、runtime 和人工排查再次混淆可运行内容与导入过程。

如果需要上传暂存，可以使用 Gateway temp、系统 temp，或 `.deer-flow/uploads/...` 之类非 runtime namespace。

## 创建 Skill 版本的写入顺序

因为目录 key 使用 `(skill_id, version_number)`，终态推荐流程：

1. 解析上传或创建输入。
2. 找到或创建 `skill(id UUID)`。
3. 计算 `content_hash`。
4. 计算 `file_manifest_hash`。
5. 在同一 `skill_id` 下用 `(skill_id, content_hash)` 查找是否已有版本。
6. 如果已有，复用该 `(skill_id, version_number)` 和目录。
7. 如果没有，分配同一 `skill_id` 下下一个不可变 `version_number`。
8. 将内容写入 `.deer-flow/skills/{skill_id}/{version_number}`。
9. 创建 `skill_version(skill_id, version_number)` row。
10. 失败时清理新目录或回滚 DB row，不能留下半完成事实来源。

## Agent runtime 读取规则

默认聊天读取规则：

```text
Thread(agent_id=null)
  -> default_chat.system_skills[{skill_id, version_number}]
  -> .deer-flow/skills/{skill_id}/{version_number}
  -> read-only runtime path
  -> prompt / sandbox / skill_load
```

自定义 Agent 读取规则：

```text
Thread(agent_id)
  -> Agent
  -> agent_skills
  -> skill_installations
  -> skill_versions(skill_id, version_number)
  -> .deer-flow/skills/{skill_id}/{version_number}
  -> read-only runtime path
  -> prompt / sandbox / skill_load
```

runtime 不允许从这些位置发现或回退：

```text
public/{skill_name}
public/{owner_user_id}/{skill_name}
{user_id}/{skill_name}
{user_id}/definitions/{definition_id}/{skill_name}
custom/{skill_name}
local/{skill_name}
name-only scan
{skill_version_id}
```

若实现继续使用 `.runtime-skill-bundles` 或其他 sandbox cache，它只能是从精确版本目录派生出的运行时临时物，不能成为下一次业务解析的来源。

## 业务链路影响

后续实现任务需要覆盖：

1. `skill.id` 使用 UUID。
2. `skill_version` 以 `(skill_id, version_number)` 为身份。
3. 删除独立 `skill_version_id` 路径口径。
4. 不再保存独立 `artifact_uri` 作为运行事实；运行路径由 `(skill_id, version_number)` 推导。
5. 新建版本时按 `skill_id/version_number` 目录写入。
6. 同内容复用时复用已有版本，不写新目录。
7. install 不复制内容目录，只写用户可用关系和当前版本引用。
8. publish 不复制 public latest 事实来源；先确保或创建 `skill_version(skill_id, version_number)` 和 `.deer-flow/skills/{skill_id}/{version_number}/` 内容目录，再创建或更新 `skill_releases(skill_id, version_number, status)`。
9. `skill_releases` / release 语义保留，表示某个 `(skill_id, version_number)` 的发布、公开、审核可见性；发现、install、update 只选择 `status="published"` 的 release。
10. Runtime 已经拿到具体 `(skill_id, version_number)` 后不通过 release 找目录，release 不参与路径授权。
9. update 只切换 DB 引用，不覆盖旧目录。
10. 旧 public/custom/local/user/artifacts 路径删除、迁移或替换。

## 验收标准

后续 implementation 完成后，应能证明：

1. 两个不同作者的同名 Skill 目录不冲突。
2. 同一作者同一 Skill 的新内容创建新版本号目录。
3. 同一作者同一 Skill 的相同内容复用既有版本。
4. 用户安装 Skill 不复制内容目录。
5. 用户更新 Skill 只切换 DB 引用。
6. 默认聊天只读取 config 指定版本目录。
7. 自定义 Agent runtime 读取的是 DB 解析出的版本目录。
8. `public`、`custom`、`local`、`{user_id}`、name-only scan、`{skill_version_id}` 不参与新版 runtime 事实来源。
