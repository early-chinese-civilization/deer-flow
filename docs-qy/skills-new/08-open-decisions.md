# 待决问题

日期：2026-05-12

状态：必须回到用户确认的高影响设计点

## 用途

本文记录当前终态里仍未完全确定、后续实现不能隐式假设的内容。

已关闭的高影响决策不在本文展开：

1. 默认聊天不是 default Agent。
2. `thread.agent_id = null` 表示默认聊天。
3. `thread.agent_id` 非空表示绑定自定义 Agent。
4. 默认聊天系统 Skill 由平台级 `default_chat.system_skills` 配置决定。
5. 默认聊天配置不产生 `skill_installation`、`install_origin` 或启用关系表。
6. `skill.id` 是 UUID。
7. `skill_version` 身份是 `(skill_id, version_number)`。
8. OSS 目录是 `.deer-flow/skills/{skill_id}/{version_number}/`。

规则：

1. 已确定的设计只用一句引用指向对应终态文档。
2. 不确定项不能藏在正文里。
3. 后续 implementation task 不能绕过 P0/P1 open decision 自行假设。
4. 每个不确定项都要说明影响面和当前推荐。

## P1：RuntimeManifest 的非核心审计取舍

问题：

```text
是否需要另行设计非核心审计记录来替代 runtime_manifests 的核心模型位置？
```

已确定：

1. 它不能是核心业务事实来源。
2. prompt/sandbox/skill_load 不应依赖读取 DB 中的 manifest JSON。
3. 这项取舍不能阻塞新 runtime descriptor 链路。
4. 如果保留审计记录，记录的版本身份必须是 `(skill_id, version_number)`。

当前推荐：

```text
先把 RuntimeManifest 移出核心链路；如审计调试确有需要，再单独设计非核心记录和对应测试命名。
```

## P1：旧 route 和旧目录删除与迁移清理顺序

问题：

```text
旧 download/fork/name-only/public/custom/local/user-dir 入口按什么顺序删除、迁移和替换？
```

必须逐项决定：

1. download route。
2. fork claim route / PendingSkillForkClaim。
3. archive install route。
4. public latest copy。
5. `load_skills()` global scan。
6. `normalize_skill_file_path()` 旧路径 normalization。
7. `{skill_version_id}` 目录和 `artifact_uri` 旧路径。

当前推荐：

```text
用户可见 fork/download 删除；先切断旧 API 的可用行为，迁移窗口内只返回明确“已移除/请使用 install”的错误；历史数据迁移到 `skill` / `skill_version` / `skill_installation` 链路后，删除旧字段、旧目录写入和旧入口。
```

## P1：默认聊天配置加载与热更新策略

问题：

```text
default_chat.system_skills 是启动时读取并校验，还是支持运行时 reload？
```

已确定：

1. 配置是平台全局配置。
2. 配置只允许内部系统用户拥有的 Skill。
3. 配置项必须是 `(skill_id, version_number)`。
4. 配置不产生用户级状态。

当前推荐：

```text
第一轮启动时读取并严格校验；若配置无效，Gateway 明确失败或降级为空配置需要单独产品确认。热更新不进入第一轮。
```

## P2：上传/编辑工作区位置

问题：

```text
用户上传或编辑 Skill 的临时目录放在哪里？
```

已确定：

1. 不放在 `.deer-flow/skills` 事实命名空间。
2. 不作为 runtime 读取来源。

可选位置：

1. Gateway temp。
2. `.deer-flow/uploads/...`。
3. 用户 workspace 体系下的非 runtime path。

这是实现任务中的存储选择，不应影响 SkillVersion 目录终态。

## P2：社区发布审核的精确 schema

问题：

```text
二期审核只扩展 skill_releases.status，还是引入 publish submission / review 表？
```

当前第一轮只需要：

1. 沿用 release status。
2. 查询只把 `published` 当作 discover/install/update target。
3. 不把 publish 代码写死为永远立即公开。

二期再决定 reviewer 字段、原因字段、队列表和审计模型。
