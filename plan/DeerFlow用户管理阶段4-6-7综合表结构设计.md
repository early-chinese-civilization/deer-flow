# DeerFlow用户管理阶段4-6-7 综合表结构设计

## 1. 设计原则

1. **关注点分离**: Agents、Skills、Memory各自独立管理
2. **多对多关系**: Agent可以绑定多个Skills，Skills可以被多个Agents使用
3. **用户级隔离**: 所有资源都按user_id隔离
4. **OSS存储**: Skills内容存储在OSS，数据库只存元数据和路径
5. **JSON存储**: Memory以JSON格式存储，便于灵活扩展

## 2. 核心表结构

### 2.1 user_agents表

用户自定义Agent主表，只存储Agent自身的配置。

```sql
CREATE TABLE user_agents (
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
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT uq_user_agents_user_name UNIQUE (user_id, name)
);

CREATE INDEX ix_user_agents_user_id ON user_agents(user_id);
```

**移除的字段**:
- ❌ `skills_json` - 移到 `agent_skills` 关联表
- ❌ `memory_json` - 移到 `user_memories` 表

### 2.2 user_skills表

用户自定义Skills主表，存储元数据和OSS路径。

```sql
CREATE TABLE user_skills (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Skill基本信息
    name VARCHAR(255) NOT NULL,            -- skill唯一标识
    display_name VARCHAR(255),             -- 显示名称
    description TEXT,                      -- skill描述
    
    -- 版本信息
    version VARCHAR(50),                   -- 版本号
    author VARCHAR(255),                   -- 作者
    license VARCHAR(100),                  -- 许可证
    
    -- OSS存储
    oss_path VARCHAR(500) NOT NULL,        -- OSS路径: users/{user_id}/skills/{name}/SKILL.md
    
    -- 状态
    enabled BOOLEAN NOT NULL DEFAULT true,
    sync_status VARCHAR(50) DEFAULT 'pending',  -- pending, syncing, synced, failed
    
    -- 元数据
    allowed_tools_json JSONB,              -- 允许的工具列表
    metadata_json JSONB,                   -- 其他元数据
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT uq_user_skills_user_name UNIQUE (user_id, name)
);

CREATE INDEX ix_user_skills_user_id ON user_skills(user_id);
CREATE INDEX ix_user_skills_enabled ON user_skills(enabled);
CREATE INDEX ix_user_skills_sync_status ON user_skills(sync_status);
```

**关键点**:
- ✅ Skill内容存储在OSS，不存数据库
- ✅ `oss_path` 记录OSS存储路径
- ✅ `sync_status` 追踪OSS同步状态

### 2.3 agent_skills表

Agent与Skills的多对多关联表。

```sql
CREATE TABLE agent_skills (
    id BIGSERIAL PRIMARY KEY,
    agent_id BIGINT NOT NULL REFERENCES user_agents(id) ON DELETE CASCADE,
    skill_id BIGINT NOT NULL REFERENCES user_skills(id) ON DELETE CASCADE,
    
    -- 绑定顺序（用于排序）
    display_order INT DEFAULT 0,
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT uq_agent_skills_agent_skill UNIQUE (agent_id, skill_id)
);

CREATE INDEX ix_agent_skills_agent_id ON agent_skills(agent_id);
CREATE INDEX ix_agent_skills_skill_id ON agent_skills(skill_id);
```

**关系说明**:
- 一个Agent可以绑定多个Skills
- 一个Skill可以被多个Agents使用
- `display_order` 控制Skills在Agent中的显示顺序

### 2.4 user_memories表

用户Memory主表，存储完整的memory JSON。

```sql
CREATE TABLE user_memories (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id BIGINT REFERENCES user_agents(id) ON DELETE CASCADE,
    
    -- Memory内容（完整JSON）
    memory_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    -- 时间戳
    last_updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT uq_user_memories_user_agent UNIQUE (user_id, agent_id)
);

CREATE INDEX ix_user_memories_user_id ON user_memories(user_id);
CREATE INDEX ix_user_memories_agent_id ON user_memories(agent_id);
CREATE INDEX ix_user_memories_last_updated ON user_memories(last_updated_at);
```

**memory_json结构**:

```json
{
  "workContext": "用户是Python开发者",
  "personalContext": "喜欢简洁的代码",
  "topOfMind": "正在学习FastAPI",
  "recentMonths": "最近在做API开发",
  "earlierContext": "之前做过Django项目",
  "longTermBackground": "5年Python经验",
  "facts": [
    {
      "id": "fact_1",
      "content": "User prefers type hints",
      "category": "preference",
      "confidence": 0.9,
      "createdAt": "2024-01-01T00:00:00Z",
      "source": "conversation"
    }
  ]
}
```

**关系说明**:
- `agent_id = NULL`: 用户全局Memory
- `agent_id = specific_id`: Agent专属Memory
- 运行时合并：全局Memory + Agent Memory

### 2.5 threads表（更新）

```sql
ALTER TABLE threads 
    ADD COLUMN agent_id BIGINT REFERENCES user_agents(id) ON DELETE SET NULL;

CREATE INDEX ix_threads_agent_id ON threads(agent_id);
```

## 3. 表关系图

```
users (用户表)
  ├─→ user_agents (1:N)          用户的agents
  ├─→ user_skills (1:N)          用户的skills
  ├─→ user_memories (1:N)        用户的memories
  └─→ threads (1:N)              用户的threads

user_agents (Agent表)
  ├─→ agent_skills (1:N)         Agent绑定的skills
  ├─→ user_memories (1:N)        Agent专属memory
  └─→ threads (1:N)              使用该Agent的threads

user_skills (Skills表)
  └─→ agent_skills (1:N)         被哪些Agents使用

agent_skills (关联表)
  ├─→ user_agents (N:1)
  └─→ user_skills (N:1)
```

## 4. 数据流示例

### 4.1 创建Agent并绑定Skills

```sql
-- 1. 创建Agent
INSERT INTO user_agents (user_id, name, description, model)
VALUES (1, 'python-expert', 'Python专家', 'claude-sonnet-4-6')
RETURNING id;  -- 返回 agent_id = 100

-- 2. 创建Skills
INSERT INTO user_skills (user_id, name, description, oss_path)
VALUES 
    (1, 'python-best-practices', 'Python最佳实践', 'users/1/skills/python-best-practices/SKILL.md'),
    (1, 'fastapi-expert', 'FastAPI专家', 'users/1/skills/fastapi-expert/SKILL.md')
RETURNING id;  -- 返回 skill_id = 200, 201

-- 3. 绑定Agent和Skills
INSERT INTO agent_skills (agent_id, skill_id, display_order)
VALUES 
    (100, 200, 1),
    (100, 201, 2);

-- 4. 创建Agent专属Memory
INSERT INTO user_memories (user_id, agent_id, memory_json)
VALUES (1, 100, '{"workContext": "Python开发专家"}');
```

### 4.2 查询Agent的完整配置

```sql
-- 查询Agent基本信息
SELECT * FROM user_agents WHERE id = 100;

-- 查询Agent绑定的Skills
SELECT s.* 
FROM user_skills s
JOIN agent_skills as ON as.skill_id = s.id
WHERE as.agent_id = 100
ORDER BY as.display_order;

-- 查询Agent的Memory
SELECT memory_json 
FROM user_memories 
WHERE user_id = 1 AND agent_id = 100;

-- 查询用户全局Memory
SELECT memory_json 
FROM user_memories 
WHERE user_id = 1 AND agent_id IS NULL;
```

### 4.3 运行时加载流程

```python
def load_agent_runtime_config(user_id: int, agent_id: int):
    """加载Agent运行时配置"""
    
    # 1. 加载Agent基本配置
    agent = db.query(UserAgent).filter_by(id=agent_id, user_id=user_id).first()
    
    # 2. 加载Agent绑定的Skills
    skills = (
        db.query(UserSkill)
        .join(AgentSkill)
        .filter(AgentSkill.agent_id == agent_id)
        .filter(UserSkill.sync_status == 'synced')
        .order_by(AgentSkill.display_order)
        .all()
    )
    
    # 3. 从OSS下载Skills内容
    skill_contents = []
    for skill in skills:
        content = download_from_oss(skill.oss_path)
        skill_contents.append(content)
    
    # 4. 加载Memory（合并全局和Agent专属）
    global_memory = db.query(UserMemory).filter_by(
        user_id=user_id, agent_id=None
    ).first()
    
    agent_memory = db.query(UserMemory).filter_by(
        user_id=user_id, agent_id=agent_id
    ).first()
    
    merged_memory = merge_memories(
        global_memory.memory_json if global_memory else {},
        agent_memory.memory_json if agent_memory else {}
    )
    
    # 5. 返回完整配置
    return {
        'agent': agent,
        'skills': skill_contents,
        'memory': merged_memory,
    }
```

