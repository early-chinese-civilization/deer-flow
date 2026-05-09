#!/usr/bin/env bash
# DeerFlow Server Deployment Script
# Usage:
#   ./scripts/server-deploy.sh up       - Build and start all services
#   ./scripts/server-deploy.sh down     - Stop and remove all services
#   ./scripts/server-deploy.sh restart  - Restart all services
#   ./scripts/server-deploy.sh logs     - View all logs
#   ./scripts/server-deploy.sh status   - Show service status
#   ./scripts/server-deploy.sh db-init  - Initialize database and run migrations

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker/docker-compose-server.yaml"

export DEER_FLOW_ROOT="${DEER_FLOW_ROOT:-$PROJECT_DIR}"
export PORT="${PORT:-2026}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $*"; }

check_docker() {
    if ! docker info &>/dev/null; then
        log_error "Docker is not running"
        exit 1
    fi
}

load_env() {
    if [ -f "$PROJECT_DIR/.env" ]; then
        set -a
        # shellcheck disable=SC1091
        . "$PROJECT_DIR/.env"
        set +a
    fi
}

check_env() {
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        log_warn ".env file not found, using defaults"
    fi
    if [ ! -f "$PROJECT_DIR/config.yaml" ]; then
        log_error "config.yaml not found. Run 'make config' first."
        exit 1
    fi
    if [ ! -f "$PROJECT_DIR/extensions_config.json" ]; then
        log_warn "extensions_config.json not found, creating empty"
        echo '{"mcpServers":{},"skills":{}}' > "$PROJECT_DIR/extensions_config.json"
    fi
    mkdir -p "$DEER_FLOW_ROOT/backend/.deer-flow"
}

ensure_auth_secret() {
    local secret_file="$DEER_FLOW_ROOT/backend/.deer-flow/.better-auth-secret"
    if [ -z "${BETTER_AUTH_SECRET:-}" ]; then
        if [ -f "$secret_file" ]; then
            export BETTER_AUTH_SECRET
            BETTER_AUTH_SECRET="$(cat "$secret_file")"
            log_info "BETTER_AUTH_SECRET loaded from $secret_file"
        else
            export BETTER_AUTH_SECRET
            BETTER_AUTH_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
            echo "$BETTER_AUTH_SECRET" > "$secret_file"
            chmod 600 "$secret_file"
            log_info "BETTER_AUTH_SECRET generated -> $secret_file"
        fi
    fi
}

cmd_up() {
    log_info "Starting DeerFlow server deployment..."
    check_docker
    check_env
    ensure_auth_secret

    cd "$PROJECT_DIR"
    load_env

    log_step "Building images..."
    docker compose -f "$COMPOSE_FILE" build

    log_step "Running database migrations..."
    docker compose -f "$COMPOSE_FILE" run --rm \
        -e CI=true \
        gateway sh -c "cd /app/backend && uv run alembic upgrade head" || {
        log_error "Migration failed. Check database connection and config."
        exit 1
    }

    log_step "Starting all services..."
    docker compose -f "$COMPOSE_FILE" up -d

    log_step "Waiting for services to be healthy..."
    for _ in $(seq 1 30); do
        if curl -sf "http://localhost:${PORT}/health" > /dev/null 2>&1; then
            break
        fi
        sleep 2
    done

    echo ""
    log_info "DeerFlow server deployment complete!"
    log_info "Internal health: http://localhost:${PORT}/health"
    log_info "Public access:  http://<server-ip>:${PORT}/"
    echo ""
    log_info "Services:"
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
}

cmd_down() {
    log_info "Stopping DeerFlow server deployment..."
    cd "$PROJECT_DIR"
    load_env
    docker compose -f "$COMPOSE_FILE" down
    log_info "All services stopped."
}

cmd_restart() {
    log_info "Restarting DeerFlow server deployment..."
    cd "$PROJECT_DIR"
    load_env
    docker compose -f "$COMPOSE_FILE" restart
    log_info "Services restarted."
}

cmd_logs() {
    cd "$PROJECT_DIR"
    load_env
    docker compose -f "$COMPOSE_FILE" logs -f "${@:2}"
}

cmd_status() {
    cd "$PROJECT_DIR"
    load_env
    docker compose -f "$COMPOSE_FILE" ps
}

cmd_db_init() {
    log_info "Initializing database..."
    check_docker
    cd "$PROJECT_DIR"
    load_env

    log_step "Running migrations..."
    docker compose -f "$COMPOSE_FILE" run --rm \
        -e CI=true \
        gateway sh -c "cd /app/backend && uv run alembic upgrade head"

    log_info "Database initialization complete."
}

case "${1:-}" in
    up)
        cmd_up
        ;;
    down)
        cmd_down
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        cmd_logs "$@"
        ;;
    status)
        cmd_status
        ;;
    db-init)
        cmd_db_init
        ;;
    *)
        echo "Usage: $0 {up|down|restart|logs|status|db-init}"
        echo ""
        echo "  up       - Build and start all services"
        echo "  down     - Stop and remove all services"
        echo "  restart  - Restart all services"
        echo "  logs     - View all logs (use -f to follow)"
        echo "  status   - Show service status"
        echo "  db-init  - Initialize database and run migrations"
        exit 1
        ;;
esac
