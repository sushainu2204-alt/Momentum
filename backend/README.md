# Trading System Backend

Clean architecture trading system with order execution and position management.

## Architecture

```
backend/
├── infrastructure/          # External dependencies
│   ├── database/           # PostgreSQL + repositories
│   └── data_sources/       # NSE, Zerodha APIs
├── core/                   # Business logic
│   ├── services/           # Order, Position, Capital, Signal execution
│   ├── strategies/         # Trading strategies
│   └── config/             # Configuration
├── workers/                # Background workers
├── jobs/                   # Sync jobs (orders, positions, margins)
└── api/                    # REST API
```

## Database

Schema in `infrastructure/database/schema.sql`. Apply with:

```bash
docker exec momentum-postgres-1 psql -U appuser -d appdb -f /path/to/schema.sql
```

**Tables**: positions, orders, capital_state, trade_logs, cooldown_tracker, signals

## Core Services

1. **OrderManager** - Place/track orders via Kite API
2. **PositionManager** - Track positions and P&L
3. **CapitalManager** - Enforce capital/risk limits (5 positions max, 20% per trade)
4. **SignalExecutor** - Decision engine with 9 guardrails

## Trading Modes

### 1. Signal Only (Current)
Workers generate signals saved to files/DB. No execution.

```bash
cd workers && python run_workers.py
# Select option 1
```

### 2. Paper Trading
Full execution system without real orders. Validates all guardrails.

```bash
cd workers && python run_workers.py
# Select option 2
```

Monitor: Check `trade_logs` table for all decisions.

### 3. Live Trading
⚠️ **Real money**. Start small (₹10k-₹25k). Active monitoring required.

```bash
cd workers && python run_workers.py
# Select option 3, type "CONFIRM"
```

## Testing

```bash
# Database setup verification
python -m backend.tests.test_database_setup

# Mock integration tests
python -m backend.tests.test_managers_integration

# Live API tests (requires valid Kite token)
python -m backend.tests.test_live_integration

# Sync jobs tests
python -m backend.tests.test_sync_jobs
```

## Configuration

`.env` file:
```
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_secret
KITE_ACCESS_TOKEN=your_token
DATABASE_URL=postgresql://appuser:secret@localhost:5432/appdb
REDIS_URL=redis://localhost:6379/0
```

## Key Rules

- **Max 5 positions** simultaneously
- **20% capital per trade** maximum
- **2% risk per trade** (for position sizing)
- **Cooldown**: No re-entry same day
- **Time window**: Skip first/last 15 minutes
- **Auto-exit**: 3:20 PM all positions

## Next Steps

1. Apply database schema
2. Run paper trading to validate guardrails
3. Review `trade_logs` for decision quality
4. Start live with small capital when confident

See `ARCHITECTURE.md` for detailed design patterns.
