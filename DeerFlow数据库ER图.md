# DeerFlow 数据库 ER 图
## flow 数据库 ER 图

```mermaid
erDiagram
    users ||--o{ workspaces : "拥有"
    users ||--o{ threads : "拥有"
    users ||--o{ agents : "拥有"
    users ||--o{ skills : "[改] 系统/社区 owner"
    users ||--o{ skill_installations : "安装"
    users ||--o{ skill_releases : "[新] 发布"
    users ||--o{ memories : "拥有"
    
    workspaces ||--o{ threads : "绑定"
    
    agents ||--o{ threads : "自定义聊天关联"
    agents ||--o{ agent_skills : "[新] 绑定"
    agent_skills }o--|| skill_installations : "[改] 引用可用版本"
    skills ||--o{ skill_versions : "[新] 包含版本"
    skills ||--o{ skill_installations : "可用身份"
    skill_versions ||--o{ skill_releases : "[新] 发布可见性"
    skill_versions ||--o{ skill_installations : "[新] 被安装"
    
    users {
        BIGINT id PK
        VARCHAR external_auth_id UK "Keycloak subject"
        VARCHAR username
        VARCHAR display_name
        VARCHAR email
        VARCHAR given_name
        VARCHAR family_name
        BOOLEAN email_verified
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ deleted_at "软删除"
    }
    
    workspaces {
        UUID id PK
        BIGINT user_id FK
        VARCHAR name
        TEXT file_path "Workspace OSS 根前缀"
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ deleted_at
    }
    
    threads {
        VARCHAR thread_id PK
        BIGINT user_id FK
        BIGINT agent_id FK "NULL=默认聊天"
        UUID workspace_id FK "可选"
        TEXT title
        VARCHAR status "idle/busy/interrupted/error"
        JSONB metadata
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ deleted_at
    }
    
    agents {
        BIGSERIAL id PK
        BIGINT user_id FK
        VARCHAR name "用户内唯一"
        TEXT description
        TEXT soul "人格定义"
        JSONB mcp_config "MCP配置"
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ deleted_at
    }
    
    skills {
        UUID id PK "[改] 稳定 Skill 身份"
        BIGINT owner_user_id FK "内部系统用户或普通用户"
        VARCHAR name "拥有者内唯一"
        VARCHAR display_name
        TEXT description
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ deleted_at
    }
    
    skill_versions {
        UUID skill_id PK, FK "[新] Skill 版本身份"
        INT version_number PK "同一 skill 下递增不可变"
        VARCHAR content_hash "内容去重"
        VARCHAR file_manifest_hash "完整性校验"
        VARCHAR source_package_version "可选包元数据"
        JSONB metadata
        TIMESTAMPTZ created_at
    }

    skill_releases {
        UUID skill_id PK, FK "[新] 发布版本"
        INT version_number PK, FK
        VARCHAR status "published/pending_review/rejected/delisted/suspended"
        BIGINT publisher_user_id FK "发布者"
        TIMESTAMPTZ published_at
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    skill_installations {
        BIGSERIAL id PK "[新] 用户可用 Skill"
        BIGINT user_id FK
        UUID skill_id FK
        INT version_number "当前安装/选定版本；与 skill_id 组成复合 FK"
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ deleted_at
    }

    agent_skills {
        BIGSERIAL id PK "[新] Agent-Skill 绑定"
        BIGINT agent_id FK
        BIGINT skill_installation_id FK
        INT display_order "排序"
        BOOLEAN enabled "是否启用"
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ deleted_at
    }
    
    memories {
        BIGSERIAL id PK
        BIGINT user_id FK
        JSONB memory_json "记忆内容"
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ deleted_at
    }
```

- 运行时文件与 Skill 内容由 Docker 容器内挂载的对象存储目录提供，不单独建文件内容表，因此不存在 `workspace_files` 实体。
- 默认聊天不是 default agent：`threads.agent_id = NULL` 表示默认聊天；`threads.agent_id` 非空表示自定义 Agent 聊天。
- 默认聊天启用的系统 Skill 来自平台级 `config.yaml`：`default_chat.system_skills: [{skill_id, version_number}]`。这是全局配置，只允许引用内部系统用户拥有的 Skill，不产生 `skill_installation`，也不需要启用关系表。

### flow ER 图变更标记

- 【修改】`skills.id` 改为 UUID，用于表达稳定 Skill 身份；系统 Skill 和社区 Skill 使用同一模型，系统 Skill 是内部系统用户拥有的普通 Skill。
- 【新增】`skill_versions` 依附 `skills`，版本身份为 `(skill_id, version_number)`；`version_number` 是同一 Skill 下递增且不可变的版本号。
- 【新增】`skill_releases` 保留，表示某个 `(skill_id, version_number)` 的发布、公开、审核可见性；发现、install、update 只选择 `status="published"` 的 release。
- 【新增】Skill 版本内容的 OSS 路径固定由 `(skill_id, version_number)` 派生为 `.deer-flow/skills/{skill_id}/{version_number}/`，不写入 DB 字段。
- 【新增】自定义 Agent 的绑定链路为 `agents -> agent_skills -> skill_installations -> skill_versions`。
- 【约束】`agent_skills.agent_id` 与 `agent_skills.skill_installation_id` 必须解析到同一用户：`agents.user_id = skill_installations.user_id`。
- 【新增】默认聊天系统 Skill 来自平台级 `config.yaml` 的 `default_chat.system_skills: [{skill_id, version_number}]`，只允许引用内部系统用户拥有的 Skill，不产生 `skill_installation`、`install_origin` 或 `skill_binding`/启用关系表。
- 【说明】`threads.agent_id` 空值表示默认聊天，非空表示自定义 Agent 聊天；`agents` 不设计 `kind` 字段。
- 【改名】旧口径 `skill_users` 名字不清晰，表名采用 `skill_installations`；旧口径 `skill_agent` 名字不清晰，表名采用 `agent_skills`。
- 【改名】旧字段 `skill_user_id` 名字不清晰，字段采用 `skill_installation_id`。
- 【删除】`oss_path` / `storage_uri` 字段：Skill 内容路径只能由 `(skill_id, version_number)` 派生，不能作为 `skill_versions` 或其他业务表字段保存。
- 【删除】旧 `skills.file_path` 当前生效版本路径口径，版本路径归属到不可变的派生目录 `.deer-flow/skills/{skill_id}/{version_number}/`。

---

## check_point 数据库 ER 图

```mermaid
erDiagram
    checkpoints ||--o{ checkpoint_blobs : "包含"
    checkpoints ||--o{ checkpoint_writes : "包含"
    
    checkpoints {
        TEXT thread_id PK
        TEXT checkpoint_ns PK
        TEXT checkpoint_id PK
        TEXT parent_checkpoint_id
        TEXT type
        JSONB checkpoint "状态数据"
        JSONB metadata
    }
    
    checkpoint_blobs {
        TEXT thread_id PK
        TEXT checkpoint_ns PK
        TEXT channel PK
        TEXT version PK
        TEXT type
        BYTEA blob "二进制数据"
    }
    
    checkpoint_writes {
        TEXT thread_id PK
        TEXT checkpoint_ns PK
        TEXT checkpoint_id PK
        TEXT task_id PK
        INTEGER idx PK
        TEXT channel
        TEXT type
        JSONB value
    }
    
    store {
        TEXT prefix PK
        TEXT key PK
        JSONB value
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }
    
    checkpoint_migrations {
        INTEGER v "版本号"
    }
    
    store_migrations {
        INTEGER v "版本号"
    }
```

---
