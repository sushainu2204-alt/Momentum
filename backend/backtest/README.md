# Momentum Backtesting Engine

A professional-grade backtesting framework designed for momentum trading strategies.

## Architecture

```
+----------------+         +----------------+         +----------------+
|  Data Loader   | ----->  | Feature Engine | ----->  | Signal Engine  |
+----------------+         +----------------+         +----------------+
                                                              |
                                                              v
                         +----------------+         +----------------------+
                         | Risk Engine    | ---->   | Order Simulator      |
                         +----------------+         +----------------------+
                                                              |
                                                              v
                                          +-------------------------------+
                                          | Trade Ledger + Performance    |
                                          +-------------------------------+
```

## Components

### 1. Data Loader (`data_loader.py`)
- Loads minute-level OHLCV data from CSV/Parquet files
- Normalizes timestamps and columns
- Supports parallel loading for multiple symbols
- Includes synthetic data generator for testing

### 2. Feature Engine (`feature_engine.py`)
- Computes all technical indicators:
  - VWAP (Volume Weighted Average Price)
  - EMA (9, 20, 50)
  - RSI
  - ATR
  - Bollinger Bands
  - Volume surge factors
  - Price patterns
- Daily VWAP reset for intraday
- Incremental computation support

### 3. Signal Engine (`signal_engine.py`)
- Evaluates strategy rules at each candle
- Strategy adapter pattern for pluggable strategies
- Built-in adapters for:
  - VWAP Breakout
  - Bullish Flag
  - Top Gainers Momentum
- Signal prioritization

### 4. Risk Engine (`risk_engine.py`)
- Capital allocation and position sizing
- Maximum position limits
- Daily loss limits
- Drawdown protection
- Per-strategy and per-symbol limits

### 5. Order Simulator (`order_simulator.py`)
- Multiple fill models (next open, same close, VWAP)
- Slippage simulation
- Stop loss management
- Trailing stop loss
- Target profit booking
- Time-based exits (MIS square-off)

### 6. Trade Ledger (`trade_ledger.py`)
- Complete trade recording
- Daily P&L tracking
- Equity curve generation
- Export to CSV/JSON

### 7. Performance Engine (`performance_engine.py`)
- Comprehensive metrics:
  - Returns: CAGR, Total Return
  - Risk: Max Drawdown, Volatility, VaR
  - Risk-Adjusted: Sharpe, Sortino, Calmar
  - Trades: Win Rate, Profit Factor, Expectancy, SQN
- Strategy comparison
- HTML report generation

## Quick Start

### Basic Usage

```python
from datetime import date
from backend.backtest import BacktestConfig, BacktestOrchestrator

# Create configuration
config = BacktestConfig(
    start_date=date(2024, 1, 1),
    end_date=date(2024, 6, 30),
    initial_capital=100000,
    strategies=['vwap_breakout', 'bullish_flag', 'top_gainers'],
    symbols=['RELIANCE', 'TCS', 'INFY', 'HDFCBANK'],
    data_path="data/historical/1min"
)

# Run backtest
orchestrator = BacktestOrchestrator(config)
result = orchestrator.run()

# View results
result.print_summary()

# Save results
result.save("backtest_results/my_test")
```

### Using Convenience Function

```python
from datetime import date
from backend.backtest.orchestrator import run_backtest

result = run_backtest(
    strategies=['vwap_breakout'],
    start_date=date(2024, 1, 1),
    end_date=date(2024, 3, 31),
    initial_capital=100000,
    symbols=['RELIANCE', 'TCS', 'INFY']
)

result.print_summary()
```

### Advanced Configuration

```python
from backend.backtest import (
    BacktestConfig,
    RiskConfig,
    ExecutionConfig,
    StopLossConfig,
    FillModelType,
    SlippageModel
)

# Custom risk settings
risk = RiskConfig(
    per_trade_capital_pct=0.15,
    max_positions=5,
    max_daily_loss_pct=2.0,
    max_drawdown_pct=8.0
)

# Custom execution settings
execution = ExecutionConfig(
    fill_model=FillModelType.NEXT_OPEN,
    slippage_pct=0.05,
    commission_per_trade=20
)

# Custom stop loss settings
stop_loss = StopLossConfig(
    initial_sl_pct=0.8,
    enable_trailing_sl=True,
    trailing_sl_distance_pct=0.3,
    risk_reward_ratio=2.0
)

config = BacktestConfig(
    start_date=date(2024, 1, 1),
    end_date=date(2024, 6, 30),
    initial_capital=500000,
    strategies=['vwap_breakout'],
    risk=risk,
    execution=execution,
    stop_loss=stop_loss
)
```

## Data Download

### Download NSE Daily Data

```bash
# Download specific symbols
python backend/backtest/scripts/download_data.py \
    --source nse \
    --symbols RELIANCE TCS INFY HDFCBANK \
    --start 2023-01-01 \
    --end 2024-06-30

# Download entire universe
python backend/backtest/scripts/download_data.py \
    --source nse \
    --universe nifty500 \
    --start 2023-01-01 \
    --end 2024-06-30
```

### Download Kite Intraday Data

```bash
# First time - complete login
python backend/backtest/scripts/download_kite_historical.py --login

# Download 1-minute data
python backend/backtest/scripts/download_kite_historical.py \
    --symbols RELIANCE TCS \
    --start 2024-06-01 \
    --end 2024-06-30 \
    --interval 1minute
```

