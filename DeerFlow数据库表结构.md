# DeerFlow 数据库表结构文档

本文档描述了 DeerFlow Gateway 使用的数据库表结构（基于 SQLAlchemy ORM 模型）。

## 数据库配置

| 数据库 | 配置项 | 用途 |
|--------|--------|------|
| **flow** | `DATABASE_URL` | 存储用户、工作空间、线程、Agent、Skill 等业务数据 |
| **check_point** | `DEER_FLOW_CHECKPOINTER_DATABASE_URL` | 存储 LangGraph 对话状态检查点 |

---

## 一、flow 数据库表结构

### 1.1 users 表

用户表，存储从 Keycloak 同步的用户身份信息。

| 字段名 | 类型 | 可空 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | BIGINT | 否 | AUTO_INCREMENT | 用户ID（主键） |
| external_auth_id | VARCHAR(255) | 否 | - | Keycloak subject (sub)，唯一标识 |
| username | VARCHAR(255) | 否 | - | 用户名 |
| display_name | VARCHAR(255) | 否 | - | 显示名称 |
| email | VARCHAR(255) | 是 | - | 邮箱地址 |
| given_name | VARCHAR(255) | 是 | - | 名 |
| family_name | VARCHAR(255) | 是 | - | 姓 |
| email_verified | BOOLEAN | 否 | false | 邮箱是否已验证 |
| created_at | TIMESTAMPTZ | 否 | NOW() | 创建时间 |
| updated_at | TIMESTAMPTZ | 否 | NOW() | 更新时间 |
| deleted_at | TIMESTAMPTZ | 是 | - | 软删除时间 |

**主键**: `id`

**唯一约束**: `external_auth_id`

**索引**:
- `ix_users_deleted_at`: (deleted_at)

**关系**:
- 一对多: `workspaces` (级联删除)
- 一对多: `threads` (级联删除)
- 一对多: `agents` (级联删除)
- 一对多: `skills` (级联删除，仅用户级)
- 一对多: `memories` (级联删除)

---

### 1.2 workspaces 表

工作空间表，独立于线程的文件存储空间。

| 字段名 | 类型 | 可空 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | UUID | 否 | uuid4() | 工作空间ID（主键） |
| user_id | BIGINT | 否 | - | 用户ID（外键） |
| name | VARCHAR(255) | 是 | - | 工作空间显示名称 |
| created_at | TIMESTAMPTZ | 否 | NOW() | 创建时间 |
| updated_at | TIMESTAMPTZ | 否 | NOW() | 更新时间 |
| deleted_at | TIMESTAMPTZ | 是 | - | 软删除时间 |

**主键**: `id`

**外键**:
- `user_id` → `users.id` (ON DELETE CASCADE)

**索引**:
- `ix_workspaces_user_id`: (user_id)
- `ix_workspaces_deleted_at`: (deleted_at)

**关系**:
- 多对一: `user`
- 一对多: `workspace_files` (级联删除)
- 一对多: `threads`

---

### 1.3 workspace_files 表

工作空间文件表，存储工作空间内的文件元数据（实际文件存储在 OSS）。

| 字段名 | 类型 | 可空 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | BIGINT | 否 | AUTO_INCREMENT | 文件ID（主键） |
| workspace_id | UUID | 否 | - | 工作空间ID（外键） |
| name | VARCHAR(255) | 否 | - | 文件名称 |
| file_path | TEXT | 否 | - | 工作空间内的相对路径 |
| content_type | VARCHAR(100) | 是 | - | MIME类型 |
| created_at | TIMESTAMPTZ | 否 | NOW() | 创建时间 |
| updated_at | TIMESTAMPTZ | 否 | NOW() | 更新时间 |
| deleted_at | TIMESTAMPTZ | 是 | - | 软删除时间 |

**主键**: `id`

**外键**:
- `workspace_id` → `workspaces.id` (ON DELETE CASCADE)

**索引**:
- `ix_workspace_files_workspace_id`: (workspace_id)
- `ix_workspace_files_deleted_at`: (deleted_at)

**唯一约束**:
- `uq_workspace_files_workspace_path`: (workspace_id, file_path)

**关系**:
- 多对一: `workspace`

---

### 1.4 threads 表

线程表，存储用户对话线程的业务记录。

