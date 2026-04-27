#!/usr/bin/env bash
#
# start.sh - Start all DeerFlow development services
#
# Must be run from the repo root directory.

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ---- Load environment variables from .env ----
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    source "$REPO_ROOT/.env"
    set +a
fi

export DEER_FLOW_ROOT="${DEER_FLOW_ROOT:-$REPO_ROOT}"
export K8S_SKILLS_HOST_PATH="${K8S_SKILLS_HOST_PATH:-$REPO_ROOT/backend/.deer-flow/skills}"
export K8S_SHARED_FS_HOST_PATH="${K8S_SHARED_FS_HOST_PATH:-$REPO_ROOT/backend/.deer-flow}"
export K8S_WORKSPACES_HOST_PATH="${K8S_WORKSPACES_HOST_PATH:-$REPO_ROOT/backend/.deer-flow/workspaces}"
export DEER_FLOW_SANDBOX_PROVISIONER_URL="${DEER_FLOW_SANDBOX_PROVISIONER_URL:-http://localhost:8002}"
export DEER_FLOW_SANDBOX_READY_TIMEOUT="${DEER_FLOW_SANDBOX_READY_TIMEOUT:-300}"

# ---- Argument parsing ----

DEV_MODE=true
for arg in "$@"; do
    case "$arg" in
        --dev)  DEV_MODE=true ;;
        --prod) DEV_MODE=false ;;
        *) echo "Unknown argument: $arg"; echo "Usage: $0 [--dev|--prod]"; exit 1 ;;
    esac
done

if $DEV_MODE; then
    FRONTEND_CMD="pnpm run dev"
else
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="python"
    else
        echo "Python is required to generate BETTER_AUTH_SECRET, but neither python3 nor python was found."
        exit 1
    fi
    FRONTEND_CMD="env BETTER_AUTH_SECRET=$($PYTHON_BIN -c 'import secrets; print(secrets.token_hex(16))') pnpm run preview"
fi

# ---- Stop existing services ----

echo "Stopping existing services if any..."
pkill -f "langgraph dev" 2>/dev/null || true
pkill -f "scripts/langgraph_windows.py" 2>/dev/null || true
pkill -f "uvicorn app.gateway.app:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
nginx -c "$REPO_ROOT/docker/nginx/nginx.local.conf" -p "$REPO_ROOT" -s quit 2>/dev/null || true
docker compose -f "$REPO_ROOT/docker/docker-compose-dev.yaml" --profile provisioner stop provisioner 2>/dev/null || true
sleep 1
pkill -9 nginx 2>/dev/null || true
killall -9 nginx 2>/dev/null || true
./scripts/cleanup-containers.sh deer-flow-sandbox 2>/dev/null || true
sleep 1

# ---- Banner ----

echo ""
echo "=========================================="
echo "  Starting DeerFlow Development Server"
echo "=========================================="
echo ""
if $DEV_MODE; then
    echo "  Mode: DEV  (hot-reload enabled)"
    echo "  Tip:  run \`make start\` in production mode"
else
    echo "  Mode: PROD (hot-reload disabled)"
    echo "  Tip:  run \`make dev\` to start in development mode"
fi
echo ""
echo "Services starting up..."
echo "  -> Backend: LangGraph + Gateway"
echo "  -> Provisioner: Sandbox Provisioner"
echo "  -> Frontend: Next.js"
echo "  -> Nginx: Reverse Proxy"
echo ""

# ---- Config check ----

if ! { \
        [ -n "$DEER_FLOW_CONFIG_PATH" ] && [ -f "$DEER_FLOW_CONFIG_PATH" ] || \
        [ -f backend/config.yaml ] || \
        [ -f config.yaml ]; \
    }; then
    echo "[ERROR] No DeerFlow config file found."
    echo "  Checked these locations:"
    echo "    - $DEER_FLOW_CONFIG_PATH (when DEER_FLOW_CONFIG_PATH is set)"
    echo "    - backend/config.yaml"
    echo "    - ./config.yaml"
    echo ""
    echo "  Run 'make config' from the repo root to generate ./config.yaml, then set required model API keys in .env or your config file."
    exit 1
