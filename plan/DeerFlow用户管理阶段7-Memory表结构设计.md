# DeerFlow用户管理阶段7 - Memory表结构设计方案

## 1. 设计目标

将memory从全局文件系统迁移到用户级数据库存储，支持：
- 用户级memory隔离
- Agent级memory隔离
- 结构化存储facts、context、history
- 高效的查询和更新
- 与现有memory系统兼容

## 2. 核心设计原则

1. **用户级隔离**: 每个用户的memory独立存储
2. **Agent级隔离**: 同一用户的不同agents有独立memory
3. **结构化存储**: facts、context分表存储，便于查询和管理
4. **版本化**: 支持memory的历史追踪
5. **兼容性**: 保留与现有memory.json格式的兼容

## 3. 数据库表结构

### 3.1 user_memories表

用户memory的主表，存储context和summary信息。

```sql
CREATE TABLE user_memories (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id BIGINT REFERENCES user_agents(id) ON DELETE CASCADE,
    
    -- Context字段（对应memory.json的顶层字段）
    work_context TEXT,
    personal_context TEXT,
    top_of_mind TEXT,
    
    -- History字段
    recent_months TEXT,
    earlier_context TEXT,
    long_term_background TEXT,
    
    -- 元数据
    last_updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT uq_user_memories_user_agent UNIQUE (user_id, agent_id)
);

CREATE INDEX ix_user_memories_user_id ON user_memories(user_id);
CREATE INDEX ix_user_memories_agent_id ON user_memories(agent_id);
CREATE INDEX ix_user_memories_last_updated ON user_memories(last_updated_at);
```

**字段说明**:

- `user_id`: 用户ID（必填）
- `agent_id`: Agent ID（可选，NULL表示用户全局memory）
- `work_context`: 工作上下文（1-3句话）
- `personal_context`: 个人上下文（1-3句话）
- `top_of_mind`: 当前关注点（1-3句话）
- `recent_months`: 近期活动记录
- `earlier_context`: 早期上下文
- `long_term_background`: 长期背景信息

### 3.2 memory_facts表

Memory facts的存储表，支持高效查询和过滤。

```sql
CREATE TABLE memory_facts (
    id BIGSERIAL PRIMARY KEY,
    memory_id BIGINT NOT NULL REFERENCES user_memories(id) ON DELETE CASCADE,
    
    -- Fact内容
    content TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,  -- preference, knowledge, context, behavior, goal
    confidence DECIMAL(3,2) NOT NULL DEFAULT 0.5,  -- 0.0 - 1.0
    
    -- 来源追踪
    source VARCHAR(100),  -- 来源描述
    thread_id VARCHAR(255),  -- 关联的thread
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- 软删除
    deleted_at TIMESTAMP WITH TIME ZONE,
    
    CONSTRAINT chk_confidence CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE INDEX ix_memory_facts_memory_id ON memory_facts(memory_id);
CREATE INDEX ix_memory_facts_category ON memory_facts(category);
CREATE INDEX ix_memory_facts_confidence ON memory_facts(confidence);
CREATE INDEX ix_memory_facts_created_at ON memory_facts(created_at DESC);
CREATE INDEX ix_memory_facts_deleted_at ON memory_facts(deleted_at) WHERE deleted_at IS NULL;
```

**字段说明**:

- `memory_id`: 关联的user_memories记录
- `content`: Fact内容（去除前后空格后唯一）
- `category`: Fact类别
  - `preference`: 用户偏好
  - `knowledge`: 知识点
  - `context`: 上下文信息
  - `behavior`: 行为模式
  - `goal`: 目标
- `confidence`: 置信度（0.0-1.0）
- `source`: 来源描述
- `thread_id`: 关联的thread ID
- `deleted_at`: 软删除时间戳

### 3.3 memory_updates表（可选）

Memory更新历史表，用于审计和回溯。

```sql
CREATE TABLE memory_updates (
    id BIGSERIAL PRIMARY KEY,
    memory_id BIGINT NOT NULL REFERENCES user_memories(id) ON DELETE CASCADE,
    
    -- 更新内容
    update_type VARCHAR(50) NOT NULL,  -- context_update, fact_added, fact_removed
    changes_json JSONB NOT NULL,
    
    -- 来源
    thread_id VARCHAR(255),
    conversation_snippet TEXT,
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX ix_memory_updates_memory_id ON memory_updates(memory_id);
CREATE INDEX ix_memory_updates_created_at ON memory_updates(created_at DESC);
```

## 4. Memory层级设计

### 4.1 三层Memory结构

```
用户全局Memory (agent_id = NULL)
  ↓ 继承
Agent专属Memory (agent_id = specific_id)
  ↓ 运行时合并
Thread运行时Memory
```

**加载规则**:

1. 加载用户全局memory（`agent_id IS NULL`）
2. 如果有agent_id，加载agent专属memory
3. 合并两层memory，agent专属覆盖全局
4. 注入到系统提示

### 4.2 Memory继承示例

