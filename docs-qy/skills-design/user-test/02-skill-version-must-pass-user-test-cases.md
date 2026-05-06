# Skill Version 必过用户测试用例

日期：2026-05-06

## 一、最大主流程

### 1 上传、发布、安装、绑定、运行、更新完整链路
- **优先级**: P0
- **前置条件**:
  - 测试环境已有两个同名“运行验收 Skill”包，内容不同
  - 版本 1 的触发输入为 `请执行 Skill 运行验收`，期望回复为 `SKILL_RUNTIME_OK_V1`
  - 版本 2 的触发输入为 `请执行 Skill 运行验收`，期望回复为 `SKILL_RUNTIME_OK_V2`
  - 用户 A 有发布 Skill 权限，用户 B 已登录并有一个可编辑 Agent
- **步骤**:
  1. 用户 A 上传“运行验收 Skill”版本 1 包
  2. 用户 A 将平台版本 1 发布到 SkillHub
  3. 用户 B 打开 SkillHub，安装该 Skill
  4. 用户 B 在 我的 Skills 中确认该 Skill 已安装，当前版本为 版本 1
  5. 用户 B 进入 Agent 配置页，把该已安装 Skill 绑定给 Agent 并保存
  6. 用户 B 发起新对话，输入 `请执行 Skill 运行验收`
  7. 用户 A 上传同名但内容不同的版本 2 包，并将平台版本 2 发布到 SkillHub
  8. 用户 B 不点击更新，再次用同一个 Agent 输入 `请执行 Skill 运行验收`
  9. 用户 B 在 我的 Skills 或更新提示中进入更新确认页
  10. 用户 B 确认从版本 1 更新到版本 2
  11. 用户 B 重新发起新对话，输入 `请执行 Skill 运行验收`
- **预期**:
  - 首次上传后平台生成 版本 1，不要求包内填写版本
  - 用户 B 安装后看到状态为 已安装，当前版本为 版本 1
  - Agent Skills 区域展示已绑定 Skill、来源和版本 1
  - 第一次对话回复 `SKILL_RUNTIME_OK_V1`
  - 版本 2 发布后，用户 B 看到 有更新，但 Agent 绑定状态仍是版本 1
  - 用户 B 未确认更新前，第二次对话仍回复 `SKILL_RUNTIME_OK_V1`
  - 更新确认页展示当前版本、可更新版本、更新说明和受影响 Agent
  - 用户 B 确认更新后，我的 Skills 和 Agent Skills 都显示版本 2
  - 更新后的对话回复 `SKILL_RUNTIME_OK_V2`
  - 全流程中 Agent 不回退到 SkillHub 最新版、同名目录或默认能力

---

## 二、平台版本与不可变快照

### 2 平台版本不依赖包内版本
- **优先级**: P0
- **前置条件**: 用户已登录，准备一个没有包内 version 字段的合法 Skill 包
- **步骤**:
  1. 上传该 Skill 包
  2. 查看上传成功页、Skill 详情或 我的 Skills 列表
  3. 如包内存在自带 version 字段，再上传一个内容相同但包内 version 不同的包
- **预期**:
  - 平台生成用户可见的 版本 1
  - 页面不要求用户理解 `SKILL.md`、frontmatter 或 package version
  - 包内 version 只可作为后台来源信息，不作为用户可见平台版本
  - 内容相同但包内 version 不同，不应生成新的平台版本

### 3 同内容重复上传不创建重复版本
- **优先级**: P0
- **前置条件**: 已存在“运行验收 Skill”平台版本 1
- **步骤**:
  1. 再次上传与版本 1 内容完全相同的 Skill 包
  2. 查看上传结果和版本历史
  3. 刷新页面后再次查看当前版本
- **预期**:
  - 系统提示内容未变化或保留当前版本
  - 版本历史不新增版本 2
  - 当前版本仍是版本 1
  - 已发布或已安装的版本 1 内容不被覆盖

### 4 新内容创建新平台版本且旧版本不可变
- **优先级**: P0
- **前置条件**: 已存在“运行验收 Skill”平台版本 1
- **步骤**:
  1. 上传同名但内容不同的版本 2 包
  2. 查看版本历史
  3. 查看版本 1 和版本 2 的说明或运行验收行为
- **预期**:
  - 平台新增 版本 2
  - 版本 1 仍可被审计和继续使用
  - 版本 1 不会被版本 2 原地替换
  - 用户看到的是平台维护的 版本 1、版本 2，不是包内版本号

---

