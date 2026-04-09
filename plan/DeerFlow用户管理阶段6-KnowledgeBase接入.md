# DeerFlow用户管理阶段6-KnowledgeBase接入与实时同步

## 1. 本阶段目标

- 建立 Knowledge Base 资源层
- 建立文件上传与 OSS 存储
- 建立解析、切分、向量索引与运行时检索

## 2. 前置依赖

- user skills 的业务化和运行时投影已具备基础
- 用户级 agent / workspace / thread 模型已稳定

## 3. 分层策略

### 6A 资源层

- 建立 `knowledge_bases`
- 建立 `knowledge_base_files`
- 建立 `agent_knowledge_bases`
- 用户可上传自定义文件

### 6B 索引层

- 文件解析
- 文本切分
- `knowledge_chunks` 写入 `pgvector`

### 6C 运行时接入

- agent / thread 可绑定 Knowledge Base
- Gateway 在运行前按当前引用组装检索上下文
- Knowledge Base 内容变更后，后续 run 直接使用最新状态

## 4. 运行时容错规则

- thread 创建或绑定 agent 时不再保存 Knowledge Base 的历史副本
- 运行时缺失 Knowledge Base 引用、文件缺失或路径不可达时，跳过对应检索增强
- 缺失单个 Knowledge Base 不阻断整次模型调用
- 历史 thread 会跟随当前 Knowledge Base 状态变化而变化，这是已接受的 tradeoff

## 5. 为什么 PG 仍然必须保留文件表

- OSS 解决的是文件存储，不解决业务管理
- 前端仍需要文件列表、状态、失败原因、去重和索引关系
- 因此 `knowledge_base_files` 不能省略

## 6. 允许修改范围

- `backend/app/**`
- `frontend/src/**`
- `backend/tests/**`
- `plan/**`

## 7. 边界与不做事项

- 本阶段不做高级权限共享模型
- 本阶段不做复杂的跨 KB 联邦检索

## 8. 风险与注意事项

- 若文件只进 OSS 不落 PG，业务管理层会缺失
- 若先接入检索再补状态管理，问题定位会非常困难
- 若缺失文件或路径异常不做软失败处理，会直接扩大调用失败面

## 9. 验收动作

- KB 文件可上传到 OSS
- PG 中可看到文件元数据与处理状态
- `pgvector` 检索链路可跑通
- thread / agent 可使用当前绑定的 KB 检索结果
- Knowledge Base 引用缺失、文件缺失或路径不可达时，会跳过对应增强并继续执行模型
