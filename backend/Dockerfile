# Backend Development Dockerfile

# UV source image (override for restricted networks that cannot reach ghcr.io)
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.7.20
FROM ${UV_IMAGE} AS uv-source

FROM python:3.12-slim-bookworm

ARG NODE_MAJOR=22
ARG APT_MIRROR
ARG UV_INDEX_URL
ARG OSSFS2_DEB_URL=https://gosspublic.alicdn.com/ossfs/ossfs2_2.0.7_linux_x86_64.deb
ARG OSSFS2_RPM_URL=https://gosspublic.alicdn.com/ossfs/ossfs2_2.0.7_linux_aarch64.rpm
ARG LIBSSL11_DEB_URL_AMD64=https://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.24_amd64.deb
ARG LIBSSL11_DEB_URL_ARM64=https://ports.ubuntu.com/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.24_arm64.deb

# Optionally override apt mirror for restricted networks (e.g. APT_MIRROR=mirrors.aliyun.com)
RUN if [ -n "${APT_MIRROR}" ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list 2>/dev/null || true; \
    fi

# Install system dependencies + Node.js (provides npx for MCP servers)
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    gnupg \
    ca-certificates \
    cpio \
    rpm2cpio \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install ossfs2 so Docker dev containers can mount the shared workspace root
# to the same OSS prefix used by Kubernetes sandboxes.
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      arm64) \
        curl -fsSL "${LIBSSL11_DEB_URL_ARM64}" -o /tmp/libssl1.1.deb; \
        dpkg -i /tmp/libssl1.1.deb; \
        curl -fsSL "${OSSFS2_RPM_URL}" -o /tmp/ossfs2.rpm; \
        cd /; \
        rpm2cpio /tmp/ossfs2.rpm | cpio -idmv; \
        ;; \
      amd64) \
        curl -fsSL "${LIBSSL11_DEB_URL_AMD64}" -o /tmp/libssl1.1.deb; \
        dpkg -i /tmp/libssl1.1.deb; \
        curl -fsSL "${OSSFS2_DEB_URL}" -o /tmp/ossfs2.deb; \
        dpkg -i /tmp/ossfs2.deb; \
        ;; \
      *) \
        echo "Unsupported architecture for ossfs2: $arch" >&2; \
        exit 1; \
        ;; \
    esac; \
    rm -f /tmp/libssl1.1.deb /tmp/ossfs2.rpm /tmp/ossfs2.deb; \
    echo /usr/local/lib64/ossfs2 > /etc/ld.so.conf.d/ossfs2.conf; \
    ldconfig; \
    touch /etc/fuse.conf; \
    grep -qxF user_allow_other /etc/fuse.conf || echo user_allow_other >> /etc/fuse.conf; \
    /usr/local/bin/ossfs2 --version

# Install Docker CLI (for DooD: allows starting sandbox containers via host Docker socket)
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

# Install uv (source image overridable via UV_IMAGE build arg)
COPY --from=uv-source /uv /uvx /usr/local/bin/

COPY backend/scripts/mount-ossfs2-workspaces.sh /usr/local/bin/deer-flow-mount-ossfs2-workspaces.sh
RUN chmod +x /usr/local/bin/deer-flow-mount-ossfs2-workspaces.sh

# Set working directory
WORKDIR /app

# Copy frontend source code
COPY backend ./backend

# Install dependencies with cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    sh -c "cd backend && UV_INDEX_URL=${UV_INDEX_URL:-https://pypi.org/simple} uv sync"

# Expose ports (gateway: 8001, langgraph: 2024)
EXPOSE 8001 2024

# Default command (can be overridden in docker-compose)
CMD ["sh", "-c", "cd backend && PYTHONPATH=. uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001"]
