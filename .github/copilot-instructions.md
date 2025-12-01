# GitHub Copilot Instructions

## Project Context

Clean up and update the documentations if something has changed in the codebase. 
Do not cretae unncessary run files/test files/documenttaion. Lets keep them crisp and to the point.

Python-based trading system using:
- **Language**: Python 3.13
- **Framework**: FastAPI (backend), APScheduler (workers)
- **Architecture**: Clean/layered architecture with separation of concerns

---

## Architecture Principles

### Layer Separation

```
infrastructure/     ← External dependencies (DB, APIs, cache, messaging)
core/              ← Business logic (NO external dependencies)
workers/           ← Background jobs/workers
models/            ← Domain models
api/               ← REST API endpoints
```

**Critical Rule**: Core business logic must NEVER directly import external libraries (psycopg2, requests, etc.). Always use abstraction layers in `infrastructure/`.

### Dependency Flow

```
Workers/API → Core Services → Infrastructure
                ↓
         Core Strategies
```

- Workers and API depend on core services
- Core services use infrastructure through interfaces
- Strategies contain pure business logic

---

## Code Standards

### 1. Type Hints (Mandatory)

Always use type hints for function signatures:

```python
# ✅ CORRECT
def save_signal(
    self,
    signal: Signal,
    strategy_name: str,
    metadata: Optional[Dict[str, Any]] = None
) -> int:
    pass

# ❌ WRONG - No type hints
def save_signal(self, signal, strategy_name, metadata=None):
    pass
```

### 2. Async/Await Consistency

Use async for I/O operations only:

```python
# ✅ I/O operations - use async
async def save_to_database(self, data: Dict) -> int:
    return await self.db.insert("table", data)

async def fetch_api_data(self, url: str) -> Dict:
    async with aiohttp.ClientSession() as session:
        response = await session.get(url)
        return await response.json()

# ✅ Pure computation - NO async
def calculate_vwap(self, df: pd.DataFrame) -> float:
    return (df['close'] * df['volume']).sum() / df['volume'].sum()

# ❌ WRONG - Can't mix sync/async
def save_signal(self):  # sync function
    await self.db.insert(...)  # Can't await in sync!
```

### 3. Error Handling by Layer

**Infrastructure Layer**: Log and raise (let caller decide)
```python
async def save_signal(self, signal: Signal) -> int:
    try:
        return await self.db.insert("signals", data)
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise  # Don't swallow, let caller handle
```

**Service Layer**: Log and return safe defaults
```python
async def get_signals(self, date: datetime) -> List[Dict]:
    try:
        return await self.repository.get_signals_by_date(date)
    except Exception as e:
        logger.error(f"Failed to retrieve signals: {e}")
        return []  # Safe default, don't crash
```

**Worker Layer**: Log and continue
```python
async def scan_market(self):
    try:
        signals = await self.generate_signals()
        await self.storage.save_signal(signal)
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        # Continue to next scan, don't stop worker
```

### 4. Logging Levels

Use appropriate log levels:

```python
logger.info("Signal saved: RELIANCE @ 2450.50")      # Normal operations
logger.warning("Kite token expired, refreshing...")   # Recoverable issues
logger.error("Failed to save signal: {e}")            # Failed operations
logger.debug("Fetching data for RELIANCE 9:15-9:20") # Detailed diagnostics
```

### 5. Dependency Injection

Always inject dependencies via constructor:

```python
# ✅ CORRECT - Dependency injected
class SignalStorage:
    def __init__(
        self,
        storage_type: str = "file",
        database: Optional[IDatabase] = None  # Injected
    ):
        self.database = database
        self.repository = SignalRepository(database) if database else None

# ❌ WRONG - Hard-coded dependency
class SignalStorage:
    def __init__(self):
        self.db = PostgresDatabase()  # Hard-coded!
```

### 6. Configuration Over Hard-Coding

Use configuration objects for parameters:

```python
# ✅ CORRECT - Configuration driven
class VWAPBreakoutStrategy(BaseStrategy):
    def __init__(self, config: VWAPBreakoutConfig):
        super().__init__(config)
        self.volume_multiplier = config.volume_multiplier
        self.breakout_pct = config.vwap_breakout_pct

# ❌ WRONG - Hard-coded values
class VWAPBreakoutStrategy:
    def __init__(self):
        self.volume_multiplier = 1.5  # Hard-coded!
```

---

## Database Pattern

### Repository Pattern (Required)

All database operations must use repository pattern:

```python
# ✅ CORRECT - Repository in infrastructure/database/
class SignalRepository:
    def __init__(self, database: IDatabase):
        self.db = database
    
    async def save_signal(self, signal: Signal) -> int:
        data = {
            "timestamp": signal.timestamp,
            "symbol": signal.symbol,
            "price": signal.price,
            # ...
        }
        return await self.db.insert("signals", data)

# ❌ WRONG - SQL in service/core layer
class SignalStorage:
    async def save_signal(self, signal: Signal):
        await db.execute("INSERT INTO signals ...")  # NO!
```

### Database Interface

New databases must implement `IDatabase`:

```python
# infrastructure/database/base.py
class IDatabase(ABC):
    @abstractmethod
    async def connect(self): pass
    
    @abstractmethod
    async def insert(self, table: str, data: Dict) -> Any: pass
    
    @abstractmethod
    async def fetch_all(self, query: str, params: Dict) -> List[Dict]: pass
    # ... other methods
```

---

## File Organization

### Where to Place Code

| Type | Location | Example |
|------|----------|---------|
| Database interface | `infrastructure/database/base.py` | `IDatabase` |
| Database implementation | `infrastructure/database/<name>.py` | `postgres.py` |
| Repository | `infrastructure/database/<entity>_repository.py` | `signal_repository.py` |
| External API client | `infrastructure/data_sources/<name>.py` | `nse_data_source.py` |
| Business service | `core/services/<name>.py` | `signal_storage.py` |
| Trading strategy | `core/strategies/<name>.py` | `vwap_breakout.py` |
| Strategy config | `core/config/strategy_config.py` | Config classes |
| Domain model | `models/<name>.py` | `Signal`, `Candidate` |
| Worker | `workers/<name>_worker.py` | `vwap_breakout_worker.py` |
| API endpoint | `api/routes/<name>.py` | Trading routes |

### Common Mistakes

❌ **DON'T**: Put database code in `core/services/`
```python
# WRONG: backend/core/services/signal_storage.py
import psycopg2
conn = psycopg2.connect(...)  # NO! External dependency in core
```

✅ **DO**: Put database code in `infrastructure/database/`
```python
# CORRECT: backend/infrastructure/database/postgres.py
class PostgresDatabase(IDatabase):
    async def connect(self):
        self.pool = await asyncpg.create_pool(...)
```

❌ **DON'T**: Create duplicate infrastructure folders
```python
backend/core/database/  # NO! Use existing infrastructure/database/
```

✅ **DO**: Use existing infrastructure structure
```python
backend/infrastructure/database/signal_repository.py  # YES!
```

---

## Design Patterns

### 1. Strategy Pattern
Used for trading strategies:

```python
class BaseStrategy(ABC):
    @abstractmethod
    def apply_filters(self, candidate, df): pass
    
    @abstractmethod
    def generate_entry_signal(self, candidate, df): pass

class VWAPBreakoutStrategy(BaseStrategy):
    def apply_filters(self, candidate, df):
        # Implementation
        pass
```

### 2. Factory Pattern
Used for strategy configuration:

```python
class StrategyConfigFactory:
    _registry = {}
    
    @classmethod
    def register(cls, name: str):
        def decorator(func):
            cls._registry[name] = func
            return func
        return decorator
    
    @classmethod
    def create(cls, name: str, **kwargs):
        return cls._registry[name](**kwargs)
```

### 3. Repository Pattern
Used for data access:

```python
# infrastructure/database/signal_repository.py
class SignalRepository:
    def __init__(self, database: IDatabase):
        self.db = database
    
    async def save_signal(self, signal: Signal) -> int:
        return await self.db.insert("signals", data)
    
    async def get_signals_by_date(self, date) -> List[Dict]:
        return await self.db.fetch_all(query, params)
```

### 4. Dependency Injection
Used throughout for loose coupling:

```python
# Services accept dependencies
class SignalStorage:
    def __init__(self, database: Optional[IDatabase] = None):
        self.repository = SignalRepository(database) if database else None

# Workers inject dependencies
class VWAPBreakoutWorker(BaseStrategyWorker):
    def __init__(self):
        super().__init__()
        self.storage = SignalStorage(database=db)  # Injected
```

---

## Trading-Specific Guidelines

### 1. Strategy Implementation

Strategies should be pure business logic:

```python
class VWAPBreakoutStrategy(BaseStrategy):
    def apply_filters(self, candidate: Candidate, df: pd.DataFrame) -> bool:
        """
        Apply filters to determine if candidate qualifies.
        
        Returns:
            True if all filters pass, False otherwise
        """
        # Calculate indicators
        vwap = self._calculate_vwap(df)
        avg_volume = df['volume'].tail(20).mean()
        
        # Apply filters
        if df['close'].iloc[-1] <= vwap * (1 + self.config.vwap_breakout_pct / 100):
            return False
        
        if df['volume'].iloc[-1] <= avg_volume * self.config.volume_multiplier:
            return False
        
        return True
    
    def generate_entry_signal(self, candidate: Candidate, df: pd.DataFrame) -> Optional[Signal]:
        """Generate entry signal if conditions met"""
        if not self.apply_filters(candidate, df):
            return None
        
        entry_price = df['close'].iloc[-1]
        return Signal(
            symbol=candidate.symbol,
            signal_type="BUY",
            price=entry_price,
            stop_loss=entry_price * (1 - self.config.stop_loss_pct / 100),
            target=entry_price * (1 + self.config.target_pct / 100),
            timestamp=df.index[-1],
            reason=f"VWAP breakout with volume surge"
        )
```

### 2. Worker Implementation

Workers should be thin orchestrators:

```python
class VWAPBreakoutWorker(BaseStrategyWorker):
    """
    Worker for VWAP Breakout strategy.
    
    Responsibilities:
    - Fetch top gainers from NSE
    - Get historical data for each candidate
    - Apply strategy filters
    - Generate and save signals
    """
    
    def get_strategy_name(self) -> str:
        return "vwap_breakout"
    
    def create_strategy(self) -> BaseStrategy:
        return VWAPBreakoutStrategy(self.config)
    
    def create_config(self) -> BaseStrategyConfig:
        return StrategyConfigFactory.create("vwap_breakout")
```

### 3. Signal Storage

Signals should be stored with rich metadata:

```python
signal_data = {
    "timestamp": signal.timestamp,
    "symbol": signal.symbol,
    "signal_type": signal.signal_type,
    "price": signal.price,
    "stop_loss": signal.stop_loss,
    "target": signal.target,
    "quantity": signal.quantity,
    "reason": signal.reason,
    "metadata": {
        "gain_pct": candidate.gain_pct,
        "volume": df['volume'].iloc[-1],
        "avg_volume": avg_volume,
        "vwap": vwap,
        "ema_20": ema_20,
        # ... other context
    }
}
```

---

## Testing Guidelines

### Unit Tests
Test components in isolation with mocks:

```python
def test_vwap_breakout_filter():
    config = VWAPBreakoutConfig(
        volume_multiplier=1.5,
        vwap_breakout_pct=0.2
    )
    strategy = VWAPBreakoutStrategy(config)
    
    # Test with mock data
    df = create_mock_dataframe()
    candidate = Candidate(symbol="TEST", gain_pct=3.0)
    
    assert strategy.apply_filters(candidate, df) == True
```

### Integration Tests
Test components working together:

```python
async def test_signal_storage_with_database():
    # Use mock database
    mock_db = MockDatabase()
    storage = SignalStorage(storage_type="database", database=mock_db)
    
    signal = Signal(symbol="RELIANCE", price=2450.50, ...)
    signal_id = await storage.save_signal(signal, "vwap_breakout")
    
    assert signal_id is not None
```

---

## Pre-Commit Checklist

Before suggesting code changes, verify:

- [ ] Type hints on all function parameters and return values
- [ ] Async/await used consistently (async for I/O, sync for computation)
- [ ] Error handling appropriate for layer (raise in infra, default in service, continue in worker)
- [ ] Logging with correct levels (info/warning/error/debug)
- [ ] Dependencies injected via constructor, not hard-coded
- [ ] Database code in `infrastructure/database/`, not `core/`
- [ ] Repositories implement `IDatabase` interface
- [ ] Configuration objects used instead of hard-coded values
- [ ] Business logic in `core/`, external dependencies in `infrastructure/`

---

## Key Documentation

- **Architecture**: `/backend/ARCHITECTURE.md`
- **Database Migration**: `/backend/infrastructure/database/MIGRATION.md`
- **Worker Documentation**: `/backend/workers/README.md`

---

## Summary

**Golden Rules**:
1. Separate concerns - infrastructure vs core vs workers
2. Type everything - use type hints everywhere
3. Inject dependencies - never hard-code
4. Use repositories - all database ops through `IDatabase`
5. Handle errors by layer - raise in infra, default in service, continue in worker
6. Async for I/O only - pure computation stays sync
7. Configure, don't hard-code - use config objects
