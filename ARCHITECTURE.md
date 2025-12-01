# Momentum Trading System - Architecture

## 🏗️ Overview

The system follows **Clean Architecture** principles with SOLID design patterns, ensuring maintainability, testability, and scalability. The architecture separates business logic from infrastructure concerns through well-defined layers and interfaces.

## 📦 Layer Structure

```
backend/
├── config/                    # Configuration Layer
│   └── settings.py           # Centralized settings (Singleton)
│
├── core/                      # Business Logic Layer
│   ├── models/               # Domain Models
│   │   ├── tick.py          # Market tick data
│   │   ├── signal.py        # Trading signals
│   │   ├── candidate.py     # Stock candidates
│   │   └── position.py      # Position tracking
│   │
│   ├── strategies/           # Trading Strategies (Strategy Pattern)
│   │   ├── base.py          # Abstract Strategy interface
│   │   └── top_gainers_momentum.py  # Momentum strategy
│   │
│   └── services/             # Business Services
│       ├── kite_service.py           # Kite API wrapper
│       ├── market_data_service.py    # Historical data
│       └── signal_service.py         # Signal publishing
│
├── workers/                   # Application Layer
│   ├── live_worker.py        # Live trading worker
│   └── backtest_worker.py    # Backtest worker (future)
│
├── backtesting/              # Backtesting Framework
│   ├── engine.py            # Backtest simulation
│   └── runner.py            # CLI interface
│
├── infrastructure/           # Infrastructure Layer
│   └── data_sources/
│       └── universes.py     # Stock universe management
│
└── data/                     # Data Storage
    └── universes/           # CSV files with stock lists
```

## 🎯 Design Principles

### SOLID Principles

1. **Single Responsibility** - Each class has one reason to change
   - `KiteService`: Only handles Kite API communication
   - `MarketDataService`: Only manages market data fetching
   - `TopGainersMomentumStrategy`: Only implements momentum logic

2. **Open/Closed** - Open for extension, closed for modification
   - Add new strategies by extending `BaseStrategy`
   - Add new universes by extending `BaseUniverse`
   - Existing code unchanged when adding features

3. **Liskov Substitution** - Can swap implementations seamlessly
   - Any `BaseStrategy` subclass works with backtest engine
   - Any `BaseUniverse` subclass works with strategy

4. **Interface Segregation** - Small, focused interfaces
   - `BaseStrategy`: Only strategy-specific methods
   - `BaseUniverse`: Only universe-specific methods

5. **Dependency Inversion** - Depend on abstractions
   - Services depend on abstract base classes
   - Strategies independent of data sources

### Design Patterns

#### 1. Strategy Pattern (`core/strategies/`)
**Problem**: Need pluggable trading algorithms  
**Solution**: Abstract `BaseStrategy` with concrete implementations

```python
class BaseStrategy(ABC):
    @abstractmethod
    def analyze(self, candidate: Candidate) -> bool:
        pass

class TopGainersMomentumStrategy(BaseStrategy):
    def analyze(self, candidate: Candidate) -> bool:
        # 5-filter momentum logic
```

**Benefits**:
- Add strategies without modifying engine
- Test strategies independently
- Switch strategies at runtime

#### 2. Facade Pattern (`core/services/kite_service.py`)
**Problem**: Complex Kite API with multiple interfaces  
**Solution**: Simple unified wrapper

```python
class KiteService:
    def get_quote(self, symbols: list) -> dict:
        # Simplifies Kite's complex API
```

**Benefits**:
- Hides complexity from business logic
- Easy to mock for testing
- Single point for API changes

#### 3. Repository Pattern (`core/services/market_data_service.py`)
**Problem**: Need flexible data access  
**Solution**: Abstract data layer with optional caching

```python
class MarketDataService:
    def fetch_quote(self, symbol: str) -> Quote:
        # Abstracts data source
```

**Benefits**:
- Swap data sources without code changes
- Easy caching implementation
- Testable without external APIs

## 🔄 Data Flow

