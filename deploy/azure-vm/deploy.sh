#!/bin/bash
# =============================================================================
# Quick Deployment Script for Azure VM
# =============================================================================
# This script handles the deployment of the Momentum Trading System.
# Run from the project root directory on your Azure VM.
#
# Usage:
#   ./deploy/azure-vm/deploy.sh [command]
#
# Commands:
#   start     - Build and start all services
#   stop      - Stop all services
#   restart   - Restart all services
#   logs      - View backend logs
#   status    - Show service status
#   update    - Pull latest code and redeploy
#   backup    - Backup the database
# =============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.prod.yml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Change to project root
cd "$PROJECT_ROOT"

# Check if .env exists
check_env() {
    if [ ! -f ".env" ]; then
        log_error "No .env file found!"
        log_info "Creating from template..."
        cp "$SCRIPT_DIR/.env.example" .env
        log_warn "Please edit .env with your credentials before starting!"
        exit 1
    fi
}

# Commands
cmd_start() {
    check_env
    log_info "Starting Momentum Trading System..."
    docker-compose -f "$COMPOSE_FILE" up -d --build
    
    log_info "Waiting for services to be healthy..."
    sleep 10
    
    cmd_status
    echo ""
    log_info "Application started! Access at http://$(curl -s ifconfig.me):8000"
}

cmd_stop() {
    log_info "Stopping Momentum Trading System..."
    docker-compose -f "$COMPOSE_FILE" down
    log_info "All services stopped"
}

cmd_restart() {
    log_info "Restarting Momentum Trading System..."
    docker-compose -f "$COMPOSE_FILE" restart
    cmd_status
}

cmd_logs() {
    docker-compose -f "$COMPOSE_FILE" logs -f --tail=100 backend
}

cmd_status() {
    echo ""
    echo -e "${BLUE}Service Status:${NC}"
    docker-compose -f "$COMPOSE_FILE" ps
    
    echo ""
    echo -e "${BLUE}Health Check:${NC}"
    HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo "Service unavailable")
    echo "$HEALTH"
}

cmd_update() {
    log_info "Pulling latest code..."
    git pull origin main
    
    log_info "Rebuilding and restarting services..."
    docker-compose -f "$COMPOSE_FILE" up -d --build
    
    cmd_status
}

cmd_backup() {
    log_info "Creating database backup..."
    BACKUP_DIR="$PROJECT_ROOT/backups"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    mkdir -p "$BACKUP_DIR"
    
    docker exec momentum-postgres pg_dump -U appuser appdb > "$BACKUP_DIR/db_backup_$TIMESTAMP.sql"
    gzip "$BACKUP_DIR/db_backup_$TIMESTAMP.sql"
    
    log_info "Backup created: $BACKUP_DIR/db_backup_$TIMESTAMP.sql.gz"
}

cmd_help() {
    echo "Momentum Trading System - Deployment Script"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start     Build and start all services"
    echo "  stop      Stop all services"
    echo "  restart   Restart all services"
    echo "  logs      View backend logs (follow mode)"
    echo "  status    Show service status and health"
    echo "  update    Pull latest code and redeploy"
    echo "  backup    Backup the database"
    echo "  help      Show this help message"
}

# Main
case "${1:-help}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    logs)    cmd_logs ;;
    status)  cmd_status ;;
    update)  cmd_update ;;
    backup)  cmd_backup ;;
    help)    cmd_help ;;
    *)
        log_error "Unknown command: $1"
        cmd_help
        exit 1
        ;;
esac
