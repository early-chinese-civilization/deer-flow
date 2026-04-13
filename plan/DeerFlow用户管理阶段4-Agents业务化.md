# DeerFlow用户管理阶段4-Agents业务化

## 1. 本阶段目标

将 agents 从文件系统迁移到数据库业务模型，建立 agent 与 skills 的实时资源关联，实现完整的 Agent CRUD 业务功能。

## 2. 现状分析

### 2.1 数据库层（已完成）

**ORM模型** ([backend/app/gateway/db/models.py](backend/app/gateway/db/models.py)):
- ✅ `Agent` 模型：id, user_id, name, description, soul, mcp_config, 软删除
- ✅ `Skill` 模型：id, user_id, name, display_name, description, file_path, 软删除
- ✅ `AgentSkill` 模型：agent_id, skill_id, display_order, enabled, 软删除
- ✅ 唯一约束：(user_id, name) 确保用户内agent名称唯一
- ✅ 关系：Agent ↔ Thread, Agent ↔ AgentSkill ↔ Skill

**Repository层** ([backend/app/gateway/db/repository.py](backend/app/gateway/db/repository.py)):
- ✅ `AgentRepository.create_agent()` - 创建agent
- ✅ `AgentRepository.get_agent_by_id()` - 按ID查询（排除软删除）
- ✅ `AgentRepository.list_agents()` - 列出用户的agents（排除软删除）
- ❌ 缺少：update_agent, soft_delete_agent, get_agent_by_name
- ❌ 缺少：agent-skill关联管理方法

### 2.2 API层（文件系统实现）

**当前实现** ([backend/app/gateway/routers/agents.py](backend/app/gateway/routers/agents.py)):
- 基于文件系统：agents存储为目录，包含 `config.yaml` 和 `SOUL.md`
- 使用 `deerflow.config.agents_config` 模块加载配置
- 端点：GET /agents, GET /agents/check, GET /agents/{name}, POST /agents, PUT /agents/{name}, DELETE /agents/{name}
- Pydantic模型：AgentResponse, AgentCreateRequest, AgentUpdateRequest

**问题**：
- 文件系统与数据库双轨制，数据不一致
- 无法利用数据库的事务、索引、关联查询
- 无法实现agent与skill的动态绑定

### 2.3 Thread集成

**当前状态** ([backend/app/gateway/routers/threads.py](backend/app/gateway/routers/threads.py)):
- Thread模型已有 `agent_id` 字段（nullable）
- 创建thread时传入 `agent_id=None`
- 需要支持：创建时指定agent，验证agent所有权

## 3. 实施方案

### 3.1 完善Repository层

**文件**: [backend/app/gateway/db/repository.py](backend/app/gateway/db/repository.py)

在 `AgentRepository` 类中新增方法：

```python
@staticmethod
async def update_agent(
    db: AsyncSession,
    agent_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    soul: str | None = None,
    mcp_config: dict[str, Any] | None = None,
    commit: bool = True,
) -> Agent | None:
    """更新agent记录"""
    agent = await AgentRepository.get_agent_by_id(db, agent_id)
    if not agent:
        return None
    if name is not None:
        agent.name = name
    if description is not None:
        agent.description = description
    if soul is not None:
        agent.soul = soul
    if mcp_config is not None:
        agent.mcp_config = mcp_config
    await db.flush()
    await db.refresh(agent)
    if commit:
        await db.commit()
        await db.refresh(agent)
    return agent

@staticmethod
async def soft_delete_agent(
    db: AsyncSession,
    agent_id: int,
    commit: bool = True,
) -> bool:
    """软删除agent"""
    agent = await AgentRepository.get_agent_by_id(db, agent_id)
    if not agent:
        return False
    agent.deleted_at = datetime.now(UTC)
    await db.flush()
    if commit:
        await db.commit()
    return True

@staticmethod
async def get_agent_by_name(
    db: AsyncSession,
    user_id: int,
    name: str,
) -> Agent | None:
    """按用户ID和名称查询agent"""
    result = await db.execute(
        select(Agent).where(
            Agent.user_id == user_id,
            Agent.name == name,
            Agent.deleted_at.is_(None)
        )
    )
    return result.scalar_one_or_none()

@staticmethod
async def sync_agent_skills(
    db: AsyncSession,
    agent_id: int,
    skill_ids: list[int],
    commit: bool = True,
) -> list[AgentSkill]:
    """同步agent的skill关联（先删后建）"""
    # 删除旧关联
    await db.execute(
        delete(AgentSkill).where(AgentSkill.agent_id == agent_id)
    )
    # 创建新关联
    agent_skills = []
    for order, skill_id in enumerate(skill_ids):
        agent_skill = AgentSkill(
            agent_id=agent_id,
            skill_id=skill_id,
            display_order=order,
            enabled=True,
        )
        db.add(agent_skill)
        agent_skills.append(agent_skill)
    
    await db.flush()
    if commit:
        await db.commit()
    return agent_skills

@staticmethod
async def list_agent_skills(
    db: AsyncSession,
    agent_id: int,
) -> list[tuple[AgentSkill, Skill]]:
    """查询agent关联的skills（含skill详情）"""
    result = await db.execute(
        select(AgentSkill, Skill)
        .join(Skill, AgentSkill.skill_id == Skill.id)
        .where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.deleted_at.is_(None),
            Skill.deleted_at.is_(None)
        )
        .order_by(AgentSkill.display_order)
    )
    return result.all()
```

