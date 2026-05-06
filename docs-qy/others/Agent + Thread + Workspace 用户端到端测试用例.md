# Agent + Thread + Workspace 用户端到端测试用例

## 一、Agent 全生命周期

### 1 创建 Agent — 完整向导流程
- **优先级**: P0
- **前置条件**: 用户已登录，系统中无同名 Agent
- **步骤**:
  1. 进入 智能体 页面
  2. 点击 "新建智能体"
  3. 输入 名称（如 `my-coder`），输入框失焦后观察实时校验结果
  4. 切换到 描述 tab，输入描述
  5. 切换到 Soul tab，输入 soul 内容（如 "You are a Python expert..."）
  6. 切换到 技能 tab，勾选 2-3 个 skills
  7. 切换到 确认 tab，确认所有信息
  8. 点击 "创建智能体"
- **预期**:
  - 每步切换时 填写数据 自动保存到 localStorage
  - name 实时校验通过（仅允许 `[A-Za-z0-9-]`，自动转小写）
  - 创建成功后跳转回 Agent Gallery，新 Agent 卡片出现
  - 卡片显示 name、description、skills 标签（最多 3 个 + overflow）

### 2 创建 Agent — 名称校验
- **优先级**: P1
- **前置条件**: 已存在名为 `my-coder` 的 Agent
- **步骤**:
  1. 创建新 Agent，输入 name = `my-coder`
  2. 观察校验结果
  3. 输入 name = `My-Coder`（大写）
  4. 观察校验结果
  5. 输入 name = `my coder`（含空格）
  6. 输入 name = `my_coder`（含下划线）
  7. 输入 name = `中文名`
- **预期**:
  - `my-coder` 提示名称已被占用
  - `My-Coder` 自动转小写后提示已被占用
  - 含空格/下划线/中文的名称实时校验不通过，提示格式错误

### 3 编辑 Agent
- **优先级**: P1
- **前置条件**: 已存在 Agent `my-coder`
- **步骤**:
  1. 在 Gallery 点击 `my-coder` 卡片的 Edit 按钮
  2. 修改 description
  3. 修改 soul 内容
  4. 增删 skills 绑定
  5. 点击保存
  6. 刷新页面，再次进入编辑页，检查数据
- **预期**:
  - 编辑页加载时显示已有数据（非空表单）
  - 保存成功后返回 Gallery，卡片信息更新
  - 再次进入编辑页，显示最新数据
  - name 字段在编辑模式下不可修改

### 4 删除 Agent
- **优先级**: P1
- **前置条件**: 存在 Agent `my-coder`，且有 1 个 Thread 绑定了该 Agent
- **步骤**:
  1. 在 Gallery 点击 `my-coder` 卡片的 Delete 按钮
  2. 确认删除对话框
  3. 检查 Gallery（Agent 应消失）
  4. 检查之前绑定该 Agent 的 Thread，查看 Agent 显示
- **预期**:
  - 确认后 Agent 从列表消失
  - 绑定该 Agent 的 Thread，其 agent 显示应为空/default（SET NULL）
  - Thread 本身不受影响，仍可正常对话

---

## 二、Thread 全生命周期

### 5 创建 Thread — 从 Agent 卡片发起
- **优先级**: P0
- **前置条件**: 已存在 Agent `my-coder`
- **步骤**:
  1. 在 智能体 点击 `my-coder` 卡片的 会话 按钮
  2. 观察跳转的 URL
  3. 观察页面顶部 Agent 显示
- **预期**:
  - URL 为 `/workspace/chats/{thread_id}?agent=my-coder`
  - 页面顶部显示 `my-coder` 的 ThreadAgentBadge
  - AgentWelcome 组件显示 agent 名称和描述

### 6 创建 Thread — 无 Agent（通用对话）
- **优先级**: P1
- **前置条件**: 用户已登录
- **步骤**:
  1. 点击侧边栏 "新会话" 按钮
  2. 观察创建的 Thread
  3. 在输入框区域使用 切换智能体 下拉选择 Agent
  4. 发送消息
