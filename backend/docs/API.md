# API Reference

This document provides a complete reference for the DeerFlow backend APIs.

## Overview

DeerFlow backend exposes two sets of APIs:

1. **LangGraph API** - Agent interactions, threads, and streaming (`/api/langgraph/*`)
2. **Gateway API** - Models, MCP, skills, uploads, and artifacts (`/api/*`)

All APIs are accessed through the Nginx reverse proxy at port 2026.

## LangGraph API

Base URL: `/api/langgraph`

The LangGraph API is provided by the Gateway-backed LangGraph runtime and follows the LangGraph SDK conventions.

### Threads

#### Create Thread

```http
POST /api/langgraph/threads
Content-Type: application/json
```

**Request Body:**
```json
{
  "metadata": {}
}
```

**Response:**
```json
{
  "thread_id": "abc123",
  "created_at": "2024-01-15T10:30:00Z",
  "metadata": {}
}
```

#### Get Thread State

```http
GET /api/langgraph/threads/{thread_id}/state
```

**Response:**
```json
{
  "values": {
    "messages": [...],
    "sandbox": {...},
    "artifacts": [...],
    "thread_data": {...},
    "title": "Conversation Title"
  },
  "next": [],
  "config": {...}
}
```

### Runs

#### Create Run

Execute the agent with input.

```http
POST /api/langgraph/threads/{thread_id}/runs
Content-Type: application/json
```

**Request Body:**
```json
{
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "Hello, can you help me?"
      }
    ]
  },
  "config": {
    "configurable": {
      "model_name": "gpt-4",
      "thinking_enabled": false,
      "is_plan_mode": false
    }
  },
  "stream_mode": ["values", "messages-tuple", "custom"]
}
```

**Stream Mode Compatibility:**
- Use: `values`, `messages-tuple`, `custom`, `updates`, `events`, `debug`, `tasks`, `checkpoints`
- Do not use: `tools` (deprecated/invalid in current `langgraph-api` and will trigger schema validation errors)

**Configurable Options:**
- `model_name` (string): Override the default model
- `thinking_enabled` (boolean): Enable extended thinking for supported models
- `is_plan_mode` (boolean): Enable TodoList middleware for task tracking

**Response:** Server-Sent Events (SSE) stream

```
event: values
data: {"messages": [...], "title": "..."}

event: messages
data: {"content": "Hello! I'd be happy to help.", "role": "assistant"}

event: end
data: {}
```

#### Get Run History

```http
GET /api/langgraph/threads/{thread_id}/runs
```

