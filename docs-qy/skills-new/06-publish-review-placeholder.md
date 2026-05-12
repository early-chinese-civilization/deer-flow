# Publish Review Placeholder

日期：2026-05-12

状态：终态占位版；二期能力，不进入当前第一轮实现主线

## 结论

社区发布审核应作为二期能力预留，但 release 语义本身保留在第一轮终态里。

当前终态设计不能把 publish 固定理解成“立即公开”。更稳定的模型是：

```text
skill_version(skill_id, version_number)
  -> publish submission / skill_releases
  -> review state
  -> published visibility
```

`skill_version` 是不可变内容版本；审核决定的是这个版本是否能作为社区公开 release 被发现、安装和更新。

删除的是 public latest copy、`artifact_uri` / `oss_path` / `storage_uri` 作为事实来源、独立 `skill_version_id` 版本身份，以及 fork/download 等旧语义，不是 `skill_releases`。

## 为什么放在 Release 层

审核不应该放在物理目录或 runtime 层。

原因：

1. 内容版本创建和公开发布是两件事。
2. 一个 `(skill_id, version_number)` 可以存在，但尚未公开。
3. 审核拒绝不应该删除不可变内容目录。
4. 下架不应该改写 SkillVersion。
5. 安装者是否能看到更新，应取决于是否存在可见的 `published` release。

因此，审核状态应属于 release / publish submission，而不是 SkillVersion 内容本身。

## 状态机占位

推荐状态：

```text
draft / local only
pending_review
approved
published
rejected
withdrawn
delisted
suspended
```

第一轮可以先只实现或保留：

```text
published
```

并在表结构/代码命名上避免把状态写死成“发布即公开”。

二期审核时，最小状态机可以是：

```text
pending_review -> published
pending_review -> rejected
published -> delisted
published -> suspended
```

## 业务链路影响

### DB

当前代码已有 `skill_releases.status`，默认 `published`。这可以作为二期审核的最小占位字段。

终态 release 应指向具体：

```text
(skill_id, version_number)
```

而不是独立 `skill_version_id`。

publish 流程顺序必须是：

1. 确保或创建 `skill_version(skill_id, version_number)`。
2. 写入并校验 `.deer-flow/skills/{skill_id}/{version_number}/` 内容目录。
3. 创建或更新 `skill_releases(skill_id, version_number, status)`。

Release 不保存内容路径，也不参与 runtime 目录授权。

二期可能需要补充：

1. `review_status` 或继续扩展 `skill_releases.status`。
2. `reviewed_by_user_id`。
3. `reviewed_at`。
4. `review_reason` / `rejection_reason`。
5. `submitted_at`。
6. `visibility` 或 `published_at`，如果要区分审核通过和公开时间。

如果审核流程复杂，再引入单独的 `skill_release_reviews` 或 `skill_publish_submissions` 表；第一轮不必实现。

### Gateway

Gateway 查询规则要预留：

1. 社区发现列表只查 `status="published"`。
2. install 只能安装 `published` release。
3. update preview 只能选择 `published` target version。
4. 默认聊天 config 只能引用内部系统用户拥有且存在的版本；是否必须要求 `published` 可作为实现策略，但不能绕过系统 owner 校验。
5. 作者可以看到自己的 pending/rejected release。
6. 审核角色可以看到 pending queue。
7. 内部系统用户发布可以 auto-approve。

### 权限

系统发布者身份仍然使用统一发布模型，但可以有特殊权限：

1. 内部系统用户的 release 默认 `published`，可以 auto-publish。
2. 普通作者 release 第一轮可以默认 `published`；二期审核上线后再改为 `pending_review`。
3. 管理员或审核角色可以 approve/reject/delist/suspend。
4. 内部系统用户可以作为审核/运营动作的执行身份之一。
5. 审核操作记录应区分“系统自动审核”和“人工审核”。

这不是 System Skill 的模型分叉，只是发布权限策略。

## Runtime 影响

审核状态不应改变 runtime 的内容解析方式。runtime 已经拿到具体 `(skill_id, version_number)` 后不通过 release 找目录，release 不参与路径授权。

默认聊天 runtime 仍然走：

```text
Thread(agent_id=null)
  -> default_chat.system_skills
  -> skill_versions(skill_id, version_number)
  -> .deer-flow/skills/{skill_id}/{version_number}
```

自定义 Agent runtime 仍然走：

```text
Thread(agent_id)
  -> Agent
  -> agent_skills
  -> skill_installations
  -> skill_versions
  -> .deer-flow/skills/{skill_id}/{version_number}
```

审核状态主要影响：

1. 新用户能否发现并安装某个 release。
2. 已安装用户是否能看到更新。
3. 某个 release 是否被下架或安全阻断。

如果状态是 `suspended`，需要单独定义是否阻断已安装用户或默认聊天的后续运行。这属于安全策略，不要混进普通审核通过/拒绝流程。

## 当前第一轮占位要求

第一轮不实现审核，但要避免把未来堵死：

1. 保留 release status 概念。
2. 社区列表和 install/update 查询明确只依赖 `published` release。
3. publish 代码不要假设所有状态永远只有 `published`。
4. 文档中明确审核是二期扩展点。
5. 测试命名尽量写“published release”，不要写“any release”。
