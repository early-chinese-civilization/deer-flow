# Thread API 整理与 OSS 文件上传集成方案

## 背景

DeerFlow 项目目前拥有完善的线程管理系统,采用双存储架构(PostgreSQL + LangGraph Store),以及基于本地文件系统的文件上传功能。本方案旨在:

1. **整理 Thread 接口文档** - 当前的接口结构合理,需要清晰的文档说明
2. **集成阿里云 OSS** - 为文件上传添加对象存储支持,使用签名 URL 访问

### 当前状态

- Thread API 分布在 3 个路由模块:
  - `threads.py` - 线程 CRUD 操作
  - `thread_runs.py` - 线程执行操作
  - `uploads.py` - 文件上传操作
- 文件上传保存到本地文件系统: `.deer-flow/threads/{thread_id}/user-data/uploads/`
- 上传系统提供线程级隔离,支持自动文档转换(PDF、PPT、Excel、Word → markdown)
- 文件会同步到沙箱环境,并为非本地沙箱设置可写权限

### 目标

添加阿里云 OSS 存储后端,支持签名 URL 访问,同时保持与本地存储的向后兼容性。

---

## Thread API 接口文档

### 1. Thread CRUD 接口 (`/api/threads`)

**基础路径**: `/api/threads`

#### 1.1 创建线程
```
POST /api/threads
```
**请求体**:
```json
{
  "thread_id": "optional-custom-id",  // 可选,不提供则自动生成
  "metadata": {}                       // 可选,初始元数据
}
```

#### 1.2 搜索线程
```
POST /api/threads/search
```
**请求体**:
```json
{
  "metadata": {},           // 元数据过滤(精确匹配)
  "status": "idle",         // 可选,按状态过滤
  "limit": 100,             // 最大结果数(1-1000)
  "offset": 0               // 分页偏移
}
```

#### 1.3 获取线程详情
```
GET /api/threads/{thread_id}
```

#### 1.4 更新线程元数据
```
PATCH /api/threads/{thread_id}
```
**请求体**:
```json
{
  "metadata": {}  // 要合并的元数据
}
```

#### 1.5 删除线程
```
DELETE /api/threads/{thread_id}
```
删除 LangGraph 线程后清理本地 `.deer-flow/threads/{thread_id}` 目录。

#### 1.6 获取线程状态
```
GET /api/threads/{thread_id}/state
```
返回当前通道值、检查点信息、待执行任务等。

#### 1.7 更新线程状态
```
POST /api/threads/{thread_id}/state
```
**请求体**:
```json
{
  "values": {},              // 可选,要合并的通道值
  "checkpoint_id": "..."     // 可选,从指定检查点分支
}
```

#### 1.8 获取线程历史
```
POST /api/threads/{thread_id}/history
```
返回线程的检查点历史记录。

---

### 2. Thread 执行接口 (`/api/threads/{thread_id}/runs`)

**基础路径**: `/api/threads/{thread_id}/runs`

#### 2.1 创建运行
```
POST /api/threads/{thread_id}/runs
```

#### 2.2 流式运行
```
POST /api/threads/{thread_id}/runs/stream
```
返回 SSE 事件流,实时推送执行状态。

#### 2.3 等待运行完成
```
POST /api/threads/{thread_id}/runs/wait
```
阻塞直到运行完成,返回最终结果。

#### 2.4 列出运行记录
```
GET /api/threads/{thread_id}/runs
```

#### 2.5 获取运行详情
```
GET /api/threads/{thread_id}/runs/{run_id}
```

#### 2.6 取消运行
```
POST /api/threads/{thread_id}/runs/{run_id}/cancel
```

#### 2.7 加入运行
```
GET /api/threads/{thread_id}/runs/{run_id}/join
```
等待指定运行完成。

---

### 3. 文件上传接口

**基础路径**: `/api/workspaces/{workspace_id}/uploads`

#### 3.1 上传文件
```
POST /api/workspaces/{workspace_id}/uploads
```
**请求**: `multipart/form-data`
- 支持多文件上传
- 自动转换文档格式(PDF、PPT、Excel、Word → markdown)
- 文件保存到工作区 OSS 目录
- 同步到沙箱环境

