# DeerFlow用户管理阶段4 - Agents业务化实施细节

## 1. 概述

本文档基于以下设计方案，提供可执行的具体实施步骤：
- [DeerFlow用户管理阶段4-Agents业务化.md](./DeerFlow用户管理阶段4-Agents业务化.md)
- [用户级自定义Agent方案设计](../user-level-custom-agent-design.md)

### 核心设计原则

1. **配置源抽象**: 通过 `custom_agent.source` 配置项控制agent配置来源（file/db）
2. **保留文件模式**: 不删除现有文件读取链路，通过Provider模式切换
3. **用户级隔离**: agent、SOUL、memory都按用户维度隔离
4. **实时解析**: 每次run都重新解析当前agent配置
5. **容错优先**: 资源缺失不阻断执行，只记录警告

## 2. 数据库设计

### 2.1 user_agents表

```sql
CREATE TABLE user_agents (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    model VARCHAR(255),
    tool_groups_json JSONB,
    skills_json JSONB,
    soul_markdown TEXT,
    memory_json JSONB,
    extensions_config_json JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_user_agents_user_name UNIQUE (user_id, name)
);
CREATE INDEX ix_user_agents_user_id ON user_agents(user_id);
```

**字段说明**:
- `model`: 覆盖系统默认模型
- `tool_groups_json`: 工具组白名单
- `skills_json`: 技能白名单
- `soul_markdown`: Agent人格定义
- `memory_json`: Agent记忆数据
- `extensions_config_json`: Agent专属MCP/技能配置

### 2.2 threads表修改

```sql
ALTER TABLE threads ADD COLUMN agent_id BIGINT REFERENCES user_agents(id) ON DELETE SET NULL;
CREATE INDEX ix_threads_agent_id ON threads(agent_id);
```

## 3. 实施步骤

### 步骤1: 数据库迁移

**文件**: `backend/alembic/versions/YYYYMMDD_add_user_agents.py`

```bash
cd backend
uv run alembic revision -m "add user_agents table"
uv run alembic upgrade head
```

### 步骤2: ORM模型

**文件**: `backend/app/gateway/db/models.py`

添加 `UserAgent` 模型，更新 `User` 和 `Thread` 的关系。

### 步骤3: Repository层

**文件**: `backend/app/gateway/db/repository.py`

实现 `UserAgentRepository` 类，提供CRUD方法。

### 步骤4: Provider抽象层

**文件**: `backend/packages/harness/deerflow/config/custom_agent_provider.py`

实现:
- `CustomAgentProvider` 接口
- `FileCustomAgentProvider` (封装现有逻辑)
- `DbCustomAgentProvider` (数据库实现)
- `get_custom_agent_provider()` 工厂函数

### 步骤5: 配置加载改造

**文件**: `backend/packages/harness/deerflow/config/agents_config.py`

改造 `load_agent_config()` 和 `load_agent_soul()` 使其通过Provider加载。

### 步骤6: Gateway API

**文件**: `backend/app/gateway/routers/agents.py`

改造为用户级CRUD API: `/api/me/agents`

### 步骤7: Thread API更新

**文件**: `backend/app/gateway/routers/threads.py`

支持 `agent_id` 参数，验证agent归属。

### 步骤8: 运行时集成

**文件**: `backend/packages/harness/deerflow/agents/lead_agent/agent.py`

从 `config.configurable` 读取 `user_id` 和 `agent_id`，支持配置覆盖。

### 步骤9: Memory系统改造

**文件**: `backend/packages/harness/deerflow/agents/memory/updater.py`

支持用户级memory隔离。

### 步骤10: 测试

编写单元测试、API测试、集成测试。

## 4. 配置示例

**config.yaml**:
```yaml
custom_agent:
  source: db  # file 或 db
```

## 5. 验收标准

- ✅ 用户可以创建/查询/更新/删除自己的agents
- ✅ 用户只能访问自己的agents
- ✅ Thread可以绑定agent_id
- ✅ Agent配置正确覆盖系统配置
- ✅ SOUL正确注入
- ✅ Memory按用户隔离
- ✅ 文件模式继续工作
- ✅ 数据库模式正常工作

## 6. 关键文件清单

- `backend/alembic/versions/*_add_user_agents.py`
- `backend/app/gateway/db/models.py`
- `backend/app/gateway/db/repository.py`
- `backend/packages/harness/deerflow/config/custom_agent_provider.py`
- `backend/packages/harness/deerflow/config/agents_config.py`
- `backend/app/gateway/routers/agents.py`
- `backend/app/gateway/routers/threads.py`
- `backend/packages/harness/deerflow/agents/lead_agent/agent.py`
