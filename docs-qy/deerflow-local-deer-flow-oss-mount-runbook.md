# DeerFlow 本机 `.deer-flow` 挂载 OSS 操作手册

日期：2026-04-29

## 1. 这份文档给谁看

这份文档给下一次需要恢复本机 DeerFlow OSS 挂载的人看，尤其是“隔了一段时间忘记当时怎么弄”的自己。

读完后应该能做到三件事：

1. 看懂现在 `.deer-flow` 到底挂载了什么
2. 判断当前挂载是否正常
3. 在挂载丢失时按步骤恢复

## 2. 一句话结论

当前项目的本机挂载点是：

```bash
/Users/sayori/Desktop/work/deer-flow/backend/.deer-flow
```

它直接挂载到 `.env` 中配置的阿里云 OSS bucket 根目录。

也就是说，OSS bucket 根目录里的：

```text
channels/
skills/
threads/
workspaces/
```

会直接出现在本机：

```text
backend/.deer-flow/channels/
backend/.deer-flow/skills/
backend/.deer-flow/threads/
backend/.deer-flow/workspaces/
```

这不是 README 里说的“只把 `workspaces/` 前缀挂到 `backend/.deer-flow/workspaces`”。这里的约定是：

```text
backend/.deer-flow = OSS bucket 根目录
```

## 3. 为什么没有直接用 ossfs

需求里习惯上叫“挂到 ossfs 上”，但这台机器是 macOS。

实际处理时发现：

- 本机没有可用的 `ossfs` 命令
- Homebrew 里没有直接可用的阿里云 `ossfs` 包
- 阿里云官方 `ossfs2` 更偏 Linux 场景
- macOS 上可行的方案是用 `rclone + FUSE-T`

所以现在的实现是：

```text
阿里云 OSS
  -> rclone Alibaba S3 backend
  -> FUSE-T
  -> backend/.deer-flow
```

从 DeerFlow 的角度看，它只看到一个普通目录：`backend/.deer-flow`。底层到底是 `ossfs` 还是 `rclone + FUSE-T`，对 DeerFlow 没区别。

## 4. 当前机器上已经做过什么

### 4.1 安装了依赖

已经通过 Homebrew 安装：

```bash
brew install rclone fuse-t
```

但 Homebrew 版 rclone 在 macOS 上禁用了 `rclone mount`，所以又下载了官方 rclone 二进制：

```text
/Users/sayori/Desktop/work/deer-flow/.bg-shell/rclone-official/rclone-v1.73.5-osx-arm64/rclone
```

这个官方版带 `cmount`，可以在 macOS 上执行真正的 `rclone mount`。

### 4.2 写了挂载脚本

挂载脚本在：

```text
/Users/sayori/Desktop/work/deer-flow/.bg-shell/mount-deerflow-rclone-runtime.sh
```

它做的事是：

1. 进入项目根目录
2. 读取项目根目录的 `.env`
3. 从 `.env` 里拿到：
   - `ALIYUN_OSS_ENDPOINT`
   - `ALIYUN_OSS_BUCKET`
   - `ALIYUN_OSS_ACCESS_KEY_ID`
   - `ALIYUN_OSS_ACCESS_KEY_SECRET`
4. 把 OSS 配成 rclone 的 Alibaba S3 backend
5. 把 bucket 根目录挂载到 `backend/.deer-flow`

脚本里不写死密钥，只引用 `.env`。

### 4.3 写了 macOS LaunchAgent

为了避免“终端关了挂载就没了”，已经创建用户级 LaunchAgent：

```text
/Users/sayori/Library/LaunchAgents/com.deerflow.rclone.mount.plist
```

它会在登录后自动运行挂载脚本，并保持挂载进程常驻。

当前服务名是：

```text
com.deerflow.rclone.mount
```

## 5. 日常怎么确认挂载正常

在项目根目录执行：

```bash
mount | rg 'deer-flow|fuse-t|rclone|nfs'
```