- **预期**:
  - 创建时不指定 agent，Thread 正常运行
  - 可通过下拉框选择 Agent 后再对话
  - URL 更新为 `?agent=xxx`

### 7 Thread 对话 — 流式响应
- **优先级**: P0
- **前置条件**: 存在一个 Thread（绑定或未绑定 Agent）
- **步骤**:
  1. 在输入框输入 "Hello"，点击发送
  2. 观察消息流式渲染
  3. 发送第二条消息 "Write a Python hello world script 输入到一个文件中"
  4. 观察 面板 + 工作区
- **预期**:
  - 消息通过 SSE 流式渲染，非一次性显示
  - 用户消息和 AI 回复正确展示
  - 如 agent 生成了代码文件，面板展示文件内容，工作区展示文件列表
  - Thread 状态从 idle → busy → idle

### 8 Thread 状态显示
- **优先级**: P1
- **前置条件**: 存在一个 Thread
- **步骤**:
  1. 发送一条会长时间运行的消息
  2. 在运行期间观察 Thread 列表中的状态标识
  3. 运行完成后刷新，观察状态
  4. 发送消息后立即中断（关闭页面/取消请求）
- **预期**:
  - 运行中 Thread 显示 "busy" 状态（如 loading 图标）
  - 正常运行完成后显示 "idle"
  - 中断后显示 "interrupted"
  - 出错后显示 "error"

### 9 Thread 列表 — 搜索与排序
- **优先级**: P1
- **前置条件**: 用户有 20+ 个 Thread
- **步骤**:
  1. 打开侧边栏 对话
  3. 使用搜索功能过滤 Thread
  4. 验证搜索结果
- **预期**:
  - 最近更新的 Thread 排在最前
  - 搜索支持按标题过滤
  - 搜索结果实时更新

### 10 Thread 重命名
- **优先级**: P2
- **前置条件**: 存在一个 Thread，当前标题为自动生成
- **步骤**:
  1. 在 Thread 列表中右键或点击更多菜单
  2. 选择 重命名
  3. 输入新标题，确认
  4. 刷新页面，验证标题持久化
- **预期**:
  - 新标题立即在列表和聊天页面更新
  - 刷新后标题保持

### 11 Thread 删除
- **优先级**: P1
- **前置条件**: 存在一个 Thread（有对话历史 + 有 artifacts面板）
- **步骤**:
  1. 在 Thread 列表中点击删除
  2. 确认删除对话框
  3. 验证 Thread 从列表消失
  4. 验证关联的 checkpoint 和 Store 数据被清理
  5. 验证其 Workspace 是否仍存在
- **预期**:
  - Thread 从列表消失
  - 后端清理：Store metadata、checkpoint、DB row、本地文件目录
  - Workspace 不受影响（ON DELETE SET NULL）

### 12 Thread 导出
- **优先级**: P2
- **前置条件**: 存在一个有 10+ 轮对话的 Thread
- **步骤**:
  1. 在 Thread 详情页点击导出按钮
  2. 选择导出为 Markdown
  3. 选择导出为 JSON
  4. 检查导出文件内容
- **预期**:
  - Markdown 导出包含完整对话、标题、时间戳
  - JSON 导出包含结构化数据
  - 文件正确下载到本地

---

## 三、Workspace 文件管理

### 13 文件上传 — 多文件上传
- **优先级**: P0
- **前置条件**: 存在一个 Thread（已绑定 Workspace）
- **步骤**:
  1. 点击上传按钮，选择 3 个文件（.txt, .py, .pdf）
  2. 观察上传进度
  3. 上传完成后检查文件列表和 `/api/workspaces/{workspace_id}/uploads/list` 响应
- **预期**:
  - 3 个文件出现在列表中
  - 上传接口使用当前 Thread 绑定的 `workspace_id`，返回 `relative_path`、`virtual_path`、`object_key`、`http_uri`，OSS 模式还返回 `oss_uri`
  - 文件树结构正确，上传文件默认位于 `uploads/`
  - 文件显示正确的 filename、size、extension
  - 如后端返回 `markdown_file`/`markdown_virtual_path` companion 字段，则列表和 Agent 文件上下文必须显示并引用 companion；如未返回，不应出现断链或空 companion

