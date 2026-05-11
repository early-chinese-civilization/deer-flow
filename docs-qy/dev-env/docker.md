# DeerFlow Docker 本地调试记录

本文记录 2026-05-11 对当前分支 Docker 启动方式的只读梳理结论，以及在本机 Mac 上优先尝试的配置路线。

## 背景

此前常用启动方式是：

```bash
make dev
```

这会在宿主机直接启动前端、gateway、LangGraph 等开发服务。现在为了测试 sandbox，需要改用 Docker dev stack：

```bash
make docker-start
```

Docker dev stack 的入口在：

- `Makefile`
- `scripts/docker.sh`
- `docker/docker-compose-dev.yaml`

## 当前启动链路

`make docker-start` 会执行：

```bash
./scripts/docker.sh start
```

`scripts/docker.sh` 会读取 `config.yaml` 的 `sandbox:` 段并判断模式：

- `LocalSandboxProvider` -> `local`
- `AioSandboxProvider` 且没有 `provisioner_url` -> `aio`
- `AioSandboxProvider` 且存在 `provisioner_url` -> `provisioner`

当前 `config.yaml` 是：

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  provisioner_url: $DEER_FLOW_SANDBOX_PROVISIONER_URL
```

因此当前 `make docker-start` 会进入 `provisioner` 模式，启动：

```text
frontend gateway langgraph provisioner nginx
```

## 两条可选路径

### 路径 A：本机 AIO sandbox，优先尝试

配置方式：保留 `AioSandboxProvider`，但移除或注释 `provisioner_url`。

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
```

效果：

- `make docker-start` 只启动 `frontend gateway langgraph nginx`。
- gateway/langgraph 容器通过挂载的 `/var/run/docker.sock` 调用宿主 Docker daemon。
- sandbox 会作为宿主 Docker daemon 里的 `deer-flow-sandbox-*` 容器启动。
- 这是最符合“不改代码，只靠配置先本地调试 sandbox”的路线。

注意：

- 必须先启动 Docker Desktop，并确保 `docker info` 能正常返回。
- 如果本机安装了 Apple Container，AIO provider 在 macOS 上会优先尝试 `container` CLI，否则回退 Docker。
- Docker dev compose 已设置 `DEER_FLOW_SANDBOX_HOST=host.docker.internal`，用于让 gateway/langgraph 容器访问宿主上启动的 sandbox 容器端口。

### 路径 B：provisioner/Kubernetes sandbox，不建议作为纯配置首选

配置方式：保留 `provisioner_url`。

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  provisioner_url: $DEER_FLOW_SANDBOX_PROVISIONER_URL
```

效果：

- `make docker-start` 会启动 `provisioner` 服务。
- sandbox 由 provisioner 在本机 Kubernetes 中创建 Pod + NodePort Service。

当前风险：

- 本机 Kubernetes 必须可用，`kubectl cluster-info` 必须能连通。
- 当前 `.env` 中已有 `K8S_API_SERVER=https://host.docker.internal:55153`，但初查时本机 `kubectl` 指向的 `https://127.0.0.1:55153` 拒绝连接。
- `chore/qy-dev` 的成功并非纯配置：它改过 Dockerfile、compose、sandbox OSSFS2 挂载行为和 remote sandbox 挂载前缀。

## qy-dev 与当前分支的关键差异

`chore/qy-dev` 中与 Docker/sandbox 相关的关键差异包括：

- `backend/Dockerfile` 安装 `ossfs2`、`libssl1.1`、`rpm2cpio`、`cpio`。
- 新增 `backend/scripts/mount-ossfs2-workspaces.sh`，用于在 gateway/langgraph 容器内挂载 OSS workspace root。
- `docker/docker-compose-dev.yaml` 给 gateway/langgraph 增加 `/dev/fuse`、`SYS_ADMIN`、`apparmor:unconfined`。
- provisioner 服务暴露 `8002:8002`，并加入额外 Docker/Kubernetes 网络。
- `remote_backend.py` 将 `/mnt/user-data` 的 OSS prefix 从 `workspaces/{workspace_id}/user-data` 改为 `workspaces/{workspace_id}`。
- `aio_sandbox_provider.py` 改过 skills 挂载逻辑，允许没有 `skill_scope` 时挂载 skills root。

