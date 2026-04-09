# DeerFlow用户管理阶段5 - Skills表结构设计方案

## 1. 设计目标

将skills从纯文件系统扩展为用户级业务资源，支持：
- 用户可以创建、管理自己的skills
- Skills可以被多个agents复用
- Skills内容存储在数据库和OSS
- 运行时实时解析最新skill内容
- 保留系统级skills兼容性

## 2. 核心设计原则

1. **双层存储**: 数据库存储元数据和关系，OSS存储skill文件内容
2. **用户级隔离**: 每个用户拥有自己的skills，互不干扰
3. **实时解析**: 运行时总是使用最新的skill内容
4. **容错优先**: 缺失的skill不阻断执行
5. **系统兼容**: 保留 `skills/public/` 目录的系统级skills

## 3. 数据库表结构

### 3.1 user_skills表

用户自定义skill的主资源表。

```sql
CREATE TABLE user_skills (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    description TEXT,
    version VARCHAR(50),
    author VARCHAR(255),
    license VARCHAR(100),
    
    -- Skill内容
    skill_markdown TEXT NOT NULL,
    
    -- OSS存储路径
    oss_path VARCHAR(500),
    
    -- 状态
    enabled BOOLEAN NOT NULL DEFAULT true,
    sync_status VARCHAR(50) DEFAULT 'pending',  -- pending, syncing, synced, failed
    
    -- 元数据
    allowed_tools_json JSONB,
    metadata_json JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT uq_user_skills_user_name UNIQUE (user_id, name)
);

CREATE INDEX ix_user_skills_user_id ON user_skills(user_id);
CREATE INDEX ix_user_skills_enabled ON user_skills(enabled);
CREATE INDEX ix_user_skills_sync_status ON user_skills(sync_status);
```

**字段说明**:

- `name`: skill唯一标识（小写，连字符分隔）
- `display_name`: 显示名称
- `description`: skill描述
- `version`: 版本号（如 "1.0.0"）
- `author`: 作者
- `license`: 许可证
- `skill_markdown`: SKILL.md完整内容（包含frontmatter）
- `oss_path`: OSS存储路径（如 `users/{user_id}/skills/{name}/SKILL.md`）
- `enabled`: 是否启用
- `sync_status`: OSS同步状态
- `allowed_tools_json`: 允许的工具列表
- `metadata_json`: 其他元数据

### 3.2 agent_skills表（已存在，复用）

Agent与skill的绑定关系表。

```sql
-- 此表在阶段4已创建，这里复用
CREATE TABLE agent_skills (
    id BIGSERIAL PRIMARY KEY,
    agent_id BIGINT NOT NULL REFERENCES user_agents(id) ON DELETE CASCADE,
    skill_id BIGINT NOT NULL REFERENCES user_skills(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT uq_agent_skills_agent_skill UNIQUE (agent_id, skill_id)
);

CREATE INDEX ix_agent_skills_agent_id ON agent_skills(agent_id);
CREATE INDEX ix_agent_skills_skill_id ON agent_skills(skill_id);
```

**注意**: 阶段4中 `agent_skills` 存储的是 `skill_name` (VARCHAR)，需要迁移为 `skill_id` (BIGINT)。

### 3.3 skill_versions表（可选，用于版本历史）

如果需要保留skill的历史版本，可以添加此表。

```sql
CREATE TABLE skill_versions (
    id BIGSERIAL PRIMARY KEY,
    skill_id BIGINT NOT NULL REFERENCES user_skills(id) ON DELETE CASCADE,
    version VARCHAR(50) NOT NULL,
    skill_markdown TEXT NOT NULL,
    oss_path VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by BIGINT REFERENCES users(id),
    
    CONSTRAINT uq_skill_versions_skill_version UNIQUE (skill_id, version)
);

CREATE INDEX ix_skill_versions_skill_id ON skill_versions(skill_id);
```

## 4. 数据流设计

### 4.1 Skill创建流程

