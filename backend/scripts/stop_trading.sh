#!/bin/bash
# =============================================================================
# Momentum Trading System - Stop Script
# =============================================================================
#
# Stops all running components:
#   1. Strategy Workers
#   2. Sync Jobs
#   3. Docker containers (optional)
#
# Usage:
#   ./stop_trading.sh           # Stop workers and sync jobs (keep Docker)
#   ./stop_trading.sh --all     # Stop everything including Docker
#
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Change to project root (parent of scripts directory)
cd "$(dirname "$0")/../.."

echo ""
echo -e "${BLUE}=============================================================================${NC}"
echo -e "${BLUE}  MOMENTUM TRADING SYSTEM - Shutdown${NC}"
echo -e "${BLUE}=============================================================================${NC}"
echo ""

# Stop workers
if [ -f ".pids/workers.pid" ]; then
    WORKER_PID=$(cat .pids/workers.pid)
    if kill -0 "$WORKER_PID" 2>/dev/null; then
        echo -e "${YELLOW}Stopping strategy workers (PID: $WORKER_PID)...${NC}"
        kill "$WORKER_PID" 2>/dev/null || true
        sleep 1
        echo -e "  ${GREEN}✓${NC} Workers stopped"
    else
        echo -e "  ${YELLOW}Workers not running${NC}"
    fi
    rm -f .pids/workers.pid
else
    echo -e "  ${YELLOW}No worker PID file found${NC}"
fi

# Stop sync jobs
if [ -f ".pids/sync_jobs.pid" ]; then
    SYNC_PID=$(cat .pids/sync_jobs.pid)
    if kill -0 "$SYNC_PID" 2>/dev/null; then
        echo -e "${YELLOW}Stopping sync jobs (PID: $SYNC_PID)...${NC}"
        kill "$SYNC_PID" 2>/dev/null || true
        sleep 1
        echo -e "  ${GREEN}✓${NC} Sync jobs stopped"
    else
        echo -e "  ${YELLOW}Sync jobs not running${NC}"
    fi
    rm -f .pids/sync_jobs.pid
else
    echo -e "  ${YELLOW}No sync jobs PID file found${NC}"
fi

# Stop Docker if --all flag is passed
if [ "$1" = "--all" ]; then
    echo ""
    echo -e "${YELLOW}Stopping Docker containers...${NC}"
    docker compose down
    echo -e "  ${GREEN}✓${NC} Docker containers stopped"
fi

echo ""
echo -e "${GREEN}=============================================================================${NC}"
echo -e "${GREEN}  ✅ SYSTEM STOPPED${NC}"
echo -e "${GREEN}=============================================================================${NC}"
echo ""

# Show any remaining Python processes (in case of stragglers)
REMAINING=$(pgrep -f "backend\.(jobs\.run_sync_jobs|workers)" 2>/dev/null || true)
if [ -n "$REMAINING" ]; then
    echo -e "${YELLOW}⚠️  Some processes may still be running:${NC}"
    echo "$REMAINING"
    echo ""
    echo "To force kill all: pkill -f 'backend\.(jobs\.run_sync_jobs|workers)'"
fi