**响应**:
```json
{
  "success": true,
  "files": [
    {
      "filename": "document.pdf",
      "size": "1024",
      "path": "workspaces/{workspace_id}/document.pdf",
      "url": "https://oss.example.com/...",  // OSS 签名 URL
      "modified_at": "2026-04-13T14:00:00Z"
    }
  ],
  "message": "Successfully uploaded 1 file(s)"
}
```

#### 3.2 列出已上传文件
```
GET /api/workspaces/{workspace_id}/uploads/list
```

**响应**:
```json
{
  "files": [
    {
      "filename": "document.pdf",
      "size": "1024",
      "url": "https://oss.example.com/...",  // OSS 签名 URL
      "modified_at": "2026-04-13T14:00:00Z"
    }
  ],
  "count": 1
}
```

#### 3.3 删除文件
```
DELETE /api/workspaces/{workspace_id}/uploads/{filename}
```

#### 3.4 刷新单个文件签名 URL
```
POST /api/workspaces/{workspace_id}/files/url
```
**请求体**:
```json
{
  "filename": "文档.pdf"
}
```

**响应**:
```json
{
  "url": "https://oss.example.com/...",
  "expires_at": "2026-04-13T15:00:00Z"
}
```

**说明**:
- 当 OSS 签名 URL 过期(默认 1 小时)时,客户端调用此接口刷新单个文件的签名 URL
- 使用 POST 请求避免 URL 中中文文件名的编码问题

---

### 架构说明

#### 双存储架构
1. **PostgreSQL** (通过 SQLAlchemy)
   - 存储规范的业务记录
   - 用户所有权管理
   - 线程基本信息(thread_id, user_id, agent_id, workspace_id, title, status, metadata)

2. **LangGraph Store**
   - 运行时元数据
   - 状态同步
   - ThreadRecord 包含: thread_id, status, created_at, updated_at, metadata, values

#### 线程生命周期
1. 创建线程 → 在 PostgreSQL 和 Store 中创建记录
2. 执行运行 → 更新 Store 中的状态
3. 上传文件 → 保存到线程隔离目录
4. 删除线程 → 清理数据库记录和本地文件

---

## OSS 集成实施方案

### 1. 创建存储后端接口

**文件**: `backend/packages/harness/deerflow/uploads/storage.py`

定义抽象的 `StorageBackend` 协议:

```python
from typing import Protocol

class StorageBackend(Protocol):
    """存储后端抽象接口"""
    
    def upload_file(self, thread_id: str, filename: str, content: bytes) -> str:
        """
        上传文件到存储
        
        Args:
            thread_id: 线程 ID
            filename: 文件名
            content: 文件内容
            
        Returns:
            存储路径或对象键
        """
        ...
    
    def get_file_url(self, thread_id: str, filename: str, expires_in: int = 3600) -> str:
        """
        获取文件访问 URL
        
        Args:
            thread_id: 线程 ID
            filename: 文件名
            expires_in: URL 过期时间(秒),默认 1 小时
            
        Returns:
            文件访问 URL(本地存储返回 artifact URL,OSS 返回签名 URL)
        """
        ...
    
    def delete_file(self, thread_id: str, filename: str) -> None:
        """删除文件"""
        ...
    
    def file_exists(self, thread_id: str, filename: str) -> bool:
        """检查文件是否存在"""
        ...
```

---

### 2. 实现本地存储后端

**文件**: `backend/packages/harness/deerflow/uploads/local_storage.py`

```python
from pathlib import Path
from deerflow.uploads.manager import (
    ensure_uploads_dir,
    get_uploads_dir,
    upload_artifact_url,
)

class LocalStorageBackend:
    """本地文件系统存储后端"""
    
    def upload_file(self, thread_id: str, filename: str, content: bytes) -> str:
        """保存文件到本地文件系统"""
        uploads_dir = ensure_uploads_dir(thread_id)
        file_path = uploads_dir / filename
        file_path.write_bytes(content)
        return str(file_path)
    
    def get_file_url(self, thread_id: str, filename: str, expires_in: int = 3600) -> str:
        """返回 artifact URL"""
        return upload_artifact_url(thread_id, filename)
    
    def delete_file(self, thread_id: str, filename: str) -> None:
        """删除本地文件"""
        uploads_dir = get_uploads_dir(thread_id)
        file_path = uploads_dir / filename
        if file_path.exists():
            file_path.unlink()
    
    def file_exists(self, thread_id: str, filename: str) -> bool:
        """检查文件是否存在"""
        uploads_dir = get_uploads_dir(thread_id)
        return (uploads_dir / filename).exists()
```

