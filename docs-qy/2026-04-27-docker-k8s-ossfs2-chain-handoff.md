# Docker + Kubernetes + ossfs2 链路打通 handoff

日期：2026-04-27

## 1. 目标

这份文档记录本轮如何把本机 macOS 上的 DeerFlow Docker dev 容器、Docker Desktop Kubernetes sandbox、以及阿里云 OSS/ossfs2 2.0 这一整条链路打通。

本轮最重要的结论是：

- 失败不是简单的 `cp` 命令问题。
- 失败根因是 `write_file` / `ls` 看到的是 gateway/langgraph 容器内的本地 workspaces，而 sandbox 里的 `bash` / `cp` 看到的是另一份 OSS 挂载。
- 要跑通，必须让 Docker dev 容器里的 `backend/.deer-flow/workspaces` 和 k8s sandbox 里的 `/mnt/user-data` 指向同一个 OSS prefix。

## 2. 最终跑通的形态

最终形态是：

- `gateway` 和 `langgraph` 容器启动时先执行 ossfs2 挂载脚本。
- 它们把 `/app/backend/.deer-flow/workspaces` 挂到 OSS 的 `workspaces/` prefix。
- k8s sandbox 启动后，把 `/mnt/user-data` 挂到同一个 workspace prefix：`workspaces/<workspace_id>/`。
- 因此：
  - DeerFlow file tools 写入 `backend/.deer-flow/workspaces/<workspace_id>/workspace/foo`
  - sandbox bash 从 `/mnt/user-data/workspace/foo` 读取
  - 两边访问的是同一个 OSS 对象路径

对应关系：

```text
gateway/langgraph:
  /app/backend/.deer-flow/workspaces/<workspace_id>/workspace/file.html

OSS:
  workspaces/<workspace_id>/workspace/file.html

k8s sandbox:
  /mnt/user-data/workspace/file.html
```

## 3. 根因复盘

截图里的失败表现是：

```text
cp: cannot stat '/mnt/user-data/workspace/user_stats_chart.html': No such file or directory
```

但同一轮中，`write_file` 和 `ls` 又能看到文件。这不是矛盾，而是两个执行面看到的 filesystem 不一致：

- `write_file` / `ls` 是 DeerFlow 工具侧，运行在 `langgraph` / gateway 进程附近。
- `bash` / `cp` 是 sandbox 内部命令，运行在 k8s Pod 里。
- 之前 local workspaces 没有挂到 ossfs2，sandbox 也曾使用过 `workspaces/<workspace_id>/user-data/` 这样的 prefix。
- 所以工具侧写到本地目录，sandbox 侧去 OSS 的另一个 prefix 找，自然找不到。

这也是为什么“再画个图表，然后 cp”会进入奇怪的 fallback：模型看到工具层文件存在，但 bash 层 `cp` 失败，于是继续尝试创建输出文件。

## 4. 本轮关键改动

### 4.1 backend 镜像安装 ossfs2

修改：

- `backend/Dockerfile`

作用：

- 在 `gateway` / `langgraph` dev 镜像中安装 ossfs2 2.0.7。
- arm64 使用阿里云 aarch64 rpm。
- amd64 使用阿里云 x86_64 deb。
- 同时补 `libssl1.1`、`rpm2cpio`、`cpio` 等依赖。

原因：

- mac 本机 Docker Desktop 里实际跑的是 Linux 容器。
- 要让业务容器自己挂 OSS，需要容器内有 `/usr/local/bin/ossfs2`。

### 4.2 gateway/langgraph 启动时挂载本地 workspaces

新增：

- `backend/scripts/mount-ossfs2-workspaces.sh`

修改：

- `docker/docker-compose-dev.yaml`

作用：

- `gateway` / `langgraph` 的 command 先进入挂载脚本，再启动原来的服务。
- 容器增加：
  - `/dev/fuse:/dev/fuse`
  - `SYS_ADMIN`
  - `apparmor:unconfined`
- 挂载点：
  - `/app/backend/.deer-flow/workspaces`
- OSS prefix：
  - `workspaces/`

注意：

- ossfs2 2.0 官方要求挂载目录必须为空。
- 脚本会把已有本地目录挪到旁边，例如：
  - `backend/.deer-flow/workspaces.local-before-ossfs2`
- 这个目录只是旧本地数据备份，不再是运行期真实数据源。