### 3.2 重构API层

**文件**: [backend/app/gateway/routers/agents.py](backend/app/gateway/routers/agents.py)

#### 3.2.1 更新Pydantic模型

```python
from datetime import datetime
from app.gateway.db.models import Agent, AgentSkill, Skill
from app.gateway.db.repository import AgentRepository, SkillRepository
from app.gateway.db.engine import get_db_session
from app.gateway.deps import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession

class AgentSkillResponse(BaseModel):
    """Agent关联的Skill响应"""
    id: int
    name: str
    display_name: str | None
    display_order: int
    enabled: bool

class AgentResponse(BaseModel):
    """Agent响应模型"""
    id: int
    name: str
    description: str | None
    soul: str | None
    mcp_config: dict[str, Any] | None
    skills: list[AgentSkillResponse]
    created_at: datetime
    updated_at: datetime

class AgentCreateRequest(BaseModel):
    """创建Agent请求"""
    name: str = Field(..., pattern="^[A-Za-z0-9-]+$", max_length=255)
    description: str | None = None
    soul: str | None = None
    mcp_config: dict[str, Any] | None = None
    skill_ids: list[int] = Field(default_factory=list)

class AgentUpdateRequest(BaseModel):
    """更新Agent请求"""
    name: str | None = Field(None, pattern="^[A-Za-z0-9-]+$", max_length=255)
    description: str | None = None
    soul: str | None = None
    mcp_config: dict[str, Any] | None = None
    skill_ids: list[int] | None = None
```

#### 3.2.2 重写API端点（核心逻辑）

替换现有的文件系统实现为数据库操作：

- **GET /agents** - 查询数据库，JOIN加载skills
- **POST /agents** - 事务创建agent + 关联skills
- **GET /agents/{agent_id}** - 按ID查询，验证所有权
- **PUT /agents/{agent_id}** - 更新agent + 同步skills
- **DELETE /agents/{agent_id}** - 软删除

### 3.3 更新Thread创建

**文件**: [backend/app/gateway/routers/threads.py](backend/app/gateway/routers/threads.py)

```python
class ThreadCreateRequest(BaseModel):
    agent_id: int | None = None  # 新增字段
    metadata: dict[str, Any] = Field(default_factory=dict)

# 在create_thread端点中验证agent_id
if body.agent_id:
    agent = await AgentRepository.get_agent_by_id(db, body.agent_id)
    if not agent or agent.user_id != current_user.id:
        raise HTTPException(404, "Agent not found")

created_thread = await ThreadRepository.create_thread(
    db=db,
    thread_id=thread_id,
    user_id=current_user.id,
    agent_id=body.agent_id,  # 传入agent_id
    workspace_id=workspace.id,
    metadata=body.metadata,
    commit=False,
)
```

## 4. 迁移策略

### 4.1 文件系统兼容

**短期**：保留文件系统路由，添加弃用警告  
**中期**：文档说明迁移路径，提供迁移工具  
**长期**：移除文件系统实现

### 4.2 默认Agent

- 系统默认agent (id=1, user_id=NULL) 已存在
- 可作为未指定agent时的fallback

## 5. 验收标准

- [ ] Repository层所有CRUD方法完成并测试通过
- [ ] API端点完整实现（创建、查询、更新、删除、列表）
- [ ] Agent-Skill关联正确管理（事务保证）
- [ ] Thread创建支持agent_id参数并验证所有权
- [ ] 软删除正确实现（deleted_at字段）
- [ ] 唯一约束生效（user_id + name）
- [ ] 权限验证：用户只能操作自己的agents
- [ ] 集成测试：完整CRUD流程 + Thread绑定

## 6. 边界与不做事项

- ❌ 本阶段不处理运行时agent解析和skill加载
- ❌ 本阶段不处理Knowledge Base集成
- ❌ 本阶段不实现文件系统agent自动迁移
- ❌ 本阶段不涉及前端实现

## 7. 关键文件清单

- [backend/app/gateway/db/models.py](backend/app/gateway/db/models.py) - ORM模型（已完成）
- [backend/app/gateway/db/repository.py](backend/app/gateway/db/repository.py) - Repository层（需补充）
- [backend/app/gateway/routers/agents.py](backend/app/gateway/routers/agents.py) - API路由（需重写）
- [backend/app/gateway/routers/threads.py](backend/app/gateway/routers/threads.py) - Thread创建（需更新）
- [backend/app/gateway/deps.py](backend/app/gateway/deps.py) - 依赖注入（需确认get_current_user）

## 8. 风险与注意事项

- **数据一致性**：使用数据库事务保证agent和skill关联的原子性
- **软删除**：已删除的agent仍可能被thread引用（ON DELETE SET NULL）
- **名称唯一性**：唯一约束(user_id, name)确保用户内不重复
- **权限验证**：每个操作都需验证agent.user_id == current_user.id
- **Skill访问控制**：验证skill属于当前用户或系统级(user_id=NULL)
