# Skill Market Runtime Mechanism Research

日期：2026-04-30

状态：外部机制调研与目标架构输入

## 文档目的

这份文档基于 [10-runtime-manifest-and-artifact-store.md](../design/10-runtime-manifest-and-artifact-store.md) 的痛点，调研主流 Skill / Plugin / Agent marketplace 的相似机制，并提炼对 DeerFlow Skills 目标架构的可用结论。

读者是后续要继续设计或实现 SkillHub、Runtime Resolver、Artifact Store、sandbox allowlist、`skill_load` 和运行审计的同学。

读完后应该能做的事：

1. 判断哪些外部机制能直接借鉴，哪些只能作为反例。
2. 把“市场展示、安装态、版本锁定、运行时授权”拆开设计。
3. 为 Runtime Manifest、不可变 Artifact Store、手动更新和同名冲突方案做下一步决策。

## 我们真正要解决的痛点

当前 DeerFlow 的核心 gap 不是缺少一个 Skill 市场页面，而是“业务层已安装”无法证明 Agent 层实际使用了用户指定版本。

从 10 号文档和相邻设计文档看，调研必须围绕这些问题：

1. public latest、目录复制、skill name 不能成为运行时真相。
2. Agent 绑定应该指向用户安装态，而不是公共 Skill、目录或名称。
3. 每次运行前必须生成 Runtime Manifest，并让 prompt、`skill_load`、sandbox allowlist 共同消费。
4. SkillVersion artifact 必须不可变，运行记录必须能审计本次实际使用的版本和内容 hash。
5. 发布新版不能自动改变已安装用户的 Agent 行为，必须由用户确认更新。
6. 同名不同作者、官方/社区/用户自建 Skill 必须能共存。

## 总体结论

主流实现没有一个完全等价于 DeerFlow 目标架构，但可以拼出清晰方向：

1. Claude Code Plugin Marketplace 和 Azure SRE Agent Plugin Marketplace 最接近“Agent skill 市场”。它们证明 marketplace 应该保存 source、version、content hash，并用 install/update 流程管理本地可用内容。
2. Terraform Provider Registry + lock file 最接近我们的 Runtime Manifest 语义。它把“可接受版本范围”和“本次实际选择版本”拆开，并用 checksum 防止同版本内容漂移。
3. Dify Plugin Marketplace 证明 plugin manifest 应显式声明资源、权限、runner 和能力入口，但它的 workspace-wide install 与 auto-update 策略不能直接照搬到 Agent 绑定。
4. OpenAI GPT Store / GPTs 更值得借鉴治理面：sharing、RBAC、workspace action domain allowlist、OAuth/user approval、draft-to-live 更新，但公开资料里没有强版本 artifact/lock 机制。
5. VS Code Marketplace 和 MCP Registry 都强调全局身份不是 display name，而是 publisher/namespace/name；这直接对应 DeerFlow 的同名 Skill 冲突问题。

因此，DeerFlow 不应该实现“目录市场”，而应该实现：

```text
Catalog entry
  -> immutable SkillVersion artifact
  -> user SkillInstall current pointer
  -> AgentSkillBinding
  -> run-scoped Runtime Manifest
  -> prompt / skill_load / sandbox allowlist
```

## 外部机制调研

### Claude Code Plugin Marketplace

Claude Code 的 plugin marketplace 使用 `marketplace.json` 作为目录，用 `plugin.json` 描述插件。插件来源可以是相对路径、GitHub 仓库、Git URL 或 git 子目录；插件 source 可以 pin 到 branch/tag/commit。版本解析规则很关键：优先取 plugin manifest 里的 version，其次取 marketplace entry 里的 version，最后回退到 git commit SHA。解析后的版本决定 cache path 和 update detection；版本相同则 update/auto-update 会跳过。它还支持通过 managed settings 限制可用 marketplace/source。

可借鉴点：

1. Marketplace catalog 和 plugin artifact source 是两层对象，可以分别 pin。
2. 显式 version 和 content ref 都能参与 update detection。
3. 版本决定 cache path，说明“安装后的可用内容”不应该直接读 marketplace latest。
4. plugin skill 使用 namespace，降低不同来源 skill name 冲突。
5. 企业环境需要 strict known marketplaces / source allowlist。

