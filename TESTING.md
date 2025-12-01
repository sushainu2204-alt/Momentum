# Testing Guide

Complete testing guide for the Momentum Trading System covering all components from authentication to live signal generation.

## 🎯 Quick Start

Run tests in this order:
1. **Universe Loading** (30 seconds)
2. **Authentication** (5 minutes)
3. **Backtesting** (5-10 minutes)
4. **Live Worker** (optional, market hours only)

## 📋 Test Flows

### 1. Universe Loading Test ⚡ (30 seconds)

**Purpose**: Verify stock universes load correctly from CSV files with fallbacks.

```bash
# Test universe loading
python backend/scripts/manage_universes.py test
```

**Expected Output**:
```
✓ Loaded 143 F&O stocks
✓ Loaded 140 Nifty 500 stocks
✓ Overlap: 140 common stocks
✓ F&O-only: 3 stocks
```

**Success Criteria**:
- ✅ 143 F&O stocks loaded
- ✅ 140 Nifty 500 stocks loaded
- ✅ No errors

---

### 2. Authentication & OAuth Flow 🔐 (5 minutes)

**Purpose**: Test Kite Connect login and token management.

**Prerequisites**: Docker running, Redis container up

#### Steps

**Terminal 1: Start Backend**
```bash
uvicorn backend.main:app --reload
```

**Expected Output**:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
Backend started. Use /connect to get the login URL.
```

**Terminal 2: Get Login URL**
```bash
curl http://localhost:8000/connect
```

**Expected Response**:
```json
{
  "login_url": "https://kite.zerodha.com/connect/login?api_key=...",
  "message": "Visit this URL to login with Zerodha"
}
```

**Browser: Complete Authentication**
1. Visit the `login_url`
2. Login with Zerodha credentials
3. Allow app access
4. You'll be redirected to `/callback`

**Expected Result**:
```
✓ Authentication successful
  User ID: XX1234
  Access token saved to .env
```

**Verify Token Saved**:
```bash
cat .env | grep KITE_ACCESS_TOKEN
```

**Success Criteria**:
- ✅ Login URL generated
- ✅ OAuth flow completes
- ✅ Access token saved to `.env`
- ✅ Backend responds without errors

---

### 3. Backtesting Framework 📈 (5-10 minutes)

**Purpose**: Test strategy with historical data.

**Prerequisites**: Authentication completed (access token in `.env`)

#### Basic Backtest

```bash
# Test last 7 days with default parameters
python backend/backtesting/runner.py --days 7
```

**Expected Output**:
```
============================================================
BACKTEST RUNNER
============================================================
Instrument: NIFTY 50
Days: 7
Capital: ₹100,000.00
============================================================

Fetching historical data...
✓ Loaded data

Running backtest...
✓ Backtest complete

============================================================
BACKTEST RESULTS
============================================================
Initial Capital: ₹100,000.00
Final Capital: ₹102,450.00
Total Return: 2.45%
Total Trades: 12
Winning Trades: 8 (66.67%)
Losing Trades: 4 (33.33%)
...
```

#### Custom Parameters

```bash
# Test with specific parameters
python backend/backtesting/runner.py \
  --days 30 \
  --capital 200000 \
  --position-size 0.9 \
  --export-trades
```

**Expected**:
- Backtest runs successfully
- Results displayed
- Trade log exported to `backtest_trades_*.csv`

**Verify Trade Log**:
```bash
ls -la backtest_trades_*.csv
head -20 backtest_trades_*.csv
```

**Success Criteria**:
- ✅ Backtest runs without errors
- ✅ Historical data fetched
- ✅ Strategy applied correctly
- ✅ P&L calculated
- ✅ Performance metrics displayed
- ✅ Trade log exportable

---

### 4. Live Strategy Worker 🤖 (Market Hours Only)

**Purpose**: Test live tick processing and signal generation.

**Prerequisites**:
- Authentication completed
- Backend running
- Redis running
- **Market hours** (9:15 AM - 3:30 PM IST)

#### Start Live Worker

```bash
# Terminal 1: Backend should be running
# Terminal 2: Start strategy worker
python backend/workers/live_worker.py
```

**Expected Output**:
```
============================================================
LIVE STRATEGY WORKER
============================================================
✅ Worker initialized
  Strategy: Top Gainers Momentum
  Universes: F&O (143), Nifty 500 (140)

📡 Starting live processing...
```

**During Market Hours**:
```
📊 Processing tick: RELIANCE @ ₹2500.00
📈 Enriched with volume data
🔍 Analyzing 5 candidates...
✅ 2 candidates passed filters

