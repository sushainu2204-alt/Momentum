# Infrastructure Organization

## Overview

The codebase now follows proper **separation of concerns** with the infrastructure layer handling all external dependencies like databases, APIs, caching, and messaging.

## Current Structure

```
backend/
├── infrastructure/          # External dependencies & integrations
│   ├── database/           # Database abstraction & implementations
│   │   ├── base.py                # IDatabase interface (abstract)
│   │   ├── signal_repository.py   # Signal DB operations
│   │   ├── postgres.py            # PostgreSQL implementation
│   │   ├── MIGRATION.md           # Database migration guide
│   │   └── __init__.py
│   ├── data_sources/       # NSE, Zerodha, etc.
│   ├── cache/              # Caching layer
│   └── messaging/          # Message queues
│
├── core/                   # Business logic
│   ├── services/           # Application services
│   │   └── signal_storage.py     # Storage abstraction (file or DB)
│   ├── strategies/         # Trading strategies
│   └── config/             # Strategy configurations
│
└── workers/                # Background workers
    ├── base_strategy_worker.py    # Base worker class
    ├── vwap_breakout_worker.py    # VWAP strategy worker
    ├── bullish_flag_worker.py     # Bullish flag worker
    ├── vwap_ema_breakout_worker.py # VWAP EMA worker
    └── run_all_workers.py         # Multi-strategy launcher
```

## Architecture Patterns

### 1. Repository Pattern
**Location:** `infrastructure/database/signal_repository.py`

Encapsulates all database operations for signals:
- `save_signal()` - Insert signal
- `get_signals_by_date()` - Query by date
- `get_signals_by_symbol()` - Query by symbol
- `get_signals_by_strategy()` - Query by strategy
- `get_daily_summary()` - Aggregate statistics

**Benefits:**
- Business logic doesn't know about SQL
- Easy to mock for testing
- Can swap database implementations

### 2. Dependency Injection
**Location:** `core/services/signal_storage.py`

Storage service accepts database instance via constructor:

```python
# File-based (default)
storage = SignalStorage(storage_type="file")

# Database-based
storage = SignalStorage(storage_type="database", database=postgres_db)
```

**Benefits:**
- Loose coupling
- Easy testing with mock database
- Runtime configuration

### 3. Interface Segregation
**Location:** `infrastructure/database/base.py`

`IDatabase` interface defines contract for any database:

```python
class IDatabase(ABC):
    async def connect(self): ...
    async def disconnect(self): ...
    async def fetch_one(self, query, params): ...
    async def fetch_all(self, query, params): ...
    async def insert(self, table, data): ...
    async def update(self, table, data, where): ...
    async def delete(self, table, where): ...
```

**Current Implementations:**
- `PostgresDatabase` (postgres.py)

**Future Implementations:**
- SQLite, MySQL, MongoDB, etc.

### 4. Strategy Pattern
**Location:** `core/strategies/`

Each strategy extends `BaseStrategy`:
- `VWAPBreakoutStrategy`
- `BullishFlagStrategy`
- `VWAPEMABreakoutStrategy`

Workers use strategies without knowing implementation details.

## Data Flow

### File Storage (Current)
```
Worker → SignalStorage → JSON File
                ↓
        ./signals/YYYY-MM-DD/strategy_signals.json
```

### Database Storage (Future)
```
Worker → SignalStorage → SignalRepository → PostgresDatabase → PostgreSQL
                                  ↓
                          Uses IDatabase interface
```

## Key Benefits of This Organization

### 1. Testability
```python
# Mock database for testing
class MockDatabase(IDatabase):
    async def insert(self, table, data):
        return 1  # Mock ID

storage = SignalStorage(storage_type="database", database=MockDatabase())
```

### 2. Flexibility
Switch storage without changing worker code:
```python
# Development: File storage
storage = SignalStorage(storage_type="file")

# Production: Database storage
storage = SignalStorage(storage_type="database", database=prod_db)
```

### 3. Scalability
Add new database implementations without touching business logic:
```python
# Add TimescaleDB (optimized for time-series)
class TimescaleDatabase(IDatabase):
    # Implement interface methods
    ...

storage = SignalStorage(storage_type="database", database=timescale_db)
```

### 4. Maintainability
- **Infrastructure changes** → Only touch `infrastructure/` folder
- **Business logic changes** → Only touch `core/` folder
- **Worker changes** → Only touch `workers/` folder

## Migration Path

Workers remain unchanged during migration:

```python
# Workers code (no changes needed)
await self.storage.save_signal(signal, strategy_name, metadata)
```

Only change configuration:

```python
# Before (file)
storage = SignalStorage(storage_type="file")

# After (database)
database = PostgresDatabase(config)
await database.connect()
storage = SignalStorage(storage_type="database", database=database)
```

## File Organization Checklist

✅ **Infrastructure Layer** (`infrastructure/`)
- [x] Database abstraction (IDatabase interface)
- [x] PostgreSQL implementation
- [x] Signal repository
- [x] Migration guide
- [x] Data sources (NSE, Zerodha)

✅ **Core Layer** (`core/`)
- [x] Signal storage service
- [x] Trading strategies
- [x] Strategy configurations
- [x] Models (Signal, Candidate, etc.)

✅ **Workers Layer** (`workers/`)
- [x] Base strategy worker
- [x] 3 concrete strategy workers
- [x] Multi-strategy launcher
- [x] Documentation

## Next Steps

1. **For Development**: Continue using file storage
   - No additional dependencies
   - Easy to inspect signals (JSON files)
   - Simple debugging

2. **For Production**: Migrate to database
   - Follow `infrastructure/database/MIGRATION.md`
   - Install PostgreSQL and asyncpg
   - Update worker configuration
   - Run migration scripts

3. **For Testing**: Use mock database
   - Implement `IDatabase` interface
   - Return mock data
   - No actual database needed

## Questions?

- **Database setup**: See `infrastructure/database/MIGRATION.md`
- **Worker usage**: See `workers/README.md`
- **Adding new database**: Extend `IDatabase` interface
- **Switching storage**: Update worker configuration only