**Response:**
```json
{
  "runs": [
    {
      "run_id": "run123",
      "status": "success",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### Stream Run

Stream responses in real-time.

```http
POST /api/langgraph/threads/{thread_id}/runs/stream
Content-Type: application/json
```

Same request body as Create Run. Returns SSE stream.

---

## Gateway API

Base URL: `/api`

### Models

#### List Models

Get all available LLM models from configuration.

```http
GET /api/models
```

**Response:**
```json
{
  "models": [
    {
      "name": "gpt-4",
      "display_name": "GPT-4",
      "supports_thinking": false,
      "supports_vision": true
    },
    {
      "name": "claude-3-opus",
      "display_name": "Claude 3 Opus",
      "supports_thinking": false,
      "supports_vision": true
    },
    {
      "name": "deepseek-v3",
      "display_name": "DeepSeek V3",
      "supports_thinking": true,
      "supports_vision": false
    }
  ]
}
```

#### Get Model Details

```http
GET /api/models/{model_name}
```

**Response:**
```json
{
  "name": "gpt-4",
  "display_name": "GPT-4",
  "model": "gpt-4",
  "max_tokens": 4096,
  "supports_thinking": false,
  "supports_vision": true
}
```

### MCP Configuration

#### Get MCP Config

Get current MCP server configurations.

```http
GET /api/mcp/config
```

**Response:**
```json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "***"
      },
      "description": "GitHub operations"
    },
    "filesystem": {
      "enabled": false,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"],
      "description": "File system access"
    }
  }
}
```

#### Update MCP Config

Update MCP server configurations.

```http
PUT /api/mcp/config
Content-Type: application/json
```

**Request Body:**
```json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "$GITHUB_TOKEN"
      },
      "description": "GitHub operations"
    }
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "MCP configuration updated"
}
```

### Skills

Skills use two related persistence concepts:

- `skills` rows are the current visible/installable copies: user-owned custom skills and public latest catalog skills.
- `skill_releases` rows are immutable publish records. They track which publish produced a public latest skill copy.

`package_version` comes from `SKILL.md` frontmatter `version` and is optional, non-unique, and not SemVer-enforced. If present, it must be a string. `release_version` is system-generated and immutable.

#### Skill Response Shape

Skill responses include version metadata when available:

```json
{
  "name": "pdf-processing",
  "description": "Handle PDF documents efficiently",
  "category": "public",
  "enabled": true,
  "license": "MIT",
  "version": "1.2.0",
  "package_version": "1.2.0",
  "release_version": "rel_9b5e0b9a2b6d4e7a9f1c2d3e4f5a6b7c",
  "release_status": "published",
  "published_at": "2026-04-28T08:00:00+00:00",
  "owner_user_id": 42,
  "owner_display_name": "Alice"
}
```

For legacy public skills without a release record, `version`, `package_version`, `release_version`, `release_status`, and `published_at` are `null`. For custom skills, `package_version` is read from that custom copy's `SKILL.md` when available.

#### List Skills

Get the current user's custom skills plus public latest skills.

```http
GET /api/skills
```

**Response:**
```json
{
  "skills": [
    {
      "name": "pdf-processing",
      "description": "Handle PDF documents efficiently",
      "category": "public",
      "enabled": true,
      "license": "MIT",
      "version": "1.2.0",
      "package_version": "1.2.0",
      "release_version": "rel_9b5e0b9a2b6d4e7a9f1c2d3e4f5a6b7c",
      "release_status": "published",
      "published_at": "2026-04-28T08:00:00+00:00",
      "owner_user_id": 42,
      "owner_display_name": "Alice"
    }
  ]
}
```

#### Get Skill Details

```http
GET /api/skills/{skill_name}
```

The Gateway prefers the current user's custom copy when one exists; otherwise it returns public latest. The response uses the same `SkillResponse` shape as list.

#### Check Skill Upload

Check whether an uploaded `.skill` ZIP would conflict with the current user's custom skill names.

```http
POST /api/skills/check-upload
Content-Type: multipart/form-data
```

**Request Body:**
- `file`: `.skill` / ZIP archive containing exactly one skill folder with `SKILL.md`

#### Upload Skills

Upload one or more custom skill ZIP archives.

```http
POST /api/skills/uploads
Content-Type: multipart/form-data
```

**Request Body:**
- `files`: one or more ZIP archives
- `overwrite_names`: optional repeated form field naming custom skills that may be overwritten

Gateway upload validation accepts standard optional frontmatter keys (`version`, `author`, `compatibility`) and rejects non-string `version` values with a 400 detail.

#### Publish Custom Skill

Publish the current user's custom skill as public latest.

```http
POST /api/skills/{skill_name}/publish
```

Publish flow:
1. Validate the current user's custom skill and parse `SKILL.md` metadata.
2. Copy the custom skill artifact to the public latest storage path.
3. Soft-delete previous active public rows for the same skill name.
4. Create the new public latest `skills` row.
5. Create a `skill_releases` record with generated `release_version` and optional `package_version`.
6. Commit once and return the version-aware `SkillResponse`.

User-visible behavior:
- Missing custom skill returns 404.
- Invalid metadata returns 400 with actionable detail.
- System failures return a generic 500 detail. Publish phase logs include skill name, publisher user ID, phase, release_version when known, and sanitized error type/message.
- In-process failures before commit roll back DB changes and restore the previous public artifact directory when possible.

#### Check Skill Download

Check whether downloading public latest would overwrite the current user's custom skill.

```http
POST /api/skills/{skill_name}/check-download
Content-Type: application/json
```

**Request Body:**
```json
{
  "owner_user_id": null
}
```

`owner_user_id` is accepted for compatibility but public lookup uses the skill name.

#### Download Public Skill

Copy public latest into the current user's custom skills.

```http
POST /api/skills/{skill_name}/download
Content-Type: application/json
```

**Request Body:**
```json
{
  "owner_user_id": null,
  "overwrite": false
}
```

If a same-name custom skill exists and `overwrite` is false, the endpoint returns 409. On success, the response includes the source public latest release/package metadata when available.

#### Update Skill

```http
PUT /api/skills/{skill_name}
Content-Type: application/json
```

**Request Body:**
```json
{
  "enabled": true
}
```

For user-owned custom skills, this refreshes the current skill row. Public skills are read-only.

#### Delete Skill

```http
DELETE /api/skills/{skill_name}
```

Soft-deletes the current user's custom skill. Public skills cannot be deleted, and custom skills currently bound to an agent return 409.

#### Install Skill

Install a skill from a `.skill` file already present in a thread's user-data path.

```http
POST /api/skills/install
Content-Type: application/json
```

**Request Body:**
```json
{
  "thread_id": "abc123",
  "path": "mnt/user-data/outputs/my-skill.skill"
}
```

**Response:**
```json
{
  "success": true,
  "skill_name": "my-skill",
  "message": "Skill installed successfully"
}
```

### File Uploads

#### Upload Files

Upload one or more files to a thread.

```http
POST /api/threads/{thread_id}/uploads
Content-Type: multipart/form-data
```

**Request Body:**
- `files`: One or more files to upload

**Response:**
```json
{
  "success": true,
  "files": [
    {
      "filename": "document.pdf",
      "size": 1234567,
      "path": ".deer-flow/threads/abc123/user-data/uploads/document.pdf",
      "virtual_path": "/mnt/user-data/uploads/document.pdf",
      "artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf",
      "markdown_file": "document.md",
      "markdown_path": ".deer-flow/threads/abc123/user-data/uploads/document.md",
      "markdown_virtual_path": "/mnt/user-data/uploads/document.md",
      "markdown_artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.md"
    }
  ],
  "message": "Successfully uploaded 1 file(s)"
}
```

**Supported Document Formats** (auto-converted to Markdown):
- PDF (`.pdf`)
- PowerPoint (`.ppt`, `.pptx`)
- Excel (`.xls`, `.xlsx`)
- Word (`.doc`, `.docx`)

#### List Uploaded Files

```http
GET /api/threads/{thread_id}/uploads/list
```

**Response:**
```json
{
  "files": [
    {
      "filename": "document.pdf",
      "size": 1234567,
      "path": ".deer-flow/threads/abc123/user-data/uploads/document.pdf",
      "virtual_path": "/mnt/user-data/uploads/document.pdf",
      "artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf",
      "extension": ".pdf",
      "modified": 1705997600.0
    }
  ],
  "count": 1
}
```

#### Delete File

```http
DELETE /api/threads/{thread_id}/uploads/{filename}
```

**Response:**
```json
{
  "success": true,
  "message": "Deleted document.pdf"
}
```

### Thread Cleanup

Remove DeerFlow-managed local thread files under `.deer-flow/threads/{thread_id}` after the LangGraph thread itself has been deleted.

```http
DELETE /api/threads/{thread_id}
```

**Response:**
```json
{
  "success": true,
  "message": "Deleted local thread data for abc123"
}
```

**Error behavior:**
- `422` for invalid thread IDs
- `500` returns a generic `{"detail": "Failed to delete local thread data."}` response while full exception details stay in server logs

### Artifacts

#### Get Artifact

Download or view an artifact generated by the agent.

```http
GET /api/threads/{thread_id}/artifacts/{path}
```

**Path Examples:**
- `/api/threads/abc123/artifacts/mnt/user-data/outputs/result.txt`
- `/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf`

**Query Parameters:**
- `download` (boolean): If `true`, force download with Content-Disposition header

**Response:** File content with appropriate Content-Type

---

## Error Responses

All APIs return errors in a consistent format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**HTTP Status Codes:**
- `400` - Bad Request: Invalid input
- `404` - Not Found: Resource not found
- `422` - Validation Error: Request validation failed
- `500` - Internal Server Error: Server-side error

---

## Authentication

Currently, DeerFlow does not implement authentication. All APIs are accessible without credentials.

Note: This is about DeerFlow API authentication. MCP outbound connections can still use OAuth for configured HTTP/SSE MCP servers.

For production deployments, it is recommended to:
1. Use Nginx for basic auth or OAuth integration
2. Deploy behind a VPN or private network
3. Implement custom authentication middleware

---

## Rate Limiting

No rate limiting is implemented by default. For production deployments, configure rate limiting in Nginx:

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location /api/ {
    limit_req zone=api burst=20 nodelay;
    proxy_pass http://backend;
}
```

