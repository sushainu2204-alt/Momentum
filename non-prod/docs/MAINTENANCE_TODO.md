# Maintenance Tasks & Reminders

TODO:
1. SHould we use webhook callss to update orders insated of syncing???
2. Positions automated right now -- test it clearly
3. We should be running sync jobs always -- we need to etter script to automatically run them
4. How are we calculating indicators?? Are we even using them now, do we have any libraries?
5. check bracket order calculation and placing. focus on the timing...
6. Check if every file is referring to the proper timestamp
7. TRailing stop loss, check the config, should it be same for all satrategies/workers??


Order flow TODO's
1. While squaring off - see order MIS should be placed. SL-M should be cancelled. Check what we are doing while squaring off?

## Recurring Tasks

# TODO : Use api to get these and save in DB
### 📅 Monthly (First Monday)
- [ ] **Update F&O Stock List**
  - Source: https://www.nseindia.com/market-data/equity-derivatives
  - Run: `python -m backend.scripts.manage_universes export`
  - Replace: `backend/data/universes/fno_stocks.csv`
  - Test: `python -m backend.scripts.manage_universes test`

### 📅 Quarterly (Mar/Jun/Sep/Dec - After Index Rebalancing)
- [ ] **Update Nifty 500 List**
  - Source: https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv
  - Download CSV, extract symbol column
  - Replace: `backend/data/universes/nifty500_stocks.csv`
  - Test: `python -m backend.scripts.manage_universes test`

- [ ] **Update Nifty 200 List** (if using separate file)
  - Source: https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv

### 📅 Daily (Before Market Open)
- [ ] **Check Kite Connect Auth**
  - Tokens expire daily at 6 AM
  - Re-authenticate: Visit `http://localhost:8000/login`

### 📅 As Needed
- [ ] **Validate Data Fetching**
  - Run: `PYTHONPATH=/Users/sushmagollapudi/Momentum python test_data_fetching.py`
  - Should see: All 4 tests pass

- [ ] **Check Universe Counts**
  - Run: `python -m backend.scripts.manage_universes stats`
  - Expected: ~150 F&O stocks, ~500 Nifty stocks

---

## Before Backtesting Checklist

- [ ] Kite Connect authenticated (tokens valid)
- [ ] Universe lists up-to-date
- [ ] Validation tests passing (4/4)
- [ ] Config parameters reviewed
- [ ] Date range selected (suggest 6 months min)

**Run backtest:**
```bash
python -m backend.backtesting.top_gainers_backtest \
    --start 2024-06-01 \
    --end 2024-11-26 \
    --capital 100000 \
    --universe fno
```

---

## Before Live Trading Checklist

- [ ] Backtest results validated:
  - [ ] Win rate > 50%
  - [ ] Profit factor > 1.5
  - [ ] Sharpe ratio > 1.0
  - [ ] Max drawdown acceptable

- [ ] Paper trading completed (1-2 weeks)

- [ ] Risk parameters reviewed:
  - [ ] Max concurrent positions
  - [ ] Position size limits
  - [ ] Stop loss % appropriate
  - [ ] Max capital at risk

- [ ] Enable order placement:
  - [ ] Uncomment order APIs in `top_gainers_worker.py`
  - [ ] Test with small quantities first
  - [ ] Monitor first few trades closely

- [ ] Monitoring setup:
  - [ ] Logging configured
  - [ ] Alert system ready
  - [ ] Daily P&L tracking

---

## Known Issues / Watch Items

### Volume Enrichment Performance
- Each candidate requires 1 API call to fetch 10-day avg volume
- With ~20 candidates per scan → ~20 API calls
- Monitor API rate limits (Kite: 3 requests/sec)
- Consider caching daily volumes if performance issue

### Universe Data Quality
- CSV files are static - need manual updates
- Missing stocks won't appear in scans
- Extra stocks will be filtered out by Kite instruments
- **Action:** Set calendar reminders for quarterly updates

### Kite API Token Expiry
- Access tokens expire daily at 6 AM IST
- Live worker will fail if token expired
- **Action:** Implement auto-refresh or daily restart

---

## Quick Commands Reference

```bash
# Test universes
python -m backend.scripts.manage_universes test

# Export current F&O from Kite
python -m backend.scripts.manage_universes export

# Show universe stats
python -m backend.scripts.manage_universes stats

# Run validation tests
PYTHONPATH=/Users/sushmagollapudi/Momentum python test_data_fetching.py

# Run backtest
python -m backend.backtesting.top_gainers_backtest --start YYYY-MM-DD --end YYYY-MM-DD

# Start live worker (paper trading mode - orders commented)
python -m backend.workers.top_gainers_worker
```

---

## File Locations

**Universe Data:**
- `/backend/data/universes/fno_stocks.csv` - F&O stocks (~150)
- `/backend/data/universes/nifty500_stocks.csv` - Nifty 500 stocks

**Utility Scripts:**
- `/backend/scripts/manage_universes.py` - Universe management

**Test Scripts:**
- `/test_data_fetching.py` - Validation tests

**Main Components:**
- `/backend/backtesting/top_gainers_backtest.py` - Backtest runner
- `/backend/workers/top_gainers_worker.py` - Live trading worker
- `/backend/core/strategies/top_gainers_momentum.py` - Strategy logic

---

## Update History

**2024-11-26:** 
- Created maintenance doc
- Updated universe system with CSV files
- Fixed volume filter bug
- Added volume enrichment

**Next Review:** 2024-12-01 (Universe updates)