## 三、发布、安装与更新状态

### 5 发布指定平台版本到 SkillHub
- **优先级**: P0
- **前置条件**: 用户 A 已拥有“运行验收 Skill”的版本 1 和版本 2
- **步骤**:
  1. 打开版本 1 的发布入口
  2. 在发布确认页查看将发布的版本
  3. 填写发布说明并发布
  4. 再打开版本 2 的发布入口并发布
  5. 打开 SkillHub 查看该 Skill
- **预期**:
  - 发布确认页明确展示将发布的平台版本
  - 发布动作指向具体平台版本，不是“当前目录”或“public latest”
  - SkillHub 展示当前公开版本和更新说明
  - 发布弹窗不出现“版本来自 SKILL.md”之类旧文案

### 6 用户从 SkillHub 安装到自己的空间
- **优先级**: P0
- **前置条件**: SkillHub 已发布“运行验收 Skill”版本 1，用户 B 尚未安装
- **步骤**:
  1. 用户 B 打开 SkillHub
  2. 找到“运行验收 Skill”
  3. 点击“安装”
  4. 安装完成后进入 我的 Skills
- **预期**:
  - 未安装时主按钮为“安装”
  - 安装过程中有明确进行中状态
  - 安装成功后状态为“已安装”
  - 我的 Skills 中出现该 Skill，当前版本为 版本 1
  - 调试记录或接口能定位到当前用户的安装态（SkillInstall）及其 current version
  - 页面不使用 Download、Public、Custom、Package version 等旧心智作为主文案

### 7 发布新版后只出现可更新状态，不自动改变 Agent
- **优先级**: P0
- **前置条件**:
  - 用户 B 已安装版本 1 并绑定给 Agent
  - 用户 A 准备发布版本 2
- **步骤**:
  1. 用户 A 发布版本 2
  2. 用户 B 刷新 SkillHub、我的 Skills 和 Agent 配置页
  3. 用户 B 不点击更新，直接用 Agent 输入 `请执行 Skill 运行验收`
- **预期**:
  - 页面显示该 Skill 有更新
  - 页面能同时表达当前已安装版本为版本 1，可更新版本为版本 2
  - Agent Skills 区域仍显示版本 1
  - Agent 回复 `SKILL_RUNTIME_OK_V1`
  - 系统不会因为 SkillHub 有新版本就自动改变 Agent 行为

### 8 手动更新从版本 1 切换到版本 2
- **优先级**: P0
- **前置条件**: 用户 B 已安装版本 1，SkillHub 已有版本 2
- **步骤**:
  1. 用户 B 点击“查看更新”或“更新”
  2. 查看更新确认页
  3. 确认受影响 Agent 列表
  4. 点击“更新”
  5. 回到 我的 Skills 和 Agent 配置页
  6. 发起新对话，输入 `请执行 Skill 运行验收`
- **预期**:
  - 更新确认页展示当前版本 1、可更新版本 2、更新说明、发布者和受影响 Agent
  - 用户点击更新前不会切换版本
  - 更新后 我的 Skills 显示当前版本 2
  - 绑定该安装态的 Agent 下一次运行使用版本 2
  - 如果更新确认发生在一次 Agent run 已开始后，本次 run 仍使用开始时的版本，下一次 run 才使用版本 2
  - 对话回复 `SKILL_RUNTIME_OK_V2`

---

## 四、Agent 绑定与同名来源

### 9 Agent 只能绑定当前用户已安装 Skill
- **优先级**: P0
- **前置条件**:
  - 用户 B 已安装“运行验收 Skill”版本 1
  - SkillHub 中仍存在该 Skill
- **步骤**:
  1. 用户 B 打开 Agent 配置页
  2. 打开添加 Skill 入口
  3. 选择“运行验收 Skill”并保存
  4. 查看 Agent Skills 区域
- **预期**:
  - 可选项来自当前用户可绑定的已安装 Skill
  - 选项展示名称、来源和当前版本
  - 保存后 Agent Skills 展示已绑定 Skill 和版本 1
  - 调试记录或接口能确认 AgentSkillBinding 指向当前用户的安装态（SkillInstall）
  - Agent 不直接绑定 SkillHub 公共对象、skill name 或 latest release

### 10 同名不同来源不能绑定错
- **优先级**: P0
- **前置条件**:
  - SkillHub 中存在两个同名或近似同名 Skill，来源或作者不同
  - 用户 B 至少安装其中一个