### 14 文件上传 — 单文件大文件
- **优先级**: P2
- **前置条件**: 同上
- **步骤**:
  1. 上传一个接近部署网关限制但仍应允许的文件（如 100MB，按实际环境配置调整）
  2. 观察上传进度和结果
  3. 上传一个明显超过部署限制的文件（如 200MB，按实际环境配置调整）
- **预期**:
  - 允许范围内的文件正常上传，返回的 `size` 与浏览器 File.size 一致
  - 超限文件如果被浏览器、反向代理、OSS 或后端拒绝，附件状态变为 `error`，HoverCard 显示错误并提供 Retry
  - 发送按钮在附件处于 `uploading`/`error` 时不能把该文件提交给 Agent，不出现半上传文件进入 `additional_kwargs.files`
  - 计划中不硬编码应用层 100MB/200MB 阈值，实际阈值以部署配置或网关限制为准

### 15 文件列表 — 目录树展示
- **优先级**: P1
- **前置条件**: Workspace 中有如下文件结构；`uploads/` 下的文件来自普通 UI 上传，嵌套目录来自 Agent 产出或测试夹具预置：
  ```
  uploads/
    readme.md
    config.json
    sample.csv
  workspace/
    project/
      script.py
  outputs/
    reports/
      result.txt
  ```
- **步骤**:
  1. 打开 工作区文件列表
  2. 展开/折叠各目录节点
  3. 使用搜索过滤（如搜索 "config"）
- **预期**:
  - 普通 UI 上传文件直接展示在 `uploads/` 根目录下，不保留客户端本地目录层级
  - Agent 生成或测试夹具预置的 `workspace/project/`、`outputs/reports/` 正确展示为嵌套目录树
  - workspace/、uploads/、outputs/ 三个根目录正确区分
  - 搜索过滤实时生效，支持部分匹配

### 16 文件下载
- **优先级**: P1
- **前置条件**: Workspace 中存在文件
- **步骤**:
  1. 点击文件的下载按钮
  2. 观察浏览器下载行为
  3. 对不同类型的文件测试下载（.txt, .py, .html, .svg）
- **预期**:
  - 文件正确下载，内容无损

### 17 文件预览/内容查看
- **优先级**: P2
- **前置条件**: Workspace 中有 .txt 和 .py 文件
- **步骤**:
  1. 点击一个 .txt 文件
  2. 观察内容展示
  3. 点击一个 .py 文件
- **预期**:
  - 文本类文件内容正确展示
  - 大文件内容分页或限制展示行数
  - 二进制文件提示无法预览并提供下载

### 18 上传代码文件 → Agent 读取并执行
- **优先级**: P1
- **前置条件**: 存在一个 Thread，Agent 具备 bash/sandbox 能力
- **步骤**:
  1. 上传 `fibonacci.py`（含 `print(fib(10))` 调用）
  2. 发送 "读取 fibonacci.py 并用 bash 执行它，告诉我输出"
  3. 观察 Agent 回复中的执行结果
  4. 检查 `<uploaded_files>` 中是否包含正确的 `oss_uri` 和 `virtual_path`
- **预期**:
  - Agent 通过 `read_file` 读取上传文件内容
  - Agent 通过 `bash` 执行脚本并返回 stdout
  - 输出结果正确（fib(10) = 55）
  - Agent 引用文件时优先使用 `oss_uri`

### 19 上传数据文件 → Agent 统计分析
- **优先级**: P1
- **前置条件**: 存在一个 Thread
- **步骤**:
  1. 上传 `sales.csv`（含 12 行月度销售数据，列：month, revenue, cost）
  2. 发送 "读取 sales.csv，计算每月利润率并找出利润最高的月份"
  3. 观察 Agent 的分析过程
  4. 验证 Agent 回复中的统计结果是否与 CSV 数据一致
- **预期**:
  - Agent 正确读取 CSV 内容
  - Agent 计算出正确的利润率（(revenue-cost)/revenue）
  - Agent 正确识别利润最高月份
  - 可通过 bash 或 Python 工具完成计算