结论：如果目标是完整复刻 `qy-dev` 的 Kubernetes + OSSFS2 行为，当前分支只靠 `.env`/`config.yaml` 很可能不够；如果目标是先验证本机 Docker sandbox 是否能启动和执行命令，路径 A 更合适。

## 本机操作建议

1. 启动 Docker Desktop。
2. 确认 Docker daemon 可用：

   ```bash
   docker info
   ```

3. 将 `config.yaml` 切到 AIO 无 provisioner：

   ```yaml
   sandbox:
     use: deerflow.community.aio_sandbox:AioSandboxProvider
   ```

4. 启动 Docker dev stack：

   ```bash
   make docker-start
   ```

5. 查看日志：

   ```bash
   make docker-logs
   make docker-logs-gateway
   ```

6. 如果需要回到 provisioner/Kubernetes 路线，再恢复 `provisioner_url`，并先确保 Docker Desktop Kubernetes 或其他本机集群正常。

## 当前初查状态

- `docker compose version` 可用。
- 初查时 `docker info` 无法连接 Docker daemon。
- 初查时 `kubectl current-context` 是 `docker-desktop`。
- 初查时 `kubectl cluster-info` 连接 `127.0.0.1:55153` 失败。
- 因此第一步不是改源码，而是先启动 Docker Desktop，再试路径 A。

## 2026-05-11 首次操作记录

- 已启动 Docker Desktop，随后 `docker info` 可用。
- 已将本机 `config.yaml` 切到 AIO 无 provisioner，`detect_sandbox_mode` 返回 `aio`。
- 首次执行 `make docker-start` 时，前端镜像构建完成，后端镜像构建卡在 Docker build context 传输阶段十多分钟。
- 原因判断：`.dockerignore` 未排除本地运行态目录，例如 `backend/.deer-flow`、`.trellis`、`docs-qy`，导致 Docker Desktop 扫描不必要的工作区内容。
- 后续处理：补充 `.dockerignore`，排除这些运行态/文档目录后重新尝试启动。
- 第二次执行 `make docker-start` 后，镜像构建和容器启动成功，但 gateway/langgraph 容器端口没有打开，nginx 返回 502。
- 进一步检查发现 `backend/.deer-flow` 在本机是 FUSE/NFS 挂载：

  ```text
  fuse-t:/deerflow... on /Users/sayori/Desktop/work/deer-flow/backend/.deer-flow
  ```

  Docker dev compose 默认把它挂到容器内 `/app/backend/.deer-flow`，会拖慢或卡住后端启动初始化。

- 后续处理：给 `docker/docker-compose-dev.yaml` 增加 `DEER_FLOW_DOCKER_DATA_DIR`，本机调试时使用独立本地目录 `backend/.deer-flow-docker`，避免触碰原来的 FUSE 挂载。

本机已写入被 git ignore 的 `docker/.env`：

```env
DEER_FLOW_DOCKER_DATA_DIR=/Users/sayori/Desktop/work/deer-flow/backend/.deer-flow-docker
```

`backend/.deer-flow-docker/` 也需要保持为本地运行态目录，不应进入 Git 或 Docker build context。

## 2026-05-11 本机调试改动溯源

本节记录本次为了让 Docker AIO sandbox 在本机 Mac 可调试而发生的每一项配置和目录变化。核心结论是：本机调试走 AIO 本地 Docker 模式，不走 provisioner/Kubernetes；Docker stack 已经启动成功，gateway health 正常，并已在 `deer-flow-langgraph` 容器内验证 `AioSandboxProvider` 可以创建 sandbox、执行 `echo sandbox-ok`、释放 sandbox。

### 1. `config.yaml`：移除或注释 `sandbox.provisioner_url`