正常时应该看到类似：

```text
fuse-t:/deerflow{...} shiz-flow on /Users/sayori/Desktop/work/deer-flow/backend/.deer-flow
```

再看 `.deer-flow` 目录：

```bash
ls backend/.deer-flow
```

正常时应该看到：

```text
channels
skills
threads
workspaces
```

再看 LaunchAgent：

```bash
launchctl print gui/$(id -u)/com.deerflow.rclone.mount | sed -n '1,40p'
```

正常时应该看到：

```text
state = running
program = /Users/sayori/Desktop/work/deer-flow/.bg-shell/mount-deerflow-rclone-runtime.sh
```

## 6. 最小读写验证

如果想确认“不只是能列目录，而是真的能同步到 OSS”，可以做一个临时探针。

在项目根目录执行：

```bash
probe=".mount-check-$(date +%s).txt"
echo "hello from local mount" > "backend/.deer-flow/$probe"
cat "backend/.deer-flow/$probe"
rm "backend/.deer-flow/$probe"
```

如果没有报错，说明本机挂载至少具备基本写入、读取、删除能力。

如果要进一步确认它真的到达 OSS，可以用官方 rclone 直接读远端：

```bash
set -a
source ./.env
set +a

export RCLONE_CONFIG_DEERFLOW_TYPE=s3
export RCLONE_CONFIG_DEERFLOW_PROVIDER=Alibaba
export RCLONE_CONFIG_DEERFLOW_ACCESS_KEY_ID="$ALIYUN_OSS_ACCESS_KEY_ID"
export RCLONE_CONFIG_DEERFLOW_SECRET_ACCESS_KEY="$ALIYUN_OSS_ACCESS_KEY_SECRET"
export RCLONE_CONFIG_DEERFLOW_ENDPOINT="$ALIYUN_OSS_ENDPOINT"

.bg-shell/rclone-official/rclone-v1.73.5-osx-arm64/rclone lsf "deerflow:${ALIYUN_OSS_BUCKET}/" --max-depth 1
```

正常输出应该包含：

```text
channels/
skills/
threads/
workspaces/
```

## 7. 挂载丢了怎么恢复

### 7.1 先尝试重启 LaunchAgent

在项目根目录执行：

```bash
label="com.deerflow.rclone.mount"
uid="$(id -u)"
plist="$HOME/Library/LaunchAgents/${label}.plist"

launchctl bootout "gui/$uid/$label" 2>/dev/null || true
launchctl bootstrap "gui/$uid" "$plist"
launchctl kickstart -k "gui/$uid/$label"
```

然后检查：

```bash
mount | rg 'deer-flow|fuse-t|rclone|nfs'
ls backend/.deer-flow
```

如果能看到 `channels skills threads workspaces`，就恢复了。

### 7.2 如果 `.deer-flow` 目录被本地文件占住

挂载点必须是一个空目录，或者至少不能是你想保留的普通本地目录。

如果 `backend/.deer-flow` 里是旧的本地数据，而不是 OSS 内容，请先判断这些数据要不要保留。

保留方式示例：

```bash
mv backend/.deer-flow "backend/.deer-flow.local-before-mount-$(date +%Y%m%d-%H%M%S)"
mkdir -p backend/.deer-flow
```

然后再执行 7.1 的 LaunchAgent 重启流程。

如果你本来就是要删掉旧本地目录，也可以删除后重建空目录：

```bash
rm -rf backend/.deer-flow
mkdir -p backend/.deer-flow
```

注意：这一步会删除本地目录，不会删除 OSS 里的数据。但如果这个目录当时已经是挂载状态，就不要直接 `rm -rf`，先卸载。

## 8. 如何停止挂载

如果只是临时停止：

```bash
launchctl bootout "gui/$(id -u)/com.deerflow.rclone.mount"
```

如果挂载还在，可以再卸载：

