# Agent Skill Runtime Scheduling

日期：2026-04-30

状态：当前运行时缺口说明；目标架构见 10

## 文档目的

这份文档把前面偏业务视角的 SkillHub、版本、安装态设计，落到 Agent 运行时如何加载 Skill。

读者是后续要改 Agent 调度、sandbox 挂载、Skill 安装和版本迁移的后端与接手 agent。

读完后应该能判断：

1. 当前 `public` 和 `user_id` 目录模型为什么能支撑简单实现。
2. 为什么它不能表达“用户安装别人 Skill 并手动更新”。
3. 目标运行时 resolver 应该从哪些领域对象解析到可读 artifact。
4. 为什么“物化到用户 scope”只能作为迁移备选，不能作为最佳目标架构。

## 一句话结论

当前实现把 Skill 的运行时读取绑定在共享文件系统的两个 scope 上：

1. `public/<skill_name>`：系统公共或 public latest Skill。
2. `<user_id>/<skill_name>`：当前用户自己的 custom Skill。

这个设计简单、可挂载、可隔离，也符合早期“系统预置 Skill + 用户上传 Skill”的需求。

但它没有足够语义表达：

1. 用户 B 安装了用户 A 发布的哪个 Skill。
2. 用户 B 当前安装的是版本 1 还是版本 2。
3. 用户 A 发布版本 2 后，用户 B 是否需要手动更新。
4. 用户 B 的 Agent 是否仍稳定使用旧版本。
5. 同名但不同作者或不同来源的 Skill 如何共存。

因此，`public` 和 `user_id` 应该保留为运行时 artifact scope，而不是继续充当产品身份、版本身份和安装身份。

【关键点】本文件主要解释当前 gap。目标方案以后续 [10-runtime-manifest-and-artifact-store.md](10-runtime-manifest-and-artifact-store.md) 为准：运行时授权真相应是 Runtime Manifest，而不是 public 目录、用户目录或复制后的 custom Skill 行。

## 当前运行时链路

当前链路可以分成四层。

### 1. 文件层

共享文件系统的 skills 根目录里有：

```text
skills/
  public/
    <skill_name>/
      SKILL.md
  <user_id>/
    <skill_name>/
      SKILL.md
```

本机开发时，这个共享目录来自 `.deer-flow` 的 OSS 挂载。远端 sandbox 也会按 OSS 前缀挂载。

### 2. 数据层

当前 `skills` 行用 `user_id` 表达可见范围：

1. `user_id = null` 表示 public Skill。
2. `user_id = 当前用户` 表示用户自己的 Skill。
3. `file_path` 指向共享文件系统里的相对目录。

`skill_releases` 记录 publish 事件，但 release 不是运行时可绑定的版本实体。

`agents_skills` 绑定的是 `skills` 行，不绑定 release、安装态或不可变版本。

### 3. Agent 配置层

Agent 创建或编辑时，当前只允许按名称解析当前用户自己的 Skill。

这带来一个隐含规则：

1. 没有指定自定义 Agent 时，运行时默认注入 public Skills。
2. 指定自定义 Agent 时，Agent 只能绑定用户目录下的 Skills。
3. 用户想让自定义 Agent 使用 public Skill，必须先把 public Skill 复制到自己的用户目录。

这就是当前 `download` 能跑通的原因，也是它的边界。

### 4. 运行时和 sandbox 层

运行时会把 Agent 绑定解析成 Skill 描述：

1. `name`
2. `description`
3. `file_path`
4. `virtual_path`

系统提示词只暴露稳定的虚拟路径，例如 `/mnt/skills/<skill_name>/SKILL.md`。

当模型调用 `skill_load` 时，工具不会直接信任虚拟路径，而是用运行时注入的 `file_path` 把虚拟路径映射回共享文件系统里的真实 artifact。

sandbox 还有一个更强约束：同一次运行的 Skills 必须来自同一个 scope。

1. 全部来自 `public`，则挂载 public scope。
2. 全部来自同一个 `user_id`，则挂载该用户 scope。
3. public 和 user scope 混用会被拒绝。
4. 多个不同 user scope 混用会被拒绝。

这个约束对安全和挂载很有价值，但它也要求产品层的“安装别人 Skill”必须先被解析成当前用户 scope 下的运行时 artifact。