```
用户创建skill
  ↓
写入user_skills表 (sync_status=pending)
  ↓
异步任务: 上传到OSS
  ↓
更新sync_status=synced, oss_path
  ↓
Skill可用于运行时
```

### 4.2 Skill更新流程

```
用户更新skill内容
  ↓
更新user_skills表 (sync_status=pending)
  ↓
异步任务: 上传新内容到OSS
  ↓
更新sync_status=synced
  ↓
后续run自动使用最新内容
```

### 4.3 运行时加载流程

```
Thread启动
  ↓
读取thread.agent_id
  ↓
查询agent_skills获取skill_id列表
  ↓
查询user_skills获取skill详情
  ↓
检查sync_status=synced
  ↓
从OSS下载skill文件到运行时目录
  ↓
注入到agent系统提示
```

## 5. OSS存储结构

### 5.1 目录结构

```
oss://deerflow-skills/
├── system/                          # 系统级skills（只读）
│   ├── python-expert/
│   │   └── SKILL.md
│   └── git-helper/
│       └── SKILL.md
└── users/                           # 用户级skills
    ├── {user_id_1}/
    │   └── skills/
    │       ├── my-skill-1/
    │       │   └── SKILL.md
    │       └── my-skill-2/
    │           └── SKILL.md
    └── {user_id_2}/
        └── skills/
            └── custom-skill/
                └── SKILL.md
```

### 5.2 OSS路径规则

- 系统skill: `system/{skill_name}/SKILL.md`
- 用户skill: `users/{user_id}/skills/{skill_name}/SKILL.md`

## 6. Skill类型设计

### 6.1 系统Skill (System Skills)

- 存储位置: `skills/public/` 目录（文件系统）
- 管理方式: 代码仓库管理
- 可见性: 所有用户可见
- 修改权限: 仅管理员
- 运行时加载: 直接从文件系统读取

### 6.2 用户Skill (User Skills)

- 存储位置: `user_skills` 表 + OSS
- 管理方式: 用户通过API管理
- 可见性: 仅创建者可见
- 修改权限: 创建者
- 运行时加载: 从OSS下载到临时目录

### 6.3 共享Skill (Shared Skills) - 未来扩展

- 存储位置: `user_skills` 表 + OSS
- 管理方式: 用户创建，设置为公开
- 可见性: 所有用户可见（只读）
- 修改权限: 仅创建者
- 运行时加载: 从OSS下载

## 7. API设计

### 7.1 Skill CRUD

```
POST   /api/me/skills              创建skill
GET    /api/me/skills              列出用户的skills
GET    /api/me/skills/{skill_id}  获取skill详情
PUT    /api/me/skills/{skill_id}  更新skill
DELETE /api/me/skills/{skill_id}  删除skill
```

### 7.2 Agent-Skill绑定

```
GET /api/me/agents/{agent_id}/skills              获取agent绑定的skills
PUT /api/me/agents/{agent_id}/skills              更新agent的skills绑定
    Body: {"skill_ids": [1, 2, 3]}
```

### 7.3 Skill同步状态

```
GET /api/me/skills/{skill_id}/sync-status         查询同步状态
POST /api/me/skills/{skill_id}/sync               手动触发同步
```

## 8. 运行时集成

### 8.1 Skill解析器

**文件**: `backend/packages/harness/deerflow/skills/skill_resolver.py`

```python
class SkillResolver:
    """运行时skill解析器"""
    
    async def resolve_skills_for_agent(
        self,
        user_id: int,
        agent_id: int,
    ) -> list[ResolvedSkill]:
        """解析agent绑定的所有skills
        
        Returns:
            可用的skills列表，缺失的skills被过滤
        """
        # 1. 查询agent_skills获取skill_id列表
        # 2. 查询user_skills获取skill详情
        # 3. 检查sync_status=synced
        # 4. 从OSS下载到临时目录
        # 5. 返回可用的skills
        pass
```

### 8.2 OSS同步服务

**文件**: `backend/app/gateway/services/skill_sync_service.py`