```python
def load_memory_for_agent(user_id: int, agent_id: int | None) -> Memory:
    # 加载用户全局memory
    global_memory = load_user_memory(user_id, agent_id=None)
    
    if agent_id is None:
        return global_memory
    
    # 加载agent专属memory
    agent_memory = load_user_memory(user_id, agent_id)
    
    # 合并（agent覆盖global）
    return merge_memories(global_memory, agent_memory)
```

## 5. 数据迁移

### 5.1 从memory.json迁移

**现有格式** (`backend/.deer-flow/memory.json`):

```json
{
  "workContext": "...",
  "personalContext": "...",
  "topOfMind": "...",
  "recentMonths": "...",
  "earlierContext": "...",
  "longTermBackground": "...",
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

**迁移脚本**:

```python
# backend/scripts/migrate_memory_to_db.py
import json
from pathlib import Path

async def migrate_memory_file(user_id: int, memory_file: Path):
    """迁移单个memory.json文件到数据库"""
    
    # 读取文件
    data = json.loads(memory_file.read_text())
    
    # 创建user_memories记录
    memory = await UserMemoryRepository.create_memory(
        db=db,
        user_id=user_id,
        agent_id=None,  # 全局memory
        work_context=data.get('workContext'),
        personal_context=data.get('personalContext'),
        top_of_mind=data.get('topOfMind'),
        recent_months=data.get('recentMonths'),
        earlier_context=data.get('earlierContext'),
        long_term_background=data.get('longTermBackground'),
    )
    
    # 迁移facts
    for fact in data.get('facts', []):
        await MemoryFactRepository.create_fact(
            db=db,
            memory_id=memory.id,
            content=fact['content'],
            category=fact['category'],
            confidence=fact['confidence'],
            source=fact.get('source'),
            created_at=fact.get('createdAt'),
        )
    
    print(f"Migrated memory for user {user_id}")
```

### 5.2 迁移策略

1. **阶段1**: 双写模式
   - 新memory同时写入数据库和文件
   - 读取时优先从数据库读取，fallback到文件

2. **阶段2**: 批量迁移
   - 运行迁移脚本，将所有memory.json导入数据库
   - 验证数据完整性

3. **阶段3**: 切换到数据库
   - 停止写入文件
   - 只从数据库读取

4. **阶段4**: 清理文件
   - 备份旧文件
   - 删除legacy memory.json

## 6. API设计

### 6.1 Memory CRUD

```
GET    /api/me/memory                    获取用户全局memory
GET    /api/me/agents/{agent_id}/memory  获取agent专属memory
PUT    /api/me/memory                    更新用户全局memory
PUT    /api/me/agents/{agent_id}/memory  更新agent专属memory
```

### 6.2 Facts管理

```
GET    /api/me/memory/facts              列出所有facts
POST   /api/me/memory/facts              添加fact
PUT    /api/me/memory/facts/{fact_id}   更新fact
DELETE /api/me/memory/facts/{fact_id}   删除fact（软删除）
```

### 6.3 Memory搜索

```
GET /api/me/memory/search?q=keyword&category=preference
```

## 7. Repository实现

### 7.1 UserMemoryRepository

```python
class UserMemoryRepository:
    """用户Memory数据访问层"""
    
    @staticmethod
    async def get_or_create_memory(
        db: AsyncSession,
        user_id: int,
        agent_id: int | None = None,
    ) -> UserMemory:
        """获取或创建memory记录"""
        stmt = select(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.agent_id == agent_id,
        )
        result = await db.execute(stmt)
        memory = result.scalar_one_or_none()
        
        if memory is None:
            memory = UserMemory(
                user_id=user_id,
                agent_id=agent_id,
            )
            db.add(memory)
            await db.commit()
            await db.refresh(memory)
        
        return memory
    
    @staticmethod
    async def update_context(
        db: AsyncSession,
        memory_id: int,
        work_context: str | None = None,
        personal_context: str | None = None,
        top_of_mind: str | None = None,
    ) -> UserMemory:
        """更新context字段"""
        stmt = select(UserMemory).where(UserMemory.id == memory_id)
        result = await db.execute(stmt)
        memory = result.scalar_one()
        
        if work_context is not None:
            memory.work_context = work_context
        if personal_context is not None:
            memory.personal_context = personal_context
        if top_of_mind is not None:
            memory.top_of_mind = top_of_mind
        
        memory.last_updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(memory)
        return memory