### 4.3 sandbox 侧 prefix 对齐

修改：

- `backend/packages/harness/deerflow/community/aio_sandbox/remote_backend.py`

关键变化：

```text
旧：
  workspaces/<workspace_id>/user-data/

新：
  workspaces/<workspace_id>/
```

原因：

- sandbox 内固定把用户数据挂到 `/mnt/user-data`。
- 如果 OSS prefix 是 `workspaces/<workspace_id>/user-data/`，那么 `/mnt/user-data/workspace/foo` 实际对应 `workspaces/<workspace_id>/user-data/workspace/foo`。
- 但 Docker dev 容器挂的是 `workspaces/` 根，工具侧路径对应 `workspaces/<workspace_id>/workspace/foo`。
- 两边必须统一成后者。

### 4.4 sandbox 镜像自己包含 ossfs2

新增：

- `docker/sandbox/Dockerfile.ossfs2`

本机已构建并导入 Docker Desktop k8s node 的镜像：

```text
deer-flow-sandbox-ossfs2:local
```

`.env` 中通过下面配置使用它：

```dotenv
DEER_FLOW_SANDBOX_IMAGE=deer-flow-sandbox-ossfs2:local
```

原因：

- sandbox Pod 也需要 `/usr/local/bin/ossfs2`。
- Docker Desktop Kubernetes 不会自动看到普通 Docker image，构建后需要确保 node/containerd 能拉到或已经导入。

### 4.5 Docker dev 网络和 provisioner 对齐

修改：

- `docker/docker-compose-dev.yaml`
- `docker/docker-compose.yaml`

关键点：

- provisioner 暴露 `8002:8002`。
- gateway/langgraph 在 compose 内使用 `http://provisioner:8002`。
- provisioner 通过 `NODE_HOST=desktop-control-plane` 返回 k8s NodePort URL。
- gateway/langgraph 加入 Docker Desktop Kubernetes 的 docker network，才能访问 `desktop-control-plane:<NodePort>`。

本机 dev 里目前依赖：

```dotenv
DEER_FLOW_K8S_DOCKER_NETWORK=kind
DEER_FLOW_SANDBOX_NODE_HOST=desktop-control-plane
K8S_API_SERVER=https://host.docker.internal:<当前 Docker Desktop k8s API 端口>
```

`K8S_API_SERVER` 里的端口来自当前 kubeconfig，本机可能变化。

## 5. 本地配置清单

这些是本机 Docker Desktop dev 需要的配置，不应直接照搬到线上。

### 5.1 `.env`

关键项：

```dotenv
DEER_FLOW_ROOT=/Users/sayori/Desktop/work/deer-flow

DEER_FLOW_SANDBOX_PROVISIONER_URL=http://localhost:8002
K8S_API_SERVER=https://host.docker.internal:<docker-desktop-k8s-api-port>
DEER_FLOW_K8S_DOCKER_NETWORK=kind
DEER_FLOW_SANDBOX_NODE_HOST=desktop-control-plane
DEER_FLOW_SANDBOX_IMAGE=deer-flow-sandbox-ossfs2:local

DEER_FLOW_OSSFS2_WORKSPACES_MOUNT=true
DEER_FLOW_OSSFS2_WORKSPACES_PREFIX=workspaces/
```

OSS 相关项来自既有 `config.yaml` / `.env`，不要写进文档明文：

```dotenv
ALIYUN_OSS_ENDPOINT=...
ALIYUN_OSS_BUCKET=...
ALIYUN_OSS_ACCESS_KEY_ID=...
ALIYUN_OSS_ACCESS_KEY_SECRET=...
```

### 5.2 `config.yaml`

必须满足：

```yaml
uploads:
  backend: oss
  oss:
    endpoint: ...
    bucket: ...
    access_key_id: ...
    access_key_secret: ...
```

`RemoteSandboxBackend` 会从这里读 OSS 配置，然后在 sandbox 里生成 ossfs2 config。

### 5.3 Docker Desktop Kubernetes

本机依赖：

- Docker Desktop Kubernetes 已启用。
- kubeconfig 在 `~/.kube/config`。
- provisioner 容器能通过 `K8S_API_SERVER=https://host.docker.internal:<port>` 访问 k8s API。
- gateway/langgraph 能访问 `desktop-control-plane:<NodePort>`。
- CoreDNS 正常，kube-dns endpoints 正常。

