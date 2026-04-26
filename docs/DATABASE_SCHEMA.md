# flow / check_point 数据库表结构快照

## 文档说明

- 生成日期：2026-04-09
- 数据源：项目根目录 `.env` 中的 `DATABASE_URL`、`DEER_FLOW_CHECKPOINTER_DATABASE_URL` 与 `DEER_FLOW_DB_SCHEMA`
- 范围：仅整理 DeerFlow 使用的 PostgreSQL schema（默认写入 `DEER_FLOW_DB_SCHEMA` 指定的 schema）
- 快照属性：本文档反映生成当日的真实库结构，后续表结构变化不会自动同步到本文档
- 交叉校对来源：
  - `flow` 章节结合 `backend/app/gateway/db/models.py` 与 Alembic 迁移定义整理
  - `check_point` 章节结合 `backend/packages/harness/deerflow/agents/checkpointer/provider.py` 与 `backend/packages/harness/deerflow/runtime/store/provider.py` 的职责说明整理
- 说明：
  - “索引数”包含主键对应的唯一索引
  - `check_point` 中多数表与字段没有数据库注释，本文仅补充最小必要的用途说明

---

## 1. flow 数据库

`flow` 是业务数据库，当前主要承载用户、工作区、工作区文件和线程主记录。表结构以 Gateway ORM 模型与 Alembic 迁移为主来源，并以当前实库结果为准。

### 1.1 总览

| 表名 | 用途 | 主键 | 外键数 | 索引数 | 备注 |
| --- | --- | --- | ---: | ---: | --- |
| `public.alembic_version` | Alembic 迁移版本记录 | `version_num` | 0 | 1 | 系统表 |
| `public.users` | 本地用户主表，映射外部认证身份 | `id` | 0 | 2 | 业务表 |
| `public.workspaces` | 用户工作区主表 | `id` | 1 | 2 | 业务表 |
| `public.workspace_files` | 工作区内文件内容存储 | `id` | 1 | 3 | 业务表，含组合唯一约束 |
| `public.threads` | 用户线程主记录 | `thread_id` | 2 | 3 | 业务表 |

### 1.2 `public.alembic_version`

**用途**

用于记录 `flow` 库当前已应用的 Alembic 迁移版本。

**字段明细**

| 字段名 | 类型 | 可空 | 默认值 | 注释 |
| --- | --- | --- | --- | --- |
| `version_num` | `character varying` | 否 | `-` | `-` |

**主键 / 唯一约束**

- 主键：`alembic_version_pkc (version_num)`
- 唯一约束：无额外唯一约束

**外键关系**

- 无

**索引列表**

- `alembic_version_pkc`：`CREATE UNIQUE INDEX alembic_version_pkc ON public.alembic_version USING btree (version_num)`

**备注**

- 系统迁移表，通常只有一条当前版本记录。

### 1.3 `public.users`

**用途**

本地用户主表，用于保存与外部认证系统对应的用户身份信息。模型定义中注明其映射 Keycloak 身份数据。

**字段明细**

| 字段名 | 类型 | 可空 | 默认值 | 注释 |
| --- | --- | --- | --- | --- |
| `id` | `bigint` | 否 | `nextval('users_id_seq'::regclass)` | `用户ID` |
| `external_auth_id` | `character varying` | 否 | `-` | `Keycloak 用户标识 (sub)` |
| `username` | `character varying` | 否 | `-` | `用户名` |
| `display_name` | `character varying` | 否 | `-` | `显示名称` |
| `email` | `character varying` | 是 | `-` | `邮箱` |
| `given_name` | `character varying` | 是 | `-` | `名` |
| `family_name` | `character varying` | 是 | `-` | `姓` |
| `email_verified` | `boolean` | 否 | `-` | `邮箱是否验证` |
| `created_at` | `timestamp with time zone` | 否 | `-` | `创建时间` |
| `updated_at` | `timestamp with time zone` | 否 | `-` | `更新时间` |

**主键 / 唯一约束**

- 主键：`users_pkey (id)`
- 唯一约束：通过唯一索引保证 `external_auth_id` 唯一

**外键关系**

- 无

**索引列表**

- `ix_users_external_auth_id`：`CREATE UNIQUE INDEX ix_users_external_auth_id ON public.users USING btree (external_auth_id)`
- `users_pkey`：`CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)`

**备注**

- `external_auth_id` 是业务上最关键的外部身份映射字段。

### 1.4 `public.workspaces`

**用途**

用户工作区主表，用于保存可独立绑定到线程的工作区实体。