不能照搬点：

1. 如果 version 字段陈旧，新的 commit 可能不会触发更新。这说明 DeerFlow 不能只信包内版本字段。
2. branch/tag ref 仍可能漂移，DeerFlow 运行时必须落到不可变 content hash 或版本 artifact。
3. 它主要是客户端安装/cache 机制，不是 run-scoped prompt/tool/sandbox 共同授权真相。

对 DeerFlow 的启发：

SkillVersion 应由平台生成，content_hash 和 artifact_uri 是运行时强约束；导入包里的 version 只能作为 `source_package_version`。Runtime Resolver 不应重新解析 marketplace source，而应只消费数据库里已经确认的 SkillVersion。

### Azure SRE Agent Plugin Marketplace

Azure SRE Agent 的 Plugin Marketplace 明确把问题定义为：手工从 GitHub 拷贝 skill 和配置 connector 不可规模化，且无法知道 source 何时更新。它使用 GitHub-hosted catalog，支持 `.github/plugin/marketplace.json` 和 `.claude-plugin/marketplace.json`，能浏览、预览 skill 和 MCP server 配置；导入时会处理 name conflict。最重要的是：每个 imported skill 会记录 source、version 和 SHA-256 content hash，并支持 check for updates，通过和 source 比较展示 side-by-side diff 后再应用。

可借鉴点：

1. source、version、SHA-256 content hash 是 install record 的核心字段。
2. 更新检查是显式动作，不是运行时自动跟随 latest。
3. side-by-side diff 适合 DeerFlow 在用户确认 SkillInstall 更新前展示变化。
4. marketplace 可以同时分发 skill 和 MCP connector 配置，但安装时要拆成平台内对象。
5. name conflict 要在导入时解决，不能等到运行时覆盖目录。

不能照搬点：

1. Azure 的描述更偏“把 skill 导入 agent”，DeerFlow 还需要多 Agent 共享一个 SkillInstall 的更新语义。
2. 它没有公开说明 run-level manifest 如何约束 prompt、tool 和 sandbox。

对 DeerFlow 的启发：

SkillInstall 至少应该保存 source_skill_id/source_release_id、current_version_id、content_hash、installed_at、updated_at。更新 UX 可以做成“发现新版 -> 展示 diff 与受影响 Agent -> 用户确认 -> 修改 SkillInstall current_version_id”。

### Claude / Agent Skills

Claude Skills 和 Agent Skills 规范把 skill 定义为一个目录，最少包含 `SKILL.md`。`SKILL.md` 通过 YAML frontmatter 提供 name 和 description，agent 启动时只加载 metadata，任务匹配后再加载完整内容，脚本、references、assets 按需读取。Claude Code 还有 user/project/plugin/enterprise scopes；SDK 模式下 Skills 是 filesystem artifacts，通过 setting sources 自动发现，启用 Skill tool 后由模型按 description 选择。

可借鉴点：

1. Progressive disclosure 很适合 DeerFlow prompt：运行前只注入 Manifest 授权 skill 的 name、description、virtual entrypoint。
2. `SKILL.md` 适合作为 artifact entrypoint，但不是平台版本身份。
3. supporting files 应通过 Manifest virtual root 按需暴露，避免 prompt 一次性塞入所有内容。
4. `allowed-tools` 这种 skill 级权限字段可以作为作者声明，但不能替代平台 runtime allowlist。

不能照搬点：

1. filesystem discovery 是 DeerFlow 当前痛点之一；它不能作为目标运行时真相。
2. Claude Code 的 `allowed-tools` 是预批准工具，不是严格 deny；DeerFlow 的 sandbox / `skill_load` 必须按 Manifest 强制拒绝未授权路径。
3. user/project/plugin scope 的优先级不等价于 DeerFlow 的 SkillInstall/AgentSkillBinding。

对 DeerFlow 的启发：

可以继续兼容 `SKILL.md` 目录格式，但平台解析后必须生成 SkillDefinition、SkillVersion、Artifact metadata。Agent 运行时只看 Runtime Manifest，不扫描目录。

### Dify Plugin Marketplace