## 5. API设计

### 5.1 Agent API

```
POST   /api/me/agents                      创建Agent
GET    /api/me/agents                      列出Agents
GET    /api/me/agents/{agent_id}           获取Agent详情
PUT    /api/me/agents/{agent_id}           更新Agent
DELETE /api/me/agents/{agent_id}           删除Agent
```

### 5.2 Skills API

```
POST   /api/me/skills                      创建Skill（上传到OSS）
GET    /api/me/skills                      列出Skills
GET    /api/me/skills/{skill_id}           获取Skill详情
PUT    /api/me/skills/{skill_id}           更新Skill（重新上传OSS）
DELETE /api/me/skills/{skill_id}           删除Skill
```

### 5.3 Agent-Skills绑定API

```
GET /api/me/agents/{agent_id}/skills       获取Agent绑定的Skills
PUT /api/me/agents/{agent_id}/skills       更新Agent的Skills绑定
    Body: {"skill_ids": [200, 201]}
```

### 5.4 Memory API

```
GET /api/me/memory                         获取用户全局Memory
PUT /api/me/memory                         更新用户全局Memory
    Body: {"memory_json": {...}}

GET /api/me/agents/{agent_id}/memory       获取Agent专属Memory
PUT /api/me/agents/{agent_id}/memory       更新Agent专属Memory
    Body: {"memory_json": {...}}
```

## 6. 优势分析

### 6.1 相比原设计的优势

**原设计问题**:
```sql
-- ❌ 所有内容都塞在agent表
CREATE TABLE user_agents (
    skills_json JSONB,           -- 难以查询和管理
    memory_json JSONB,           -- 无法复用
    ...
);
```

**新设计优势**:

1. **关注点分离**
   - Agent表只管Agent配置
   - Skills表独立管理
   - Memory表独立管理

2. **多对多关系**
   - 一个Skill可以被多个Agents复用
   - 避免Skill内容重复存储

3. **灵活查询**
   ```sql
   -- 查询使用某个Skill的所有Agents
   SELECT a.* FROM user_agents a
   JOIN agent_skills as ON as.agent_id = a.id
   WHERE as.skill_id = 200;
   
   -- 查询某个用户的所有Skills
   SELECT * FROM user_skills WHERE user_id = 1;
   ```

4. **OSS存储**
   - Skills内容存OSS，数据库只存路径
   - 支持大文件，不占用数据库空间

5. **Memory层级**
   - 全局Memory（agent_id = NULL）
   - Agent专属Memory（agent_id = specific_id）
   - 运行时合并

## 7. 迁移路径

### 7.1 从阶段4的设计迁移

如果已经实现了阶段4的单表设计，迁移步骤：

```sql
-- 1. 创建新表
CREATE TABLE user_skills (...);
CREATE TABLE agent_skills (...);
CREATE TABLE user_memories (...);

-- 2. 迁移Skills数据
INSERT INTO user_skills (user_id, name, oss_path, ...)
SELECT 
    user_id,
    skill_name,
    'users/' || user_id || '/skills/' || skill_name || '/SKILL.md',
    ...
FROM (
    SELECT DISTINCT 
        user_id,
        jsonb_array_elements_text(skills_json) as skill_name
    FROM user_agents
    WHERE skills_json IS NOT NULL
) t;

-- 3. 迁移Agent-Skills关联
INSERT INTO agent_skills (agent_id, skill_id)
SELECT 
    a.id,
    s.id
FROM user_agents a
CROSS JOIN LATERAL jsonb_array_elements_text(a.skills_json) skill_name
JOIN user_skills s ON s.name = skill_name AND s.user_id = a.user_id;

-- 4. 迁移Memory数据
INSERT INTO user_memories (user_id, agent_id, memory_json)
SELECT user_id, id, memory_json
FROM user_agents
WHERE memory_json IS NOT NULL;

-- 5. 删除旧字段
ALTER TABLE user_agents DROP COLUMN skills_json;
ALTER TABLE user_agents DROP COLUMN memory_json;
```

## 8. 验收标准

- ✅ Agent、Skills、Memory三表独立管理
- ✅ Agent可以绑定多个Skills
- ✅ Skill可以被多个Agents复用
- ✅ Skills内容存储在OSS
- ✅ Memory支持全局和Agent专属两层
- ✅ 查询性能满足要求
- ✅ API功能完整
- ✅ 数据迁移成功
