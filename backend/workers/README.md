# Strategy Workers

Automated workers that scan the market and generate trading signals for multiple strategies.

## Overview

Workers can operate in two modes:

### Mode 1: Signal-Only (Original)
- ✅ Scans NSE top gainers every minute (9:15 AM - 3:20 PM)
- ✅ Applies strategy-specific filters
- ✅ Generates BUY signals when conditions met
- ✅ Saves signals to JSON files
- ✅ Logs all activity
- ❌ **Does NOT place orders** - signals saved for manual review

### Mode 2: Execution (New)
- ✅ All features from Signal-Only mode
- ✅ Integrates with **SignalExecutor** for automated execution
- ✅ Runs 9 guardrails before placing orders:
  1. Market hours check
  2. Time window check (skip first/last 15 mins)
  3. No existing position check
  4. No pending order check
  5. Cooldown check (no re-entry same day)
  6. Max positions limit (max 5)
  7. Position sizing (based on risk)
  8. Capital availability check
  9. Place order via Zerodha Kite API
- ✅ Tracks positions, P&L, capital in real-time
- ✅ Records all decisions to database
- ✅ Supports **Paper Trading** (dry_run=True) or **Live Trading** (dry_run=False)

## Available Workers

### 1. VWAP Breakout Worker
**Strategy:** Enter when price breaks above VWAP with volume confirmation

**Entry Criteria:**
- Price > VWAP + 0.2%
- Volume > 1.5x average (20 candles)

**Exit:**
- Target: +1.5%
- Stop Loss: -0.7%

**Command:**
```bash
python -m backend.workers.vwap_breakout_worker
```

---

### 2. Bullish Flag Worker
**Strategy:** Enter on breakout after pullback following strong move

**Entry Criteria:**
- Flag pole: +2% move
- Pullback: 0.3-1.5% over 2-5 candles
- Breakout above flag high + 0.1%
- Volume > 1.3x average

**Exit:**
- Target: +1.8%
- Stop Loss: -0.8%

**Command:**
```bash
python -m backend.workers.bullish_flag_worker
```

---

### 3. VWAP EMA Breakout Worker
**Strategy:** Combined VWAP, EMA, and breakout confirmation

**Entry Criteria:**
- Gain: 2-4%
- Price > VWAP
- Price > 20 EMA
- Volume > 1.5x average
- Breakout of previous candle high

**Exit:**
- Target: +1.5%
- Stop Loss: -0.7%

**Command:**
```bash
python -m backend.workers.vwap_ema_breakout_worker
```

---

## Running Workers

### Unified Strategy Runner

All workers are run through a single script:

```bash
# Signal-only mode (save to files, no guardrails)
python -m backend.workers.run_strategy vwap_breakout --mode signals

# Paper trading mode (guardrails, no real orders)
python -m backend.workers.run_strategy vwap_breakout --mode paper

# Live trading mode (REAL ORDERS)
python -m backend.workers.run_strategy vwap_breakout --mode live

# Run ALL strategies
python -m backend.workers.run_strategy all --mode paper
```

### Available Strategies

| Strategy | Description |
|----------|-------------|
| `vwap_breakout` | Enter when price breaks VWAP with volume |
| `vwap_ema` | Combined VWAP + EMA + breakout |
| `bullish_flag` | Flag pattern breakout after pullback |
| `all` | Run all strategies concurrently |

### Execution Modes

| Mode | `use_execution` | `dry_run` | What happens |
|------|-----------------|-----------|--------------|
| `signals` | False | - | Signals saved to files only |
| `paper` | True | True | Guardrails checked, no real orders |
| `live` | True | False | **REAL ORDERS placed** |

### Mode Details

#### 1. Signal-Only Mode
```python
# Only generates and saves signals to file
worker = VWAPBreakoutWorker(use_execution=False)
await worker.start()
```
- Signals saved to `./signals/YYYY-MM-DD/` as JSON
- No database required
- No orders placed
- Use for backtesting or manual trading

