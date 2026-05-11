# 当前稳定现状：产品语义

日期：2026-05-11

状态：稳定事实说明

## 资料优先级

发生冲突时，判断顺序是：

1. 当前代码和测试。
2. `/Users/sayori/Desktop/work/docs`。
3. `docs-qy/skills-design` 下的历史设计和计划文档。

本文只描述当前产品语义。后端兼容路由名里出现的 `download` 不等于用户心智里的“下载文件”。

## 产品空间

当前 Skills 产品面稳定分成三类：

1. System Skills：平台预置能力。
2. Community Skills：别人发布到 SkillHub 的能力。
3. My Skills：我创建的、我安装的、我 fork 后拥有的能力。

这三个空间不能再退回到早期的 `public` / `custom` 两个技术桶。

## System Skills

System Skills 是平台预置资源。

稳定语义：

1. 用户不需要先安装 System Skill。
2. System Skill 可直接进入 Agent 绑定。
3. Agent 绑定时必须记录具体 system definition/version。
4. System Skill 不应暴露“安装”“下载可编辑包”“加入我的 Skills”等普通 Community 操作。
5. 普通用户不能通过发布/上传覆盖 System Skill 身份。

## Community Skills

Community Skills 是 SkillHub 中可被其他用户安装的公开发布版本。

稳定语义：

1. Community 列表展示的是公开发布态，不是某个用户目录。
2. 用户安装的是当前公开发布的具体 `SkillVersion`。
3. 发布者后续发布新版，只产生“可更新”状态。
4. 安装者不确认更新时，自己的运行版本不变。
5. SkillHub 的“当前版本”是平台版本，不是包内 metadata version。

## My Skills

My Skills 包含用户可管理或可运行的个人空间 Skills。

稳定语义：

1. 我上传/创建的 Skill 属于我拥有的 Skill 身份。
2. 我从 Community 安装的 Skill 以 `SkillInstall` 形式出现在个人空间。
3. 我 fork/export 后再上传的 Skill 应和原 Skill 解耦，形成新的个人 Skill 身份。
4. 我发布自己的 Skill 时，发布的是当前具体 `SkillVersion`。
5. My Skills 中的“已安装”不是文件下载结果，而是 install state。

## 安装语义

当前后端保留兼容路由：

```text
POST /api/skills/{name}/download
POST /api/skills/{name}/check-download
```

稳定产品语义：

1. `download` 路由实际表示“安装到 My Skills”。
2. `check-download` 实际表示“安装冲突检查”。
3. UI 和文档面向用户时应使用“安装”“已安装”“更新”，不要把这个动作叫“下载”。
4. 安装成功后应形成 `SkillInstall`，Agent 绑定时使用 install identity。

当前 API `viewer_relation` 仍使用 `downloaded` 字面值表达 installed-from-Community personal row。这是 legacy contract，用户可见文案必须渲染成“已安装”，不是“已下载”。

## 真正的下载和 fork

真正的文件下载/可编辑导出语义是：

```text
POST /api/skills/{name}/fork-package
```

稳定产品语义：

1. `fork-package` 导出可编辑 ZIP。
2. 导出包包含 `.deerflow/fork.json` claim sidecar。
3. 后续重新上传时，服务端通过 `PendingSkillForkClaim` 识别来源关系。
4. fork 后的个人版本不应覆盖原 Community/System Skill。

因此，“下载”这个词只适合描述 editable package export，不适合描述安装。

## 发布语义

发布是把当前用户拥有的某个 `SkillVersion` 发布到 SkillHub。

稳定规则：

1. 发布不会改变已安装用户的 `SkillInstall.current_version_id`。
2. 发布说明属于 `SkillRelease`。
3. 发布的版本快照不可被原地修改。
4. 发布后其他用户可以安装该发布版本。
5. 已安装用户看到更新提示后，需要显式确认更新。

## 更新语义

当前稳定更新链路是：

```text
update-install/preview
  -> 展示目标版本和受影响 Agent
update-install
  -> 修改 SkillInstall.current_version_id
```

稳定规则：

1. 更新不是自动发生的。
2. 更新前应展示当前版本、目标版本、更新说明和受影响 Agent。
3. 更新后，绑定同一个 install 的 Agent 后续新 run 会使用新版。
4. 已经生成的旧 Runtime Manifest 不会被改写。

如果产品想改成“每个 Agent 固定版本，安装更新后 Agent 不跟随”，需要新增 Agent-level version pin 或等价模型；当前稳定语义不是这个。

## 前端状态契约

当前 Skills API 暴露：

```text
space: system | community | personal
source_kind: official | community | personal | fork
viewer_relation:
  system_available
  official_available
  community_available
  downloaded
  authored
  authored_published
  authored_unpublished_changes
  update_available
  forked
```

稳定 UI 口径：

1. `downloaded` 显示为“已安装”。
2. `update_available` 显示为“可更新”。
3. System Skills 不显示安装态。
4. Community Skills 显示安装/已安装/可更新。
5. My Skills 区分我创建、我安装、我 fork。