```bash
umount /Users/sayori/Desktop/work/deer-flow/backend/.deer-flow
```

停止后再检查：

```bash
mount | rg 'deer-flow|fuse-t|rclone|nfs'
```

没有输出就说明挂载已经不在了。

## 9. 从零重建流程

如果换了一台 Mac，或者 `.bg-shell` 和 LaunchAgent 都没了，可以按这个顺序来。

### 9.1 确认 `.env` 有 OSS 配置

项目根目录 `.env` 至少要有：

```bash
ALIYUN_OSS_ENDPOINT=...
ALIYUN_OSS_BUCKET=...
ALIYUN_OSS_ACCESS_KEY_ID=...
ALIYUN_OSS_ACCESS_KEY_SECRET=...
```

不要把真实密钥写进文档、聊天记录、Git commit 或日志。

### 9.2 安装 FUSE-T 和 rclone

```bash
brew install rclone fuse-t
```

Homebrew 版 rclone 主要用来提供普通 rclone 命令；真正挂载用官方二进制。

### 9.3 下载官方 rclone

```bash
mkdir -p .bg-shell/rclone-official
cd .bg-shell/rclone-official
curl -L --fail --retry 3 -o rclone-current-osx-arm64.zip https://downloads.rclone.org/rclone-current-osx-arm64.zip
unzip -q -o rclone-current-osx-arm64.zip
cd -
```

确认它支持 macOS mount：

```bash
.bg-shell/rclone-official/rclone-v1.73.5-osx-arm64/rclone version
```

输出里应该有：

```text
go/tags: cmount
```

### 9.4 创建挂载脚本

创建：

```text
.bg-shell/mount-deerflow-rclone-runtime.sh
```

内容如下：

```bash
#!/usr/bin/env zsh
set -euo pipefail

cd /Users/sayori/Desktop/work/deer-flow

RCLONE_BIN="$PWD/.bg-shell/rclone-official/rclone-v1.73.5-osx-arm64/rclone"
MOUNT_POINT="$PWD/backend/.deer-flow"

set -a
source ./.env
set +a

export RCLONE_CONFIG_DEERFLOW_TYPE=s3
export RCLONE_CONFIG_DEERFLOW_PROVIDER=Alibaba
export RCLONE_CONFIG_DEERFLOW_ACCESS_KEY_ID="$ALIYUN_OSS_ACCESS_KEY_ID"
export RCLONE_CONFIG_DEERFLOW_SECRET_ACCESS_KEY="$ALIYUN_OSS_ACCESS_KEY_SECRET"
export RCLONE_CONFIG_DEERFLOW_ENDPOINT="$ALIYUN_OSS_ENDPOINT"

exec "$RCLONE_BIN" mount "deerflow:${ALIYUN_OSS_BUCKET}/" "$MOUNT_POINT" \
  --vfs-cache-mode full \
  --vfs-cache-max-age 24h \
  --dir-cache-time 5s \
  --attr-timeout 1s \
  --uid "$(id -u)" \
  --gid "$(id -g)" \
  --file-perms 0666 \
  --dir-perms 0777 \
  --log-level INFO \
  --log-file "$PWD/.bg-shell/rclone-deerflow-mount.log"
```

然后授权：

```bash
chmod 700 .bg-shell/mount-deerflow-rclone-runtime.sh
```

### 9.5 创建 LaunchAgent

创建：

```text
~/Library/LaunchAgents/com.deerflow.rclone.mount.plist
```

内容如下：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.deerflow.rclone.mount</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/sayori/Desktop/work/deer-flow/.bg-shell/mount-deerflow-rclone-runtime.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/sayori/Desktop/work/deer-flow</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/Users/sayori/Desktop/work/deer-flow/.bg-shell/rclone-deerflow-launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/sayori/Desktop/work/deer-flow/.bg-shell/rclone-deerflow-launchd.err.log</string>
</dict>
</plist>
```

加载：

```bash
label="com.deerflow.rclone.mount"
uid="$(id -u)"
plist="$HOME/Library/LaunchAgents/${label}.plist"

