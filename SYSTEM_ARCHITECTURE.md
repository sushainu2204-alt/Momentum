# Complete Trading System Architecture

## System Overview

The Momentum trading system is a hybrid architecture that uses **Zerodha Kite API as the source of truth** for all real-time data (orders, positions, capital) while maintaining a **local PostgreSQL database for historical records, audit trail, and strategy metadata**.

```
┌─────────────────────────────────────────────────────────────────┐
│                     ZERODHA KITE API                             │
│                   (Source of Truth)                              │
│  - Orders: Real-time order status                               │
│  - Positions: Real-time positions with P&L                       │
│  - Margins: Real-time capital availability                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ Query every 1-30 seconds
                     │ 2-second caching to reduce API load
                     │
┌────────────────────▼────────────────────────────────────────────┐
│                   SERVICE LAYER                                  │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │OrderManager  │  │ PositionMgr  │  │ CapitalMgr   │         │
│  │              │  │              │  │              │         │
│  │- Query orders│  │- Query pos   │  │- Query       │         │
│  │- Place orders│  │- Check exits │  │  margins     │         │
│  │- Cancel      │  │- Calc P&L    │  │- Calc sizes  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         │                   │                   │               │
│         └───────────────────┴───────────────────┘               │
│                             │                                    │
│                  ┌──────────▼──────────┐                        │
│                  │  SignalExecutor     │                        │
│                  │  (Decision Engine)  │                        │
│                  │                     │                        │
│                  │  9 Guardrails:      │                        │
│                  │  1. Market hours    │                        │
│                  │  2. Time window     │                        │
│                  │  3. No position     │                        │
│                  │  4. No pending      │                        │
│                  │  5. Cooldown        │                        │
│                  │  6. Max positions   │                        │
│                  │  7. Position size   │                        │
│                  │  8. Capital check   │                        │
│                  │  9. Place order     │                        │
│                  └──────────┬──────────┘                        │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             │ All decisions logged
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                  POSTGRESQL DATABASE                             │
│                  (Audit Trail + History)                         │
│                                                                  │
│  Tables:                                                         │
│  - orders: Order tracking with Kite order_id                    │
│  - positions: Position lifecycle with P&L                        │
│  - capital_state: Daily capital tracking                         │
│  - trade_logs: All decisions and reasons                         │
│  - cooldown_tracker: Re-entry prevention                         │
│  - signals: Generated signals with metadata                      │
│                                                                  │
│  Views:                                                          │
│  - active_positions: Open positions with details                 │
│  - pending_orders: Orders waiting for fill                       │
│  - todays_trades: All activity for current date                  │
│  - daily_pnl_summary: Aggregated P&L by strategy                │
└──────────────────────────────────────────────────────────────────┘
                             │
                             │ Periodic sync
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                  BACKGROUND SYNC JOBS                            │
│                  (APScheduler)                                   │
│                                                                  │
│  1. Order Sync (every 1 min)                                    │
│     - Fetch orders from Kite → Update DB                        │
│     - Detect fills, rejections, cancellations                   │
│                                                                  │
│  2. Position Sync (every 1 min)                                 │
│     - Fetch positions from Kite → Update P&L in DB              │
│     - Detect manual closures                                    │
│                                                                  │
│  3. Margins Sync (every 30 sec)                                 │
│     - Fetch margins from Kite → Update capital_state            │
│     - Real-time capital availability                            │
│                                                                  │
│  4. Position Monitoring (every 1 min)                           │
│     - Check SL/Target/Time exits                                │
│     - Generate exit signals                                     │
│     - Place exit orders via SignalExecutor                      │
│                                                                  │
│  5. Daily Initialization (9:15 AM)                              │
│     - Initialize capital_state from Kite opening balance        │
└──────────────────────────────────────────────────────────────────┘
                             │
                             │ Signals
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                  STRATEGY WORKERS                                │
│                  (Signal Generators)                             │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │VWAP Breakout │  │VWAP EMA Break│  │Bullish Flag  │         │
│  │Worker        │  │Worker        │  │Worker        │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                  │
│  Each worker:                                                    │
│  - Scans NSE top gainers (every 1 min)                          │
│  - Applies strategy filters                                     │
│  - Generates BUY signals                                        │
│  - Sends to SignalExecutor (if execution mode)                  │
│  - OR saves to file (if signal-only mode)                       │
└──────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Signal Generation → Order Placement

```
1. Worker scans market
   ↓
