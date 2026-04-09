# DeerFlow用户管理分步实施方案

本文档保留为历史拆解参考，不再作为主真相。

当前正式文档分层如下：

- 总方案主文档：`用户管理与资源模型接入方案.md`
- 执行总方案：`DeerFlow用户管理执行方案.md`
- 阶段子文档：`DeerFlow用户管理阶段*.md`

## 当前推荐阶段顺序

1. Auth(`kc_*` HttpOnly cookie) + `.env` + PG(users) + `current_user`
2. threads + messages + lazy takeover
3. workspaces + thread 闭环
4. agents 业务化
5. skills 业务化与实时同步
6. knowledge base 接入
7. user memories 与 legacy 清理

## 使用方式

- 日常执行请以 `DeerFlow用户管理执行方案.md` 为准
- 具体实现请以对应阶段文档为准
- 当前目录只保留技术方案文档，不再使用单独的门禁文件
