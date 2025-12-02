#!/bin/bash
# =============================================================================
# Momentum Trading System - Daily Startup Script
# =============================================================================
#
# This script starts all components needed for a trading day:
#   1. Docker (PostgreSQL)
#   2. Sync Jobs (order/position sync, capital tracking, EOD exit)
#   3. Strategy Workers (signal generation + execution)
#
# Usage:
#   ./start_trading.sh              # Interactive mode selection
#   ./start_trading.sh paper        # Paper trading mode
#   ./start_trading.sh live         # Live trading mode (requires confirmation)
#   ./start_trading.sh signals      # Signal-only mode (no execution)
#
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Change to script directory
cd "$(dirname "$0")"

# Ensure logs directory exists
mkdir -p logs

# PID file directory
mkdir -p .pids

echo ""
echo -e "${BLUE}=============================================================================${NC}"
echo -e "${BLUE}  MOMENTUM TRADING SYSTEM - Daily Startup${NC}"
echo -e "${BLUE}=============================================================================${NC}"
echo ""

# =============================================================================
# FUNCTIONS
# =============================================================================

check_prerequisites() {
    echo -e "${YELLOW}📋 Checking prerequisites...${NC}"
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker not found. Please install Docker.${NC}"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Docker installed"
    
    # Check Python venv
    if [ ! -d "venv" ]; then
        echo -e "${RED}❌ Virtual environment not found. Run: python -m venv venv${NC}"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Virtual environment exists"
    
    # Check .env file
    if [ ! -f ".env" ]; then
        echo -e "${RED}❌ .env file not found. Copy from .env.example and configure.${NC}"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Environment file exists"
    
    echo ""
}

start_docker() {
    echo -e "${YELLOW}🐳 Starting Docker containers...${NC}"
    
    # Check if containers are already running
    if docker compose ps --format '{{.Status}}' 2>/dev/null | grep -q "Up"; then
        echo -e "  ${GREEN}✓${NC} Docker containers already running"
    else
        docker compose up -d
        echo -e "  ${GREEN}✓${NC} Docker containers started"
        
        # Wait for PostgreSQL to be ready
        echo -e "  ⏳ Waiting for PostgreSQL to be ready..."
        sleep 3
        
        for i in {1..10}; do
            if docker compose exec -T postgres pg_isready -U appuser -d appdb &>/dev/null; then
                echo -e "  ${GREEN}✓${NC} PostgreSQL is ready"
                break
            fi
            sleep 1
        done
    fi
    echo ""
}

start_sync_jobs() {
    echo -e "${YELLOW}🔄 Starting Sync Jobs...${NC}"
    
    # Kill existing sync jobs if running
    if [ -f ".pids/sync_jobs.pid" ]; then
        OLD_PID=$(cat .pids/sync_jobs.pid)
        if kill -0 "$OLD_PID" 2>/dev/null; then
            echo -e "  ⚠️ Stopping existing sync jobs (PID: $OLD_PID)"
            kill "$OLD_PID" 2>/dev/null || true
            sleep 1
        fi
    fi
    
    # Start sync jobs in background
    source venv/bin/activate
    nohup python -m backend.run_sync_jobs > logs/sync_jobs_$(date +%Y%m%d).log 2>&1 &
    SYNC_PID=$!
    echo $SYNC_PID > .pids/sync_jobs.pid
    
    echo -e "  ${GREEN}✓${NC} Sync jobs started (PID: $SYNC_PID)"
    echo -e "  📝 Log: logs/sync_jobs_$(date +%Y%m%d).log"
    echo ""
}

start_workers_paper() {
    echo -e "${YELLOW}📈 Starting Strategy Workers (PAPER TRADING)...${NC}"
    
    # Kill existing workers if running
    if [ -f ".pids/workers.pid" ]; then
        OLD_PID=$(cat .pids/workers.pid)
        if kill -0 "$OLD_PID" 2>/dev/null; then
            echo -e "  ⚠️ Stopping existing workers (PID: $OLD_PID)"
            kill "$OLD_PID" 2>/dev/null || true
            sleep 1
        fi
    fi
    
    source venv/bin/activate
    nohup python -m backend.workers.run_strategy vwap_breakout --mode paper > logs/strategy_worker_$(date +%Y%m%d).log 2>&1 &
    WORKER_PID=$!
    echo $WORKER_PID > .pids/workers.pid
    
    echo -e "  ${GREEN}✓${NC} Paper trading worker started (PID: $WORKER_PID)"
    echo -e "  📝 Log: logs/strategy_worker_$(date +%Y%m%d).log"
    echo ""
}

start_workers_live() {
    echo -e "${RED}📈 Starting Strategy Workers (LIVE TRADING)...${NC}"
    
    # Kill existing workers if running
    if [ -f ".pids/workers.pid" ]; then
        OLD_PID=$(cat .pids/workers.pid)
        if kill -0 "$OLD_PID" 2>/dev/null; then
            echo -e "  ⚠️ Stopping existing workers (PID: $OLD_PID)"
            kill "$OLD_PID" 2>/dev/null || true
            sleep 1
        fi
    fi
    
    source venv/bin/activate
    # Live trading mode - requires CONFIRM in the script itself
    echo "CONFIRM" | python -m backend.workers.run_strategy vwap_breakout --mode live > logs/strategy_worker_$(date +%Y%m%d).log 2>&1 &
    WORKER_PID=$!
    echo $WORKER_PID > .pids/workers.pid
    
    echo -e "  ${GREEN}✓${NC} Live trading worker started (PID: $WORKER_PID)"
    echo -e "  📝 Log: logs/strategy_worker_$(date +%Y%m%d).log"
    echo ""
}