Dify 的插件系统支持 Marketplace、GitHub URL + version、本地 zip 三种安装来源。插件是 workspace-scoped，安装一次后 workspace 内应用都可用。`manifest.yaml` 声明 version、author、name、资源申请、权限、插件能力入口、runner language/version/entrypoint、privacy 等。Workspace 还可以控制安装权限、debug 权限、auto-update 策略以及允许的插件来源和类型。

可借鉴点：

1. Manifest 中显式声明资源、权限、runner 和能力入口，这对 DeerFlow 的 sandbox mount、tool allowlist、runtime capability descriptor 有参考价值。
2. Marketplace / GitHub / local upload 可以汇入同一个安装流水线。
3. 企业策略应控制允许安装的来源类型：official、partner/community、local/internal。
4. Auto-update 应该是策略字段，而不是隐式跟随 latest。

不能照搬点：

1. Workspace-wide install 不够精确；DeerFlow 需要 AgentSkillBinding 指向用户 SkillInstall。
2. Auto-update 默认策略如果套到 Agent，会破坏“用户未确认则 Manifest 仍指向旧版本”的验收标准。
3. Dify manifest 的 version 来自包，DeerFlow 应把包内版本降级为来源记录，平台版本由 SkillVersion 生成。

对 DeerFlow 的启发：

Skill artifact manifest 可以包含作者声明的 permission/resource/runner 信息，但 Runtime Resolver 必须重新计算最终 allowlist，并且允许安全策略禁用某个 SkillVersion 或某类 source。

### MCP Registry

MCP Registry 是 MCP server 的 app store。`server.json` 标准化描述 registry publishing、client discovery 和 package management；server name 使用反向域名/namespace 形态，并通过 GitHub OAuth/OIDC、DNS 或 HTTP 验证 namespace ownership。一个 server version 可以声明 packages、remotes、environment variables、arguments、transport 等。MCPB bundle 例子还包含 `fileSha256`，用于客户端下载执行前校验。

可借鉴点：

1. 全局身份应是 namespace/name，而不是 display name。
2. 发布时需要证明 namespace/package ownership。
3. 一个可发现条目可以有多种 runtime distribution 形式，但安装态必须解析到具体 package/remotes/version。
4. bundle 类 artifact 应有 SHA-256，用于完整性校验。

不能照搬点：

1. Remote server 本身可能是可变服务；如果 DeerFlow Skill 是可读 artifact，仍应优先不可变内容快照。
2. Registry metadata 解决的是发现和安装信息，不是某个 Agent run 的授权 Manifest。

对 DeerFlow 的启发：

SkillDefinition 可以采用 `source_namespace + name` 的稳定身份模型。社区发布需要绑定 owner identity。Artifact Store 对 zip / bundle 类内容应保存 content_hash、size、file_manifest 和校验状态。

### OpenAI GPT Store / GPTs / Workspace Agents

OpenAI 的 GPTs 支持私有、指定用户、workspace、link、GPT Store 等分享级别。Enterprise/Edu workspace 可以控制谁能创建/编辑/分享 GPT，是否允许第三方 GPT，以及 actions 的允许域名。GPT Actions 通过外部 API schema 调用服务，支持 none/API key/OAuth，public GPT actions 需要 privacy policy，用户可能需要在 action 执行前批准。发布后的 GPT 编辑会保存为 draft，选择 Update 后才应用到 live GPT。

可借鉴点：

1. 管理面要有 RBAC、sharing level、workspace/source policy。
2. 外部 action/tool 应经过 domain allowlist、OAuth/secret 管理和用户批准。
3. draft-to-live 更新模型适合 SkillRelease：发布者编辑不等于安装用户自动更新。
4. 公开 marketplace 条目需要 policy/review/appeal/visibility 状态。

不能照搬点：

1. 公开资料里没有稳定的 artifact hash / immutable version / lock manifest 机制。
2. GPT Store 更像“共享配置和能力入口”，不是可审计的 run-level artifact resolver。

对 DeerFlow 的启发：

SkillHub 可以借鉴 GPT sharing/governance，但运行安全不能停在 marketplace policy。最终仍要落到 Runtime Manifest、artifact hash 和 run record。

### VS Code Extension Marketplace