### Generate Synthetic Data

```bash
# Generate test data for backtesting without real data
python backend/backtest/scripts/generate_synthetic_data.py \
    --symbol TESTSTOCK \
    --days 365 \
    --interval 1minute \
    --pattern bullish
```

### Data Sources

| Source | Data Type | Max History | Notes |
|--------|-----------|-------------|-------|
| NSE | Daily OHLCV | ~2 years | Free, no API key needed |
| Kite | Minute to Daily | 60d (1m), 2000d (daily) | Requires Zerodha account |
| Synthetic | Any | Unlimited | For testing |

## Data Format

Expected OHLCV data format:

```csv
timestamp,open,high,low,close,volume
2024-01-02 09:15:00,100.5,101.0,100.2,100.8,50000
2024-01-02 09:16:00,100.8,101.2,100.6,101.0,45000
...
```

Column aliases supported:
- `datetime`, `date`, `time` → `timestamp`
- `o` → `open`, `h` → `high`, `l` → `low`, `c` → `close`
- `v`, `vol` → `volume`

## Strategies Supported

### 1. VWAP Breakout (`vwap_breakout`)
- Price above VWAP
- EMA 20 > EMA 50
- Volume surge confirmation

### 2. Bullish Flag (`bullish_flag`)
- Initial +2% move (flag pole)
- 0.3-1.0% pullback
- Breakout above flag high
- Volume confirmation

### 3. Top Gainers Momentum (`top_gainers`)
- 2-3% daily gainers
- Volume surge
- Above VWAP and EMA
- Index trend filter

## Performance Metrics

| Category | Metrics |
|----------|---------|
| Returns | Total Return, CAGR, Best/Worst Day |
| Risk | Max Drawdown, Volatility, VaR |
| Risk-Adjusted | Sharpe, Sortino, Calmar |
| Trade Stats | Win Rate, Profit Factor, Expectancy, SQN |
| Advanced | Recovery Factor, Ulcer Index |

## Output Files

After running a backtest with `result.save()`:

```
backtest_results/
├── trades.csv           # All trades with details
├── daily_summary.csv    # Daily P&L summary
├── equity_curve.csv     # Equity curve data
├── strategy_summary.csv # By-strategy breakdown
└── metrics.json         # All metrics in JSON
```

## Adding New Strategies

1. Create adapter in `signal_engine.py`:

```python
class MyStrategyAdapter(BacktestStrategyAdapter):
    def __init__(self, config=None):
        super().__init__("my_strategy", "My Strategy")
        self.config = config
    
    def evaluate(self, symbol, instrument_token, 
                 current_candle, historical_df, 
                 current_time) -> Optional[BacktestSignal]:
        # Your strategy logic here
        if my_conditions_met:
            return BacktestSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=current_candle['close'],
                stop_loss=...,
                target=...,
                ...
            )
        return None
```

2. Register in `STRATEGY_REGISTRY`:

```python
STRATEGY_REGISTRY = {
    'vwap_breakout': VWAPBreakoutAdapter,
    'bullish_flag': BullishFlagAdapter,
    'top_gainers': TopGainersMomentumAdapter,
    'my_strategy': MyStrategyAdapter,  # Add here
}
```

## Testing

Run with synthetic data (no real data needed):

```python
from backend.backtest.data_loader import SyntheticDataGenerator

# Generate test data
df = SyntheticDataGenerator.generate_random_walk(
    symbol='TEST',
    start_date=date(2024, 1, 1),
    end_date=date(2024, 1, 31),
    initial_price=100,
    volatility=0.02
)
```

## Best Practices

1. **Use realistic fill models**: `NEXT_OPEN` is most realistic
2. **Include slippage and commission**: Real trading has friction
3. **Set proper risk limits**: Max 5 positions, 2% daily loss limit
4. **Validate with out-of-sample data**: Avoid overfitting
5. **Compare against benchmarks**: Ensure strategy adds value

## File Structure

```
backend/backtest/
├── __init__.py          # Package exports
├── config.py            # Configuration classes
├── data_loader.py       # Data loading
├── feature_engine.py    # Indicator computation
├── signal_engine.py     # Signal generation
├── risk_engine.py       # Risk management
├── order_simulator.py   # Order execution
├── trade_ledger.py      # Trade recording
├── performance_engine.py # Performance metrics
├── orchestrator.py      # Main coordinator
├── events.py            # Event system
├── README.md            # This file
├── data/                # Data management module
│   ├── __init__.py
│   ├── downloader.py    # Base downloader interface
│   ├── nse_downloader.py    # NSE historical data
│   ├── kite_downloader.py   # Zerodha Kite data
│   └── data_manager.py  # Data inventory/validation
├── scripts/             # CLI scripts
│   ├── download_data.py
│   ├── download_kite_historical.py
│   └── generate_synthetic_data.py
└── examples/
    └── run_backtest.py  # Example scripts
```

## Live Trading Integration

The backtest engine mirrors the live trading system:

| Backtest | Live Trading |
|----------|--------------|
| DataLoader | Kite WebSocket |
| FeatureEngine | TechnicalIndicators |
| SignalEngine | Strategy classes |
| RiskEngine | Position manager |
| OrderSimulator | Zerodha OMS |
| TradeLedger | MySQL/Redis |

This allows you to validate strategies before deploying to production.