### 20 上传文档 → Agent 总结或翻译
- **优先级**: P2
- **前置条件**: 存在一个 Thread
- **步骤**:
  1. 上传一篇英文长文档 `report.md`（500+ 词）
  2. 发送 "把这个文档翻译成中文并做 3 句话的摘要"
  3. 观察 Agent 回复
  4. 验证翻译准确性和摘要是否覆盖核心内容
- **预期**:
  - Agent 正确读取文档全文（不截断）
  - 中文翻译覆盖原文关键信息
  - 摘要简洁且包含核心观点
  - markdown 格式保留（标题、列表等）

### 21 上传文件 → Agent 修改并写回 outputs
- **优先级**: P1
- **前置条件**: 存在一个 Thread
- **步骤**:
  1. 上传 `config.json`（含一个拼写错误的字段 `"enbled": true`）
  2. 发送 "config.json 中有个拼写错误，把 enbled 改成 enabled 并存到 outputs/config_fixed.json"
  3. 等待 Agent 完成
  4. 打开 工作区文件列表，检查 outputs/ 目录
  5. 下载 outputs/config_fixed.json 并验证内容
- **预期**:
  - Agent 正确识别拼写错误
  - Agent 将修正后的文件写入 `/mnt/user-data/outputs/config_fixed.json`
  - 工作区文件列表 中 outputs/ 下出现修正后的文件
  - 下载后内容正确，其他字段不变
  - 原始上传文件不受影响

### 22 多轮上传 — Agent 累积文件上下文
- **优先级**: P1
- **前置条件**: 存在一个 Thread
- **步骤**:
  1. 第一轮：上传 `data_jan.csv`，发送 "记录这个文件，稍后分析"
  2. 第二轮：上传 `data_feb.csv`，发送 "同样记录"
  3. 第三轮：发送 "把刚才上传的两个 CSV 文件做一个合并对比分析"（本轮不上传任何文件）
  4. 观察 Agent 是否能找到并读取两个历史文件
- **预期**:
  - 第三轮 `<uploaded_files>` 中 historical files 区域包含 `data_jan.csv` 和 `data_feb.csv`
  - Agent 能正确读取两个文件并做对比分析
  - 文件引用使用 `oss_uri`，不因跨轮次而丢失上下文
  - 不会因重复 `object_key` 导致 `uploaded_files` state 中文件列表异常增长

---

## 四、Agent + Thread 集成场景

### 23 Agent Soul 注入验证
- **优先级**: P0
- **前置条件**: 创建 Agent `poet`，soul = "You are a poet. Always reply in rhyming couplets."
- **步骤**:
  1. 用 `poet` Agent 创建 Thread
  2. 发送 "Introduce yourself"
  3. 用普通（无 Agent）Thread 发送同样消息
  4. 对比两个回复
- **预期**:
  - `poet` 的回复应体现诗人风格（押韵）
  - 普通 Thread 的回复无特殊风格
  - 确认 soul 内容被注入到系统提示词

### 24 Agent Skills 绑定验证
- **优先级**: P0
- **前置条件**: 系统中存在 skills A、B、C；Agent `dev` 绑定了 A、B
- **步骤**:
  1. 用 `dev` Agent 创建 Thread
  2. 发送消息询问 "What skills/tools do you have?"
  3. 检查 Agent 运行时实际可用的 skills
  4. 创建另一个 Agent `ops` 绑定 C
  5. 比较两个 Agent 的 skills 列表
- **预期**:
  - `dev` 只能使用 skills A、B（不含 C）
  - `ops` 只能使用 skill C
  - Agent 回复中列出的 skills 与其绑定的 skills 一致

### 25 Agent 删除后关联 Thread 行为
- **优先级**: P1
- **前置条件**: Agent `test-agent` 有 3 个关联 Thread
- **步骤**:
  1. 删除 Agent `test-agent`
  2. 打开其中一个关联 Thread
  3. 发送新消息
  4. 检查 Thread 的 Agent 显示
- **预期**:
  - Thread 仍可正常对话（使用默认 Agent 或无 Agent）
  - ThreadAgentBadge 显示为空或默认状态
  - Thread.agent_id 已变为 NULL

