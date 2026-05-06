# 生产环境部署资源清单

## 说明

- 本文件仅记录部署所需资源与访问地址。
- 账号密钥、数据库密码等敏感信息不写入仓库，统一使用占位符。
- 集群内优先使用内网地址。

## OSS

- Bucket: `sais-staging-bio-dev`
- 外网 Endpoint: `oss-cn-wulanchabu.aliyuncs.com`
- 内网 Endpoint: `oss-cn-wulanchabu-internal.aliyuncs.com`
- AccessKeyId: `<redacted>`
- AccessKeySecret: `<redacted>`

用途：
- 作为 `ossfs` 后端存储
- 为 `gateway` 和 `sandbox` 提供共享工作空间 PVC

## 镜像仓库

- 外网仓库地址: `novainspire-acr-registry.cn-wulanchabu.cr.aliyuncs.com`
- 内网仓库地址: `novainspire-acr-registry-vpc.cn-wulanchabu.cr.aliyuncs.com`

登录示例：

```bash
docker login http://novainspire-acr-registry.cn-wulanchabu.cr.aliyuncs.com/ --username=<redacted>
```

推镜像示例：

```bash
docker tag alpine:3.18 novainspire-acr-registry.cn-wulanchabu.cr.aliyuncs.com/sais/bio/alpine:3.18
docker push novainspire-acr-registry.cn-wulanchabu.cr.aliyuncs.com/sais/bio/alpine:3.18
```

集群内镜像拉取地址优先使用：

- `novainspire-acr-registry-vpc.cn-wulanchabu.cr.aliyuncs.com/sais/bio/alpine:3.18`

## 数据库

- PostgreSQL 用户: `admin_ops`
- 数据库名: `chinese_civilization`

私网地址：

- `pgm-0jl6dkvhya7fdy49.pg.rds.aliyuncs.com:5432`

公网地址：

- `pgm-0jl6dkvhya7fdy49uo.pg.rds.aliyuncs.com:5432`

密码：

- `<redacted>`

用途：
- DeerFlow 业务库
- LangGraph checkpointer / runtime 持久化库

## Kubernetes

- 已配置本地 kubeconfig
- 当前仅允许 `bio-dev` 命名空间操作

### 验证目标

- 检查集群是否已有可用 OSS `StorageClass`
- 确认 `bio-dev` 命名空间是否可创建 `PVC`
- 如需安装 OSS 存储驱动，则需要额外集群级权限

## 建议的生产使用原则

- 集群内访问 OSS 优先使用内网 Endpoint
- 集群内拉镜像优先使用 VPC 仓库地址
- 数据库优先使用私网地址
- 密钥统一通过 Kubernetes Secret 或外部密钥系统注入