start_workers_signals_only() {
    echo -e "${YELLOW}📊 Starting Strategy Workers (SIGNALS ONLY)...${NC}"
    
    # Kill existing workers if running
    if [ -f ".pids/workers.pid" ]; then
        OLD_PID=$(cat .pids/workers.pid)
        if kill -0 "$OLD_PID" 2>/dev/null; then
            echo -e "  ⚠️ Stopping existing workers (PID: $OLD_PID)"
            kill "$OLD_PID" 2>/dev/null || true
            sleep 1
        fi
    fi
    
    source venv/bin/activate
    nohup python -m backend.workers.run_strategy vwap_breakout --mode signals > logs/strategy_worker_$(date +%Y%m%d).log 2>&1 &
    WORKER_PID=$!
    echo $WORKER_PID > .pids/workers.pid
    
    echo -e "  ${GREEN}✓${NC} Signal-only workers started (PID: $WORKER_PID)"
    echo -e "  📝 Log: logs/strategy_worker_$(date +%Y%m%d).log"
    echo ""
}

show_status() {
    echo -e "${BLUE}=============================================================================${NC}"
    echo -e "${GREEN}  ✅ SYSTEM STARTED SUCCESSFULLY${NC}"
    echo -e "${BLUE}=============================================================================${NC}"
    echo ""
    echo -e "  ${YELLOW}Running Processes:${NC}"
    
    if [ -f ".pids/sync_jobs.pid" ]; then
        SYNC_PID=$(cat .pids/sync_jobs.pid)
        if kill -0 "$SYNC_PID" 2>/dev/null; then
            echo -e "    • Sync Jobs:     PID $SYNC_PID ${GREEN}(running)${NC}"
        else
            echo -e "    • Sync Jobs:     ${RED}(not running)${NC}"
        fi
    fi
    
    if [ -f ".pids/workers.pid" ]; then
        WORKER_PID=$(cat .pids/workers.pid)
        if kill -0 "$WORKER_PID" 2>/dev/null; then
            echo -e "    • Workers:       PID $WORKER_PID ${GREEN}(running)${NC}"
        else
            echo -e "    • Workers:       ${RED}(not running)${NC}"
        fi
    fi
    
    echo ""
    echo -e "  ${YELLOW}Log Files:${NC}"
    echo "    • logs/sync_jobs_$(date +%Y%m%d).log"
    echo "    • logs/strategy_worker_$(date +%Y%m%d).log"
    echo ""
    echo -e "  ${YELLOW}Useful Commands:${NC}"
    echo "    • View logs:     tail -f logs/*.log"
    echo "    • Stop system:   ./stop_trading.sh"
    echo "    • Check DB:      docker compose exec postgres psql -U appuser -d appdb"
    echo ""
    echo -e "${BLUE}=============================================================================${NC}"
}

show_menu() {
    echo "Select trading mode:"
    echo ""
    echo -e "  ${GREEN}1)${NC} Paper Trading  - Full execution flow, no real orders"
    echo -e "  ${YELLOW}2)${NC} Signals Only   - Generate signals, no execution"
    echo -e "  ${RED}3)${NC} Live Trading   - REAL ORDERS (requires confirmation)"
    echo ""
    read -p "Enter choice (1-3): " choice
    echo ""
    
    case $choice in
        1) MODE="paper" ;;
        2) MODE="signals" ;;
        3) MODE="live" ;;
        *) 
            echo -e "${RED}Invalid choice${NC}"
            exit 1
            ;;
    esac
}

# =============================================================================
# MAIN
# =============================================================================

# Parse command line argument
MODE=${1:-""}

# If no mode specified, show menu
if [ -z "$MODE" ]; then
    show_menu
fi

# Run prerequisites
check_prerequisites

# Start Docker
start_docker

# Start Sync Jobs (always needed)
start_sync_jobs

# Start workers based on mode
case $MODE in
    paper)
        echo -e "${GREEN}📋 Mode: PAPER TRADING${NC}"
        echo ""
        start_workers_paper
        ;;
    signals)
        echo -e "${YELLOW}📋 Mode: SIGNALS ONLY${NC}"
        echo ""
        start_workers_signals_only
        ;;
    live)
        echo -e "${RED}📋 Mode: LIVE TRADING${NC}"
        echo ""
        echo -e "${RED}⚠️  WARNING: This will place REAL ORDERS with real money!${NC}"
        read -p "Type 'CONFIRM' to proceed: " confirm
        if [ "$confirm" = "CONFIRM" ]; then
            start_workers_live
        else
            echo -e "${YELLOW}Live trading cancelled. Starting in paper mode instead.${NC}"
            start_workers_paper
        fi
        ;;
    *)
        echo -e "${RED}Unknown mode: $MODE${NC}"
        exit 1
        ;;
esac

# Show status
show_status
