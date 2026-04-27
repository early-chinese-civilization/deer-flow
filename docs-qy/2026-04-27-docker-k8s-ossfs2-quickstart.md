# Docker + k8s + ossfs2 本地启动速记

日期：2026-04-27

## 1. 一句话记忆

本地要跑通这条链路，核心是：

```text
gateway/langgraph 的 /app/backend/.deer-flow/workspaces
和
sandbox 的 /mnt/user-data
必须通过 ossfs2 指向同一个 OSS prefix: workspaces/<workspace_id>/
```

如果 `write_file` 看得到，但 sandbox `cp` 看不到，几乎一定是这个链路又 split-brain 了。

## 2. 启动前检查

确认 Docker Desktop Kubernetes 已启用：

```bash
kubectl get nodes
kubectl -n kube-system get endpoints kube-dns
```

确认 `.env` 关键项：

```dotenv
DEER_FLOW_ROOT=/Users/sayori/Desktop/work/deer-flow
DEER_FLOW_SANDBOX_PROVISIONER_URL=http://localhost:8002
K8S_API_SERVER=https://host.docker.internal:<当前 kubeconfig 里的 Docker Desktop k8s 端口>
DEER_FLOW_K8S_DOCKER_NETWORK=kind
DEER_FLOW_SANDBOX_NODE_HOST=desktop-control-plane
DEER_FLOW_SANDBOX_IMAGE=deer-flow-sandbox-ossfs2:local

DEER_FLOW_OSSFS2_WORKSPACES_MOUNT=true
DEER_FLOW_OSSFS2_WORKSPACES_PREFIX=workspaces/
```

确认 OSS 配置存在，不要把 secret 打到日志里：

```bash
rg -n "uploads:|backend: oss|ALIYUN_OSS|DEER_FLOW_OSSFS2" config.yaml .env
```

## 3. 构建 sandbox 镜像

只在 sandbox 镜像不存在或 Dockerfile 改过时做：

```bash
docker build \
  -f docker/sandbox/Dockerfile.ossfs2 \
  -t deer-flow-sandbox-ossfs2:local \
  .
```

如果 Docker Desktop k8s node 拉不到这个本地镜像，需要导入到 node/containerd。当前 node 名是：

```text
desktop-control-plane
```

## 4. 构建并启动 dev 服务

```bash
cd docker

docker compose \
  -p deer-flow-dev \
  --profile provisioner \
  --env-file ../.env \
  -f docker-compose-dev.yaml \
  build gateway langgraph

docker compose \
  -p deer-flow-dev \
  --profile provisioner \
  --env-file ../.env \
  -f docker-compose-dev.yaml \
  up -d --no-build --force-recreate gateway langgraph provisioner
```

如果只是配置检查：

```bash
cd docker
docker compose -p deer-flow-dev --profile provisioner --env-file ../.env -f docker-compose-dev.yaml config --quiet
```

## 5. 必查状态

```bash
docker ps --filter name=deer-flow --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

`gateway` / `langgraph` 必须是 Up，不应反复 Restarting。

检查 ossfs2：

```bash
for c in deer-flow-gateway deer-flow-langgraph; do
  echo "===$c==="
  docker exec "$c" sh -lc '
    command -v ossfs2
    ossfs2 --version | head -1
    grep " /app/backend/.deer-flow/workspaces " /proc/mounts
    mountpoint /app/backend/.deer-flow/workspaces
  '
done
```

期望看到：

```text
ossfs2 /app/backend/.deer-flow/workspaces fuse.ossfs2 ...
/app/backend/.deer-flow/workspaces is a mountpoint
```

## 6. 最短端到端验证

在 `langgraph` 容器的 ossfs2 挂载点写一个小文件：

```bash
docker exec deer-flow-langgraph sh -lc '
  wid=codex-ossfs2-smoke
  mkdir -p /app/backend/.deer-flow/workspaces/$wid/workspace /app/backend/.deer-flow/workspaces/$wid/outputs
  printf %s codex-ossfs2-ok > /app/backend/.deer-flow/workspaces/$wid/workspace/probe.txt
  cp /app/backend/.deer-flow/workspaces/$wid/workspace/probe.txt /app/backend/.deer-flow/workspaces/$wid/outputs/probe-copy.txt
  wc -c /app/backend/.deer-flow/workspaces/$wid/workspace/probe.txt /app/backend/.deer-flow/workspaces/$wid/outputs/probe-copy.txt
