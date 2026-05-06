#!/usr/bin/env bash
# DeerFlow WSL Deployment Script
# Usage:
#   ./scripts/wsl-deploy.sh up       - Build and start all services
#   ./scripts/wsl-deploy.sh down     - Stop and remove all services
#   ./scripts/wsl-deploy.sh restart  - Restart all services
#   ./scripts/wsl-deploy.sh logs     - View all logs
#   ./scripts/wsl-deploy.sh status   - Show service status
#   ./scripts/wsl-deploy.sh db-init  - Initialize database (run migrations)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker/docker-compose-wsl.yaml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

check_docker() {
    if ! docker info &>/dev/null; then
        log_error "Docker is not running. Please start Docker Desktop first."
        exit 1
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
}

cmd_up() {
    log_info "Starting DeerFlow WSL deployment..."
    check_docker
    check_env

    # Load project .env for compose variable substitution
    if [ -f "$PROJECT_DIR/.env" ]; then
        set -a
        # shellcheck disable=SC1091
        . "$PROJECT_DIR/.env"
        set +a
    fi

    cd "$PROJECT_DIR"

    # Start PostgreSQL first
    log_info "Starting PostgreSQL..."
    docker compose -f "$COMPOSE_FILE" --env-file "$PROJECT_DIR/.env" up -d --build postgres

    # Wait for PostgreSQL to be healthy
    log_info "Waiting for PostgreSQL to be ready..."
    for _ in $(seq 1 30); do
        if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U "${PG_USER:-deerflow}" -d "${PG_DB:-flow}" > /dev/null 2>&1; then
            break
        fi
        sleep 2
    done

    # Create check_point database before gateway starts
    log_info "Creating check_point database..."
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
        psql -U "${PG_USER:-deerflow}" -d "${PG_DB:-flow}" \
        -c "CREATE DATABASE check_point;" 2>/dev/null || log_warn "check_point DB may already exist"

    # Start remaining services
    log_info "Starting all services..."
    docker compose -f "$COMPOSE_FILE" --env-file "$PROJECT_DIR/.env" up -d --build

    # Run migrations
    log_info "Running database migrations..."
    sleep 5
    docker compose -f "$COMPOSE_FILE" exec -T gateway sh -c "cd /app/backend && uv run alembic upgrade head" || {
        log_warn "Migration may have failed or already applied. Check logs."
    }

    # Wait for gateway health check
    log_info "Waiting for gateway to be healthy..."
    for _ in $(seq 1 30); do
        if curl -sf http://localhost:2026/health > /dev/null 2>&1; then
            break
        fi
        sleep 2
    done

    log_info "DeerFlow is starting up..."
    log_info "Access at: http://localhost:2026"
    log_info ""
    log_info "Services:"
    docker compose -f "$COMPOSE_FILE" ps
}

cmd_down() {
    log_info "Stopping DeerFlow WSL deployment..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" down
    log_info "All services stopped."
}

cmd_restart() {
    log_info "Restarting DeerFlow WSL deployment..."
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" restart
    log_info "Services restarted."
}

cmd_logs() {
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" logs -f "${@:2}"
}

cmd_status() {
    cd "$PROJECT_DIR"
    docker compose -f "$COMPOSE_FILE" ps
}

cmd_db_init() {
    log_info "Initializing database..."
    check_docker
    cd "$PROJECT_DIR"

    # Create check_point database
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
        psql -U "${PG_USER:-deerflow}" -d "${PG_DB:-flow}" \
        -c "CREATE DATABASE check_point;" 2>/dev/null || log_warn "check_point DB may already exist"

    # Run migrations
    docker compose -f "$COMPOSE_FILE" exec -T gateway \
        sh -c "cd /app/backend && uv run alembic upgrade head"

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