### 26 Memory 用户级别共享
- **优先级**: P1
- **前置条件**: 创建 Agent `alice` 和 `bob`
- **步骤**:
  1. 用 `alice` 对话，告诉它 "My name is John, I like Python"
  2. 新建 Thread 仍用 `alice`，问 "What's my name and what do I like?"
  3. 用 `bob` 新建 Thread，问 "What's my name?"
  4. 用无 Agent Thread 问 "What's my name?"
- **预期**:
  - `alice` Thread 2 能记住 "John likes Python"
  - `bob` Thread 也能记住 "John"（memory 是用户级别的，所有 Agent 共享）
  - 无 Agent Thread 也能记住 "John"（同一用户共享 memory）

---

## 五、Workspace + Agent 集成场景

### 27 上传文件 → Agent 感知文件
- **优先级**: P0
- **前置条件**: 有 Thread + Workspace
- **步骤**:
  1. 上传 `data.csv` 到 Workspace
  2. 发送消息 "Read and describe the content of data.csv"
  3. 观察 Agent 回复
- **预期**:
  - `<uploaded_files>` 标签被注入到 prompt 中
  - Agent 能识别并读取文件
  - 上传元数据使用 canonical `oss_uri` 作为 `path`，同时保留虚拟路径 `/mnt/user-data/uploads/data.csv`
  - `<uploaded_files>` 中明确提示模型优先引用 `oss_uri`，只有工具需要 sandbox 路径时才使用 `virtual_path`
  - 回复中包含对 CSV 内容的正确描述

### 28 Agent 生成文件 → Workspace 可见
- **优先级**: P0
- **前置条件**: 有 Thread + Workspace
- **步骤**:
  1. 发送消息 "Create a file named hello.py that prints 'Hello World'"
  2. 等待 Agent 完成
  3. 打开 工作区文件列表
  4. 检查 outputs/ 目录
  5. 下载 hello.py 验证内容
- **预期**:
  - Agent 将文件写入 `/mnt/user-data/outputs/hello.py`
  - 工作区文件列表 中 outputs/ 目录下出现 hello.py
  - 下载后文件内容为正确的 Python hello world
  - artifacts 面板也显示该文件

### 29 多文件格式 — Agent 处理不同格式
- **优先级**: P2
- **前置条件**: 上传了 .pdf、.xlsx、.pptx、.docx、.txt 文件
- **步骤**:
  1. 上传 5 种格式文件
  2. 对每种文件，要求 Agent 读取并描述内容
- **预期**:
  - 如果上传响应包含 `markdown_file`/`markdown_http_uri`/`markdown_oss_uri`，Agent 优先读取 companion 并能正确描述内容
  - 如果当前 Workspace Gateway 上传路径未生成 markdown companion，Agent 应仍能基于原文件可用性给出可理解的处理结果或明确说明无法解析
  - Agent 能正确读取并描述每种文件内容
  - markdown companion 字段一旦存在，必须与原文件位于同一 `relative_path` 目录且能通过 `markdown_virtual_path` 映射

---

## 六、完整端到端场景

### 30 典型用户工作流
- **优先级**: P0
- **场景**: 用户从零开始完成一个数据分析任务
- **步骤**:
  1. 创建 Agent `data-analyst`（soul = "You are a data analyst. Always provide statistical insights."，绑定 Python 和数据处理 skills）
  2. 用该 Agent 创建新 Thread
  3. 上传 `sales.csv`（含 12 个月销售数据）
  4. 发送 "Analyze the sales data, find trends, and create a summary report"
  5. 等待 Agent 完成分析
  6. 在 Workspace 中检查 Agent 生成的报告文件
  7. 下载报告文件验证内容
  8. 导出 Thread 为 Markdown
- **预期**:
  - Agent 正确识别为 `data-analyst` 身份
  - Agent 能读取上传的 CSV 文件
  - Agent 生成分析报告文件到 outputs/
  - 对话包含分析过程和结论
  - 导出文件包含完整对话和报告内容

