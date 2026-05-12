# 默认聊天系统 Skill 平台配置

日期：2026-05-12

状态：终态收口版；文件名沿用历史编号，不表示终态采用 system_default install。

## 结论

默认聊天启用系统 Skill 由平台级 `config.yaml` 配置决定：

```yaml
default_chat:
  system_skills:
    - skill_id: "00000000-0000-0000-0000-000000000000"
      version_number: 1
```

这是平台全局配置，面向所有用户。

终态明确不采用上一轮“系统 Skill 默认安装 / 懒物化 `skill_installation` / `install_origin=system_default`”方案。该方案是历史问题。

## 配置语义

`default_chat.system_skills` 表示默认聊天 runtime 应加载哪些系统 Skill 版本。

每个配置项必须是：

```text
skill_id: UUID
version_number: int
```

二者共同定位一个不可变版本：

```text
skill_version(skill_id, version_number)
```

runtime 内容目录由该版本推导：

```text
.deer-flow/skills/{skill_id}/{version_number}/
```

## 强约束

该配置必须满足：

1. `skill_id` 对应的 `skill` 必须存在。
2. `skill.owner_user_id` 必须指向内部系统用户。
3. 内部系统用户通过 `users.external_auth_id="system:deerflow"` 稳定识别。
4. `(skill_id, version_number)` 对应的 `skill_version` 必须存在。
5. 是否必须要求对应 `status="published"` 的系统 release 是平台策略；无论是否要求，都不能绕过系统 owner 和版本存在性校验。
6. 配置项不能引用社区用户拥有的 Skill。
7. 配置项不能引用可变 latest。
8. 配置项不能通过 name-only、public/custom 路径或 manifest JSON 解析。

## 不产生用户级状态

默认聊天配置不产生：

1. `skill_installation`。
2. `install_origin`。
3. `agent_skills`。
4. `skill_binding` 或默认聊天启用关系表。
5. hidden default Agent。
6. 用户级启用/禁用开关。

用户不想在自定义 Agent 中使用某个系统 Skill，只需要不把它配置到自定义 Agent。默认聊天的系统 Skill 是平台全局策略，不是用户偏好。

## Runtime 链路

默认聊天 runtime 链路：

```text
Thread(agent_id=null)
  -> default_chat.system_skills
  -> validate skill owner is internal system User
  -> skill_versions(skill_id, version_number)
  -> .deer-flow/skills/{skill_id}/{version_number}
  -> descriptor(skill_id, version_number, file_manifest_hash, virtual_path)
  -> prompt / sandbox / skill_load
```

descriptor 最小字段：

| 字段 | 来源 | runtime 用途 |
| ---- | ---- | ------------ |
| `skill_id` | config | 稳定 Skill 身份和目录第一层 |
| `version_number` | config | 同一 Skill 下的不可变版本和目录第二层 |
| `file_manifest_hash` | `skill_version` | 完整性校验 |
| `virtual_path` | resolver 派生 | 面向模型的稳定路径 |

## 与自定义 Agent 的区别

自定义 Agent 仍走业务链路：

```text
Thread(agent_id)
  -> Agent
  -> agent_skills
  -> skill_installations
  -> skill_versions(skill_id, version_number)
  -> .deer-flow/skills/{skill_id}/{version_number}
```

默认聊天和自定义 Agent 的区别是 Skill 来源不同：

| 场景 | Skill 来源 | 是否产生 `skill_installation` | 是否产生 `agent_skills` |
| ---- | ---------- | --------------------- | ---------------------- |
| 默认聊天 | 平台 `config.yaml` | 否 | 否 |
| 自定义 Agent | 用户业务数据 | 是 | 是 |

二者最终都只能读取 `.deer-flow/skills/{skill_id}/{version_number}/`。

`skill_releases` 保留为发布、公开、审核可见性层。发现、install、update 只选择 `status="published"` 的 release；默认聊天 runtime 已经拿到 config 中的 `(skill_id, version_number)` 后不通过 release 找目录，release 不参与路径授权。

## 版本更新规则

默认聊天配置引用精确 `version_number`，不会自动漂移到最新版本。

系统作者发布新版后，平台是否把默认聊天切到新版，是一次显式配置变更：

```yaml
default_chat:
  system_skills:
    - skill_id: "00000000-0000-0000-0000-000000000000"
      version_number: 2
```

这不是用户更新，也不会修改任何用户的 `skill_installation`。

## Gateway 查询规则

默认聊天 resolver 应：

1. 读取平台 config。
2. 批量查询配置项对应的 `skill` 和 `skill_version`。
3. 校验 owner 是内部系统用户。
4. 校验内容目录和 `file_manifest_hash`。
5. 生成 runtime descriptor。

如果配置无效，第一轮推荐启动或解析时明确失败，而不是静默跳过或回退 name-only/public/custom 扫描。

## 验收标准

后续实现应证明：

1. 普通聊天 `thread.agent_id=null`。
2. 默认聊天加载 `default_chat.system_skills` 指定版本。
3. 配置社区用户 Skill 会失败。
4. 配置不存在版本会失败。
5. 默认聊天不会创建 hidden default Agent。
6. 默认聊天不会创建 `skill_installation`、`install_origin`、`agent_skills` 或默认聊天绑定表。
7. 系统 Skill 发布新版后，默认聊天不会自动漂移，除非平台 config 显式改到新版。
8. runtime 只读取 `.deer-flow/skills/{skill_id}/{version_number}/`。