## 当前 `download` 的真实语义

当前已有 `download` API，但它不是目标产品语义里的安装态。

它做的是：

1. 找到某个 public Skill 的当前 latest 行。
2. 把 public 目录复制到当前用户目录下的同名目录。
3. 创建一个新的当前用户 Skill 行。
4. 如果当前用户已有同名 Skill 且选择覆盖，则 soft-delete 旧行，并把 Agent 绑定迁移到新行。
5. 返回源 public Skill 的 release 展示信息。

这可以让用户“拿来用”，但缺少以下关系：

1. 新用户 Skill 行没有稳定记录“我来自哪个 SkillDefinition”。
2. 新用户 Skill 行没有稳定记录“我安装的是哪个 SkillVersion”。
3. release 信息只随响应返回，不成为安装态。
4. 后续发布者发布新版后，系统无法可靠判断这个用户 copy 是否可更新。
5. 覆盖同名 copy 会改变绑定它的 Agent 后续行为，缺少安装态更新确认模型。
6. public lookup 按 name 取最新，无法表达同名不同作者的社区 Skill。

所以，当前 `download` 更像“复制 public latest 到我的 custom 空间”，不是“安装别人 Skill 的某个版本”。

## 核心 gap

真正缺的不是一个下载按钮，而是安装态。

用户安装别人 Skill 时，需要同时保存三类信息：

1. 来源：这个 Skill 来自哪个官方或社区 Skill 身份。
2. 版本：这次安装的是哪个不可变内容版本。
3. 当前运行指针：我的 Agent 当前应该读取哪个版本的 artifact。

如果没有安装态，运行时只能看见“当前用户目录里有一个同名 Skill”。这会导致：

1. 无法提示更新。
2. 无法解释更新会影响哪些 Agent。
3. 无法阻止发布者新版自动污染安装用户心智。
4. 无法区分“我安装的别人的 Skill”和“我自己创建的 Skill”。
5. 无法把社区来源、官方来源和个人来源放进同一个 Agent 绑定模型。

## 目标运行时解析链路

目标链路不应该从目录猜身份，而应该从领域对象解析 artifact。

推荐链路：

1. Run 请求确定当前用户和 Agent。
2. Agent 读取 active Skill bindings。
3. Binding 指向当前用户空间里的 SkillInstall。
4. SkillInstall 指向当前使用的 SkillVersion。
5. SkillVersion 提供不可变 artifact。
6. Runtime resolver 生成本次运行的 Skill 描述。
7. sandbox 按 resolver 结果挂载只读 artifact scope。
8. `skill_load` 只能读取 resolver 允许的虚拟路径。

这个链路中，Agent 不直接绑定 SkillHub 公共对象，也不直接绑定别人发布的 SkillDefinition。

## 旧约束下的迁移备选

如果必须保守迁移，可以保留当前 sandbox 的单 scope 规则，把安装结果物化到当前用户 scope。

但这不是推荐目标架构。

【关键点】在允许大改的前提下，不应该把“复制到用户 scope”作为长期方案。它只能是兼容旧 sandbox 的过渡手段。最佳方向是 Runtime Manifest + 不可变 Artifact Store + artifact allowlist。

### 1. 保留 `public` 作为系统和 SkillHub 发布入口

`public` 可以继续承载当前公开可安装的 artifact，尤其是官方预置和 SkillHub 展示需要的 latest artifact。

但 public 不再是“用户已安装”的运行时身份。

用户自定义 Agent 要使用 public Skill 时，应先安装到自己的空间。

### 2. 安装时创建 SkillInstall

用户 B 安装用户 A 的 Skill 时，系统应该：

1. 创建或更新用户 B 的 SkillInstall。
2. 记录 source SkillDefinition。
3. 记录 installed/current SkillVersion。
4. 把当前版本 artifact 物化到用户 B 的 runtime scope。
5. 让 Agent 绑定用户 B 的 install，而不是绑定 public Skill。

物化可以是复制、受控同步或未来的只读引用。在旧 scope 约束下，复制到用户 scope 最容易兼容当前实现。

关键是：复制目录只是 runtime artifact，不再是安装身份本身。

### 3. Agent 绑定安装态

`agents_skills` 应演进为绑定 install。

运行时 resolver 从 install 的 `current_version_id` 找到 artifact，并生成：