VS Code extension 的 `package.json` manifest 要求 name、version、publisher、engines，并把 extension id 定义为 `${publisher}.${name}`。Marketplace 展示用 displayName、description、categories 等字段，运行入口由 main/browser、contributes、activationEvents 描述。

可借鉴点：

1. displayName 不是身份；publisher/name 才是全局身份。
2. compatibility/engine requirement 属于 manifest 的一等字段。
3. activationEvents 与 contributes 是“什么时候可用、提供什么能力”的声明。
4. 同名冲突通过 publisher namespace 解决。

不能照搬点：

1. IDE extension marketplace 运行在客户端扩展宿主，不涉及 LLM prompt 与 sandbox 文件读取的一致授权。
2. 扩展自动更新心智不适合默认 Agent Skill。

对 DeerFlow 的启发：

SkillDefinition 需要稳定 namespace/name；Skill 的 display_name 可以重复。Manifest 中应显式表达 runtime compatibility，但运行前仍由 Resolver 判断当前 sandbox 是否满足。

### Terraform Provider Registry 与 lock file

Terraform provider source address 是全局身份，格式是 `[hostname/]namespace/type`。同一个 module 内如果两个 provider preferred local name 冲突，Terraform 推荐使用 namespace-type 复合 local name。版本选择上，configuration 用 version constraint 表达兼容范围；`terraform init` 选择具体版本后写入 `.terraform.lock.hcl`。之后默认复用 lock file 中的版本，即使有新版；只有显式 `-upgrade` 才重新选择。安装时还会校验 checksum，不匹配则报错。

可借鉴点：

1. “兼容范围”和“实际选择版本”必须分离。
2. lock/manifest 是运行或安装的具体选择结果，不能被 latest 覆盖。
3. 手动 upgrade 是用户确认更新的成熟模型。
4. checksum mismatch 应 hard fail。
5. local display name 冲突可以通过 namespace-type 或 install-id 派生虚拟名解决。

不能照搬点：

1. Terraform lock file 是项目级文件；DeerFlow 更适合 run-scoped Runtime Manifest + install-scoped current_version_id。
2. Terraform 主要锁 provider 二进制，DeerFlow 还需要同时约束 prompt、`skill_load` 和 sandbox。

对 DeerFlow 的启发：

Runtime Manifest 可以被视为“本次 Agent run 的 lock file”。它应保存实际选择的 SkillVersion、artifact hash、virtual path 和 allowlist。Run record 至少要保存 Manifest 摘要；更稳妥的做法是保存完整 Manifest JSON。

## 痛点映射矩阵

| DeerFlow 痛点 | 外部可借鉴机制 | 建议落点 |
| --- | --- | --- |
| public latest 会让 Agent 未确认跟随新版 | Terraform lock file；Claude Code version cache；Azure SRE update check | SkillInstall 保存 current_version_id；Resolver 只读 install current，不读 latest |
| 目录复制无法证明来源和版本 | Azure SRE source/version/SHA-256；MCP server.json package/version；Terraform source address | SkillInstall 保存 source、current_version_id、content_hash；目录只是 artifact 物化 |
| 同名不同作者冲突 | VS Code `${publisher}.${name}`；Terraform `[hostname/]namespace/type`；Claude plugin namespace | SkillDefinition 用 namespace/name；virtual path 冲突由 Resolver 分配 |
| prompt、tool、sandbox 各自解析会漂移 | 没有完全等价机制；Dify permissions、OpenAI domain allowlist、Claude allowed-tools 只能部分参考 | Runtime Manifest 是唯一运行时真相；三者只消费 Manifest |
| artifact 可能原地替换 | Terraform checksum；MCPB `fileSha256`；Azure SHA-256 content hash | Artifact Store content-addressed；SkillVersion artifact 不允许原地替换 |
| 用户更新前需要看影响范围 | Azure side-by-side diff；OpenAI draft/live update | 更新 SkillInstall 前展示 diff 和受影响 Agent |
| source/trust/policy | Claude strictKnownMarketplaces；Dify source restrictions；OpenAI workspace domain allowlist；MCP namespace verification | Resolver 前校验 source policy；Resolver 中校验 version status/security status |
| 运行审计 | Terraform lock；MCP package/version metadata | Run record 保存完整 Manifest 或 version/hash 快照 |