fi

# ---- Auto-upgrade config ----

"$REPO_ROOT/scripts/config-upgrade.sh"

# ---- Cleanup trap ----

cleanup() {
    trap - INT TERM
    echo ""
    echo "Shutting down services..."
    if [ "${SKIP_LANGGRAPH_SERVER:-0}" != "1" ]; then
        pkill -f "langgraph dev" 2>/dev/null || true
        pkill -f "scripts/langgraph_windows.py" 2>/dev/null || true
    fi
    pkill -f "uvicorn app.gateway.app:app" 2>/dev/null || true
    pkill -f "next dev" 2>/dev/null || true
    pkill -f "next start" 2>/dev/null || true
    pkill -f "next-server" 2>/dev/null || true
    docker compose -f "$REPO_ROOT/docker/docker-compose-dev.yaml" --profile provisioner stop provisioner 2>/dev/null || true
    # Kill nginx using the captured PID first (most reliable),
    # then fall back to pkill/killall for any stray nginx workers.
    if [ -n "${NGINX_PID:-}" ] && kill -0 "$NGINX_PID" 2>/dev/null; then
        kill -TERM "$NGINX_PID" 2>/dev/null || true
        sleep 1
        kill -9 "$NGINX_PID" 2>/dev/null || true
    fi
    pkill -9 nginx 2>/dev/null || true
    killall -9 nginx 2>/dev/null || true
    echo "Cleaning up sandbox containers..."
    ./scripts/cleanup-containers.sh deer-flow-sandbox 2>/dev/null || true
    echo "[OK] All services stopped"
    exit 0
}
trap cleanup INT TERM

# ---- Start services ----

mkdir -p logs
mkdir -p temp/client_body_temp temp/proxy_temp temp/fastcgi_temp temp/uwsgi_temp temp/scgi_temp

if $DEV_MODE; then
    LANGGRAPH_EXTRA_FLAGS="--no-reload"
    GATEWAY_EXTRA_FLAGS="--reload --reload-include='*.yaml' --reload-include='.env' --reload-exclude='*.pyc' --reload-exclude='__pycache__' --reload-exclude='sandbox/' --reload-exclude='.deer-flow/'"
else
    LANGGRAPH_EXTRA_FLAGS="--no-reload"
    GATEWAY_EXTRA_FLAGS=""
fi

if [ "${SKIP_LANGGRAPH_SERVER:-0}" != "1" ]; then
    echo "Starting LangGraph server..."
    # Read log_level from config.yaml, fallback to env var, then to "info"
    CONFIG_LOG_LEVEL=$(grep -m1 '^log_level:' config.yaml 2>/dev/null | awk '{print $2}' | tr -d ' ')
    LANGGRAPH_LOG_LEVEL="${LANGGRAPH_LOG_LEVEL:-${CONFIG_LOG_LEVEL:-info}}"

    # Use Windows-compatible launcher on Windows to fix psycopg event loop issue
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
        (cd backend && NO_COLOR=1 uv run python scripts/langgraph_windows.py dev --no-browser --allow-blocking --server-log-level $LANGGRAPH_LOG_LEVEL $LANGGRAPH_EXTRA_FLAGS > ../logs/langgraph.log 2>&1) &
    else
        (cd backend && NO_COLOR=1 uv run langgraph dev --no-browser --allow-blocking --server-log-level $LANGGRAPH_LOG_LEVEL $LANGGRAPH_EXTRA_FLAGS > ../logs/langgraph.log 2>&1) &
    fi

    ./scripts/wait-for-port.sh 2024 60 "LangGraph" || {
        echo "  See logs/langgraph.log for details"
        tail -20 logs/langgraph.log
        if grep -qE "config_version|outdated|Environment variable .* not found|KeyError|ValidationError|config\.yaml" logs/langgraph.log 2>/dev/null; then
            echo ""
            echo "  Hint: This may be a configuration issue. Try running 'make config-upgrade' to update your config.yaml."
        fi
        cleanup
    }
    echo "[OK] LangGraph server started on localhost:2024"