1. prompt 里展示的 Skill 名称和描述。
2. `skill_load` 使用的虚拟路径。
3. sandbox 允许读取的实际 artifact 路径。
4. 可选的运行审计信息，例如 `skill_install_id` 和 `skill_version_id`。

### 4. 更新安装态时再切换运行时 artifact

发布者发布版本 2 后：

1. SkillHub 展示新版本。
2. 已安装版本 1 的用户看到有更新。
3. 用户不点更新，SkillInstall 的 current version 不变。
4. 用户确认更新后，系统更新 SkillInstall 的 current version。
5. runtime scope 中的物化 artifact 随之更新。
6. 绑定该 install 的 Agent 下一次运行才使用新版。

这个模型保留了“更新会影响所有绑定该安装态的 Agent”的普通用户心智。

### 5. 官方 Skill 也按安装态进入自定义 Agent

默认无自定义 Agent 的场景可以继续使用 public scope。

但用户在自定义 Agent 上绑定官方 Skill 时，建议也走安装态：

1. 从 SkillHub 安装官方 Skill。
2. 在用户 scope 中生成可运行 artifact。
3. Agent 绑定该 install。

这样同一个 Agent 可以同时绑定官方 Skill、社区 Skill 和用户自己的 Skill，而 sandbox 仍只需要挂载当前用户 scope。

## 对现有代码的设计含义

当前已有能力应尽量复用，但语义要替换。

1. `download` 的复制能力可以演进为 install 的 artifact materialization。
2. `rebind_agent_skills` 的思路可以演进为更新 install 前的受影响 Agent 查询。
3. `file_path` 仍可作为 runtime artifact 路径，但不能继续代表产品身份。
4. `virtual_path` 继续保持稳定，避免把真实 OSS 或宿主机路径暴露给模型。
5. sandbox 的单 scope 检查可以在迁移期保留，但目标方案应调研多 artifact root allowlist 或 run-level readonly bundle。
6. public Skill 按 name dedupe 的逻辑必须替换为按稳定 Skill 身份选择，否则社区同名 Skill 无法成立。
7. `owner_user_id` 不能再只做展示兼容，社区 Skill 需要真实的 source identity。

## 需要避免的方案

不要把“安装别人 Skill”实现成单纯复制目录再创建 custom Skill 行。

这个方案会重复当前 gap：

1. 复制后失去源版本关系。
2. 同名覆盖仍会绕过明确更新确认。
3. 发布者新版仍无法触达安装用户。
4. Agent 绑定仍无法解释自己使用的是哪个版本。

也不要让自定义 Agent 直接绑定 public latest。

这个方案会让发布者发布新版后，安装用户的 Agent 行为可能在没有确认的情况下变化。

## 测试锚点

后续实现至少要覆盖这些运行时测试：

1. 用户 B 安装用户 A 发布的版本 1 后，Agent runtime manifest 明确指向版本 1。
2. 用户 A 发布版本 2 后，用户 B 的 Runtime Manifest 仍指向版本 1，直到用户确认更新。
3. 用户 B 确认更新后，绑定该 install 的 Agent 下一次运行指向版本 2。
4. 自定义 Agent 同时绑定官方 Skill、社区 Skill 和用户自建 Skill 时，运行时都来自同一份 Manifest 授权。
5. 运行时拒绝读取 resolver 没有授权的 Skill 路径。
6. 同名不同作者的 SkillHub 条目不会互相覆盖，安装时必须基于稳定身份选择来源。
7. 删除或禁用一个已安装版本时，Agent 配置页和运行时都能给出可解释状态。

## 待确认问题

这些问题不阻塞 MVP 方向，但会影响具体实现：

1. 安装 artifact 物化路径是否继续使用 `<user_id>/<skill_name>`，还是改成 `<user_id>/<install_id>` 来避免同名冲突。
2. 用户空间是否允许安装两个不同来源但同名的 Skill。
3. 用户自建 Skill 和已安装 Skill 是否共用一个列表，还是在数据模型上强分 subtype。
4. 官方默认 Skills 是否需要自动为每个用户创建 install，还是只在用户绑定到自定义 Agent 时惰性安装。
5. 是否需要在 run 记录中保存本次使用的 `skill_version_id` 作为 MVP 审计字段。