```

### 7.2 MemoryFactRepository

```python
class MemoryFactRepository:
    """Memory Fact数据访问层"""
    
    @staticmethod
    async def create_fact(
        db: AsyncSession,
        memory_id: int,
        content: str,
        category: str,
        confidence: float = 0.5,
        source: str | None = None,
        thread_id: str | None = None,
    ) -> MemoryFact:
        """创建fact"""
        fact = MemoryFact(
            memory_id=memory_id,
            content=content.strip(),
            category=category,
            confidence=confidence,
            source=source,
            thread_id=thread_id,
        )
        db.add(fact)
        await db.commit()
        await db.refresh(fact)
        return fact
    
    @staticmethod
    async def list_facts(
        db: AsyncSession,
        memory_id: int,
        category: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> list[MemoryFact]:
        """列出facts"""
        stmt = (
            select(MemoryFact)
            .where(
                MemoryFact.memory_id == memory_id,
                MemoryFact.deleted_at.is_(None),
                MemoryFact.confidence >= min_confidence,
            )
            .order_by(MemoryFact.confidence.desc(), MemoryFact.created_at.desc())
            .limit(limit)
        )
        
        if category:
            stmt = stmt.where(MemoryFact.category == category)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
    
    @staticmethod
    async def soft_delete_fact(
        db: AsyncSession,
        fact_id: int,
    ) -> bool:
        """软删除fact"""
        stmt = select(MemoryFact).where(MemoryFact.id == fact_id)
        result = await db.execute(stmt)
        fact = result.scalar_one_or_none()
        
        if fact is None:
            return False
        
        fact.deleted_at = datetime.now(UTC)
        await db.commit()
        return True
```

## 8. 运行时集成

### 8.1 Memory加载

```python
# backend/packages/harness/deerflow/agents/memory/loader.py

async def load_memory_for_agent(
    user_id: int,
    agent_id: int | None,
) -> dict:
    """加载agent的memory"""
    from app.gateway.db.repository import UserMemoryRepository, MemoryFactRepository
    from app.gateway.deps import get_db_session
    
    async with get_db_session() as db:
        # 加载用户全局memory
        global_memory = await UserMemoryRepository.get_or_create_memory(
            db, user_id, agent_id=None
        )
        
        # 加载agent专属memory（如果有）
        agent_memory = None
        if agent_id:
            agent_memory = await UserMemoryRepository.get_or_create_memory(
                db, user_id, agent_id
            )
        
        # 加载facts
        memory_id = agent_memory.id if agent_memory else global_memory.id
        facts = await MemoryFactRepository.list_facts(
            db, memory_id, min_confidence=0.7, limit=15
        )
        
        # 构建memory字典
        return {
            'workContext': agent_memory.work_context if agent_memory else global_memory.work_context,
            'personalContext': agent_memory.personal_context if agent_memory else global_memory.personal_context,
            'topOfMind': agent_memory.top_of_mind if agent_memory else global_memory.top_of_mind,
            'facts': [
                {
                    'content': f.content,
                    'category': f.category,
                    'confidence': float(f.confidence),
                }
                for f in facts
            ],
        }
```

### 8.2 Memory更新

```python
# backend/packages/harness/deerflow/agents/memory/updater.py

async def update_memory_from_conversation(
    user_id: int,
    agent_id: int | None,
    conversation: list[dict],
    thread_id: str,
):
    """从对话更新memory"""
    # 1. 调用LLM提取memory更新
    updates = await extract_memory_updates(conversation)
    
    # 2. 更新数据库
    async with get_db_session() as db:
        memory = await UserMemoryRepository.get_or_create_memory(
            db, user_id, agent_id
        )
        
        # 更新context
        if updates.get('context'):
            await UserMemoryRepository.update_context(
                db,
                memory.id,
                work_context=updates['context'].get('workContext'),
                personal_context=updates['context'].get('personalContext'),
                top_of_mind=updates['context'].get('topOfMind'),
            )
        
        # 添加新facts
        for fact in updates.get('facts', []):
            # 检查重复（去除空格后比较）
            existing = await MemoryFactRepository.find_by_content(
                db, memory.id, fact['content'].strip()
            )
            if not existing:
                await MemoryFactRepository.create_fact(
                    db,
                    memory.id,
                    content=fact['content'],
                    category=fact['category'],
                    confidence=fact['confidence'],
                    source='conversation',
                    thread_id=thread_id,
                )
```

## 9. 性能优化

### 9.1 索引优化

- `user_memories(user_id, agent_id)` 唯一索引
- `memory_facts(memory_id, confidence DESC, created_at DESC)` 复合索引
- `memory_facts(deleted_at)` 部分索引（WHERE deleted_at IS NULL）

### 9.2 查询优化

- Facts查询限制数量（默认15条）
- 按confidence降序排序，优先返回高置信度facts
- 使用软删除避免物理删除的性能开销

### 9.3 缓存策略

- Memory加载结果缓存5分钟
- Facts列表缓存（按memory_id + 查询参数）
- 更新时清除相关缓存

## 10. 监控指标

- Memory更新频率
- Facts数量分布
- Facts平均置信度
- Memory加载耗时
- 缓存命中率

## 11. 验收标准

- ✅ 用户可以查看和更新自己的memory
- ✅ Agent可以有独立的memory
- ✅ Facts正确存储和查询
- ✅ Memory更新不阻塞对话
- ✅ 旧memory.json成功迁移
- ✅ 运行时正确加载memory
- ✅ Memory更新正确触发
- ✅ 软删除正常工作
- ✅ 性能满足要求（加载<100ms）