---

### 3. 实现阿里云 OSS 存储后端

**文件**: `backend/packages/harness/deerflow/uploads/oss_storage.py`

```python
import oss2
from typing import Optional

class OssStorageBackend:
    """阿里云 OSS 存储后端"""
    
    def __init__(
        self,
        endpoint: str,
        access_key_id: str,
        access_key_secret: str,
        bucket_name: str,
        signed_url_expires: int = 3600,
    ):
        """
        初始化 OSS 客户端
        
        Args:
            endpoint: OSS 端点,如 oss-cn-hangzhou.aliyuncs.com
            access_key_id: 访问密钥 ID
            access_key_secret: 访问密钥
            bucket_name: 存储桶名称
            signed_url_expires: 签名 URL 默认过期时间(秒)
        """
        auth = oss2.Auth(access_key_id, access_key_secret)
        self.bucket = oss2.Bucket(auth, endpoint, bucket_name)
        self.signed_url_expires = signed_url_expires
    
    def _get_object_key(self, thread_id: str, filename: str) -> str:
        """生成对象键,保持线程隔离"""
        return f"threads/{thread_id}/uploads/{filename}"
    
    def upload_file(self, thread_id: str, filename: str, content: bytes) -> str:
        """上传文件到 OSS"""
        object_key = self._get_object_key(thread_id, filename)
        self.bucket.put_object(object_key, content)
        return object_key
    
    def get_file_url(self, thread_id: str, filename: str, expires_in: int = None) -> str:
        """生成签名 URL"""
        if expires_in is None:
            expires_in = self.signed_url_expires
        object_key = self._get_object_key(thread_id, filename)
        return self.bucket.sign_url('GET', object_key, expires_in)
    
    def delete_file(self, thread_id: str, filename: str) -> None:
        """从 OSS 删除文件"""
        object_key = self._get_object_key(thread_id, filename)
        self.bucket.delete_object(object_key)
    
    def file_exists(self, thread_id: str, filename: str) -> bool:
        """检查文件是否存在"""
        object_key = self._get_object_key(thread_id, filename)
        return self.bucket.object_exists(object_key)
```

---

### 4. 配置管理

#### 4.1 更新 `config.yaml`

在配置文件中添加上传配置节:

```yaml
# 文件上传配置
uploads:
  # 存储后端类型: "local" 或 "oss"
  storage_backend: "local"
  
  # 阿里云 OSS 配置(当 storage_backend 为 "oss" 时使用)
  oss:
    endpoint: "$OSS_ENDPOINT"                    # 如: oss-cn-hangzhou.aliyuncs.com
    access_key_id: "$OSS_ACCESS_KEY_ID"
    access_key_secret: "$OSS_ACCESS_KEY_SECRET"
    bucket_name: "$OSS_BUCKET_NAME"
    signed_url_expires: 3600                     # 签名 URL 过期时间(秒)
```

#### 4.2 添加配置类

**文件**: `backend/packages/harness/deerflow/config/app.py`

```python
from pydantic import BaseModel, Field

class OssConfig(BaseModel):
    """阿里云 OSS 配置"""
    endpoint: str = Field(..., description="OSS 端点")
    access_key_id: str = Field(..., description="访问密钥 ID")
    access_key_secret: str = Field(..., description="访问密钥")
    bucket_name: str = Field(..., description="存储桶名称")
    signed_url_expires: int = Field(3600, description="签名 URL 过期时间(秒)")

class UploadsConfig(BaseModel):
    """文件上传配置"""
    storage_backend: str = Field("local", description="存储后端类型: local 或 oss")
    oss: OssConfig | None = Field(None, description="OSS 配置")

# 在 AppConfig 中添加
class AppConfig(BaseModel):
    # ... 其他配置 ...
    uploads: UploadsConfig = Field(default_factory=UploadsConfig)
```

---

### 5. 更新上传路由

**文件**: `backend/app/gateway/routers/uploads.py`

主要修改:

1. **添加存储后端工厂函数**:
```python
from deerflow.config import get_app_config
from deerflow.uploads.local_storage import LocalStorageBackend
from deerflow.uploads.oss_storage import OssStorageBackend

def get_storage_backend():
    """根据配置创建存储后端"""
    config = get_app_config()
    
    if config.uploads.storage_backend == "oss":
        if not config.uploads.oss:
            raise ValueError("OSS backend selected but oss config is missing")
        return OssStorageBackend(
            endpoint=config.uploads.oss.endpoint,
            access_key_id=config.uploads.oss.access_key_id,
            access_key_secret=config.uploads.oss.access_key_secret,
            bucket_name=config.uploads.oss.bucket_name,
            signed_url_expires=config.uploads.oss.signed_url_expires,
        )
    else:
        return LocalStorageBackend()
```

2. **修改 `upload_files` 端点**:
```python
@router.post("", response_model=UploadResponse)
async def upload_files(
    thread_id: str,
    files: list[UploadFile] = File(...),
) -> UploadResponse:
    """上传多个文件到线程的上传目录"""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    storage = get_storage_backend()
    uploads_dir = ensure_uploads_dir(thread_id)  # 本地副本,用于沙箱访问
    sandbox_uploads = get_paths().sandbox_uploads_dir(thread_id)
    uploaded_files = []
    
    # ... 沙箱获取代码 ...
    
    for file in files:
        if not file.filename:
            continue
        
        safe_filename = normalize_filename(file.filename)
        content = await file.read()
        
        # 1. 上传到存储后端(OSS 或本地)
        storage.upload_file(thread_id, safe_filename, content)
        
        # 2. 保存本地副本(用于沙箱访问)
        file_path = uploads_dir / safe_filename
        file_path.write_bytes(content)
        
        # 3. 同步到沙箱
        virtual_path = upload_virtual_path(safe_filename)
        if sandbox_id != "local":
            _make_file_sandbox_writable(file_path)
            sandbox.update_file(virtual_path, content)
        
        # 4. 生成文件信息(使用存储后端的 URL)
        file_info = {
            "filename": safe_filename,
            "size": str(len(content)),
            "path": str(sandbox_uploads / safe_filename),
            "virtual_path": virtual_path,
            "artifact_url": storage.get_file_url(thread_id, safe_filename),  # OSS 签名 URL 或本地 artifact URL
        }
        
        # 5. 文档转换(如果需要)
        # ... 转换代码 ...
        
        uploaded_files.append(file_info)
    
    return UploadResponse(
        success=True,
        files=uploaded_files,
        message=f"Successfully uploaded {len(uploaded_files)} file(s)",
    )
```

3. **修改 `list_uploaded_files` 端点**:
```python
@router.get("/list", response_model=dict)
async def list_uploaded_files(thread_id: str) -> dict:
    """列出线程上传目录中的所有文件"""
    storage = get_storage_backend()
    uploads_dir = get_uploads_dir(thread_id)
    result = list_files_in_dir(uploads_dir)
    
    # 为每个文件生成 URL
    sandbox_uploads = get_paths().sandbox_uploads_dir(thread_id)
    for f in result["files"]:
        filename = f["filename"]
        f["path"] = str(sandbox_uploads / filename)
        f["virtual_path"] = upload_virtual_path(filename)
        f["artifact_url"] = storage.get_file_url(thread_id, filename)
    
    return result
```

4. **修改 `delete_uploaded_file` 端点**:
```python
@router.delete("/{filename}")
async def delete_uploaded_file(thread_id: str, filename: str) -> dict:
    """从线程上传目录删除文件"""
    storage = get_storage_backend()
    uploads_dir = get_uploads_dir(thread_id)
    
    try:
        # 1. 从存储后端删除
        storage.delete_file(thread_id, filename)
        
        # 2. 删除本地副本
        result = delete_file_safe(uploads_dir, filename, convertible_extensions=CONVERTIBLE_EXTENSIONS)
        
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    except Exception as e:
        logger.error(f"Failed to delete {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete {filename}: {str(e)}")
```

---

### 6. 添加依赖

**文件**: `backend/packages/harness/pyproject.toml`

```toml
[project]
dependencies = [
    # ... 现有依赖 ...
    "oss2>=2.18.0",  # 阿里云 OSS Python SDK
]
```

安装命令:
```bash
cd backend
uv add oss2
```

---