launchctl bootstrap "gui/$uid" "$plist"
launchctl kickstart -k "gui/$uid/$label"
```

### 9.6 验证

```bash
mount | rg 'deer-flow|fuse-t|rclone|nfs'
ls backend/.deer-flow
launchctl print gui/$(id -u)/com.deerflow.rclone.mount | sed -n '1,40p'
```

期望：

- `mount` 显示 `.deer-flow` 挂载在 `fuse-t:/...`
- `ls backend/.deer-flow` 显示 `channels skills threads workspaces`
- `launchctl` 显示 `state = running`

## 10. 常见问题

### 10.1 `ls backend/.deer-flow` 是空的

先看挂载是否存在：

```bash
mount | rg 'deer-flow|fuse-t|rclone|nfs'
```

如果没有输出，说明没挂上，按 7.1 重启 LaunchAgent。

如果有输出但目录仍然空，检查日志：

```bash
tail -80 .bg-shell/rclone-deerflow-mount.log
tail -80 .bg-shell/rclone-deerflow-launchd.err.log
```

### 10.2 Homebrew rclone 报 `mount is not supported on MacOS`

这是预期限制。不要用 `/opt/homebrew/bin/rclone mount`。

挂载要用官方二进制：

```bash
.bg-shell/rclone-official/rclone-v1.73.5-osx-arm64/rclone mount ...
```

### 10.3 看到 `Permission denied`

可能原因：

- 挂载点不是当前用户创建的
- 旧挂载残留
- FUSE-T/NFS 桥接状态异常

处理顺序：

```bash
launchctl bootout "gui/$(id -u)/com.deerflow.rclone.mount" 2>/dev/null || true
umount /Users/sayori/Desktop/work/deer-flow/backend/.deer-flow 2>/dev/null || true
mkdir -p /Users/sayori/Desktop/work/deer-flow/backend/.deer-flow
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.deerflow.rclone.mount.plist"
launchctl kickstart -k "gui/$(id -u)/com.deerflow.rclone.mount"
```

### 10.4 日志里出现密钥

不要使用 `--log-level DEBUG` 长期运行挂载，因为 DEBUG 日志可能把环境变量打印出来。

当前脚本使用的是：

```bash
--log-level INFO
```

如果曾经临时开过 DEBUG，记得检查并清理日志：

```bash
grep -n 'ALIYUN_OSS_ACCESS_KEY\|access_key_id\|secret_access_key' .bg-shell/rclone-deerflow-*.log
```

### 10.5 重启电脑后还需要手动挂吗

正常不需要。

`com.deerflow.rclone.mount` 是用户级 LaunchAgent，配置了：

```text
RunAtLoad = true
KeepAlive = true
```

登录当前 macOS 用户后，它应该自动恢复挂载。

## 11. 给 Codex 的注意事项

如果是让 Codex 在这个项目里执行命令，要遵守项目本机指令：shell 命令前加 `rtk`。

例如：

```bash
rtk mount | rtk rg 'deer-flow|fuse-t|rclone|nfs'
```

如果要让 Codex 精确查看挂载目录内容，建议用 `rtk proxy` 绕过输出压缩：

```bash
rtk proxy /bin/ls -1 /Users/sayori/Desktop/work/deer-flow/backend/.deer-flow
```

但如果是人在自己的终端里手动执行，可以直接运行本文中的普通命令，不需要 `rtk`。

## 12. 当前状态快照

最后一次验证时，状态是：

```text
backend/.deer-flow 已挂载到 OSS bucket 根目录
LaunchAgent: com.deerflow.rclone.mount
LaunchAgent state: running
本地目录可见: channels, skills, threads, workspaces
读写删除探针: 通过
```

只要这四项还成立，DeerFlow 本机 `.deer-flow` 到 OSS 的同步链路就是正常的。