**字段明细**

| 字段名 | 类型 | 可空 | 默认值 | 注释 |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | 否 | `-` | `Workspace ID` |
| `user_id` | `bigint` | 否 | `-` | `Owning user ID` |
| `name` | `character varying` | 是 | `-` | `Workspace display name` |
| `created_at` | `timestamp with time zone` | 否 | `-` | `Created at` |
| `updated_at` | `timestamp with time zone` | 否 | `-` | `Updated at` |

**主键 / 唯一约束**

- 主键：`workspaces_pkey (id)`
- 唯一约束：无

**外键关系**

- `workspaces_user_id_fkey`：`user_id -> public.users.id`

**索引列表**

- `ix_workspaces_user_id`：`CREATE INDEX ix_workspaces_user_id ON public.workspaces USING btree (user_id)`
- `workspaces_pkey`：`CREATE UNIQUE INDEX workspaces_pkey ON public.workspaces USING btree (id)`

**备注**

- 从数据库关系上看，一个用户可拥有多个工作区。

### 1.5 `public.workspace_files`

**用途**

工作区文件存储表，用于保存工作区内文件的路径、二进制内容与文件大小。

**字段明细**

| 字段名 | 类型 | 可空 | 默认值 | 注释 |
| --- | --- | --- | --- | --- |
| `id` | `bigint` | 否 | `nextval('workspace_files_id_seq'::regclass)` | `File ID` |
| `workspace_id` | `uuid` | 否 | `-` | `Workspace ID` |
| `file_path` | `text` | 否 | `-` | `Relative path within workspace` |
| `content` | `bytea` | 否 | `-` | `File content` |
| `file_size` | `bigint` | 否 | `-` | `File size in bytes` |
| `created_at` | `timestamp with time zone` | 否 | `-` | `Created at` |
| `updated_at` | `timestamp with time zone` | 否 | `-` | `Updated at` |

**主键 / 唯一约束**

- 主键：`workspace_files_pkey (id)`
- 唯一约束：`uq_workspace_files_workspace_path (workspace_id, file_path)`

**外键关系**

- `workspace_files_workspace_id_fkey`：`workspace_id -> public.workspaces.id`

**索引列表**

- `ix_workspace_files_workspace_id`：`CREATE INDEX ix_workspace_files_workspace_id ON public.workspace_files USING btree (workspace_id)`
- `uq_workspace_files_workspace_path`：`CREATE UNIQUE INDEX uq_workspace_files_workspace_path ON public.workspace_files USING btree (workspace_id, file_path)`
- `workspace_files_pkey`：`CREATE UNIQUE INDEX workspace_files_pkey ON public.workspace_files USING btree (id)`

**备注**

- 同一工作区内不允许出现重复的 `file_path`。
- 文件内容直接存储在 `bytea` 字段 `content` 中。

### 1.6 `public.threads`

**用途**

线程主记录表，用于保存用户拥有的线程实体、可选工作区绑定关系、状态和线程元数据。

**字段明细**

| 字段名 | 类型 | 可空 | 默认值 | 注释 |
| --- | --- | --- | --- | --- |
| `thread_id` | `character varying` | 否 | `-` | `Thread ID` |
| `user_id` | `bigint` | 否 | `-` | `Owning user ID` |
| `workspace_id` | `uuid` | 是 | `-` | `Bound workspace ID` |
| `title` | `text` | 是 | `-` | `Thread title` |
| `status` | `character varying` | 否 | `-` | `Thread status: idle, busy, interrupted, error` |
| `metadata` | `jsonb` | 否 | `'{}'::jsonb` | `Thread metadata` |
| `created_at` | `timestamp with time zone` | 否 | `-` | `Created at` |
| `updated_at` | `timestamp with time zone` | 否 | `-` | `Updated at` |

**主键 / 唯一约束**

- 主键：`threads_pkey (thread_id)`
- 唯一约束：无额外唯一约束

**外键关系**

- `threads_user_id_fkey`：`user_id -> public.users.id`
- `threads_workspace_id_fkey`：`workspace_id -> public.workspaces.id`

**索引列表**

- `ix_threads_status`：`CREATE INDEX ix_threads_status ON public.threads USING btree (status)`
- `ix_threads_user_updated`：`CREATE INDEX ix_threads_user_updated ON public.threads USING btree (user_id, updated_at)`
- `threads_pkey`：`CREATE UNIQUE INDEX threads_pkey ON public.threads USING btree (thread_id)`

**备注**