改了什么：

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  # provisioner_url: $DEER_FLOW_SANDBOX_PROVISIONER_URL
```

本机把 `sandbox.provisioner_url` 注释或移除，只保留 `AioSandboxProvider`。

为什么改：

- `scripts/docker.sh` 会按 `config.yaml` 判断 sandbox 模式。
- 当 `sandbox.use` 是 `AioSandboxProvider` 且存在 `sandbox.provisioner_url` 时，脚本会检测为 `provisioner`，并进入 provisioner/Kubernetes 路径。
- 本机 Mac 的纯配置调试目标是先验证 Docker AIO sandbox；provisioner/Kubernetes 路径依赖本机 Kubernetes、NodePort、provisioner 服务和相关镜像/挂载行为，不适合作为本次最小调试路径。
- 移除 `provisioner_url` 后，`scripts/docker.sh` 会检测为 `aio`，`AioSandboxProvider` 会使用本地 Docker 后端创建 `deer-flow-sandbox-*` 容器。

是否应提交：

- 不一定提交。`config.yaml` 可能是本机配置文件，未必会出现在 `git status`。
- 如果只是本机调试，应保持为本机改动；除非团队决定把默认开发模式改成 AIO 本地 Docker，否则不要把这项作为通用产品配置提交。

如何回滚或恢复默认：

- 恢复 `provisioner_url`：

  ```yaml
  sandbox:
    use: deerflow.community.aio_sandbox:AioSandboxProvider
    provisioner_url: $DEER_FLOW_SANDBOX_PROVISIONER_URL
  ```

- 恢复后重新运行 `make docker-start` 前，先确认本机 Kubernetes/provisioner 路径可用，例如 `kubectl cluster-info` 能连通，并且相关 `docker/.env` 里的 Kubernetes 地址、端口和 provisioner 配置匹配当前环境。

### 2. `.dockerignore`：排除本机文档、Trellis 和运行态目录

改了什么：

新增排除：

```gitignore
.trellis/
.omx/
docs-qy/
backend/.deer-flow
backend/.deer-flow-docker
```

为什么改：

- 首次 `make docker-start` 时，后端镜像构建卡在 Docker build context 传输阶段。
- `.trellis/`、`.omx/`、`docs-qy/` 是文档、任务和本机工具状态，不需要进入镜像 build context。
- `backend/.deer-flow`、`backend/.deer-flow-docker` 是运行态数据目录，可能包含 workspace、lock、sandbox 输出或挂载内容，也不应该打进镜像上下文。
- 排除这些路径后，Docker Desktop 不再扫描和上传无关的大目录或挂载目录，构建可以继续推进。

是否应提交：

- 建议提交。这是仓库级 Docker build context 优化，能降低其他开发者在本地构建时踩到同类问题的概率。
- 前提是 Dockerfile 不依赖这些目录；当前用途下这些目录都不应作为镜像构建输入。

如何回滚或恢复默认：

- 从 `.dockerignore` 删除上述条目即可恢复原行为。
- 回滚后如果再次出现 build context 传输慢、卡住或镜像上下文过大的问题，应优先检查是否又把运行态目录或挂载目录纳入了 build context。

### 3. `docker/docker-compose-dev.yaml`：`.deer-flow` 挂载改为可切换本地数据目录

改了什么：

- gateway/langgraph 的 `.deer-flow` bind mount 从固定 `../backend/.deer-flow` 改为支持：

  ```yaml
  ${DEER_FLOW_DOCKER_DATA_DIR:-../backend/.deer-flow}
  ```

- 相关环境变量也改为优先使用同一个目录：

  ```env
  DEER_FLOW_HOST_SHARED_FS_ROOT
  DEER_FLOW_HOST_BASE_DIR
  DEER_FLOW_HOST_SKILLS_PATH
  ```

为什么改：

- 原来的 `backend/.deer-flow` 在本机是 FUSE/NFS 挂载。
- Docker compose 把 FUSE/NFS 挂载目录 bind 到 gateway/langgraph 容器后，后端启动初始化会变慢或卡住，导致端口打不开、nginx 返回 502。
- 改成 `${DEER_FLOW_DOCKER_DATA_DIR:-../backend/.deer-flow}` 后，默认行为不变；本机可以通过 `docker/.env` 指向普通本地目录 `backend/.deer-flow-docker`，避开 FUSE/NFS 挂载。

是否应提交：

- 建议提交。这是向后兼容的 compose 配置增强：未设置 `DEER_FLOW_DOCKER_DATA_DIR` 时仍使用原默认目录，设置后才进入本机调试路径。
- 它不包含本机绝对路径，本身不是个人配置。

如何回滚或恢复默认：

- 删除 `DEER_FLOW_DOCKER_DATA_DIR` 环境变量或移除 `docker/.env` 中对应行，即可回到默认 `../backend/.deer-flow`。
- 如果要完全回滚 compose 改动，把相关 mount 和环境变量中的 `${DEER_FLOW_DOCKER_DATA_DIR:-../backend/.deer-flow}` 恢复成原来的 `../backend/.deer-flow`。

### 4. `docker/.env`：新增本机专用 `DEER_FLOW_DOCKER_DATA_DIR`

改了什么：

本机写入被 Git ignore 的 `docker/.env`：

```env
DEER_FLOW_DOCKER_DATA_DIR=/Users/sayori/Desktop/work/deer-flow/backend/.deer-flow-docker
```

为什么改：

- 让 compose 在本机 Mac 调试时使用普通本地目录 `backend/.deer-flow-docker`。
- 避免 gateway/langgraph 容器继续 bind mount 原来的 FUSE/NFS `backend/.deer-flow`。

是否应提交：

- 不应提交。`docker/.env` 是本机环境文件，包含本机绝对路径。
- 其他开发者应按自己的仓库路径创建本地 `docker/.env`，或不设置该变量继续使用默认目录。

如何回滚或恢复默认：

- 删除 `docker/.env` 中的 `DEER_FLOW_DOCKER_DATA_DIR` 行，或删除整个本机 `docker/.env`。
- 重新执行 `make docker-start` 后，compose 会回到 `${DEER_FLOW_DOCKER_DATA_DIR:-../backend/.deer-flow}` 的默认值。

### 5. `.gitignore`：排除 `backend/.deer-flow-docker/`

改了什么：

新增：

```gitignore
backend/.deer-flow-docker/
```

为什么改：

- `backend/.deer-flow-docker/` 是给本机 Docker AIO sandbox 使用的运行态数据目录。
- 目录内可能出现 sandbox 本地数据、lock 文件、workspace 输出和调试产物。
- 这些内容与源码无关，且可能包含临时状态或较大文件，不应进入 Git。

是否应提交：

- 建议提交。这是仓库级 ignore 规则，能防止本机 Docker 调试产生的运行态文件被误提交。

如何回滚或恢复默认：

- 从 `.gitignore` 删除 `backend/.deer-flow-docker/`。
- 回滚后要特别注意 `git status`，避免把该目录里的运行态文件加入提交。

### 6. `backend/.deer-flow-docker/`：本机 Docker AIO 运行态目录

改了什么：

- 本机创建或使用 `backend/.deer-flow-docker/` 作为 Docker AIO sandbox 调试的数据目录。
- 该目录由 sandbox/provider 和后端运行过程生成内容，不是手写配置。

为什么改：

- 用普通本地目录替代 FUSE/NFS `backend/.deer-flow`，让 gateway/langgraph 容器启动和 sandbox 操作可以稳定完成。
- 它承载本机调试时的 shared filesystem、workspace、lock 和 sandbox 输出。

是否应提交：

- 不应提交。目录内容是运行态产物，应由 `.gitignore` 和 `.dockerignore` 同时排除。

如何回滚或恢复默认：

- 停止 Docker dev stack 后，可以删除该目录：

  ```bash
  rm -rf backend/.deer-flow-docker
  ```

- 下次设置 `DEER_FLOW_DOCKER_DATA_DIR` 并启动服务时，后端/sandbox 流程会按需重建目录和运行态内容。
- 如果要恢复使用原目录，同时删除或注释 `docker/.env` 中的 `DEER_FLOW_DOCKER_DATA_DIR`。

## 2026-05-11 验证结果

使用上述配置后：

- `make docker-start` 可成功构建并启动 `frontend`、`gateway`、`langgraph`、`nginx`。
- `http://localhost:2026/health` 返回 gateway health：

  ```json
  { "status": "healthy", "service": "deer-flow-gateway" }
  ```

- nginx 容器内直连 `http://langgraph:2024/ok` 返回：

  ```json
  { "ok": true }
  ```

- 在 `deer-flow-langgraph` 容器里通过 `AioSandboxProvider` 完成 create -> exec -> release 流程，确认创建 sandbox、执行 `echo sandbox-ok`、释放 sandbox 均成功；关键输出如下：

  ```text
  sandbox_use= deerflow.community.aio_sandbox:AioSandboxProvider
  provisioner_url= None
  provider= AioSandboxProvider
  sandbox-ok
  /home/gem
  ```

结论：当前 Mac 上已经可以通过本地 Docker AIO 模式调试 sandbox，不需要 provisioner/Kubernetes，也不需要移植 `chore/qy-dev` 的 OSSFS2 代码改动。