### Live Trading Flow

```
Zerodha Market Data
      ↓
KiteService (fetch quotes)
      ↓
Live Worker (processes ticks)
      ↓
1. Enrich with volume data
2. Apply 5 filters
      ↓
TopGainersMomentumStrategy
      ↓
Generate Signals (BUY/SELL)
      ↓
SignalService → Redis
      ↓
Order Manager (future)
```

### Backtesting Flow

```
CLI Parameters
      ↓
MarketDataService (fetch historical)
      ↓
Backtest Engine
      ↓
1. Load universe
2. For each candle:
   - Enrich with volume
   - Apply filters
   - Generate signals
3. Simulate trades
      ↓
TopGainersMomentumStrategy (SAME code!)
      ↓
Performance Metrics
      ↓
Display Results
```

## 🎯 Top Gainers Momentum Strategy

### Architecture

```
TopGainersMomentumStrategy
│
├── __init__() - Initialize with universes and parameters
│
├── analyze() - Main entry point
│   ├── 1. Volume Surge Filter
│   ├── 2. Index Trend Filter (EMA 9 > EMA 21)
│   ├── 3. Stock Momentum Filter (EMA 9 > EMA 21)
│   ├── 4. Price Circuit Filter
│   └── 5. Risk Management Filter
│
└── _calculate_ema() - EMA calculation helper
```

### Filter Pipeline

Each filter is independent and can be enabled/disabled:

```python
# Volume Surge Filter
if candidate.volume <= candidate.avg_volume * self.volume_multiplier:
    return False

# Index Trend Filter
index_ema_fast = self._calculate_ema(index_prices, self.index_ema_fast)
index_ema_slow = self._calculate_ema(index_prices, self.index_ema_slow)
if index_ema_fast <= index_ema_slow:
    return False

# Stock Momentum Filter
stock_ema_fast = self._calculate_ema(candidate.price_history, self.stock_ema_fast)
stock_ema_slow = self._calculate_ema(candidate.price_history, self.stock_ema_slow)
if stock_ema_fast <= stock_ema_slow:
    return False

# Price Circuit Filter
if candidate.change_percent >= 9.5 or candidate.change_percent <= -9.5:
    return False

# Risk Management Filter
# Position limits, max exposure checks
```

## 📊 Component Responsibilities

### `config/settings.py`
- Load environment variables
- Provide centralized configuration
- Type-safe settings access
- Singleton pattern

### `core/models/`
- **Tick**: Market tick data from live feed
- **Signal**: BUY/SELL signals with metadata
- **Candidate**: Stock being analyzed (with price history, volume, etc.)
- **Position**: Open position tracking (entry, exit, P&L)
- **Quote**: Live market quote

### `core/strategies/`
- **BaseStrategy**: Abstract interface for all strategies
- **TopGainersMomentumStrategy**: 5-filter momentum implementation
- Shared between live trading and backtesting (DRY principle)

### `core/services/`
- **KiteService**: OAuth, WebSocket, REST API calls
- **MarketDataService**: Historical data, quote fetching
- **SignalService**: Signal generation and publishing

### `workers/`
- **live_worker.py**: Subscribes to ticks, generates signals
- Real-time processing with position tracking

### `backtesting/`
- **engine.py**: Simulates trades, calculates P&L, metrics
- **runner.py**: CLI tool with argument parsing

### `infrastructure/data_sources/`
- **universes.py**: Stock universe management
  - `FnOUniverse`: 143 F&O stocks from CSV
  - `Nifty500Universe`: 140 Nifty 500 stocks from CSV
  - Hardcoded fallbacks for reliability

## 🔧 Configuration Management

### Settings Hierarchy

```
1. Environment Variables (.env file)
   ↓
2. settings.py (loads and validates)
   ↓
3. Services (access via settings object)
```

### Key Settings