### 5.4 本地旧数据

因为 ossfs2 2.0 要求挂载点为空，脚本会移动旧目录：

```text
backend/.deer-flow/workspaces
  -> backend/.deer-flow/workspaces.local-before-ossfs2
```

如果要把旧 workspace 迁入 OSS，不建议全量 tar 进启动链路。实践证明这会卡住容器启动。

正确做法是：

- 只迁需要的 workspace。
- 确认路径从旧本地目录复制到 ossfs2 挂载目录。
- 复制完成后用 sandbox 内 `cp` 做验证。

## 6. 本轮验证结果

### 6.1 容器挂载验证

`gateway` / `langgraph` 均验证为：

```text
ossfs2 /app/backend/.deer-flow/workspaces fuse.ossfs2 ...
/app/backend/.deer-flow/workspaces is a mountpoint
```

### 6.2 sandbox 验证

用验证 workspace 写入：

```text
/app/backend/.deer-flow/workspaces/<workspace_id>/workspace/codex_cp_probe.txt
```

sandbox 内验证：

```text
/mnt/user-data is a mountpoint
ossfs2 /mnt/user-data fuse.ossfs2 ...
wc -c /mnt/user-data/workspace/codex_cp_probe.txt
cp /mnt/user-data/workspace/codex_cp_probe.txt /mnt/user-data/outputs/...
```

结果：

```text
15 /mnt/user-data/workspace/codex_cp_probe.txt
15 /mnt/user-data/outputs/codex_cp_probe_from_sandbox.txt
```

### 6.3 截图中失败 workspace 验证

workspace：

```text
13ba58b6-859f-477a-b777-7c407a0eeda2
```

已把旧本地的这几个文件补到 OSS 正确前缀：

```text
workspace/user_stats_chart.html
workspace/user_stats_chart_copy.html
outputs/user_stats_chart.html
outputs/user_stats_chart_copy.html
```

sandbox 内验证通过：

```text
wc -c /mnt/user-data/workspace/user_stats_chart.html
4865

cp /mnt/user-data/workspace/user_stats_chart.html /mnt/user-data/outputs/codex_cp_user_stats_verify.html
wc -c /mnt/user-data/outputs/codex_cp_user_stats_verify.html
4865
```

### 6.4 测试

新增测试：

- `backend/tests/test_remote_sandbox_backend.py`

验证：

- sandbox mount prefix 不再包含 `user-data`
- mount command 包含 ossfs2 一致性相关选项

命令：

```bash
docker exec deer-flow-langgraph sh -lc 'cd /app/backend && PYTHONPATH=packages/harness:. uv run pytest tests/test_remote_sandbox_backend.py -q'
```

结果：

```text
1 passed
```

## 7. 线上要额外做什么

本地跑通不等于线上可直接照搬。线上要单独设计下面几类内容。

### 7.1 镜像发布

本地使用的是：

```text
deer-flow-sandbox-ossfs2:local
```

线上需要：

- 构建正式 sandbox 镜像。
- 镜像内包含 ossfs2 2.0.7 和依赖。
- 推到线上集群可访问的 registry。
- 按架构区分或使用 multi-arch image。
- `DEER_FLOW_SANDBOX_IMAGE` 指向正式镜像 tag。

gateway/langgraph 镜像也需要正式包含：

- `/usr/local/bin/ossfs2`
- `backend/scripts/mount-ossfs2-workspaces.sh`

### 7.2 权限模型

本地为了 FUSE 使用：

```yaml
devices:
  - /dev/fuse:/dev/fuse
cap_add:
  - SYS_ADMIN
security_opt:
  - apparmor:unconfined
```

线上不能简单照搬 compose 配置，需要在集群层明确：

- 是否允许业务 Pod 使用 FUSE。
- 是否允许 `SYS_ADMIN` 或 privileged 容器。
- 节点是否开放 `/dev/fuse`。
- PodSecurity / PSP replacement / admission policy 是否允许。

更稳的线上方案可能是：

- 使用 CSI / PV 层挂载 OSS。
- 或由平台侧统一提供 workspace volume。
- 业务容器不直接拿高权限。

如果继续容器内 ossfs2，则要把这当作明确的基础设施能力，而不是应用临时 hack。

### 7.3 Secret 管理

本地通过 `.env` / `config.yaml` 提供 OSS AK/SK。

