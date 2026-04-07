# Windows PostgreSQL Checkpointer 修复

## 问题描述

在 Windows 平台上使用 PostgreSQL checkpointer 时，LangGraph 启动失败并报错：

```
psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode. 
Please use a compatible event loop, for instance by running 
'asyncio.run(..., loop_factory=asyncio.SelectorEventLoop(selectors.SelectSelector()))'
```

## 根本原因

- Python 3.8+ 在 Windows 上默认使用 `ProactorEventLoop`
- `psycopg` (PostgreSQL 异步驱动) 要求使用 `SelectorEventLoop`
- uvicorn 使用 `asyncio.run()` 创建事件循环，需要在调用前 patch

## 解决方案 ✅

使用 `scripts/langgraph_windows.py` 启动脚本，该脚本通过 monkey patch `asyncio.run()` 强制使用 `SelectorEventLoop`。

### 实现原理

```python
# backend/scripts/langgraph_windows.py
def _patched_run(main, *, debug=False, loop_factory=None):
    # 忽略 loop_factory 参数，强制使用 SelectorEventLoop
    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(main)

# Monkey patch asyncio.run
asyncio.run = _patched_run
```

### 使用方法

启动脚本 `scripts/serve.sh` 已自动检测 Windows 平台并使用修复后的启动器：

```bash
# Windows 上自动使用
uv run python scripts/langgraph_windows.py dev --no-browser --allow-blocking

# 或直接运行
make dev
```

## 验证

```bash
# 测试 PostgreSQL checkpointer
cd backend
uv run python scripts/langgraph_windows.py dev --no-browser --allow-blocking

# 输出:
# Patched asyncio.run() to use SelectorEventLoop on Windows for psycopg compatibility
# Checkpointer: using AsyncPostgresSaver
# Application startup complete. Uvicorn running on http://127.0.0.1:2024
```

## 配置

确保 `config.yaml` 中配置了 PostgreSQL checkpointer：

```yaml
checkpointer:
  type: postgres
  connection_string: $DEER_FLOW_CHECKPOINTER_DATABASE_URL
```

并在 `.env` 中设置连接字符串：

```bash
DEER_FLOW_CHECKPOINTER_DATABASE_URL=postgresql://user:password@localhost:5432/checkpointer_db
```

## 相关文件

- `backend/scripts/langgraph_windows.py` - Windows 启动包装脚本（monkey patch asyncio.run）
- `backend/packages/harness/deerflow/agents/checkpointer/async_provider.py` - Checkpointer 工厂
- `scripts/serve.sh` - 服务启动脚本（已添加 Windows 检测逻辑）

## 技术细节

### 尝试的方案

1. ❌ 在 checkpointer 初始化时设置策略 - 太晚，事件循环已创建
2. ❌ 在脚本开头设置策略 - uvicorn 会创建新的事件循环
3. ❌ Monkey patch `asyncio.new_event_loop()` - uvicorn 使用 `asyncio.run()`
4. ✅ Monkey patch `asyncio.run()` - 成功拦截 uvicorn 的事件循环创建

### 关键点

- 必须在导入 `langgraph_cli` 之前 patch `asyncio.run()`
- 必须接受 `loop_factory` 参数（uvicorn 会传递）
- 必须忽略 `loop_factory` 参数，强制使用 `SelectorEventLoop`

## 更新日期

2026-04-06 - 问题已解决
