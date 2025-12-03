# Backend Scripts

Operational scripts for running the trading system.

## Scripts

| Script | Purpose |
|--------|---------|
| `start_trading.sh` | Start all trading components (Docker, sync jobs, workers) |
| `stop_trading.sh` | Stop all running components |
| `run_sync_jobs.sh` | Run sync jobs directly (wrapper for backend/jobs/run_sync_jobs.py) |

## Usage

All scripts should be run from the project root:

```bash
# Start trading system
./backend/scripts/start_trading.sh

# With specific mode
./backend/scripts/start_trading.sh paper    # Paper trading
./backend/scripts/start_trading.sh signals  # Signals only
./backend/scripts/start_trading.sh live     # Live trading (requires confirmation)

# Stop trading system
./backend/scripts/stop_trading.sh

# Stop everything including Docker
./backend/scripts/stop_trading.sh --all
```

## Logs

All logs are written to `non-prod/logs/`:
- `sync_jobs_YYYYMMDD.log`
- `strategy_worker_YYYYMMDD.log`
- `app_YYYYMMDD.log` (application logs)
