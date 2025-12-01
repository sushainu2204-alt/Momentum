# Momentum Trading System

A production-ready algorithmic trading system for Zerodha Kite built with **clean architecture**, SOLID principles, and professional design patterns. Features the **Top Gainers Momentum Strategy** with multi-position tracking, real-time signal generation, and comprehensive backtesting.

## 🎯 Quick Links

- **Getting Started**: See [Quick Start](#-quick-start) below
- **Backtesting**: [Backtest Your Strategy](#-backtesting)
- **Testing**: [TESTING.md](TESTING.md) - Complete testing guide
- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md) - System design details
- **Maintenance**: [MAINTENANCE_TODO.md](MAINTENANCE_TODO.md) - Recurring tasks and checklists
- **Technical Fixes**: [CODE_ANALYSIS_AND_FIXES.md](CODE_ANALYSIS_AND_FIXES.md) - Bug fixes and validations

## 📊 What's Inside

### Strategy: Top Gainers Momentum
Identifies high-momentum stocks from F&O/Nifty 500 universe using 5 filters:
1. **Volume Surge Filter** - Volume > 1.5× average
2. **Index Trend Filter** - Nifty trending up (EMA 9 > EMA 21)
3. **Stock Momentum Filter** - Stock EMA 9 > EMA 21
4. **Price Circuit Filter** - Not near upper/lower circuit limits
5. **Risk Management** - Position limits and diversification

**Performance**: Designed for intraday momentum capture with dynamic position sizing and risk controls.

### System Features
- ✅ **Clean Architecture** - Layered design with clear separation of concerns
- ✅ **FastAPI Backend** - RESTful API with OAuth authentication
- ✅ **Live Worker** - Real-time tick processing and signal generation
- ✅ **Backtest Engine** - Historical strategy validation with P&L tracking
- ✅ **Universe Management** - CSV-based with 143 F&O stocks + 140 Nifty 500 stocks
- ✅ **Redis Integration** - High-speed pub/sub for ticks and signals
- ✅ **Multi-Position Tracking** - Support for multiple concurrent positions

## 🏗️ Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Zerodha   │◄────►│   FastAPI    │◄────►│   Redis     │
│  Kite API   │      │   Backend    │      │  (Pub/Sub)  │
└─────────────┘      └──────────────┘      └─────────────┘
                            │                      
                            ▼                      
                     ┌──────────────┐             
                     │  Strategy    │             
                     │   Worker     │──► Signals
                     │  (Momentum)  │
                     └──────────────┘
```

**Key Components:**
- **`backend/config/`** - Centralized settings (Singleton pattern)
- **`backend/core/models/`** - Data models (Tick, Signal, Candidate, Position)
- **`backend/core/strategies/`** - Top Gainers Momentum Strategy
- **`backend/core/services/`** - Business logic (Kite, Market Data, Signals)
- **`backend/workers/`** - Live trading worker
- **`backend/backtesting/`** - Backtest engine and runner
- **`backend/infrastructure/`** - Data sources (universes, Kite API)
- **`backend/data/universes/`** - Stock universe CSV files

## 📁 Project Structure

```
Momentum/
├── backend/
│   ├── config/              # Configuration & settings
│   ├── core/
│   │   ├── models/         # Data models (Tick, Signal, Candidate, Position)
│   │   ├── strategies/     # Top Gainers Momentum Strategy
│   │   └── services/       # Business services (Kite, Market Data, Signals)
│   ├── workers/            # Live trading worker
│   ├── backtesting/        # Backtest engine and CLI runner
│   ├── infrastructure/     # Data sources and abstractions
│   │   └── data_sources/   # Universe management
│   ├── data/
│   │   └── universes/      # CSV files with stock lists
│   └── scripts/            # Utility scripts (universe management)
├── docker-compose.yml      # Redis + Postgres services
├── .env.example            # Environment template
├── TESTING.md              # Complete testing guide
├── ARCHITECTURE.md         # System architecture details
├── MAINTENANCE_TODO.md     # Recurring tasks and checklists
└── README.md               # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for Redis)
- Zerodha Kite Connect app ([create one here](https://developers.kite.trade/))

### 1. Setup Kite Connect App

1. Go to [Kite Connect Developer Console](https://developers.kite.trade/)
2. Create a new app
3. Set **Redirect URL** to: `http://localhost:8000/callback`
4. Note your **API Key** and **API Secret**

### 2. Clone & Configure

```bash
cd /Users/sushmagollapudi/Momentum

# Copy environment template
cp .env.example .env

# Edit .env with your Kite credentials
# KITE_API_KEY=your_key_here
# KITE_API_SECRET=your_secret_here
# KITE_REDIRECT_URL=http://localhost:8000/callback
```

### 3. Install Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install packages
pip install -r backend/requirements.txt
```

### 4. Start Services

```bash
# Start Redis
docker-compose up -d redis

# Verify Redis is running
docker-compose ps
```

### 5. Authenticate with Zerodha

```bash
# Terminal 1: Start FastAPI server
uvicorn backend.main:app --reload

# Terminal 2: Get login URL
curl http://localhost:8000/connect

# Or visit in browser: http://localhost:8000/connect
```

1. Copy the `login_url` from the response
2. Open it in your browser
3. Login with Zerodha credentials
4. Approve the app
5. You'll be redirected to `/callback` - access token will be saved to `.env`

### 6. Run Live Worker (Optional)

```bash
# Start live strategy worker
python backend/workers/live_worker.py

# Worker will:
# - Subscribe to market ticks
# - Apply Top Gainers Momentum filters
# - Generate BUY/SELL signals
# - Track multiple positions
```

### 7. Run Backtest

```bash
# Basic backtest - Last 30 days
python backend/backtesting/runner.py

# Custom parameters
python backend/backtesting/runner.py --days 60 --capital 200000
```

## 📊 Backtesting

### Quick Backtest

```bash
# Test last 7 days with default parameters
python backend/backtesting/runner.py --days 7

# Test with specific capital
python backend/backtesting/runner.py --capital 100000 --days 30
```

### Backtest Options

```bash
python backend/backtesting/runner.py --help

Options:
  --days INT            Days to backtest (default: 30)
  --capital FLOAT       Initial capital in INR (default: 100000)
  --position-size FLOAT Position size % (default: 0.95 = 95%)
  --export-trades       Export trade log to CSV
```

### Understanding Results

The backtest will show:
- **Total Return %** - Overall profit/loss
- **Win Rate** - Percentage of winning trades
- **Sharpe Ratio** - Risk-adjusted returns (>1 is good, >2 is excellent)
- **Max Drawdown** - Largest peak-to-trough decline (lower is better)
- **Trade Log** - Entry/exit prices and P&L for each trade

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `KITE_API_KEY` | Your Kite Connect API key | Yes |
| `KITE_API_SECRET` | Your Kite Connect API secret | Yes |
| `KITE_REDIRECT_URL` | OAuth callback URL | Yes |
| `KITE_ACCESS_TOKEN` | Access token (auto-saved after auth) | Auto |
| `REDIS_URL` | Redis connection string | No (defaults to localhost) |

### Strategy Parameters

Edit `backend/config/settings.py` to customize:

```python
# Volume filter
VOLUME_SURGE_MULTIPLIER = 1.5  # Volume > 1.5× average

# Position sizing
MAX_POSITIONS = 5              # Max concurrent positions
POSITION_SIZE_PCT = 0.95       # Use 95% of capital per position

# Risk management
STOP_LOSS_PCT = 0.02          # 2% stop loss
TAKE_PROFIT_PCT = 0.05        # 5% take profit
```

## 📈 Universe Management

The system uses CSV-based stock universes with hardcoded fallbacks:

- **F&O Universe**: 143 stocks (from `backend/data/universes/fno_stocks.csv`)
- **Nifty 500 Universe**: 140 stocks (from `backend/data/universes/nifty500_stocks.csv`)

### Test Universe Loading

```bash
# Test universe loading
python backend/scripts/manage_universes.py test

# Show CSV statistics
python backend/scripts/manage_universes.py stats

# Export current F&O list from Kite API
python backend/scripts/manage_universes.py export
```

### Update Universe Lists

**Monthly**: Update F&O list when contracts change
**Quarterly**: Update Nifty 500 list from NSE

See [MAINTENANCE_TODO.md](MAINTENANCE_TODO.md) for detailed instructions.

## 🧪 Testing

### Quick Validation

```bash
# Test infrastructure and imports
python test_infrastructure.py

# Test universe loading
python backend/scripts/manage_universes.py test

# Run backtest (validates strategy logic)
python backend/backtesting/runner.py --days 7
```

### Complete Testing

See [TESTING.md](TESTING.md) for:
- 8 comprehensive test flows
- Step-by-step instructions
- Expected outputs
- Troubleshooting tips

## 🔐 Security & Limitations

**⚠️ IMPORTANT:**

1. **No Live Orders** - Order placement APIs are intentionally disabled. This is a signal generation and backtesting system only.
2. **Daily Token Expiration** - Kite access tokens expire daily. Re-authenticate each day.
3. **Rate Limits** - Kite API has strict rate limits. The system implements basic throttling.
4. **Paper Trading** - All signals are logged but no real orders are placed.
5. **Educational Purpose** - Test thoroughly before considering any live trading implementation.

## 🐛 Troubleshooting

### Backend Won't Start

```bash
# Check if port 8000 is in use
lsof -i :8000
kill -9 <PID>

# Restart backend
uvicorn backend.main:app --reload
```

### Redis Connection Failed

```bash
# Restart Redis
docker-compose restart redis

# Check Redis is running
docker exec -it momentum-redis-1 redis-cli PING
# Expected: PONG
```

### Universe Loading Issues

```bash
# Test universe loading
python backend/scripts/manage_universes.py test

# Check CSV files exist
ls -la backend/data/universes/

# Fallback symbols are hardcoded, so system will work even if CSV is missing
```

### Import Errors

```bash
# Set Python path
export PYTHONPATH=/Users/sushmagollapudi/Momentum:$PYTHONPATH

# Reinstall dependencies
pip install -r backend/requirements.txt
```

## 📚 Documentation

- **[TESTING.md](TESTING.md)** - Complete testing guide with 8 test flows
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design, patterns, and layer details
- **[MAINTENANCE_TODO.md](MAINTENANCE_TODO.md)** - Recurring tasks, checklists, and quick commands
- **[CODE_ANALYSIS_AND_FIXES.md](CODE_ANALYSIS_AND_FIXES.md)** - Technical fixes and validations
- **[backend/data/universes/README.md](backend/data/universes/README.md)** - Universe data documentation

## 📝 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/connect` | Get Kite login URL |
| GET | `/callback` | OAuth callback (auto-saves access token) |

## 🛠️ Development Workflow

### Hot Reload

```bash
# Backend auto-reloads with --reload flag
uvicorn backend.main:app --reload

# For worker, use watchdog
pip install watchdog
watchmedo auto-restart --pattern="*.py" --recursive -- python backend/workers/live_worker.py
```

### Running Tests

```bash
# Infrastructure tests
python test_infrastructure.py

# Universe tests
python backend/scripts/manage_universes.py test

# Strategy backtest
python backend/backtesting/runner.py --days 7
```

## 📈 Performance Metrics

Current backtesting metrics (sample run):
- **Total Return**: Varies by market conditions
- **Win Rate**: ~60-70% in trending markets
- **Sharpe Ratio**: Target >1.5
- **Max Drawdown**: Target <20%

**Note**: Past performance does not guarantee future results. Always backtest on recent data.

## 🤝 Contributing

This is a personal trading system. Fork and customize for your needs.

## ⚖️ License

MIT License - Use at your own risk. No warranties for trading outcomes.

## ⚠️ Disclaimer

**This software is for educational and research purposes only. Trading involves substantial risk of loss. The authors are not responsible for any financial losses incurred while using this software. No live orders are placed by this system. Always test thoroughly in paper trading mode and consult with financial advisors before risking real capital.**

---

**Built with ❤️ for algorithmic traders**

Questions? Check:
- Kite Connect docs: https://kite.trade/docs/connect/v3/
- TESTING.md for test flows
- ARCHITECTURE.md for system design
