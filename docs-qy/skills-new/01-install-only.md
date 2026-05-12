# Install-only Skill 语义

日期：2026-05-12

状态：终态收口版

## 结论

`feature/skill-version-new` 的终态删除 fork 语义，删除下载相关语义，只留下平台内 install 语义。

Install 只表示用户把某个发布 Skill 加入自己的可用范围。它不是文件下载，不创建可编辑副本，也不授予原作者身份。

Install 的来源必须是 `status="published"` 的 `skill_releases`。`skill_releases` / release 语义保留，表示某个 `(skill_id, version_number)` 的发布、公开、审核可见性；删除的是 public latest copy、`artifact_uri` / `oss_path` / `storage_uri` 作为事实来源、独立 `skill_version_id` 版本身份，以及 fork/download 等旧语义。

默认聊天使用的系统 Skill 不是 install。默认聊天的系统 Skill 来自平台级 `config.yaml`：

```yaml
default_chat:
  system_skills:
    - skill_id: "00000000-0000-0000-0000-000000000000"
      version_number: 1
```

这类配置不产生 `skill_installation`，不需要 `install_origin`，也不需要默认聊天启用关系表。

## 为什么删除 fork

当前代码和旧设计中的 fork 语义是历史问题，终态删除。

它把一个平台内能力管理问题拆成“下载可编辑包、携带 claim、再上传认领”的文件流。这个流程对普通用户不自然，也会制造额外对象和边界：fork package、claim sidecar、PendingSkillForkClaim、下载/认领文案、以及原作者身份和个人身份之间的解释成本。

终态不需要这些概念。

## 用户侧语义

用户能理解并需要的动作是：

1. 安装：把平台中的某个发布 Skill 加入自己的可用范围。
2. 使用：把已安装或自己拥有的 Skill 绑定到自定义 Agent。
3. 上传：创建自己的 Skill。
4. 更新：把自己可用 Skill 的当前版本切到新的平台版本。
5. 发布：把自己拥有的 Skill 版本发布给别人安装。

用户不应该看到这些动作：

1. 下载 Skill。
2. 下载可编辑包。
3. fork Skill。
4. 认领 fork。
5. 通过 sidecar 证明来源。

## Install 的稳定含义

Install 是平台内状态，不是文件下载。

安装后，平台应记录：

1. 当前用户可用哪个 `skill`。
2. 当前运行选择的是同一 `skill` 下哪个 `version_number`。
3. 哪些自定义 Agent 通过 `agent_skills` 使用这个可用关系。

安装不表示：

1. 用户获得原 Skill 的作者身份。
2. 用户获得一个本地可编辑文件副本。
3. 用户可以替原作者发布新版本。
4. 用户自动跟随作者后续发布的新版本。
5. 默认聊天启用了某个系统 Skill。

发布流程必须先确保或创建 `skill_versions(skill_id, version_number)` 和 `.deer-flow/skills/{skill_id}/{version_number}/` 内容目录，再创建或更新 `skill_releases(skill_id, version_number, status)`。后续发现、install、update 查询只选择 `status="published"` 的 release。runtime 已经拿到具体 `(skill_id, version_number)` 后不通过 release 找目录，release 不参与路径授权。

## 创建自己的 Skill

用户要创建自己的 Skill，走上传/创建流程。

如果用户想要一个“长得像某个社区 Skill 的自己的 Skill”，终态不通过 fork/download 建模。后续如果产品仍需要类似能力，应作为“创建新 Skill”的编辑体验处理，而不是恢复 fork 业务对象。

## 对后续任务的影响

后续 task 需要从终态中删除或收口：

1. fork package API / UI。
2. download Skill API / UI / 文案。
3. PendingSkillForkClaim 数据模型和迁移。
4. `.deerflow/fork.json` sidecar。
5. `viewer_relation`、按钮、toast、测试用例中下载/fork 相关语义。
6. 旧文档中把下载、fork、安装混在一起的描述。
7. 把默认聊天系统 Skill 当作用户安装或 `skill_installation` 的旧设计。

旧接口清理顺序需要单独设计：迁移窗口内如果仍被外部调用，也只能返回“已移除/请使用 install”的明确错误，不能执行安装、运行、复制或认领逻辑；迁移完成后删除入口。