- `workspace_id` 可为空，表示线程未绑定工作区。
- `metadata` 使用 `jsonb` 保存扩展信息，默认值为 `{}`。

---

## 2. check_point 数据库

`check_point` 是 LangGraph PostgreSQL 持久化库。根据 `checkpointer` 与 `store` provider 的实现，checkpointer 和 store 共用同一套 PostgreSQL backend 配置；以下表均为该运行时持久化能力所依赖的系统表。

### 2.1 总览

| 表名 | 用途 | 主键 | 外键数 | 索引数 | 备注 |
| --- | --- | --- | ---: | ---: | --- |
| `public.checkpoint_blobs` | 存放 checkpoint 关联的二进制 blob 数据 | `thread_id, checkpoint_ns, channel, version` | 0 | 2 | 系统表 |
| `public.checkpoint_migrations` | 记录 checkpointer schema 迁移版本 | `v` | 0 | 1 | 系统表 |
| `public.checkpoint_writes` | 存放任务写入阶段的数据片段 | `thread_id, checkpoint_ns, checkpoint_id, task_id, idx` | 0 | 2 | 系统表 |
| `public.checkpoints` | 存放 checkpoint 主记录与元数据 | `thread_id, checkpoint_ns, checkpoint_id` | 0 | 2 | 系统表 |
| `public.store` | LangGraph store 的键值数据表 | `prefix, key` | 0 | 3 | 系统表 |
| `public.store_migrations` | 记录 store schema 迁移版本 | `v` | 0 | 1 | 系统表 |

### 2.2 `public.checkpoint_blobs`

**用途**

用于保存 checkpoint 关联的二进制 blob 数据，按线程、命名空间、channel 和版本定位。

**字段明细**

| 字段名 | 类型 | 可空 | 默认值 | 注释 |
| --- | --- | --- | --- | --- |
| `thread_id` | `text` | 否 | `-` | `-` |
| `checkpoint_ns` | `text` | 否 | `''::text` | `-` |
| `channel` | `text` | 否 | `-` | `-` |
| `version` | `text` | 否 | `-` | `-` |
| `type` | `text` | 否 | `-` | `-` |
| `blob` | `bytea` | 是 | `-` | `-` |

**主键 / 唯一约束**

- 主键：`checkpoint_blobs_pkey (thread_id, checkpoint_ns, channel, version)`
- 唯一约束：无额外唯一约束

**外键关系**

- 无

**索引列表**

- `checkpoint_blobs_pkey`：`CREATE UNIQUE INDEX checkpoint_blobs_pkey ON public.checkpoint_blobs USING btree (thread_id, checkpoint_ns, channel, version)`
- `checkpoint_blobs_thread_id_idx`：`CREATE INDEX checkpoint_blobs_thread_id_idx ON public.checkpoint_blobs USING btree (thread_id)`

**备注**

- `blob` 允许为空，说明部分记录可能只保留元信息而无实际二进制载荷。

### 2.3 `public.checkpoint_migrations`

**用途**

用于记录 checkpointer 系统表的 schema 迁移版本。

**字段明细**

| 字段名 | 类型 | 可空 | 默认值 | 注释 |
| --- | --- | --- | --- | --- |
| `v` | `integer` | 否 | `-` | `-` |

**主键 / 唯一约束**

- 主键：`checkpoint_migrations_pkey (v)`
- 唯一约束：无额外唯一约束

**外键关系**

- 无

**索引列表**

- `checkpoint_migrations_pkey`：`CREATE UNIQUE INDEX checkpoint_migrations_pkey ON public.checkpoint_migrations USING btree (v)`

**备注**

- 仅用于运行时 schema 版本管理，不承载业务数据。

### 2.4 `public.checkpoint_writes`

**用途**

用于保存任务执行过程中与 checkpoint 相关的写入数据片段，按 `checkpoint_id + task_id + idx` 进行区分。

**字段明细**

| 字段名 | 类型 | 可空 | 默认值 | 注释 |
| --- | --- | --- | --- | --- |
| `thread_id` | `text` | 否 | `-` | `-` |
| `checkpoint_ns` | `text` | 否 | `''::text` | `-` |
| `checkpoint_id` | `text` | 否 | `-` | `-` |
| `task_id` | `text` | 否 | `-` | `-` |
| `idx` | `integer` | 否 | `-` | `-` |
| `channel` | `text` | 否 | `-` | `-` |
| `type` | `text` | 是 | `-` | `-` |
| `blob` | `bytea` | 否 | `-` | `-` |
| `task_path` | `text` | 否 | `''::text` | `-` |