| 字段名 | 类型 | 可空 | 默认值 | 说明 |
|--------|------|------|--------|------|
| thread_id | VARCHAR(255) | 否 | - | 线程ID（主键） |
| user_id | BIGINT | 否 | - | 用户ID（外键） |
| workspace_id | UUID | 是 | - | 绑定的工作空间ID（可选） |
| title | TEXT | 是 | - | 线程标题 |
| status | VARCHAR(50) | 否 | 'idle' | idle/busy/interrupted/error |
| metadata | JSONB | 否 | {} | 线程元数据 |
| created_at | TIMESTAMPTZ | 否 | NOW() | 创建时间 |
| updated_at | TIMESTAMPTZ | 否 | NOW() | 更新时间 |
| deleted_at | TIMESTAMPTZ | 是 | - | 软删除时间 |

**主键**: `thread_id`

**外键**:
- `user_id` → `users.id` (ON DELETE CASCADE)
- `workspace_id` → `workspaces.id` (ON DELETE SET NULL)

**索引**:
- `ix_threads_user_updated`: (user_id, updated_at)
- `ix_threads_status`: (status)
- `ix_threads_deleted_at`: (deleted_at)

**关系**:
- 多对一: `user`
- 多对一: `workspace`

---

### 1.5 agents 表

用户自定义 Agent 表，存储 Agent 配置。

| 字段名 | 类型 | 可空 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | BIGSERIAL | 否 | AUTO_INCREMENT | Agent ID（主键） |
| user_id | BIGINT | 否 | - | 用户ID（外键） |
| name | VARCHAR(255) | 否 | - | Agent名称 |
| description | TEXT | 是 | - | Agent描述 |
| model | VARCHAR(255) | 是 | - | 覆盖系统默认模型 |
| tool_groups_json | JSONB | 是 | - | 工具组白名单 |
| soul_markdown | TEXT | 是 | - | Agent人格定义 |
| extensions_config_json | JSONB | 是 | - | Agent专属MCP配置 |
| created_at | TIMESTAMPTZ | 否 | NOW() | 创建时间 |
| updated_at | TIMESTAMPTZ | 否 | NOW() | 更新时间 |
| deleted_at | TIMESTAMPTZ | 是 | - | 软删除时间 |

**主键**: `id`

**外键**:
- `user_id` → `users.id` (ON DELETE CASCADE)

**索引**:
- `ix_agents_user_id`: (user_id)
- `ix_agents_deleted_at`: (deleted_at)

**唯一约束**:
- `uq_agents_user_name`: (user_id, name)

**关系**:
- 多对一: `user`
- 一对多: `agents_skills`

---

### 1.6 skills 表

技能表，统一存储系统级和用户级技能。

| 字段名 | 类型 | 可空 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | BIGSERIAL | 否 | AUTO_INCREMENT | Skill ID（主键） |
| user_id | BIGINT | 是 | - | NULL=系统级，有值=用户级 |
| name | VARCHAR(255) | 否 | - | Skill名称（唯一标识） |
| display_name | VARCHAR(255) | 是 | - | 显示名称 |
| description | TEXT | 是 | - | Skill描述 |
| file_directory | VARCHAR(500) | 否 | - | OSS文件目录路径 |
| created_at | TIMESTAMPTZ | 否 | NOW() | 创建时间 |
| updated_at | TIMESTAMPTZ | 否 | NOW() | 更新时间 |
| deleted_at | TIMESTAMPTZ | 是 | - | 软删除时间 |

**主键**: `id`

**外键**:
- `user_id` → `users.id` (ON DELETE CASCADE)

**索引**:
- `ix_skills_user_id`: (user_id)
- `ix_skills_deleted_at`: (deleted_at)

**唯一约束**:
- `uq_skills_user_name_deleted`: (user_id, name, deleted_at)

**说明**:
- `user_id = NULL`: 系统级技能，所有用户共享
- `user_id = 具体值`: 用户级技能，按用户隔离

**关系**:
- 多对一: `user`
- 一对多: `agents_skills`

---

### 1.7 agents_skills 表

Agent 与 Skill 的多对多关联表。

