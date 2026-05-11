# 当前稳定现状：状态与未决点

日期：2026-05-11

状态：稳定事实说明

## 资料优先级

发生冲突时，判断顺序是：

1. 当前代码和测试。
2. `/Users/sayori/Desktop/work/docs`。
3. `docs-qy/skills-design` 下的历史设计和计划文档。

本文只列当前可以依赖的稳定状态，以及不能替产品擅自决定的未决点。

## 已稳定的代码事实

当前已经可以把以下内容视为稳定现状：

1. 数据模型已有 `SkillDefinition`、`SkillVersion`、`SkillInstall`、`SkillRelease`、`RuntimeManifest`、`PendingSkillForkClaim`。
2. `AgentSkill` 已有非系统安装绑定字段和 System Skill 直接绑定字段。
3. 平台版本使用 `SkillVersion.version_number`，不来自包内 metadata。
4. 包内版本只作为 `source_package_version` 保留。
5. 不可变 artifact 由 `SkillVersion.artifact_uri` 指向。
6. Runtime Manifest 已持久化 `manifest_json` 和 `manifest_hash`。
7. sandbox 使用 run-level readonly bundle。
8. System Skill 不要求 per-user install。
9. Community install 和 editable fork/export 是两个不同产品动作。
10. 当前 API 的 `viewer_relation="downloaded"` 是 legacy installed state，不是用户可见下载动作。

## 已验证的主链路

2026-05-09 的本地 e2e 验收已经证明 v1 主链路可跑通：

1. User A 上传并发布 v1。
2. User B 从 Community Skills 安装 v1。
3. My Skills、Agent API 和 Agent 列表可显示 install/version metadata。
4. User B 的 Agent 绑定 `skill_install_id`。
5. Runtime Manifest 指向 v1 artifact。
6. `skill_load` 读取 install-backed virtual path。
7. Agent 最终回复 `SKILL_RUNTIME_OK_V1`。

这个验收说明 v1 的 upload/publish/install/bind/runtime 链路成立。

## 不能标记完成的链路

以下内容不能写成已经通过：

1. v2 上传成功。
2. v2 发布成功。
3. User B 未更新时仍运行 v1 的完整浏览器链路。
4. 更新确认页完整展示并提交。
5. `update-install` 后新 run 回复 `SKILL_RUNTIME_OK_V2` 的完整浏览器链路。

当前未完成原因不是产品语义未定，而是本地 `backend/.deer-flow` storage mount 曾阻塞 v2 上传：页面卡在上传中，直接 API 超时，并出现 DB `idle in transaction` / lock 症状。

## 当前稳定产品决策

以下决策已经可以按当前稳定现状执行：

1. 面向用户时把 install 叫“安装”，不要叫“下载”。
2. 真正下载只指 `fork-package` 可编辑 ZIP 导出。
3. System Skills 直接可用/可绑定，不走普通 install。
4. 发布新版不自动修改安装者的当前版本。
5. 更新必须由安装者显式确认。
6. Runtime Manifest 是 run 级快照和审计凭证。
7. 新实现不要回退到 public latest、custom copy 或 name-only runtime lookup。

## 唯一关键未决业务点

当前代码语义是 follow-install-current：

```text
AgentSkill.skill_install_id
  -> SkillInstall.current_version_id
```

也就是：用户确认更新某个 install 后，绑定该 install 的 Agent 后续新 run 会跟随到新版。

仍需产品确认的问题是：

```text
Agent 是否应该长期 follow install current？
还是 Agent 绑定时应固定到具体 SkillVersion，直到用户逐个 Agent 确认？
```

如果选择后者，需要新增 Agent-level version pin 或等价模型。不能只靠 Runtime Manifest 解决，因为 Manifest 只能固定单次 run，不能表达未来 run 的产品策略。

## 剩余工程风险

这些是当前仍需继续清理或验证的工程风险：

1. settings/边角页面可能仍有 `download`、`public/custom`、package version 等历史文案。
2. standalone/local client install path 仍可能使用 `<user_id>/<skill_name>` materialized layout，需要和 definition-aware path 区分。
3. legacy `agents_skills.skill_id`、`skills.file_path`、name-only Agent API 仍存在兼容面。
4. 完整 v2/update/runtime-v2 max-flow 需要在修复 `.deer-flow` storage mount 后重跑。
5. 如果未来把 API 字面值 `downloaded` 改成 `installed`，需要后端 schema、前端类型和测试一起改。

## 后续验证优先级

建议后续按这个顺序验证：

1. 修复或替换本地 `.deer-flow` storage mount。
2. 重跑 v2 upload/publish/update/browser max-flow。
3. 验证未更新时 Agent 仍回复 v1。
4. 验证确认更新后 Agent 回复 v2。
5. 扫描并修正所有用户可见的 download/downloaded 历史文案。
6. 决定 follow-install-current 是否就是长期产品语义。