🔔 SIGNAL: RELIANCE BUY @ ₹2500.00
   Volume: 15000 (1.8× avg)
   Stock EMA: 9>21 ✓
   Index EMA: 9>21 ✓
```

#### Monitor Redis Signals

```bash
# Terminal 3: Monitor signals
docker exec -it momentum-redis-1 redis-cli SUBSCRIBE signals:trading
```

**Expected Output**:
```
1) "message"
2) "signals:trading"
3) "{\"symbol\":\"RELIANCE\",\"signal_type\":\"BUY\",\"price\":2500.0,...}"
```

**Success Criteria**:
- ✅ Worker starts successfully
- ✅ Universes loaded (143 F&O + 140 Nifty 500)
- ✅ Ticks processed with volume enrichment
- ✅ Filters applied correctly
- ✅ Signals generated and published to Redis
- ✅ Worker logs clear and informative

**Note**: Outside market hours, you won't receive live ticks. Use backtesting instead.

---

### 5. EOD Auto-Exit Testing 🕒 (Market Hours - 3:15 PM)

**Purpose**: Verify automatic position closure before Zerodha's forced square-off.

**Prerequisites**:
- Paper trading mode enabled (`USE_PAPER_TRADING=true`)
- At least one open position approaching 3:15 PM
- Backend and sync jobs running

#### Critical Information

- **Our Exit Time**: 3:15 PM IST (positions closed by our system)
- **Zerodha's Square-Off**: 3:20 PM IST (MIS auto square-off)
- **Buffer**: 5-minute safety margin to maintain control

#### Test Execution

**Terminal 1: Start Backend with Sync Jobs**
```bash
uvicorn backend.main:app --reload
```

**Terminal 2: Monitor Logs**
```bash
# Monitor position manager logs
tail -f logs/app.log | grep -E "(monitor_positions|exit_all|3:15)"
```

**Terminal 3: Verify Open Positions**
```bash
# Check current positions around 3:10 PM
curl http://localhost:8000/api/positions
```

**Expected Output (3:10 PM)**:
```json
{
  "positions": [
    {
      "symbol": "RELIANCE",
      "quantity": 10,
      "average_price": 2450.50,
      "pnl": 125.00
    }
  ]
}
```

#### Auto-Exit Trigger (3:15 PM)

**Expected Behavior**:
1. Background job `_monitor_positions_job()` runs (every 1 minute)
2. `should_exit_all_positions()` returns `True` at 3:15 PM
3. System fetches all open positions from Kite
4. Creates SELL signals for each position
5. Executes exit orders via `execute_exit_signals()`

**Expected Log Output (3:15 PM)**:
```
INFO: Time is 15:15:00, exiting all positions before Zerodha's 3:20 PM square-off
INFO: Fetching current positions for time-based exit...
INFO: Found 1 open position(s) to exit
INFO: Generated exit signal for RELIANCE: SELL 10 @ 2455.00
INFO: Executing exit order for RELIANCE
INFO: Order executed successfully: order_id=240125123456
INFO: Position closed: RELIANCE (Reason: Time-based exit at 3:15 PM)
```

**Verify Positions Closed (3:16 PM)**:
```bash
curl http://localhost:8000/api/positions
```

**Expected Output**:
```json
{
  "positions": []  // All positions closed
}
```

#### Files to Monitor

**1. sync_jobs.py** (`backend/jobs/sync_jobs.py`)
- Function: `_monitor_positions_job()` (line ~195)
- Schedule: Runs every 1 minute during market hours
- Exit trigger: Checks `should_exit_all_positions()` at 3:15 PM

**2. signal_executor.py** (`backend/core/services/signal_executor.py`)
- Function: `should_exit_all_positions()` (line ~351)
- Parameter: `auto_exit_time = time(15, 15)`
- Logic: Returns `True` when current time >= 3:15 PM and market is open

**3. order_manager.py** (`backend/core/services/order_manager.py`)
- Function: Executes exit orders
- Order type: MARKET (immediate execution)
- Product: MIS (positions should already be MIS from entry)

#### Test Checklist

**Pre-Exit (3:10 PM)**:
- [ ] Backend running with sync jobs enabled
- [ ] At least 1 open position exists (paper trading mode)
- [ ] Logs being monitored
- [ ] Current time verified: between 3:10-3:14 PM

**During Exit (3:15 PM)**:
- [ ] `should_exit_all_positions()` returns `True`
- [ ] Background job detects exit condition
- [ ] Exit signals generated for all positions
- [ ] Exit orders executed via Kite API
- [ ] Order IDs logged

**Post-Exit (3:16 PM)**:
- [ ] All positions closed (verify via API)
- [ ] Exit logged in trade_logs table
- [ ] Exit reason: "Time-based exit (3:15 PM - before auto square-off)"
- [ ] No errors in logs

#### Success Criteria

- ✅ Exit triggered automatically at 3:15 PM
- ✅ All positions closed by 3:16 PM
- ✅ Exit orders executed successfully
- ✅ Proper logging throughout the process
- ✅ 5-minute buffer before Zerodha's 3:20 PM square-off
- ✅ No manual intervention required

#### Failure Scenarios & Solutions

**Issue 1: Exit Not Triggered at 3:15 PM**
```bash
# Check background job is running
# Expected: Job scheduled every 1 minute
curl http://localhost:8000/health