```python
class SkillSyncService:
    """Skill OSS同步服务"""
    
    async def sync_skill_to_oss(self, skill_id: int) -> bool:
        """同步skill到OSS"""
        # 1. 读取user_skills记录
        # 2. 上传skill_markdown到OSS
        # 3. 更新oss_path和sync_status
        pass
    
    async def download_skill_from_oss(
        self,
        skill_id: int,
        target_dir: Path,
    ) -> Path:
        """从OSS下载skill到本地目录"""
        pass
```

## 9. 迁移策略

### 9.1 现有skills迁移

**步骤**:

1. 扫描 `skills/custom/` 目录
2. 为每个skill创建 `user_skills` 记录
3. 上传到OSS
4. 更新 `agent_skills` 表，将 `skill_name` 改为 `skill_id`

**迁移脚本**:

```python
# backend/scripts/migrate_skills_to_db.py
async def migrate_skills(user_id: int):
    skills_dir = Path("skills/custom")
    
    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        
        content = skill_md.read_text()
        
        # 创建数据库记录
        skill = await UserSkillRepository.create_skill(
            db=db,
            user_id=user_id,
            name=skill_dir.name,
            skill_markdown=content,
        )
        
        # 同步到OSS
        await SkillSyncService.sync_skill_to_oss(skill.id)
```

### 9.2 agent_skills表迁移

```sql
-- 添加新字段
ALTER TABLE agent_skills ADD COLUMN skill_id BIGINT REFERENCES user_skills(id) ON DELETE CASCADE;

-- 数据迁移（通过脚本）
-- 将 skill_name 映射到 skill_id

-- 删除旧字段
ALTER TABLE agent_skills DROP COLUMN skill_name;
```

## 10. 容错机制

### 10.1 Skill缺失处理

```python
def load_skills_with_fallback(skill_ids: list[int]) -> list[Skill]:
    """加载skills，缺失的跳过"""
    available_skills = []
    warnings = []
    
    for skill_id in skill_ids:
        try:
            skill = load_skill(skill_id)
            if skill.sync_status != 'synced':
                warnings.append(f"Skill {skill_id} not synced yet")
                continue
            available_skills.append(skill)
        except SkillNotFoundError:
            warnings.append(f"Skill {skill_id} not found")
        except OSSDownloadError:
            warnings.append(f"Skill {skill_id} OSS download failed")
    
    if warnings:
        logger.warning(f"Skill loading warnings: {warnings}")
    
    return available_skills
```

### 10.2 OSS同步失败处理

- 同步失败时，`sync_status` 设为 `failed`
- 提供手动重试接口
- 运行时跳过未同步的skills
- 记录详细错误日志

## 11. 性能优化

### 11.1 缓存策略

- **数据库查询缓存**: 缓存agent的skills列表（5分钟）
- **OSS下载缓存**: 本地缓存已下载的skills（按skill_id + updated_at）
- **运行时缓存**: 同一thread内复用已加载的skills

### 11.2 批量操作

- 批量查询skills: `SELECT * FROM user_skills WHERE id IN (...)`
- 批量下载OSS: 并发下载多个skills
- 批量同步: 后台任务批量处理待同步的skills

## 12. 安全考虑

### 12.1 权限控制

- 用户只能访问自己的skills
- Agent绑定skill时验证skill归属
- OSS路径包含user_id，防止越权访问

### 12.2 内容安全

- Skill内容大小限制（如100KB）
- 禁止上传可执行文件
- Skill markdown内容过滤（防止XSS）

## 13. 监控指标

- Skill创建/更新/删除数量
- OSS同步成功率
- OSS同步耗时
- Skill加载失败率
- 缓存命中率

## 14. 验收标准

- ✅ 用户可以创建、查询、更新、删除自己的skills
- ✅ Skills自动同步到OSS
- ✅ Agent可以绑定用户skills
- ✅ 运行时正确加载最新skill内容
- ✅ 缺失的skills不阻断执行
- ✅ 系统skills继续工作
- ✅ Skill更新后立即生效
- ✅ OSS同步失败有重试机制