| 字段名 | 类型 | 可空 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | BIGSERIAL | 否 | AUTO_INCREMENT | 关联ID（主键） |
| agent_id | BIGINT | 否 | - | Agent ID（外键） |
| skill_id | BIGINT | 否 | - | Skill ID（外键） |
| display_order | INT | 否 | 0 | 显示顺序（用于排序） |
| created_at | TIMESTAMPTZ | 否 | NOW() | 创建时间 |

**主键**: `id`

**外键**:
- `agent_id` → `agents.id` (ON DELETE CASCADE)
- `skill_id` → `skills.id` (ON DELETE CASCADE)

**索引**:
- `ix_agents_skills_agent_id`: (agent_id)
- `ix_agents_skills_skill_id`: (skill_id)

**唯一约束**:
- `uq_agents_skills_agent_skill`: (agent_id, skill_id)

**说明**:
- 通过 `skills.user_id` 自动区分系统级和用户级技能
- `display_order` 用于控制 Agent 中 Skill 的执行/展示顺序

---

### 1.8 memories 表

用户记忆表，存储用户长期记忆数据。

| 字段名 | 类型 | 可空 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | BIGSERIAL | 否 | AUTO_INCREMENT | Memory ID（主键） |
| user_id | BIGINT | 否 | - | 用户ID（外键） |
| memory_json | JSONB | 否 | '{}' | 记忆内容JSON |
| created_at | TIMESTAMPTZ | 否 | NOW() | 创建时间 |
| updated_at | TIMESTAMPTZ | 否 | NOW() | 更新时间 |
| deleted_at | TIMESTAMPTZ | 是 | - | 软删除时间 |

**主键**: `id`

**外键**:
- `user_id` → `users.id` (ON DELETE CASCADE)

**索引**:
- `ix_memories_user_id`: (user_id)
- `ix_memories_deleted_at`: (deleted_at)

**说明**:
- 用户级别的记忆表，所有对话会话共用一套记忆
- 每个用户只有一条记忆记录（通过业务逻辑保证）

---

## 二、check_point 数据库表结构

> 以下表由 LangGraph 框架自动管理，无需手动维护。

### 2.1 checkpoints 表

检查点主表，存储对话状态快照。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| thread_id | TEXT | 线程ID |
| checkpoint_ns | TEXT | 检查点命名空间 |
| checkpoint_id | TEXT | 检查点ID |
| parent_checkpoint_id | TEXT | 父检查点ID |
| type | TEXT | 检查点类型 |
| checkpoint | JSONB | 检查点数据 |
| metadata | JSONB | 元数据 |

**主键**: (thread_id, checkpoint_ns, checkpoint_id)

---

### 2.2 checkpoint_blobs 表

检查点二进制数据表，存储大型对象。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| thread_id | TEXT | 线程ID |
| checkpoint_ns | TEXT | 检查点命名空间 |
| channel | TEXT | 通道名称 |
| version | TEXT | 版本 |
| type | TEXT | 数据类型 |
| blob | BYTEA | 二进制数据 |

**主键**: (thread_id, checkpoint_ns, channel, version)

---

### 2.3 checkpoint_writes 表

检查点写入记录表，存储状态更新操作。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| thread_id | TEXT | 线程ID |
| checkpoint_ns | TEXT | 检查点命名空间 |
| checkpoint_id | TEXT | 检查点ID |
| task_id | TEXT | 任务ID |
| idx | INTEGER | 写入序号 |
| channel | TEXT | 通道名称 |
| type | TEXT | 写入类型 |
| value | JSONB | 写入值 |

**主键**: (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)

---

### 2.4 store 表

键值存储表，用于持久化配置和状态。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| prefix | TEXT | 前缀 |
| key | TEXT | 键 |
| value | JSONB | 值 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

**主键**: (prefix, key)

---

### 2.5 checkpoint_migrations 表

检查点数据库迁移版本表。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| v | INTEGER | 迁移版本号 |

---

### 2.6 store_migrations 表

存储数据库迁移版本表。

| 字段名 | 类型 | 说明 |
|--------|------|------|
| v | INTEGER | 迁移版本号 |

---

## 三、实体关系图（ER 图）


## 四、表统计

| 数据库 | 表数量 | 说明 |
|--------|--------|------|
| flow | 8 | 业务表（用户、工作空间、线程、Agent、Skill、记忆等） |
| check_point | 6 | LangGraph 框架表（检查点、存储、迁移等） |
| **总计** | **14** | |

---