#### 2. Paper Trading Mode (Recommended)
```python
# Runs through guardrails, logs decisions, NO real orders
worker = VWAPBreakoutWorker(
    use_execution=True,   # Use SignalExecutor
    dry_run=True          # Don't place real orders
)
await worker.start()
```
- All guardrails tested
- Decisions logged to `trade_logs` table
- Shows what orders WOULD be placed
- Safe for validating strategy logic
- **Recommended before going live**

#### 3. Live Trading Mode
```python
# PLACES REAL ORDERS to Zerodha
worker = VWAPBreakoutWorker(
    use_execution=True,   # Use SignalExecutor
    dry_run=False         # PLACE REAL ORDERS
)
await worker.start()
```
- ⚠️ **PLACES REAL ORDERS** via Zerodha Kite API
- All guardrails enforced
- Real capital at risk
- Positions tracked in real-time
- P&L calculated automatically
- **Use ONLY after thorough paper trading validation**

#### 4. Multiple Strategies
Runs multiple strategies simultaneously, each with independent scheduling.

### Manual Initialization (Advanced)

```python
from backend.workers.vwap_breakout_worker import VWAPBreakoutWorker

# Signal-only
worker = VWAPBreakoutWorker(use_execution=False)

# Paper trading
worker = VWAPBreakoutWorker(use_execution=True, dry_run=True)

# Live trading
worker = VWAPBreakoutWorker(use_execution=True, dry_run=False)

await worker.start()
```

## Schedule

Workers run automatically on trading days (Monday-Friday):

- **9:15 AM**: Market open - Initialize workers
- **9:16 AM - 3:20 PM**: Scan every minute
- **3:30 PM**: Market close - Generate daily report

## Signal Storage

### File Structure
Signals are saved in JSON format:

```
signals/
├── 2025-11-28/
│   ├── vwap_breakout_signals.json
│   ├── bullish_flag_signals.json
│   └── vwap_ema_breakout_signals.json
├── 2025-11-29/
│   ├── vwap_breakout_signals.json
│   ├── bullish_flag_signals.json
│   └── vwap_ema_breakout_signals.json
```

### Signal Format
Each signal contains:

```json
{
  "timestamp": "2025-11-28T10:30:00",
  "symbol": "RELIANCE",
  "instrument_token": 738561,
  "signal_type": "BUY",
  "price": 2450.50,
  "stop_loss": 2433.35,
  "target": 2487.23,
  "quantity": 4,
  "reason": "VWAP breakout with volume confirmation",
  "metadata": {
    "gain_pct": 2.5,
    "volume": 1500000,
    "avg_volume": 950000,
    "vwap": 2445.20,
    "ema_20": 2440.15
  }
}
```

## Logs

Each worker creates detailed logs:

- **Console output**: Real-time monitoring
- **Log files**: `logs/strategy_worker_YYYYMMDD.log` (individual) or `logs/all_workers_YYYYMMDD.log` (combined)

## Database Migration (Future)

The signal storage uses the **Repository Pattern** with proper infrastructure separation:

```
infrastructure/database/
├── base.py              # IDatabase interface
├── signal_repository.py # Signal database operations
├── postgres.py          # PostgreSQL implementation
└── MIGRATION.md         # Complete migration guide
```

**Current: File-based**
```python
storage = SignalStorage(storage_type="file", base_path="./signals")
```

**Future: Database**
```python
from backend.infrastructure.database.postgres import PostgresDatabase

database = PostgresDatabase(db_config)
await database.connect()
storage = SignalStorage(storage_type="database", database=database)
```

**For detailed migration steps, see:**
- `backend/infrastructure/database/MIGRATION.md`
- Database schema in `signal_repository.py`

## Dependencies

Required services:
- **NSE Data Source**: For top gainers (no auth required)
- **Zerodha Kite** (optional): For historical data (requires authentication)

If Zerodha is not available, workers will still generate signals but may have limited data.

## Daily Reports

At market close (3:30 PM), workers generate:

1. **Console summary**: Total signals, by strategy
2. **CSV export**: `signals_report_YYYYMMDD.csv` with all signals

## Example Output