线上需要：

- 使用 Kubernetes Secret 或云上 Secret 管理。
- 不要把 AK/SK 写入镜像或 ConfigMap。
- 优先考虑 RAM Role / STS / 工作负载身份，而不是长期 AK/SK。
- 明确 bucket 权限最小化：
  - 只允许目标 bucket。
  - 只允许目标 prefix。
  - 区分 read/write/delete 权限。

### 7.4 OSS prefix 规范

本轮确定的用户数据 prefix 是：

```text
workspaces/<workspace_id>/
```

线上必须固定这个 contract：

- gateway/langgraph 本地工具视角：
  - `<workspaces-root>/<workspace_id>/workspace`
  - `<workspaces-root>/<workspace_id>/outputs`
  - `<workspaces-root>/<workspace_id>/uploads`
- sandbox 视角：
  - `/mnt/user-data/workspace`
  - `/mnt/user-data/outputs`
  - `/mnt/user-data/uploads`
- OSS 视角：
  - `workspaces/<workspace_id>/workspace`
  - `workspaces/<workspace_id>/outputs`
  - `workspaces/<workspace_id>/uploads`

不要再引入 `workspaces/<workspace_id>/user-data/` 这一层，否则会回到 split-brain。

### 7.5 provisioner 和网络

本地用了 Docker Desktop 的特殊网络：

```text
desktop-control-plane:<NodePort>
```

线上要替换成正式服务发现方式：

- provisioner 在集群内运行时，应使用 in-cluster config。
- sandbox Service 可以用 ClusterIP / headless / internal DNS。
- gateway/langgraph 不应依赖 `desktop-control-plane`。
- 不要把 NodePort 当作默认线上入口，除非基础设施明确要求。

### 7.6 可观测性和排障

线上至少要保留：

- provisioner 创建 sandbox 的日志。
- sandbox mount 初始化日志。
- ossfs2 log_dir 的采集或可查看路径。
- mount table 快照。
- sandbox exec 失败时的脱敏 debug output。

需要重点脱敏：

- OSS access key id
- OSS access key secret
- base64 编码的 mount script

### 7.7 数据迁移

本地有旧目录：

```text
backend/.deer-flow/workspaces.local-before-ossfs2
```

线上如果已有本地或 PV 数据，要做显式迁移计划：

- 按 workspace 迁移到 `workspaces/<workspace_id>/...`
- 迁移后抽样用 sandbox `cp` 验证。
- 不要在应用启动脚本里做全量迁移。
- 启动链路只负责 mount，不负责历史数据搬运。

## 8. 已知注意点

### 8.1 ossfs2 写入可能比本地慢

小文件写入也可能需要数秒，因为 OSS 是对象存储，ossfs2 要模拟文件系统语义。

所以：

- 验证命令 timeout 不要太短。
- 不要在启动关键路径里做大量文件复制。

### 8.2 读写同一文件的时序

ossfs2 2.0 FAQ 明确提到，同一文件边写边读可能读到旧数据或出现 `No such file or directory`。

本轮配置加入了：

```text
--attr_timeout=1
--negative_timeout=0
--kernel_readdir_cache_timeout=0
--close_to_open=true
--oss_negative_cache_timeout=0
```

这些选项降低缓存导致的不一致，但应用层仍应避免对未关闭文件立即并发读取。

### 8.3 不要再混用本地 hostPath 和 OSS workspace

provisioner 里旧的 hostPath workspace 环境变量已经不适合这条链路。

当前 remote sandbox 模式应该通过 OSS 初始化挂载，不再把本机目录 hostPath 到 k8s Pod。

## 9. 下一位接手时的判断标准

如果未来又出现 `cp: cannot stat /mnt/user-data/...`，优先按下面顺序查：

1. `gateway/langgraph` 的 `/app/backend/.deer-flow/workspaces` 是否是 `fuse.ossfs2`。
2. sandbox 的 `/mnt/user-data` 是否是 `fuse.ossfs2`。
3. 两边 OSS prefix 是否都是 `workspaces/<workspace_id>/` 这一套。
4. 文件是否真的写到了 `workspaces/<workspace_id>/workspace/...`。
5. 是否刚写完立刻读，遇到 ossfs2 close-to-open /缓存时序。
6. 是否仍有旧代码使用 `workspaces/<workspace_id>/user-data/`。