### 31 Thread 分享 / URL 直达
- **优先级**: P2
- **场景**: 用户分享 Thread 链接给另一个用户
- **步骤**:
  1. 用户 A 创建 Thread 并进行了对话
  2. 复制 Thread URL
  3. 用户 B（未登录或其他账号）访问该 URL
- **预期**:
  - 用户 B 无法访问（403 Forbidden 或 404 Not Found）
  - ownership 校验正确工作

---

## 七、边界与异常测试

### 32 空 Agent（无 soul）
- **优先级**: P2
- **前置条件**: 无
- **步骤**:
  1. 创建 Agent 不填 soul
  2. 用该 Agent 创建 Thread 并发消息
- **预期**:
  - Agent 正常运行，使用默认行为
  - 系统提示词中无 `<soul>` 标签或为空

### 33 空 Skills（无绑定 skills）
- **优先级**: P2
- **步骤**:
  1. 创建 Agent 不勾选任何 skills
  2. 对话测试
- **预期**:
  - Agent 正常运行，仅使用基础工具
  - 系统提示词中 skills 列表为空

### 34 超长 Soul 内容
- **优先级**: P3
- **步骤**:
  1. 创建 Agent，soul 内容为 10000 字符
  2. 对话测试
- **预期**:
  - Agent 创建成功
  - Soul 内容被正确截断或完整注入（取决于 token 预算）
  - 不影响对话正常进行

### 35 并发创建同名 Agent
- **优先级**: P2
- **步骤**:
  1. 在两个标签页中同时创建同名 Agent
  2. 几乎同时点击 Create
- **预期**:
  - 一个成功，另一个返回 409 Conflict 或数据库唯一约束错误
  - 前端显示友好的错误提示

### 36 Thread 并发发送消息
- **优先级**: P2
- **前置条件**: 一个 Thread 正在运行中（状态为 busy）
- **步骤**:
  1. 发送一条消息（运行中）
  2. 在运行完成前再次发送消息
- **预期**:
  - 第二次发送被阻止或排队
  - 前端显示 "Agent is busy" 提示
  - 不会导致两个 run 同时在同一个 Thread 上执行

### 37 空消息发送
- **优先级**: P2
- **步骤**:
  1. 在输入框不输入任何内容，点击发送
  2. 输入纯空格/换行，点击发送
- **预期**:
  - 空消息被阻止发送
  - 发送按钮 disabled

### 38 仅上传文件不发文本
- **优先级**: P2
- **步骤**:
  1. 仅上传一个文件（不输入文本消息）
  2. 点击发送
  3. 再输入 "请分析这个文件" 并发送
- **预期**:
  - 当前 UI 行为：文件会立即上传到 workspace，但空文本不会触发 Agent run，也不会新增人类消息
  - 上传完成后的附件仍保持在输入框中，工作区文件列表 后续可看到该文件
  - 输入真实文本后再发送，文件元数据随本条消息进入 `additional_kwargs.files`
  - 如果产品目标改为支持文件-only 发送，则此用例应改为失败先行用例，并要求前端自动补全文案或允许空文本 run

### 39 上传恶意文件名（路径穿越）
- **优先级**: P1
- **步骤**:
  1. 上传文件名为 `../../../etc/passwd` 的文件
  2. 上传文件名为 `/etc/shadow` 的文件
  3. 通过 API 调用 `/prepare` 上传文件名为 `..\evil.txt`、`.`、`..`、空字符串、超过 255 bytes 的名称
- **预期**:
  - 正斜杠路径会被规范化为 basename（`passwd`、`shadow`），最终 `object_key` 仍在当前 workspace 的 `uploads/` 前缀下
  - 反斜杠、`.`、`..`、空文件名、超长文件名返回 400 或被跳过，不应写入存储
  - 所有 content/download/delete/finalize 接口对跨 workspace 或越界 `object_key` 返回 403/400/404，不暴露宿主文件系统

### 40 上传可执行文件/HTML文件 XSS
- **优先级**: P1
- **步骤**:
  1. 上传含 `<script>alert(1)</script>` 的 .html 文件
  2. 在 Workspace 中尝试直接查看内容
  3. 下载该文件