else
    echo "[SKIP] Skipping LangGraph server (SKIP_LANGGRAPH_SERVER=1)"
    echo "   Gateway runtime remains available at /api/langgraph/*"
fi

echo "Starting Sandbox Provisioner..."
docker compose -f "$REPO_ROOT/docker/docker-compose-dev.yaml" --profile provisioner up -d --build provisioner > logs/provisioner.log 2>&1 || {
    echo "[ERROR] Sandbox Provisioner failed to start. Last log output:"
    tail -60 logs/provisioner.log
    cleanup
}
./scripts/wait-for-port.sh 8002 60 "Sandbox Provisioner" || {
    echo "  See logs/provisioner.log for details"
    tail -60 logs/provisioner.log
    docker compose -f "$REPO_ROOT/docker/docker-compose-dev.yaml" --profile provisioner logs --tail=60 provisioner || true
    cleanup
}
echo "[OK] Sandbox Provisioner started on localhost:8002"

echo "Starting Gateway API..."
(cd backend && PYTHONPATH=. uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 $GATEWAY_EXTRA_FLAGS > ../logs/gateway.log 2>&1) &
./scripts/wait-for-port.sh 8001 30 "Gateway API" || {
    echo "[ERROR] Gateway API failed to start. Last log output:"
    tail -60 logs/gateway.log
    echo ""
    echo "Likely configuration errors:"
    grep -E "Failed to load configuration|Environment variable .* not found|config\.yaml.*not found" logs/gateway.log | tail -5 || true
    echo ""
    echo "  Hint: Try running 'make config-upgrade' to update your config.yaml with the latest fields."
    cleanup
}
echo "[OK] Gateway API started on localhost:8001"

echo "Starting Frontend..."
(cd frontend && $FRONTEND_CMD > ../logs/frontend.log 2>&1) &
./scripts/wait-for-port.sh 3000 120 "Frontend" || {
    echo "  See logs/frontend.log for details"
    tail -20 logs/frontend.log
    cleanup
}
echo "[OK] Frontend started on localhost:3000"

echo "Starting Nginx reverse proxy..."
nginx -g 'daemon off;' -c "$REPO_ROOT/docker/nginx/nginx.local.conf" -p "$REPO_ROOT" > logs/nginx.log 2>&1 &
NGINX_PID=$!
./scripts/wait-for-port.sh 2026 10 "Nginx" || {
    echo "  See logs/nginx.log for details"
    tail -10 logs/nginx.log
    cleanup
}
echo "[OK] Nginx started on localhost:2026"

# ---- Ready ----

echo ""
echo "=========================================="
if $DEV_MODE; then
    echo "  [OK] DeerFlow development server is running!"
else
    echo "  [OK] DeerFlow production server is running!"
fi
echo "=========================================="
echo ""
echo "  Application: http://localhost:2026"
echo "  API Gateway: http://localhost:2026/api/*"
echo "  Sandbox Provisioner: http://localhost:8002"
if [ "${SKIP_LANGGRAPH_SERVER:-0}" = "1" ]; then
    echo "  LangGraph: skipped (SKIP_LANGGRAPH_SERVER=1)"
else
    echo "  LangGraph Runtime: http://localhost:2026/api/langgraph/*"
    echo "  Internal LangGraph server: http://localhost:2024"
fi
echo ""
echo "  Logs:"
echo "     - LangGraph: logs/langgraph.log"
echo "     - Provisioner: logs/provisioner.log"
echo "     - Gateway:   logs/gateway.log"
echo "     - Frontend:  logs/frontend.log"
echo "     - Nginx:     logs/nginx.log"
echo ""
echo "Press Ctrl+C to stop all services"

wait
