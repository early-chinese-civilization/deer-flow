# DeerFlow用户管理阶段4-6-7 综合表结构设计

## 1. 设计原则

1. **关注点分离**: Agents、Skills、Memory各自独立管理
2. **多对多关系**: Agent可以绑定多个Skills，Skills可以被多个Agents使用
3. **用户级隔离**: 所有资源都按user_id隔离
4. **OSS存储**: Skills内容存储在OSS，数据库只存元数据和路径
5. **JSON存储**: Memory以JSON格式存储，便于灵活扩展

## 2. 核心表结构

### 2.1 agents表

用户自定义Agent主表，只存储Agent自身的配置。

```sql
CREATE TABLE agents (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Agent配置
    model VARCHAR(255),                    -- 覆盖系统默认模型
    tool_groups_json JSONB,                -- 工具组白名单 ["filesystem", "web"]
    soul_markdown TEXT,                    -- Agent人格定义
    extensions_config_json JSONB,          -- Agent专属MCP配置

    -- 时间戳
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 软删除
    deleted_at TIMESTAMPTZ,

    CONSTRAINT uq_agents_user_name UNIQUE (user_id, name)
);

CREATE INDEX ix_agents_user_id ON agents(user_id);
CREATE INDEX ix_agents_deleted_at ON agents(deleted_at);
```

### 2.2 skills表

Skills表，统一存储系统级和用户级技能。

```sql
CREATE TABLE skills (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NULL REFERENCES users(id) ON DELETE CASCADE,  -- NULL=系统级，有值=用户级
    name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    description TEXT,
    file_directory VARCHAR(500) NOT NULL,

    -- 时间戳
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 软删除
    deleted_at TIMESTAMPTZ,

  CONSTRAINT uq_skills_user_name_deleted UNIQUE (user_id, name, deleted_at)
);

CREATE INDEX ix_skills_user_id ON skills(user_id);
CREATE INDEX ix_skills_deleted_at ON skills(deleted_at);
```

**关键点**:

- ✅ 统一表设计，通过 `user_id` 区分系统级和用户级
- ✅ `user_id = NULL`: 系统级技能，所有用户共享
- ✅ `user_id = 具体值`: 用户级技能，按用户隔离
- ✅ 唯一约束确保：系统级skill name全局唯一，用户级skill name在用户范围内唯一
- ✅ Skill内容存储在OSS (`oss_path`)
- ✅ 通过 `deleted_at` 软删除，无需额外的 `status` 字段

### 2.3 agents_skills表

Agent与Skills的多对多关联表。

```sql
CREATE TABLE agents_skills (
    id BIGSERIAL PRIMARY KEY,
    agent_id BIGINT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    skill_id BIGINT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,

    -- 绑定顺序（用于排序）
    display_order INT DEFAULT 0,

    -- 时间戳
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_agents_skills_agent_skill UNIQUE (agent_id, skill_id)
);

CREATE INDEX ix_agents_skills_agent_id ON agents_skills(agent_id);
CREATE INDEX ix_agents_skills_skill_id ON agents_skills(skill_id);
```

**关系说明**:

- 一个Agent可以绑定多个Skills（系统级+用户级）
- 通过 `skills.user_id` 自动区分系统级和用户级技能
- `display_order` 控制Skills在Agent中的显示顺序

### 2.4 memories表

用户Memory主表，存储memory、soul和extensions配置。

```sql
CREATE TABLE memories (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 记忆内容
    memory_json JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- 时间戳
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 软删除
    deleted_at TIMESTAMPTZ
);

CREATE INDEX ix_memories_user_id ON memories(user_id);
CREATE INDEX ix_memories_deleted_at ON memories(deleted_at);
```