'
```

然后创建 sandbox，用同一个 workspace 在 sandbox 内验证 `/mnt/user-data`。

最核心要验证这几句能成功：

```bash
mountpoint /mnt/user-data
grep " /mnt/user-data " /proc/mounts
wc -c /mnt/user-data/workspace/probe.txt
cp /mnt/user-data/workspace/probe.txt /mnt/user-data/outputs/probe-from-sandbox.txt
wc -c /mnt/user-data/outputs/probe-from-sandbox.txt
```

期望：

```text
/mnt/user-data is a mountpoint
ossfs2 /mnt/user-data fuse.ossfs2 ...
15 /mnt/user-data/workspace/probe.txt
15 /mnt/user-data/outputs/probe-from-sandbox.txt
```

验证完清理：

```bash
docker exec deer-flow-langgraph sh -lc '
  rm -rf /app/backend/.deer-flow/workspaces/codex-ossfs2-smoke
'
```

## 7. 旧 workspace 手动补到 OSS

ossfs2 2.0 要求挂载点为空，所以旧本地目录会被移动到：

```text
backend/.deer-flow/workspaces.local-before-ossfs2
```

如果要补某个旧 workspace：

```bash
wid=<workspace_id>

docker exec -e WID="$wid" deer-flow-langgraph sh -lc '
  src=/app/backend/.deer-flow/workspaces.local-before-ossfs2/$WID
  dst=/app/backend/.deer-flow/workspaces/$WID
  test -d "$src"
  mkdir -p "$dst/workspace" "$dst/outputs" "$dst/uploads"
  cp "$src"/workspace/* "$dst/workspace"/ 2>/dev/null || true
  cp "$src"/outputs/* "$dst/outputs"/ 2>/dev/null || true
  cp "$src"/uploads/* "$dst/uploads"/ 2>/dev/null || true
'
```

不要把全量历史数据迁移放进容器启动脚本。

## 8. 常见故障速查

### gateway/langgraph Restarting

先看脱敏日志：

```bash
for c in deer-flow-gateway deer-flow-langgraph; do
  echo "===$c==="
  docker logs --tail 120 "$c" 2>&1 \
    | sed -E 's/[A-Za-z0-9+\/=]{180,}/<base64-redacted>/g'
done
```

如果看到：

```text
MOUNTPOINT directory ... is not empty
```

说明挂载点没有被脚本挪空，检查：

```bash
ls -ld backend/.deer-flow/workspaces*
```

### write_file 成功但 sandbox cp 失败

按顺序查：

```bash
docker exec deer-flow-langgraph sh -lc '
  grep " /app/backend/.deer-flow/workspaces " /proc/mounts
'
```

再查 sandbox：

```bash
mountpoint /mnt/user-data
grep " /mnt/user-data " /proc/mounts
```

两边都必须是 `fuse.ossfs2`。

### 仍然找不到文件

查 prefix 是否回退成旧的：

```bash
rg -n "user-data|workspaces/\\{workspace_id\\}|workspaces/.*user-data" \
  backend/packages/harness/deerflow/community/aio_sandbox \
  docker
```

正确用户数据 prefix 是：

```text
workspaces/<workspace_id>/
```

不是：

```text
workspaces/<workspace_id>/user-data/
```

## 9. 记住这条验证命令

截图里那类失败最终要靠 sandbox 内这条命令判断：

```bash
cp /mnt/user-data/workspace/user_stats_chart.html /mnt/user-data/outputs/user_stats_chart.html
```

只要这条能在 sandbox 里成功，说明核心链路已经通了。