# Check system time
date +"%H:%M:%S"  # Should match server time
```

**Issue 2: Exit Triggered But Orders Failed**
```bash
# Check Kite API connection
# Check access token validity
# Verify position exists in Kite (not just locally)
```

**Issue 3: Positions Still Open After 3:15 PM**
```bash
# Check logs for errors
tail -f logs/app.log | grep ERROR

# Manually trigger exit (if needed)
curl -X POST http://localhost:8000/api/exit-all-positions
```

#### Configuration Files

**Environment Variables** (`.env`):
```bash
USE_PAPER_TRADING=true  # Test with paper trading first
KITE_ACCESS_TOKEN=xxxxx  # Valid token required
```

**Signal Executor Config** (`backend/core/services/signal_executor.py`):
```python
auto_exit_time: time = time(15, 15)  # 3:15 PM exit time
```

#### Testing Timeline

| Time | Action | Expected Result |
|------|--------|----------------|
| 3:00 PM | Have open position | Position visible in logs |
| 3:10 PM | Monitor logs | Background job running |
| 3:14 PM | Prepare monitoring | `should_exit_all_positions()` returns `False` |
| **3:15 PM** | **Auto-exit trigger** | **Positions closed** |
| 3:16 PM | Verify closure | All positions = 0 |
| 3:20 PM | Zerodha square-off | Nothing to square-off (already closed) |

#### Critical Notes

⚠️ **IMPORTANT**: This test MUST pass before live trading
⚠️ **Buffer Time**: 5 minutes prevents Zerodha's forced square-off penalties
⚠️ **Paper Trading**: Always test with paper trading first
⚠️ **Manual Override**: Keep `/api/exit-all-positions` endpoint ready as backup

---

## 🔍 Common Issues & Solutions

### Issue: Backend Won't Start

```bash
# Check if port 8000 is in use
lsof -i :8000
kill -9 <PID>

# Restart backend
uvicorn backend.main:app --reload
```

### Issue: Redis Connection Failed

```bash
# Restart Redis
docker-compose restart redis

# Check Redis is running
docker exec -it momentum-redis-1 redis-cli PING
# Expected: PONG
```

### Issue: Universe Loading Fails

```bash
# Test universe loading
python backend/scripts/manage_universes.py test

# Check CSV files exist
ls -la backend/data/universes/

# System uses hardcoded fallbacks, so should work even if CSV is missing
```

### Issue: No Ticks Received (Live Worker)

**Possible Causes**:
1. Market closed (9:15 AM - 3:30 PM IST only)
2. Access token expired (re-authenticate)
3. WebSocket connection issue

**Solution**:
```bash
# Re-authenticate
# Visit http://localhost:8000/connect
# Complete login flow again

# Check market hours
date +%H:%M  # Should be between 09:15 and 15:30 IST
```

### Issue: Import Errors

```bash
# Set Python path
export PYTHONPATH=/Users/sushmagollapudi/Momentum:$PYTHONPATH

# Reinstall dependencies
pip install -r backend/requirements.txt
```

---

## 📊 Testing Priority Matrix

| Flow | Priority | Duration | Market Hours Required |
|------|----------|----------|----------------------|
| 1. Universe Loading | ⭐⭐⭐ High | 30 sec | No |
| 2. Authentication | ⭐⭐⭐ High | 5 min | No |
| 3. Backtesting | ⭐⭐⭐ High | 5-10 min | No |
| 4. Live Worker | ⭐⭐ Medium | 15+ min | **Yes** |

---

## ✅ Quick Validation Checklist

### Pre-flight Checks
- [ ] Docker containers running: `docker ps`
- [ ] Redis running: `docker exec momentum-redis-1 redis-cli PING`
- [ ] `.env` file exists with `KITE_API_KEY`
- [ ] Python dependencies installed: `pip install -r backend/requirements.txt`

### Core Tests (Must Complete)
- [ ] Universe loading: `python backend/scripts/manage_universes.py test`
- [ ] Authentication: Visit `http://localhost:8000/connect` and login
- [ ] Backtesting: `python backend/backtesting/runner.py --days 7`