## 推荐给 DeerFlow 的目标机制

### 1. Marketplace 只做发现，不做运行时授权

Catalog / SkillHub 页面可以展示 latest release，但 Agent 运行不能读 latest。用户安装时必须创建 SkillInstall：

```text
SkillRelease latest
  -> user confirms install/update
  -> SkillInstall.current_version_id
  -> Runtime Resolver
  -> Runtime Manifest
```

### 2. SkillVersion 用平台版本和 content hash 双重定位

建议 SkillVersion 同时保存：

1. 平台生成的 `version_number`。
2. `artifact_uri`。
3. `content_hash`。
4. `artifact_size`。
5. `file_manifest`。
6. `source_package_version`，仅兼容外部包内版本。
7. `status`：draft、active、disabled、security_blocked。

Artifact Store 的主路径可以采用 content hash，例如：

```text
skills/artifacts/sha256/<digest>/
```

数据库里的 SkillVersion 仍是业务版本身份。相同内容可复用同一个 artifact，但不同 SkillDefinition 下是否创建新 SkillVersion 由业务规则决定。

### 3. Runtime Manifest 是 run 级 lock file

Resolver 输出应包含：

1. user_id、agent_id、run_id。
2. binding_id、install_id、skill_id、skill_version_id。
3. source namespace/name、display_name、description。
4. virtual_root、entrypoint。
5. artifact_uri、content_hash、file_manifest_hash。
6. tool/sandbox allowlist。
7. resolver_time、policy decisions、disabled/rejected reason。

prompt、`skill_load`、sandbox mount 都只能消费这份 Manifest。任何一层重新按 name、public latest 或目录扫描解析，都应该视为架构违规。

### 4. 更新语义默认 follow install current

MVP 推荐保持：

```text
AgentSkillBinding -> SkillInstall -> current_version_id
```

发布者发布新版只更新 SkillHub latest，不修改用户 SkillInstall。用户点击更新后：

1. 展示新旧 `SKILL.md`/manifest/file list diff。
2. 展示会受影响的 Agent。
3. 用户确认后修改 SkillInstall.current_version_id。
4. 下一次 run 的 Runtime Manifest 才指向新版。

未来再扩展：

```text
version_policy = follow_install_current | pinned_version
```

### 5. 同名冲突由 Resolver 分配 virtual path

业务身份不要使用 display name。建议：

1. SkillDefinition identity：`source_namespace/name`。
2. SkillInstall 可以有用户侧 display_name。
3. Runtime Manifest 中保留 `display_name` 和 `virtual_name`。
4. 如果同一次 run 内 name 唯一，virtual root 可用 `/mnt/skills/<name>`。
5. 如果冲突，virtual root 使用 `/mnt/skills/<namespace>--<name>` 或 `/mnt/skills/<install_id>-<name>`。

这比安装时覆盖目录安全，也能让 prompt 清楚说明“两个同名 Skill 来自不同来源”。

### 6. Sandbox 优先调研 run-level readonly bundle

10 号文档提到两种方案：

1. 多 artifact root allowlist。
2. run-level readonly bundle。

结合当前 sandbox 曾经有“同一次运行只能来自同一个 scope”的约束，建议优先验证 run-level readonly bundle：

```text
Runtime Manifest
  -> assemble readonly view
  -> /mnt/skills/<virtual_name>/SKILL.md
  -> sandbox only mounts this view
```

优点是：

1. sandbox 只需挂载一个 run scope。
2. virtual path 冲突可在 bundle 组装时解决。
3. sandbox 输出路径容易映射回 Manifest virtual path。
4. run record 可以保存 bundle manifest hash。

风险是：

1. 每次运行组装成本更高。
2. 大 artifact 需要 hardlink/reflink/overlay 或对象存储 lazy mount，避免复制成本。
3. bundle 清理和审计保留期需要明确。

### 7. `skill_load` 必须以 Manifest 做路径映射

`skill_load` 不应该接受任意 `/mnt/skills/<name>` 并自己查目录。建议规则：