2. Strategy filters applied
   ↓
3. Signal generated
   ↓
4. SignalExecutor receives signal
   ↓
5. Guardrail 1: Market open? → Query system time
   ↓
6. Guardrail 2: Valid time window? → Check time
   ↓
7. Guardrail 3: No existing position? → PositionManager.has_position()
   │                                     └→ Kite API: kite.positions()
   ↓
8. Guardrail 4: No pending order? → OrderManager.has_pending_order()
   │                                 └→ Kite API: kite.orders()
   ↓
9. Guardrail 5: Not in cooldown? → Database: cooldown_tracker
   ↓
10. Guardrail 6: Below max positions? → CapitalManager.check_position_limit()
    │                                    └→ PositionManager → Kite API
    ↓
11. Guardrail 7: Calculate quantity → CapitalManager.calculate_position_size()
    │                                  └→ Based on 2% risk rule
    ↓
12. Guardrail 8: Capital available? → CapitalManager.can_allocate()
    │                                  └→ Kite API: kite.margins()
    ↓
13. Guardrail 9: Place order → OrderManager.place_order()
    │                           └→ Kite API: kite.place_order()
    ↓
14. Record to database:
    - trade_logs: Decision and reason
    - orders: Order details with Kite order_id
    - cooldown_tracker: Add cooldown for symbol
```

### Position Exit Flow

```
1. Background job: Position Monitoring (every 1 min)
   ↓
2. PositionManager.check_exits(current_time)
   ↓
3. Get open positions from Kite API
   ↓
4. For each position:
   ├─ Get SL/Target from database
   ├─ Get current price from Kite
   ├─ Check conditions:
   │  - Price <= SL? → Generate SELL signal
   │  - Price >= Target? → Generate SELL signal
   │  - Time >= 3:20 PM? → Generate SELL signal
   └─ Return exit signals
   ↓
5. SignalExecutor.execute_exit_signals()
   ├─ For each exit signal:
   │  ├─ Check no pending order (guardrail 4)
   │  ├─ Get quantity from position
   │  └─ Place SELL order via OrderManager
   ↓
6. Order placed to Kite
   ↓
7. Record to database:
   - trade_logs: Exit decision
   - orders: SELL order details
```

### Capital Tracking Flow

```
1. Market open (9:15 AM)
   ↓
2. CapitalManager.initialize_daily_capital()
   └→ Kite API: kite.margins() → Get opening_balance
   ↓
3. Insert into capital_state table:
   - starting_capital (from Kite)
   - available_capital
   - Date stamp
   ↓
4. During trading (every 30 seconds):
   CapitalManager.sync_margins_to_db()
   └→ Kite API: kite.margins()
      ├─ equity.available.cash
      ├─ equity.available.collateral
      ├─ equity.utilised.debits
      ├─ equity.utilised.m2m_realised
      └─ equity.utilised.m2m_unrealised
   ↓
5. Update capital_state table:
   - current_capital
   - available_capital
   - realized_pnl
   - unrealized_pnl
```

## Caching Strategy

To reduce Kite API load while maintaining accuracy:

```
OrderManager:
  - Cache orders for 2 seconds
  - Invalidate on: new order placed, order cancelled, sync job runs

PositionManager:
  - Cache positions for 2 seconds
  - Invalidate on: position created, position closed, sync job runs

CapitalManager:
  - Cache margins for 2 seconds
  - Invalidate on: sync job runs
```

## Operating Modes

### Mode 1: Signal-Only (Original)
```
Worker → Generate signals → Save to JSON files
```
- No database needed
- No orders placed
- Safe for backtesting

### Mode 2: Paper Trading (Recommended)
```
Worker → Generate signals → SignalExecutor (dry_run=True)
  ↓
  9 Guardrails checked
  ↓
  Decisions logged to database
  ↓
  NO real orders placed