---

## WebSocket Support

The Gateway-backed LangGraph runtime supports WebSocket connections for real-time streaming. Connect to:

```
ws://localhost:2026/api/langgraph/threads/{thread_id}/runs/stream
```

---

## SDK Usage

### Python (LangGraph SDK)

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:2026/api/langgraph")

# Create thread
thread = await client.threads.create()

# Run agent
async for event in client.runs.stream(
    thread["thread_id"],
    "lead_agent",
    input={"messages": [{"role": "user", "content": "Hello"}]},
    config={"configurable": {"model_name": "gpt-4"}},
    stream_mode=["values", "messages-tuple", "custom"],
):
    print(event)
```

### JavaScript/TypeScript

```typescript
// Using fetch for Gateway API
const response = await fetch('/api/models');
const data = await response.json();
console.log(data.models);

// Using EventSource for streaming
const eventSource = new EventSource(
  `/api/langgraph/threads/${threadId}/runs/stream`
);
eventSource.onmessage = (event) => {
  console.log(JSON.parse(event.data));
};
```

### cURL Examples

```bash
# List models
curl http://localhost:2026/api/models

# Get MCP config
curl http://localhost:2026/api/mcp/config

# Upload file
curl -X POST http://localhost:2026/api/threads/abc123/uploads \
  -F "files=@document.pdf"

# Enable skill
curl -X POST http://localhost:2026/api/skills/pdf-processing/enable

# Create thread and run agent
curl -X POST http://localhost:2026/api/langgraph/threads \
  -H "Content-Type: application/json" \
  -d '{}'

curl -X POST http://localhost:2026/api/langgraph/threads/abc123/runs \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"messages": [{"role": "user", "content": "Hello"}]},
    "config": {"configurable": {"model_name": "gpt-4"}}
  }'
```