```python
# Kite API
KITE_API_KEY: str
KITE_API_SECRET: str
KITE_ACCESS_TOKEN: str (auto-saved)

# Strategy Parameters
VOLUME_SURGE_MULTIPLIER: float = 1.5
INDEX_EMA_FAST: int = 9
INDEX_EMA_SLOW: int = 21
STOCK_EMA_FAST: int = 9
STOCK_EMA_SLOW: int = 21

# Risk Management
MAX_POSITIONS: int = 5
POSITION_SIZE_PCT: float = 0.95
STOP_LOSS_PCT: float = 0.02
TAKE_PROFIT_PCT: float = 0.05

# Redis
REDIS_URL: str = "redis://localhost:6379/0"
```

## 🧪 Testing Architecture

### Test Isolation

Each layer can be tested independently:

```python
# Test Strategy (no external dependencies)
strategy = TopGainersMomentumStrategy(...)
candidate = Candidate(...)
result = strategy.analyze(candidate)

# Test Service (mock KiteService)
mock_kite = Mock(spec=KiteService)
service = MarketDataService(kite_service=mock_kite)

# Integration Test (real components)
engine = BacktestEngine(...)
results = engine.run_backtest(...)
```

### Test Pyramid

```
     E2E Tests (1)
         ↑
   Integration (few)
         ↑
    Unit Tests (many)
```

- **Unit Tests**: Test individual components (strategies, filters)
- **Integration Tests**: Test component interactions (service + strategy)
- **E2E Tests**: Test complete flow (backtest, live worker)

## 🔮 Extension Points

### Adding New Strategy

```python
from backend.core.strategies.base import BaseStrategy
from backend.core.models import Candidate

class NewStrategy(BaseStrategy):
    def analyze(self, candidate: Candidate) -> bool:
        # Your logic here
        return True
```

### Adding New Universe

```python
from backend.infrastructure.data_sources.universes import BaseUniverse

class CustomUniverse(BaseUniverse):
    def get_symbols(self) -> List[str]:
        # Your logic to fetch symbols
        return ["SYMBOL1", "SYMBOL2"]
```

### Adding Order Management

```python
# Future: backend/core/services/order_service.py
class OrderService:
    def place_order(self, signal: Signal, position_size: float):
        # Rate limiting
        # Position sizing
        # Risk checks
        # Execute via KiteService
```

## 📈 Performance Considerations

### Optimization Points

1. **Universe Loading**: CSV-based with hardcoded fallbacks (fast)
2. **Volume Enrichment**: Done once before filtering (efficient)
3. **EMA Calculation**: Uses pandas ewm() (optimized)
4. **Position Tracking**: In-memory dict (O(1) lookup)
5. **Signal Publishing**: Redis pub/sub (high-speed)

### Bottlenecks

1. **Quote Fetching**: Kite API rate limits (3 req/sec)
2. **Historical Data**: API rate limits, cache recommended
3. **Tick Processing**: Redis pub/sub overhead (negligible)

### Scaling Strategies

1. **Caching**: Add Redis cache for quotes and historical data
2. **Worker Pool**: Multiple workers for different universe segments
3. **Database**: Add PostgreSQL for trade history and analytics
4. **Message Queue**: Add Kafka for high-throughput tick streams

## 🎓 Learning Resources

- **Strategy Pattern**: https://refactoring.guru/design-patterns/strategy
- **Clean Architecture**: https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
- **SOLID Principles**: https://en.wikipedia.org/wiki/SOLID
- **Repository Pattern**: https://martinfowler.com/eaaCatalog/repository.html

## ✅ Benefits Achieved

### Maintainability
- ✅ Clear layer separation
- ✅ Single responsibility per class
- ✅ Easy to locate code

### Testability
- ✅ Each layer testable independently
- ✅ Easy to mock dependencies
- ✅ Strategies testable without APIs

### Extensibility
- ✅ Add strategies without modifying engine
- ✅ Add universes without changing strategy
- ✅ Add services without touching workers

### Quality
- ✅ SOLID principles throughout
- ✅ Design patterns applied correctly
- ✅ Production-ready structure

---

**Built with ❤️ following professional software engineering practices**