### Optional Tests
- [ ] Live worker (market hours only): `python backend/workers/live_worker.py`
- [ ] Export trade log: `python backend/backtesting/runner.py --export-trades`

---

## 🚀 Quick Start (5 Minutes)

### Option A: Automated Startup ⭐ **RECOMMENDED**

```bash
# One command to start everything
./start_system.sh

# This automatically:
# - Installs tmux if needed
# - Checks prerequisites
# - Starts Docker containers
# - Launches backend API
# - Starts sync jobs
# - Runs strategy worker
# - Opens monitoring dashboard
```

### Option B: Manual Startup

```bash
# 1. Start Redis
docker-compose up -d redis

# 2. Test universe loading
python backend/scripts/manage_universes.py test

# 3. Start backend
uvicorn backend.main:app --reload &

# 4. Authenticate (visit in browser)
open http://localhost:8000/connect

# 5. Run backtest
python backend/backtesting/runner.py --days 7
```

---

## 📈 Success Metrics

### Functional Metrics
- ✅ Authentication success rate: 100%
- ✅ Universe loading success: 100%
- ✅ Backtest completion rate: 100%
- ✅ Signal generation accuracy: Matches expected filters
- ✅ Zero crashes during normal operation

### Performance Metrics
- ✅ Universe loading time: <1 second
- ✅ Authentication time: <30 seconds
- ✅ Backtest time: <2 minutes for 7 days
- ✅ Signal generation time: <500ms per candidate

---

## 🎓 Pro Tips

1. **Use tmux/screen** for multiple terminals:
   ```bash
   tmux new-session -s momentum
   # Ctrl-B " to split horizontal
   ```

2. **Test during market hours** for live worker validation (9:15 AM - 3:30 PM IST)

3. **Use backtesting** to validate strategy logic without waiting for market hours

4. **Keep logs** for debugging:
   ```bash
   python backend/workers/live_worker.py 2>&1 | tee worker.log
   ```

5. **Monitor Redis** to see signal flow:
   ```bash
   docker exec -it momentum-redis-1 redis-cli MONITOR
   ```

---

## 📝 Next Steps After Testing

1. **If all tests pass**: 
   - System is ready!
   - Review [MAINTENANCE_TODO.md](MAINTENANCE_TODO.md) for recurring tasks
   - Check [CODE_ANALYSIS_AND_FIXES.md](CODE_ANALYSIS_AND_FIXES.md) for technical notes

2. **If any test fails:**
   - Check logs for errors
   - Refer to "Common Issues" section above
   - Review component-specific documentation

---

## 🎛️ Automated System Startup

### Quick Start with Dashboard

```bash
# Start everything with monitoring dashboard
./start_system.sh

# Stop everything
./stop_system.sh
```

### Dashboard Features

The automated startup creates a **tmux 4-pane dashboard**:

1. **Top-Left**: Backend API + Sync Jobs
   - FastAPI server on http://localhost:8000
   - Background sync jobs (orders, positions, margins)

2. **Top-Right**: Strategy Worker
   - VWAP Breakout strategy (paper trading)
   - Signal generation and execution logic

3. **Bottom-Left**: System Logs
   - Real-time log tailing
   - All worker and API logs

4. **Bottom-Right**: Status Monitor
   - Component health checks
   - Signal/order counts
   - Auto-refreshes every 5 seconds

### Navigation

- **Switch panes**: `Ctrl-B` + arrow keys
- **Scroll logs**: `Ctrl-B` + `[`, then arrow keys (press `q` to exit)
- **Detach session**: `Ctrl-B` + `d` (system keeps running)
- **Reattach**: `tmux attach -t momentum`
- **Stop system**: `./stop_system.sh` or `Ctrl-C` in each pane

### Advanced Options

```bash
# Start with specific strategy
./start_system.sh vwap_breakout    # Default
./start_system.sh vwap_ema         # VWAP EMA strategy
./start_system.sh multiple         # Multiple strategies

# Check system status without starting
bash scripts/check_prerequisites.sh

# Monitor status manually
watch -n 5 bash scripts/status_monitor.sh
```

---

**Status**: Ready for testing! 🚀  
**Recommended**: Use `./start_system.sh` for automated startup with monitoring  
**Manual Flow**: Universe loading → Authentication → Backtesting → Live worker