## 测试验证

### 1. 本地存储模式测试(向后兼容性)

```bash
# 配置
storage_backend: "local"

# 测试步骤
1. 上传文件: POST /api/workspaces/{workspace_id}/uploads
2. 验证文件保存到 .deer-flow/threads/{id}/user-data/uploads/
3. 验证返回的 artifact_url 可访问
4. 验证 Agent 可通过沙箱访问文件
5. 测试文件列表: GET /api/workspaces/{workspace_id}/uploads/list
6. 测试文件删除: DELETE /api/workspaces/{workspace_id}/uploads/{filename}
```

### 2. OSS 存储模式测试

```bash
# 配置
storage_backend: "oss"
oss:
  endpoint: "oss-cn-hangzhou.aliyuncs.com"
  access_key_id: "your-key-id"
  access_key_secret: "your-key-secret"
  bucket_name: "your-bucket"
  signed_url_expires: 3600

# 测试步骤
1. 上传文件,验证文件出现在 OSS 存储桶中
2. 验证返回的签名 URL 可访问
3. 验证本地副本存在(用于沙箱)
4. 测试文件删除(同时删除 OSS 和本地)
5. 验证签名 URL 在配置的时间后过期
```

### 3. 集成测试

- **线程隔离**: 不同线程的文件互不干扰
- **文档转换**: PDF → markdown 转换仍然正常工作
- **沙箱同步**: 两种存储模式下沙箱都能访问文件
- **并发上传**: 多文件同时上传
- **错误处理**: OSS 连接失败、权限错误等异常情况

---

## 关键设计决策

### 1. 存储后端策略
- **适配器模式**: 使用 `StorageBackend` 协议定义统一接口
- **配置驱动**: 通过 `config.yaml` 选择存储后端
- **默认本地**: 向后兼容,默认使用本地存储

### 2. OSS 提供商
- **仅支持阿里云 OSS**: 使用 `oss2` Python SDK
- **可扩展设计**: 接口设计允许未来添加其他提供商(AWS S3、MinIO 等)

### 3. 文件访问方式
- **签名 URL**: 1 小时过期(可配置)
- **私有存储桶**: 推荐使用私有存储桶以提高安全性
- **临时访问**: 每次请求生成新的签名 URL

### 4. 双存储方案
- **OSS**: 持久化云存储,通过签名 URL 访问
- **本地副本**: Agent 沙箱访问所需(必需)
- **上传流程**: 保存到 OSS → 下载到本地 → 同步到沙箱

### 5. 线程隔离
- **OSS 对象键**: `threads/{thread_id}/uploads/{filename}`
- **安全模型**: 保持现有的线程级安全隔离

### 6. 向后兼容性
- **本地存储模式不变**: 现有功能完全保留
- **API 响应格式不变**: 只是 URL 内容不同(artifact URL vs 签名 URL)
- **配置默认值**: 默认使用本地存储

---

## 实施步骤总结

1. ✅ **文档整理**: 创建 Thread API 完整文档
2. ⬜ **创建存储接口**: 定义 `StorageBackend` 协议
3. ⬜ **实现本地后端**: 封装现有本地存储逻辑
4. ⬜ **实现 OSS 后端**: 集成阿里云 OSS SDK
5. ⬜ **添加配置**: 更新 `config.yaml` 和配置类
6. ⬜ **更新路由**: 修改上传端点使用存储后端
7. ⬜ **添加依赖**: 安装 `oss2` 包
8. ⬜ **测试验证**: 本地模式、OSS 模式、集成测试

---

## 相关文件清单

### 新增文件
- `backend/packages/harness/deerflow/uploads/storage.py` - 存储后端接口
- `backend/packages/harness/deerflow/uploads/local_storage.py` - 本地存储实现
- `backend/packages/harness/deerflow/uploads/oss_storage.py` - OSS 存储实现

### 修改文件
- `backend/app/gateway/routers/uploads.py` - 上传路由
- `backend/packages/harness/deerflow/config/app.py` - 配置类
- `backend/packages/harness/pyproject.toml` - 依赖管理
- `config.yaml` - 应用配置

### 文档文件
- `backend/docs/THREAD_API.md` - Thread API 完整文档(待创建)
- `THREAD_API_AND_OSS_PLAN.md` - 本实施方案文档
