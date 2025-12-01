#!/bin/bash
# System Testing Menu
# Interactive script to run different test flows

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

clear
echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}         MOMENTUM TRADING SYSTEM - TEST MENU${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

# Function to check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"
    
    # Check Docker
    if docker ps &> /dev/null; then
        echo -e "${GREEN}✓${NC} Docker running"
    else
        echo -e "${RED}✗${NC} Docker not running"
        exit 1
    fi
    
    # Check Redis
    if docker ps | grep -q "momentum-redis-1"; then
        echo -e "${GREEN}✓${NC} Redis container running"
    else
        echo -e "${RED}✗${NC} Redis container not running"
        echo "  Run: docker-compose up -d"
        exit 1
    fi
    
    # Check Postgres
    if docker ps | grep -q "momentum-postgres-1"; then
        echo -e "${GREEN}✓${NC} Postgres container running"
    else
        echo -e "${YELLOW}⚠${NC} Postgres container not running (optional)"
    fi
    
    # Check .env file
    if [ -f .env ]; then
        echo -e "${GREEN}✓${NC} .env file exists"
    else
        echo -e "${RED}✗${NC} .env file missing"
        exit 1
    fi
    
    echo ""
}

# Function to run test flow
run_flow() {
    flow_num=$1
    flow_name=$2
    
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}Running Flow $flow_num: $flow_name${NC}"
    echo -e "${BLUE}============================================================${NC}"
    echo ""
}

# Main menu
show_menu() {
    echo -e "${GREEN}Select test flow to run:${NC}"
    echo ""
    echo "  ${BLUE}Core Flows (Must Test)${NC}"
    echo "  1) Infrastructure Abstractions Test (Quick - 1 min)"
    echo "  2) Authentication & OAuth Flow (5 min)"
    echo "  3) Live Tick Streaming (10 min)"
    echo "  4) Strategy Worker Test (15 min)"
    echo "  7) End-to-End Integration Test (30 min)"
    echo ""
    echo "  ${YELLOW}Optional Flows${NC}"
    echo "  5) Historical Data & Caching (5 min)"
    echo "  6) Backtesting Framework (10 min)"
    echo "  8) Dependency Injection Test (2 min)"
    echo ""
    echo "  ${GREEN}Convenience Options${NC}"
    echo "  a) Run ALL core flows (sequential)"
    echo "  p) Check prerequisites only"
    echo "  s) Start backend server"
    echo "  w) Start strategy worker"
    echo "  h) Show health status"
    echo ""
    echo "  q) Quit"
    echo ""
    read -p "Enter choice: " choice
    echo ""
    
    case $choice in
        1)
            run_flow 1 "Infrastructure Abstractions"
            python test_infrastructure.py
            ;;
        2)
            run_flow 2 "Authentication & OAuth"
            echo -e "${YELLOW}Steps:${NC}"
            echo "1. Backend will start on http://localhost:8000"
            echo "2. Visit http://localhost:8000/connect"
            echo "3. Complete Zerodha login"
            echo "4. Check token saved to .env"
            echo ""
            read -p "Press Enter to start backend..."
            uvicorn backend.main_new:app --reload
            ;;
        3)
            run_flow 3 "Live Tick Streaming"
            echo -e "${YELLOW}Opening Redis monitor...${NC}"
            echo "Watch for tick messages in Redis"
            echo "Press Ctrl-C to stop"
            echo ""
            docker exec -it momentum-redis-1 redis-cli SUBSCRIBE "ticks:*"
            ;;
        4)
            run_flow 4 "Strategy Worker"
            echo -e "${YELLOW}Starting strategy worker...${NC}"
            echo "Watch for signal generation"
            echo "Press Ctrl-C to stop"
            echo ""
            python backend/workers/strategy_worker.py
            ;;
        5)
            run_flow 5 "Historical Data & Caching"
            
            # Create test script
            cat > /tmp/test_historical.py << 'EOF'
from backend.core.services import KiteService, MarketDataService

kite = KiteService()
market = MarketDataService(kite_service=kite)

print("Fetching data (first call - API)...")
df1 = market.fetch_intraday_data(256265, days=5, interval="5minute")
print(f"✓ Fetched {len(df1)} candles")

print("\nFetching data (second call - cache)...")
df2 = market.fetch_intraday_data(256265, days=5, interval="5minute")
print(f"✓ Fetched {len(df2)} candles")