- **步骤**:
  1. 用户 B 在 SkillHub 查看两个同名 Skill
  2. 安装其中一个来源的 Skill
  3. 在 Agent 配置页添加 Skill
  4. 保存后运行验收
  5. 查看 Agent Skills 区域展示
- **预期**:
  - SkillHub 和 Agent 配置页都展示来源、作者或唯一页面，避免只靠名称判断
  - Agent 绑定的是用户选择安装的来源
  - 运行时不读取另一个同名 Skill
  - 如果同名冲突无法安全处理，页面应阻止继续并给出可理解提示

### 11 删除、下架与禁用时不静默回退
- **优先级**: P0
- **前置条件**: 用户 B 的 Agent 已绑定一个已安装 Skill
- **步骤**:
  1. 模拟用户 B 的安装态或当前版本记录被删除
  2. 模拟 SkillHub 发布被下架，但用户 B 已安装版本未被禁用
  3. 模拟版本被禁用或安全阻断
  4. 打开 Agent 配置页
  5. 发起对话并输入 `请执行 Skill 运行验收`
- **预期**:
  - 安装态、当前版本记录缺失时，Agent 配置页显示该 Skill 当前不可用
  - 版本被禁用或安全阻断时，对话触发明确失败并提示 Skill 或版本不可用
  - 仅 SkillHub 发布下架但已安装版本仍可用时，Agent 可继续使用已安装版本，同时页面提示无法新安装或获取更新
  - 以上失败场景都不使用公共最新版、同名目录、其他来源 Skill 或默认 Agent 能力继续伪装成功
  - 研发能从日志或运行记录定位到具体安装态或版本失败原因

---

## 五、Runtime Manifest、skill_load 与 sandbox

### 12 Runtime Manifest 可审计本次运行版本
- **优先级**: P0
- **前置条件**:
  - 用户 B 已安装版本 1 并绑定给 Agent
  - 测试环境可以查看 run 记录、日志或调试面板中的 Runtime Manifest
- **步骤**:
  1. 用户 B 发起一次 Agent 对话
  2. 查看本次 run 的 Runtime Manifest 或审计记录
  3. 用户 A 发布版本 2，用户 B 不更新
  4. 用户 B 再发起一次对话并查看 Manifest
  5. 用户 B 手动更新到版本 2 后再发起对话并查看 Manifest
- **预期**:
  - Manifest 记录本次 run 的用户、Agent、绑定、安装态和具体 SkillVersion
  - 发布版本 2 但未更新时，Manifest 仍指向版本 1
  - 手动更新后，下一次 Manifest 指向版本 2
  - 同一次 run 的 Manifest 不因运行中发布或更新而改变
  - run 记录可回答“这次 Agent 实际用了哪个 Skill 版本”

### 13 skill_load 只能读取 Manifest 授权内容
- **优先级**: P0
- **前置条件**:
  - Agent 已绑定“运行验收 Skill”版本 1
  - SkillHub 已存在版本 2，但用户未更新
- **步骤**:
  1. 发起对话，触发 `skill_load` 读取 `/mnt/skills/.../SKILL.md`
  2. 尝试读取 Manifest 外的 Skill 路径
  3. 发布版本 2 后未更新，再次触发读取
  4. 手动更新后再次触发读取
- **预期**:
  - 授权路径读取到版本 1 内容并回复 `SKILL_RUNTIME_OK_V1`
  - Manifest 外路径读取失败
  - 未更新前即使版本 2 存在，`skill_load` 仍只能读取版本 1
  - 更新后读取版本 2 并回复 `SKILL_RUNTIME_OK_V2`
  - `skill_load` 不按 public latest、skill name 或文件扫描自行解析

### 14 sandbox 只能访问本次 Manifest 允许的 artifact
- **优先级**: P0
- **前置条件**: 测试环境可观察 sandbox 文件访问结果
- **步骤**:
  1. 用绑定版本 1 的 Agent 发起一次需要读取 Skill 文件的对话
  2. 在 sandbox 中检查可见 Skill 路径
  3. 尝试访问未授权 Skill、同名其他来源 Skill 或公共最新版 artifact
  4. 用户手动更新到版本 2 后重新发起对话
- **预期**:
  - sandbox 只暴露本次 Manifest 授权的只读 Skill artifact
  - 未授权 artifact 即使底层存在也不可读
  - 未更新前不可访问版本 2
  - 更新后下一次 run 才能访问版本 2
  - sandbox 授权与 prompt、`skill_load` 使用同一份 Manifest

