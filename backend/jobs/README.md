# Background Sync Jobs

Scheduled tasks to keep database synchronized with Zerodha Kite API.

## Overview

The trading system uses a hybrid architecture where Kite API is the source of truth, with local database for historical tracking and audit trail. Background jobs keep the database synchronized.

## Jobs

### 1. Order Sync
- **Frequency**: Every 1 minute
- **During**: Market hours (9:15 AM - 3:30 PM)
- **Purpose**: Sync order status from Kite to database
- **What it does**:
  - Fetches all orders from Kite
  - Updates order status (PENDING → COMPLETE/REJECTED/CANCELLED)
  - Detects filled orders
  - Records manual orders (placed outside our system)

### 2. Position Sync
- **Frequency**: Every 1 minute
- **During**: Market hours (9:15 AM - 3:30 PM)
- **Purpose**: Sync position P&L and detect manual closures
- **What it does**:
  - Fetches all positions from Kite
  - Updates current price and P&L for open positions
  - Detects positions closed manually in Kite
  - Closes corresponding DB records

### 3. Margins Sync
- **Frequency**: Every 30 seconds
- **During**: Market hours (9:15 AM - 3:30 PM)
- **Purpose**: Sync capital state from Kite margins API
- **What it does**:
  - Fetches margins data from Kite
  - Updates available capital, utilized margin
  - Updates realized/unrealized P&L
  - Updates positions count
  - Maintains historical capital state in DB

### 4. Position Monitoring
- **Frequency**: Every 1 minute
- **During**: Market hours (9:15 AM - 3:30 PM)
- **Purpose**: Check exit conditions and place exit orders
- **What it does**:
  - Checks all open positions for:
    - Stop loss hit
    - Target hit
    - Time-based exit (3:20 PM)
  - Generates exit signals
  - Executes exit orders via SignalExecutor
  - Logs all exit decisions

### 5. Daily Initialization
- **Frequency**: Once per day at market open
- **Schedule**: 9:15 AM (Mon-Fri)
- **Purpose**: Initialize capital state for the day
- **What it does**:
  - Fetches opening balance from Kite
  - Creates capital_state record for the day
  - Sets starting capital from Kite account

## Usage

### Starting Jobs

```python
from backend.jobs import SyncJobsScheduler

# Create scheduler with services
scheduler = SyncJobsScheduler(
    order_manager=order_manager,
    position_manager=position_manager,
    capital_manager=capital_manager,
    signal_executor=signal_executor
)

# Start all jobs
scheduler.start()
```

### Stopping Jobs

```python
# Stop all jobs
scheduler.stop()

# Pause jobs (can be resumed)
scheduler.pause()

# Resume jobs
scheduler.resume()
```

### Manual Triggers (for testing)

```python
# Trigger individual jobs manually
await scheduler.trigger_order_sync()
await scheduler.trigger_position_sync()
await scheduler.trigger_margins_sync()
await scheduler.trigger_position_monitoring()
await scheduler.trigger_daily_init()
```

### Job Status

```python
# Get status of all jobs
status = scheduler.get_job_status()
print(status)
# {
#     "running": True,
#     "paused": False,
#     "market_hours": True,
#     "jobs": [
#         {
#             "id": "sync_orders",
#             "name": "Sync Orders from Kite",
#             "next_run": "2025-11-28T10:30:00",
#             "pending": False
#         },
#         ...
#     ]
# }
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Background Jobs                           │
│                  (APScheduler)                               │
└──────────┬──────────────────────────────────────────────────┘
           │
           ├─── Order Sync (1 min)
           │    └─→ OrderManager.sync_orders_from_kite()
           │        └─→ Kite API → Database
           │
           ├─── Position Sync (1 min)
           │    └─→ PositionManager.sync_positions_from_kite()
           │        └─→ Kite API → Database
           │
           ├─── Margins Sync (30 sec)
           │    └─→ CapitalManager.sync_margins_to_db()
           │        └─→ Kite API → Database
           │
           ├─── Position Monitoring (1 min)
           │    └─→ PositionManager.check_exits()
           │        └─→ SignalExecutor.execute_exit_signals()
           │            └─→ OrderManager.place_order()
           │
           └─── Daily Init (9:15 AM)
                └─→ CapitalManager.initialize_daily_capital()
                    └─→ Kite API → Database
```

## Configuration

Jobs are configured in the `SyncJobsScheduler` constructor:

```python
scheduler = SyncJobsScheduler(
    order_manager=order_manager,
    position_manager=position_manager,
    capital_manager=capital_manager,
    signal_executor=signal_executor,
    market_open=time(9, 15),      # Market open time
    market_close=time(15, 30)     # Market close time
)
```

## Market Hours Check

All jobs (except daily initialization) check market hours before running:
- **Weekdays only**: Monday - Friday
- **Time range**: 9:15 AM - 3:30 PM

Jobs will skip execution outside market hours with a debug log.

## Error Handling

Each job has try-except error handling:
- Errors are logged but don't stop the scheduler
- Failed jobs will retry on next scheduled run
- Kite API errors fall back to cached data when available

## Logging

Jobs log at different levels:
- **INFO**: Job start, completion, important actions (exits, fills)
- **DEBUG**: Routine operations, skip reasons
- **WARNING**: Kite API unavailable, fallback to DB
- **ERROR**: Exceptions, failed operations

## Dependencies

- **APScheduler**: Job scheduling framework
- **asyncio**: Async job execution
- Services: OrderManager, PositionManager, CapitalManager, SignalExecutor

## Notes

- Jobs use `max_instances=1` to prevent overlapping executions
- Jobs use `coalesce=True` to merge multiple missed executions
- 2-second caching in services reduces API load
- Margins sync runs more frequently (30s) for capital accuracy
- Position monitoring includes auto-exit at 3:20 PM