```
- Database required
- Validates guardrails
- Shows what WOULD happen
- Safe for testing

### Mode 3: Live Trading
```
Worker → Generate signals → SignalExecutor (dry_run=False)
  ↓
  9 Guardrails checked
  ↓
  REAL orders placed to Kite
  ↓
  Positions tracked
  ↓
  P&L calculated
```
- Database required
- Zerodha authentication required
- REAL capital at risk
- Use ONLY after thorough testing

## Technology Stack

### Core
- **Python 3.13**: Main language
- **AsyncIO**: Async/await for I/O operations
- **APScheduler**: Background job scheduling

### Data Sources
- **Zerodha Kite Connect**: Order placement, positions, margins (source of truth)
- **NSE Data Source**: Top gainers list

### Database
- **PostgreSQL**: Historical records and audit trail
- **asyncpg**: Async PostgreSQL driver

### Services
- **OrderManager**: Order lifecycle management
- **PositionManager**: Position tracking and exits
- **CapitalManager**: Capital and risk management
- **SignalExecutor**: Decision engine with guardrails

### Workers
- **BaseStrategyWorker**: Abstract base for all strategies
- **VWAPBreakoutWorker**: VWAP breakout strategy
- **VWAPEMABreakoutWorker**: VWAP + EMA + breakout strategy
- **BullishFlagWorker**: Bullish flag pattern strategy

## Configuration

### Trading Limits (TradingLimits)
```python
starting_capital: 100000        # ₹1,00,000
max_positions: 5                # Max 5 concurrent positions
position_size_pct: 20           # Max 20% per trade
risk_per_trade_pct: 2           # Max 2% risk per trade
max_capital_at_risk_pct: 10     # Max 10% total risk
```

### Trading Hours (TradingHours)
```python
market_open: 09:15
market_close: 15:30
skip_first_minutes: 15          # Skip 9:15-9:30
skip_last_minutes: 15           # Skip 3:15-3:30
auto_exit_time: 15:20           # Exit all at 3:20 PM
```

## Deployment

### Prerequisites
1. PostgreSQL database
2. Zerodha Kite account with API access
3. Python 3.13+
4. Required Python packages (see requirements.txt)

### Setup Steps
1. Apply database schema (`schema.sql`)
2. Configure Kite API credentials
3. Initialize workers with desired mode
4. Start background sync jobs (if execution mode)
5. Monitor via logs and database queries

### Monitoring
- **Logs**: Real-time worker activity
- **Database**: `trade_logs` table for all decisions
- **Kite Dashboard**: Real-time positions and P&L
- **Daily Reports**: Generated at market close

## Security

### API Credentials
- Kite API key and access token stored securely
- Not committed to version control
- Access token refreshed as needed

### Order Placement
- Guardrails prevent common mistakes
- Cooldown prevents overtrading
- Position limits prevent overexposure
- Capital checks prevent overleveraging

### Audit Trail
- All decisions logged to `trade_logs`
- All orders tracked with Kite order_id
- Timestamps on all records
- Immutable history in database

## Performance

### API Load
- 2-second caching reduces API calls
- Background sync every 30-60 seconds
- Batch operations where possible

### Database
- Indexed on timestamp, symbol, strategy_name
- Views for common queries
- Triggers for automatic updates

### Worker Scheduling
- Each strategy runs independently
- Non-blocking async operations
- Graceful shutdown on interrupt

## Future Enhancements

1. **Multi-account support**: Trade across multiple Zerodha accounts
2. **Advanced exits**: Trailing stop loss, partial exits
3. **Portfolio optimization**: Kelly criterion, risk parity
4. **Machine learning**: Signal quality scoring, parameter optimization
5. **Web dashboard**: Real-time monitoring and control
6. **Alerts**: SMS/email notifications for important events
7. **Backtesting**: Historical simulation with realistic fills
8. **Paper trading competition**: Multiple strategies competing