### 15 禁用、缺 artifact、hash mismatch、missing install 必须 hard fail
- **优先级**: P0
- **前置条件**: 测试环境可模拟版本禁用、artifact 缺失、内容 hash 不匹配、安装态缺失
- **步骤**:
  1. 对已绑定 Skill 模拟当前版本被禁用或安全阻断
  2. 发起对话并观察页面和日志
  3. 对已绑定 Skill 模拟 artifact 缺失
  4. 发起对话并观察页面和日志
  5. 对已绑定 Skill 模拟 hash mismatch
  6. 发起对话并观察页面和日志
  7. 对已绑定 Skill 模拟 install 或 version 记录缺失
- **预期**:
  - 每类错误都明确失败，不生成看似成功的普通回答
  - 用户看到 Skill 不可用或版本不可用提示
  - 研发日志包含失败的 install、version 或 artifact 线索
  - 系统不 fallback 到 public latest、同名目录、历史 copy 或默认能力

---

## 六、前端状态与文案

### 16 SkillHub 和我的 Skills 状态清楚
- **优先级**: P1
- **前置条件**: 用户已登录，SkillHub 中同时存在未安装、已安装、有更新的 Skills
- **步骤**:
  1. 打开 SkillHub
  2. 查看不同 Skill 卡片
  3. 打开 我的 Skills
  4. 使用筛选项查看我创建的、我安装的、已发布、有更新
- **预期**:
  - SkillHub 卡片展示名称、描述、来源、作者、当前公开版本、安装状态
  - 我的 Skills 展示我创建和我安装的 Skill、当前版本、是否已绑定 Agent、是否有更新
  - 状态区分 未安装、已安装、可更新、不可用
  - 用户不需要理解内部路径、artifact、Runtime Manifest 或 sandbox allowlist

### 17 Agent 配置页和对话页展示运行相关状态
- **优先级**: P1
- **前置条件**: 用户已有绑定 Skills 的 Agent
- **步骤**:
  1. 打开 Agent 配置页
  2. 查看 Agent Skills 区域
  3. 打开对话页
  4. 查看当前 Agent 启用 Skills 的可见线索
  5. 模拟某个 Skill 不可用后刷新页面
- **预期**:
  - Agent Skills 区域展示名称、来源、当前版本、更新状态和不可用状态
  - 对话页至少能看到当前 Agent 启用了 Skills
  - 如支持展开详情，应能看到 Skill 名称和版本
  - Skill 不可用时，配置页和对话触发时都有明确提示

### 18 旧文案不再出现在主流程
- **优先级**: P1
- **前置条件**: 用户可访问 SkillHub、我的 Skills、发布弹窗、更新确认页和 Agent 配置页
- **步骤**:
  1. 逐页检查主按钮、状态 badge、弹窗标题和说明文案
  2. 尝试完成安装、发布、绑定、更新流程
- **预期**:
  - 用户主流程中使用“安装”“我的 Skills”“SkillHub”“版本”“当前版本”“有更新”等文案
  - 不再用 Download 表达安装
  - 不再把 Public / Custom 作为普通用户主分区
  - 不再展示 Package version 作为平台版本
  - 不再出现“版本来自 SKILL.md”之类与目标口径冲突的说明

---

## 七、失败分级

| 等级 | 含义 | 示例 |
| --- | --- | --- |
| P0 | 主链路不可用，或运行时错误被静默掩盖 | 页面显示已绑定，但 Agent 没调用 Skill；未更新用户读到 public latest；hash mismatch 后仍普通回答 |
| P1 | 用户能完成流程，但关键状态不清楚 | Agent 配置页看不到当前版本；有更新但看不到受影响 Agent |
| P2 | 文案或布局影响效率，但不阻塞理解 | 安装成功后的下一步入口不明显 |

## 八、测试记录模板

```text
测试人：
测试日期：
测试环境：
用户 A：
用户 B：
Agent：
Skill：

上传版本 1 是否成功：
发布版本 1 是否成功：
用户 B 安装版本：
Agent 绑定展示版本：
运行验收输入：
版本 1 实际回复：

上传版本 2 是否成功：
发布版本 2 是否成功：
未更新时页面状态：
未更新时实际回复：

更新确认页是否展示受影响 Agent：
更新后我的 Skills 版本：
更新后 Agent Skills 版本：
更新后实际回复：

Runtime Manifest 记录的版本：
skill_load 是否只读授权路径：
sandbox 是否只读授权 artifact：

失败现象：
用户可见错误：
研发排查线索：
交互需要调整的地方：
```