```
======================================================================
🚀 VWAP BREAKOUT WORKER STARTING
======================================================================
Strategy: VWAP Breakout
Scan Interval: 1 minute
Signals saved to: ./signals/
======================================================================

🔔 MARKET OPEN - Starting vwap_breakout
Strategy: VWAP Breakout
Description: Enter when price breaks VWAP with high volume
Risk-Reward: 1:2.14

[10:30:15] 🔍 Scanning market...
Found 20 top gainers
📈 SIGNAL: RELIANCE @ ₹2450.50, SL: ₹2433.35, Target: ₹2487.23, 
   Reason: VWAP breakout (price > VWAP + 0.2%, volume surge 1.58x)
✅ Signal saved: vwap_breakout - RELIANCE @ 2450.50
Signals generated today: 1

[10:31:15] 🔍 Scanning market...
...
```

## Stopping Workers

Press `Ctrl+C` to gracefully stop:

```
^C
🛑 Received interrupt signal, shutting down...
✅ Worker stopped
```

## Troubleshooting

### No signals generated?
- Check if market is open (9:15 AM - 3:20 PM)
- Verify NSE API is accessible
- Check filter criteria (may be too strict)

### Historical data not available?
- Ensure Zerodha Kite is authenticated
- Check `access_token.txt` exists
- Workers can still generate signals from NSE data alone

### Signals not saving?
- Check `./signals/` directory permissions
- Verify disk space available
- Check logs for errors

## Next Steps

1. **Review Signals**: Check `./signals/YYYY-MM-DD/` files
2. **Backtest**: Validate signal quality
3. **Execute Manually**: Place trades based on signals
4. **Automate** (future): Connect to broker API for auto-trading

## Execution Architecture (Mode 2)

When running with `use_execution=True`, workers integrate with the complete order execution system:

```
Worker (Signal Generator)
    ↓
SignalExecutor (Decision Engine)
    ├─→ 9 Guardrails Check
    │   1. Market hours
    │   2. Time window (skip first/last 15 mins)
    │   3. No existing position (via PositionManager → Kite API)
    │   4. No pending order (via OrderManager → Kite API)
    │   5. Cooldown check (database)
    │   6. Max positions limit (via CapitalManager)
    │   7. Position sizing calculation (based on risk)
    │   8. Capital availability (via CapitalManager → Kite margins API)
    │   9. Place order (via OrderManager → Kite API)
    ↓
Kite API (Order Placement)
    ↓
Database (Audit Trail)
    - trade_logs: All decisions
    - orders: Order tracking
    - positions: Position tracking
    - capital_state: Capital tracking
```

### Services Initialized in Execution Mode

1. **PostgresDatabase**: Database connection
2. **OrderManager**: Order lifecycle management with Kite
3. **PositionManager**: Position tracking with exit checks
4. **CapitalManager**: Real-time capital from Kite margins API
5. **SignalExecutor**: Decision engine with guardrails

### Real-Time Data Sources

All managers query **Zerodha Kite API** as source of truth:
- **Orders**: `kite.orders()` - Real-time order status
- **Positions**: `kite.positions()` - Real-time positions with P&L
- **Margins**: `kite.margins()` - Real-time capital availability

Local database serves as audit trail and historical record.

## Safety Notes

### Signal-Only Mode (use_execution=False)
✅ **Safe for experimentation**
- No orders placed
- No database required
- No capital at risk
- Signals saved for manual review

### Paper Trading Mode (use_execution=True, dry_run=True)
✅ **Safe for validation**
- All guardrails tested
- Database required (for logging)
- No real orders placed
- Logs show what WOULD happen
- **Recommended before going live**

### Live Trading Mode (use_execution=True, dry_run=False)
⚠️ **REAL CAPITAL AT RISK**
- Places REAL orders to Zerodha
- Real money used
- Positions tracked automatically
- Requires:
  - PostgreSQL database configured
  - Zerodha Kite authenticated
  - Sufficient capital in account
  - Thorough paper trading validation
- **Use ONLY after extensive testing**

### General Trading Safety
- Always validate signals before trading
- Use appropriate position sizing (default: 2% risk per trade)
- Never risk more than you can afford to lose
- Monitor positions actively
- Have stop losses in place
- Understand the strategy before running live
- Start with small capital to test
- Review trade_logs regularly