assert len(df1) == len(df2)
print("\n✅ Cache working!")
EOF
            python /tmp/test_historical.py
            rm /tmp/test_historical.py
            ;;
        6)
            run_flow 6 "Backtesting"
            echo -e "${YELLOW}Running backtest with default parameters...${NC}"
            python backend/backtesting/runner.py
            ;;
        7)
            run_flow 7 "End-to-End Integration"
            echo -e "${YELLOW}E2E test requires multiple terminals:${NC}"
            echo ""
            echo "Terminal 1: Backend"
            echo "  $ uvicorn backend.main_new:app --reload"
            echo ""
            echo "Terminal 2: Redis Ticks Monitor"
            echo "  $ docker exec -it momentum-redis-1 redis-cli"
            echo "  > SUBSCRIBE ticks:*"
            echo ""
            echo "Terminal 3: Redis Signals Monitor"
            echo "  $ docker exec -it momentum-redis-1 redis-cli"
            echo "  > SUBSCRIBE signals:trading"
            echo ""
            echo "Terminal 4: Strategy Worker"
            echo "  $ python backend/workers/strategy_worker.py"
            echo ""
            echo "Then: Complete authentication at http://localhost:8000/connect"
            echo ""
            read -p "Press Enter to continue..."
            ;;
        8)
            run_flow 8 "Dependency Injection"
            
            # Create test script
            cat > /tmp/test_di.py << 'EOF'
from backend.infrastructure.cache import InMemoryCache
from backend.infrastructure.messaging import IMessageBroker
from backend.core.services import SignalService
from backend.core.models import Signal
from datetime import datetime
import asyncio

print("Testing Dependency Injection...\n")

# Test InMemoryCache
print("1. Testing InMemoryCache...")
cache = InMemoryCache()
cache.set("test", "value")
assert cache.get("test") == "value"
print("   ✓ InMemoryCache works")

# Test Mock Broker
print("\n2. Testing Mock Broker...")

class MockBroker(IMessageBroker):
    def __init__(self):
        self.published = []
    async def publish(self, channel, message):
        self.published.append((channel, message))
    async def subscribe(self, pattern):
        yield {}
    async def close(self):
        pass

async def test():
    broker = MockBroker()
    service = SignalService(message_broker=broker)
    signal = Signal("NIFTY 50", "BUY", 19500.0, datetime.now())
    await service.publish_signal(signal)
    assert len(broker.published) == 1
    print("   ✓ Mock broker works")

asyncio.run(test())
print("\n✅ Dependency Injection working!")
EOF
            python /tmp/test_di.py
            rm /tmp/test_di.py
            ;;
        a)
            echo -e "${GREEN}Running all core flows...${NC}"
            python test_infrastructure.py
            echo -e "${GREEN}Flow 1 complete. Next: Authentication (manual)${NC}"
            read -p "Press Enter to see instructions..."
            echo ""
            echo "Complete remaining flows manually:"
            echo "  2. Authentication - Start backend, visit /connect"
            echo "  3. Tick Streaming - Monitor Redis"
            echo "  4. Strategy Worker - Start worker"
            echo "  7. E2E - Run all together"
            ;;
        p)
            check_prerequisites
            ;;
        s)
            echo -e "${GREEN}Starting backend server...${NC}"
            uvicorn backend.main_new:app --reload
            ;;
        w)
            echo -e "${GREEN}Starting strategy worker...${NC}"
            python backend/workers/strategy_worker.py
            ;;
        h)
            echo -e "${GREEN}Checking system health...${NC}"
            echo ""
            
            # Check Docker
            echo -n "Docker: "
            if docker ps &> /dev/null; then
                echo -e "${GREEN}✓ Running${NC}"
            else
                echo -e "${RED}✗ Not running${NC}"
            fi
            
            # Check Redis
            echo -n "Redis: "
            if docker exec momentum-redis-1 redis-cli PING &> /dev/null; then
                echo -e "${GREEN}✓ Running${NC}"
            else
                echo -e "${RED}✗ Not running${NC}"
            fi
            
            # Check backend
            echo -n "Backend: "
            if curl -s http://localhost:8000/health &> /dev/null; then
                echo -e "${GREEN}✓ Running${NC}"
                curl -s http://localhost:8000/health | python -m json.tool
            else
                echo -e "${RED}✗ Not running${NC}"
            fi
            
            echo ""
            ;;
        q)
            echo -e "${GREEN}Goodbye!${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice${NC}"
            ;;
    esac
    
    echo ""
    read -p "Press Enter to return to menu..."
    clear
    show_menu
}

# Main execution
check_prerequisites
show_menu