**主键 / 唯一约束**

- 主键：`checkpoint_writes_pkey (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)`
- 唯一约束：无额外唯一约束

**外键关系**

- 无

**索引列表**

- `checkpoint_writes_pkey`：`CREATE UNIQUE INDEX checkpoint_writes_pkey ON public.checkpoint_writes USING btree (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)`
- `checkpoint_writes_thread_id_idx`：`CREATE INDEX checkpoint_writes_thread_id_idx ON public.checkpoint_writes USING btree (thread_id)`

**备注**

- `task_path` 默认空字符串，说明任务路径信息是可选但结构化的一部分。

### 2.5 `public.checkpoints`

**用途**

用于保存 checkpoint 主记录，包括 checkpoint JSON 内容、父 checkpoint 引用和元数据。

**字段明细**

| 字段名 | 类型 | 可空 | 默认值 | 注释 |
| --- | --- | --- | --- | --- |
| `thread_id` | `text` | 否 | `-` | `-` |
| `checkpoint_ns` | `text` | 否 | `''::text` | `-` |
| `checkpoint_id` | `text` | 否 | `-` | `-` |
| `parent_checkpoint_id` | `text` | 是 | `-` | `-` |
| `type` | `text` | 是 | `-` | `-` |
| `checkpoint` | `jsonb` | 否 | `-` | `-` |
| `metadata` | `jsonb` | 否 | `'{}'::jsonb` | `-` |

**主键 / 唯一约束**

- 主键：`checkpoints_pkey (thread_id, checkpoint_ns, checkpoint_id)`
- 唯一约束：无额外唯一约束

**外键关系**

- 无

**索引列表**

- `checkpoints_pkey`：`CREATE UNIQUE INDEX checkpoints_pkey ON public.checkpoints USING btree (thread_id, checkpoint_ns, checkpoint_id)`
- `checkpoints_thread_id_idx`：`CREATE INDEX checkpoints_thread_id_idx ON public.checkpoints USING btree (thread_id)`

**备注**

- `checkpoint` 与 `metadata` 都使用 `jsonb`，其中 `metadata` 默认值为 `{}`。
- `parent_checkpoint_id` 可为空，表示该记录可能是某个分支链路的起点。

### 2.6 `public.store`

**用途**

用于保存 LangGraph store 的键值数据。根据 `store provider` 实现，该表与 checkpointer 共享相同的 PostgreSQL backend 配置。

**字段明细**

| 字段名 | 类型 | 可空 | 默认值 | 注释 |
| --- | --- | --- | --- | --- |
| `prefix` | `text` | 否 | `-` | `-` |
| `key` | `text` | 否 | `-` | `-` |
| `value` | `jsonb` | 否 | `-` | `-` |
| `created_at` | `timestamp with time zone` | 是 | `CURRENT_TIMESTAMP` | `-` |
| `updated_at` | `timestamp with time zone` | 是 | `CURRENT_TIMESTAMP` | `-` |
| `expires_at` | `timestamp with time zone` | 是 | `-` | `-` |
| `ttl_minutes` | `integer` | 是 | `-` | `-` |

**主键 / 唯一约束**

- 主键：`store_pkey (prefix, key)`
- 唯一约束：无额外唯一约束

**外键关系**

- 无

**索引列表**

- `idx_store_expires_at`：`CREATE INDEX idx_store_expires_at ON public.store USING btree (expires_at) WHERE (expires_at IS NOT NULL)`
- `store_pkey`：`CREATE UNIQUE INDEX store_pkey ON public.store USING btree (prefix, key)`
- `store_prefix_idx`：`CREATE INDEX store_prefix_idx ON public.store USING btree (prefix text_pattern_ops)`

**备注**

- `value` 使用 `jsonb` 保存实际值。
- `expires_at` 与 `ttl_minutes` 体现该表具备 TTL / 过期控制能力。

### 2.7 `public.store_migrations`

**用途**

用于记录 `store` 系统表的 schema 迁移版本。

**字段明细**

| 字段名 | 类型 | 可空 | 默认值 | 注释 |
| --- | --- | --- | --- | --- |
| `v` | `integer` | 否 | `-` | `-` |

**主键 / 唯一约束**

- 主键：`store_migrations_pkey (v)`
- 唯一约束：无额外唯一约束

**外键关系**

- 无

**索引列表**

- `store_migrations_pkey`：`CREATE UNIQUE INDEX store_migrations_pkey ON public.store_migrations USING btree (v)`

**备注**

- 仅用于运行时 schema 版本管理，不承载业务数据。