1. 输入 path 必须命中 Manifest 中某个 `virtual_root`。
2. 解析后目标文件必须在对应 artifact file_manifest 内。
3. 真实路径读取前校验 artifact hash 或 bundle hash。
4. 未命中 Manifest 的路径即使真实存在，也返回 unauthorized。
5. 返回给模型的路径统一映射回 virtual path。

### 8. 官方默认 Skill 也要有显式安装态

默认无自定义 Agent 的公共 Skills 可以暂时保留 legacy public 行为。

但一旦用户在自定义 Agent 里选择官方 Skill，建议也创建 SkillInstall。否则官方 Skill 与社区 Skill 在 Agent 绑定模型中会分叉，后续同名冲突、更新确认和运行审计都会复杂化。

## 不建议采用的外部模式

1. 不采用“扫描 filesystem scopes 得到可用 Skill”作为运行时主路径。Claude/Agent Skills 的 filesystem 模式适合本地 CLI，不适合 DeerFlow 的多用户 SkillHub。
2. 不采用“包内 version 字段决定平台版本”。Claude Code 和 Dify 都暴露出 version 字段可能陈旧或由作者控制的问题。
3. 不采用 workspace-wide auto-update 作为默认。Dify 的 auto-update 策略适合插件平台，但会破坏 Agent 行为可解释性。
4. 不采用 public latest 直接绑定。它和 Terraform 默认复用 lock file 的成熟实践相反。
5. 不采用 display name 去解决身份。VS Code、Terraform、MCP Registry 都说明 namespace/name 才是稳定身份。

## 下一步建议

建议后续 explorer 或实现方案继续回答：

1. Run record 保存完整 Manifest，还是保存 version/hash 快照？调研结论偏向完整 Manifest，至少 MVP 保存完整 JSON 更方便审计。
2. Artifact Store 是否需要 file_manifest_hash？建议需要，否则 `skill_load` 很难证明子文件属于对应 artifact。
3. run-level readonly bundle 的组装方式：copy、hardlink、reflink、overlayfs、对象存储 lazy mount 哪个适配当前 sandbox。
4. 安装更新 diff 的最小可用版本：先做 `SKILL.md` diff + file list diff，后续再做语义 diff。
5. source policy 的状态机：active、delisted、disabled、security_blocked 分别在 install、update、resolver、tool 调用时如何表现。
6. 旧数据迁移：从 `skills`/`skill_releases`/`agents_skills` 生成 SkillDefinition、SkillVersion、SkillInstall、AgentSkillBinding 的 backfill 规则。

## Sources

1. Claude Code Plugin Marketplace: https://code.claude.com/docs/en/plugin-marketplaces
2. Azure SRE Agent Plugin Marketplace: https://learn.microsoft.com/en-us/azure/sre-agent/plugin-marketplace
3. Claude Code Skills: https://code.claude.com/docs/en/skills
4. Claude Agent SDK Skills: https://code.claude.com/docs/en/agent-sdk/skills
5. Claude custom skills guide: https://claude.com/docs/skills/how-to
6. Agent Skills specification: https://agentskills.io/specification
7. Dify workspace plugins: https://docs.dify.ai/en/use-dify/workspace/plugins
8. Dify plugin manifest: https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/plugin-info-by-manifest
9. MCP Registry repository and docs: https://github.com/modelcontextprotocol/registry
10. MCP server.json format: https://raw.githubusercontent.com/modelcontextprotocol/registry/main/docs/reference/server-json/generic-server-json.md
11. OpenAI GPT Actions: https://platform.openai.com/docs/actions
12. OpenAI GPT action configuration and workspace restrictions: https://help.openai.com/en/articles/9442513-configuring-actions-in-gpts
13. OpenAI GPT workspace management: https://help.openai.com/en/articles/8555535
14. OpenAI GPT sharing and publishing: https://help-lb.openai.com/en/articles/8798878-sharing-and-publishing-gpts
15. OpenAI workspace agents announcement: https://openai.com/index/introducing-workspace-agents-in-chatgpt/
16. VS Code extension manifest: https://code.visualstudio.com/api/references/extension-manifest
17. Terraform dependency lock file: https://developer.hashicorp.com/terraform/language/files/dependency-lock
18. Terraform provider requirements and source addresses: https://developer.hashicorp.com/terraform/language/providers/requirements