- **预期**:
  - HTML/XHTML/SVG 通过 `/uploads/content` 获取时强制 `Content-Disposition: attachment`
  - 浏览器不执行 `<script>`，不弹窗，不污染当前页面 DOM/localStorage
  - 下载后的文件内容保持原样，作为附件保存

### 41 Workspace 大文件列表
- **优先级**: P3
- **步骤**:
  1. 在 Workspace 中上传 500 个文件
  2. 打开 工作区文件列表
  3. 加载时间和滚动性能
- **预期**:
  - 列表正常加载（可能需要分页）
  - 搜索过滤响应正常
  - 滚动无卡顿

### 42 网络中断 — SSE 重连
- **优先级**: P2
- **步骤**:
  1. 发送消息，Agent 正在流式回复
  2. 断开网络 3 秒后恢复
  3. 观察 SSE stream 行为
- **预期**:
  - `reconnect-storage.ts` 保存重连状态
  - SSE 自动重连
  - 消息不会丢失
  - 或用户看到重连提示

### 43 Agent 运行超时/错误
- **优先级**: P2
- **步骤**:
  1. 发送会导致 Agent 出错的消息（如无效工具调用）
  2. 发送需要极长运行时间的消息
- **预期**:
  - 错误时 Thread 状态变为 "error"
  - 前端显示合理的错误提示
  - 超时时状态变为 "interrupted"
  - 已生成的部分内容仍然可见

### 44 Thread 删除后访问
- **优先级**: P2
- **步骤**:
  1. 记录一个 Thread 的 URL
  2. 删除该 Thread
  3. 在浏览器中访问之前记录的 URL
- **预期**:
  - 返回 404 或重定向到新 Thread
  - 不会崩溃或白屏

---

## 八、前端 UI 专项测试

### 45 Agent Gallery 空状态
- **优先级**: P2
- **前置条件**: 用户无任何 Agent
- **步骤**:
  1. 进入 Agents 页面
- **预期**:
  - 显示空状态提示（"创建你的第一个自定义智能体，设置专属系统提示词"）
  - "新建智能体" 按钮突出显示

### 46 Agent Card — Skills 标签溢出
- **优先级**: P3
- **前置条件**: Agent 绑定了 10 个 skills
- **步骤**:
  1. 查看该 Agent 的 Card
- **预期**:
  - 最多显示 3 个 skills 标签
  - 显示 "+N more" 溢出提示

### 47 工作区文件列表 — 空状态
- **优先级**: P3
- **前置条件**: 新 Workspace 无任何文件
- **步骤**:
  1. 打开 工作区文件列表
- **预期**:
  - 显示空状态提示

### 48 响应式布局 — 侧边栏折叠
- **优先级**: P3
- **步骤**:
  1. 点击侧边栏折叠按钮
  2. 再次点击展开
- **预期**:
  - 侧边栏平滑折叠/展开
  - 主内容区宽度自适应
  - 折叠状态在 localStorage 中持久化

### 49 切换智能体 — Agent 下拉
- **优先级**: P2
- **前置条件**: 有 5+ 个 Agent
- **步骤**:
  1. 在新 Thread 中点击 切换智能体 下拉
  2. 选择一个 Agent
  3. 切换选择
  4. 清除选择（选 "默认"）
- **预期**:
  - 所有 Agent 在下拉列表中可见
  - 选中后 URL `?agent=` 参数更新
  - 清除选择后 URL 移除 agent 参数

---

## 九、数据持久化验证

### 50 刷新页面后 Thread 恢复
- **优先级**: P0
- **步骤**:
  1. 在 Thread 中进行 5 轮对话
  2. 刷新页面
  3. 检查历史消息是否完整
  4. 检查 artifacts 是否仍可见
- **预期**:
  - 所有历史消息正确加载
  - artifacts 列表完整
  - Thread 标题正确显示

### 51 跨会话 Thread 列表持久化
- **优先级**: P1
- **步骤**:
  1. 创建 3 个 Thread 并分别对话
  2. 退出登录
  3. 重新登录
  4. 检查 Thread 列表
- **预期**:
  - 所有 Thread 出现在列表中
  - 标题、更新时间正确
  - 点击进入后对话历史完整

---