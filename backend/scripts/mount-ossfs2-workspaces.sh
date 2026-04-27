#!/bin/sh
set -eu

log() {
  printf '[ossfs2-workspaces] %s\n' "$*" >&2
}

is_true() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

is_mounted() {
  grep -qs " $1 " /proc/mounts
}

has_entries() {
  find "$1" -mindepth 1 -print -quit 2>/dev/null | grep -q .
}

make_empty_mountpoint() {
  target="$1"

  if ! has_entries "$target"; then
    return 0
  fi

  backup_base="${DEER_FLOW_OSSFS2_LOCAL_WORKSPACES_BACKUP:-${target}.local-before-ossfs2}"
  backup_path="$backup_base"
  suffix=0
  while [ -e "$backup_path" ]; do
    suffix=$((suffix + 1))
    backup_path="${backup_base}.${suffix}"
  done

  log "moving non-empty mountpoint aside: $target -> $backup_path"
  if mv "$target" "$backup_path" 2>/dev/null; then
    mkdir -p "$target"
    return 0
  fi

  mkdir -p "$target"
  if has_entries "$target"; then
    log "mountpoint is still not empty and cannot be mounted by ossfs2: $target"
    exit 1
  fi
}

write_config() {
  config_path="$1"
  log_dir="$2"
  bucket_prefix="$3"

  umask 077
  cat > "$config_path" <<EOF
--oss_endpoint=${ALIYUN_OSS_ENDPOINT}
--oss_bucket=${ALIYUN_OSS_BUCKET}
--oss_access_key_id=${ALIYUN_OSS_ACCESS_KEY_ID}
--oss_access_key_secret=${ALIYUN_OSS_ACCESS_KEY_SECRET}
--oss_bucket_prefix=${bucket_prefix}

--uid=0
--gid=0
--file_mode=0777
--dir_mode=0777
--allow_other=true

--attr_timeout=1
--negative_timeout=0
--kernel_readdir_cache_timeout=0
--close_to_open=true
--oss_negative_cache_timeout=0

--log_level=info
--log_dir=${log_dir}
EOF
}

if ! is_true "${DEER_FLOW_OSSFS2_WORKSPACES_MOUNT:-false}"; then
  exec "$@"
fi

for name in ALIYUN_OSS_ENDPOINT ALIYUN_OSS_BUCKET ALIYUN_OSS_ACCESS_KEY_ID ALIYUN_OSS_ACCESS_KEY_SECRET; do
  eval "value=\${$name:-}"
  if [ -z "$value" ]; then
    log "missing required environment variable: $name"
    exit 1
  fi
done

if [ ! -e /dev/fuse ]; then
  log "/dev/fuse is missing; run the container with /dev/fuse and SYS_ADMIN"
  exit 1
fi

if [ ! -x /usr/local/bin/ossfs2 ]; then
  log "/usr/local/bin/ossfs2 is missing"
  exit 1
fi

printf 'user_allow_other\n' > /etc/fuse.conf || true

mount_root="${DEER_FLOW_OSSFS2_WORKSPACES_MOUNT_POINT:-${DEER_FLOW_SHARED_FS_ROOT:-/app/backend/.deer-flow}/workspaces}"
bucket_prefix="${DEER_FLOW_OSSFS2_WORKSPACES_PREFIX:-workspaces/}"
config_path="${DEER_FLOW_OSSFS2_WORKSPACES_CONFIG:-/tmp/ossfs2-workspaces-root.conf}"
log_dir="${DEER_FLOW_OSSFS2_WORKSPACES_LOG_DIR:-/tmp/ossfs2-log/workspaces-root}"

mkdir -p "$mount_root" "$log_dir"

if is_mounted "$mount_root"; then
  log "already mounted: $mount_root"
  exec "$@"
fi

make_empty_mountpoint "$mount_root"

write_config "$config_path" "$log_dir" "$bucket_prefix"
chmod 600 "$config_path"

log "mounting $mount_root to OSS prefix $bucket_prefix"
/usr/local/bin/ossfs2 mount "$mount_root" -c "$config_path"

if ! is_mounted "$mount_root"; then
  log "ossfs2 mount did not appear in /proc/mounts"
  exit 1
fi

log "mounted $mount_root"
exec "$@"
