# Backend Tests

Organized test suite for the trading system.

## Test Structure

```
tests/
├── test_comprehensive_verification.py  # ⭐ MAIN TEST - All managers + sync jobs
├── test_database_setup.py              # Database connectivity and schema verification
├── test_managers_integration.py        # Mock tests for all managers
└── test_sync_jobs.py                   # Background sync jobs tests
```

## Running Tests

### 0. Comprehensive Verification Test ⭐ **START HERE**
Complete verification of all managers and sync jobs with real API calls.

```bash
python -m backend.tests.test_comprehensive_verification
```

**What it tests:**
- ✅ Kite API connectivity (profile, margins, holdings, positions, orders)
- ✅ OrderManager: sync, fetch, pending checks (with bracket orders)
- ✅ PositionManager: sync, fetch, position checks
- ✅ CapitalManager: initialize, calculate sizes, enforce limits
- ✅ SignalExecutor: all 9 guardrails with test signal
- ✅ Sync Jobs: all 5 background jobs (manual trigger)
- ✅ Database state: verify all tables and data integrity

**Note:** SL/Target exits are now handled automatically by exchange via bracket orders.

**When to run:** **BEFORE paper trading** - validates entire system

**Requirements:**
- Valid KITE_ACCESS_TOKEN in .env
- Docker containers running
- Best during market hours

---

### 1. Database Setup Test
Verifies schema, tables, repositories working correctly.

```bash
python -m backend.tests.test_database_setup
```

**What it tests:**
- Database connection
- Table existence
- Insert/update/query operations
- Repository methods

**When to run:** After applying schema.sql

---

### 2. Managers Integration Test (Mock)
Tests all managers with mock Kite API - **safe, no real API calls**.

```bash
python -m backend.tests.test_managers_integration
```

**What it tests:**
- OrderManager: place, track, sync orders
- PositionManager: create, update, check exits
- CapitalManager: calculate sizes, enforce limits
- SignalExecutor: all 9 guardrails

**When to run:** During development, before paper trading

---

### 3. Sync Jobs Test
Tests background sync jobs with mock API.

```bash
python -m backend.tests.test_sync_jobs
```

**What it tests:**
- Order sync job
- Position sync job
- Margins sync job
- Position monitoring job
- Daily initialization job

**When to run:** After implementing sync jobs

---

## Test Guidelines

### Quick Validation (10 min) - Recommended
```bash
# Complete system verification with real API
python -m backend.tests.test_comprehensive_verification
```

### Basic Validation (5 min)
```bash
# 1. Verify database
python -m backend.tests.test_database_setup

# 2. Test managers with mocks
python -m backend.tests.test_managers_integration
```

### Pre-Production Testing (15 min)
```bash
# 1. Database check
python -m backend.tests.test_database_setup

# 2. Mock integration
python -m backend.tests.test_managers_integration

# 3. Sync jobs
python -m backend.tests.test_sync_jobs

# 4. Comprehensive verification (real API)
python -m backend.tests.test_comprehensive_verification
```

### Before Live Trading
1. ✅ **Comprehensive verification test passes** ⭐
2. ✅ All mock tests pass
3. ✅ Live integration test passes (optional)
4. ✅ Paper trading run for full market day
5. ✅ Trade logs reviewed for quality
6. ✅ All 9 guardrails validated

---

## Common Issues

**Import errors**: Ensure backend package installed
```bash
pip install -e .
```

**Database connection failed**: Check Docker containers
```bash
docker ps | grep postgres
```

**Kite API authentication error**: Regenerate access token
- Start backend API
- Navigate to `/auth/connect` endpoint
- Complete OAuth flow

**No data during tests**: Run during market hours (9:15 AM - 3:30 PM IST)

---

## CI/CD Integration

Add to GitHub Actions:

```yaml
- name: Run Tests
  run: |
    pip install -e .
    python -m backend.tests.test_database_setup
    python -m backend.tests.test_managers_integration
    python -m backend.tests.test_sync_jobs
  env:
    DATABASE_URL: postgresql://test:test@localhost:5432/testdb
```

Skip `test_comprehensive_verification.py` in CI (requires real Kite credentials).
