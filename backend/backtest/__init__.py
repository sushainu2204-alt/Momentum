"""
Backtesting Engine

A professional-grade backtesting framework for momentum trading strategies.

Architecture:
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

Components:
    - DataLoader: Load and normalize OHLCV data
    - FeatureEngine: Compute technical indicators
    - SignalEngine: Generate trading signals using strategies
    - RiskEngine: Capital allocation and position sizing
    - OrderSimulator: Simulate order execution with slippage
    - TradeLedger: Record all trades and positions
    - PerformanceEngine: Calculate performance metrics
    - BacktestOrchestrator: Main event loop coordinator

Usage:
    from backend.backtest import BacktestOrchestrator, BacktestConfig
    
    config = BacktestConfig(
        initial_capital=100000,
        strategies=['vwap_breakout', 'bullish_flag', 'top_gainers'],
        start_date='2024-01-01',
        end_date='2024-12-31'
    )
    
    engine = BacktestOrchestrator(config)
    results = engine.run()
    results.print_summary()
"""

from .config import BacktestConfig, RiskConfig, ExecutionConfig
from .data_loader import DataLoader, DataSource
from .feature_engine import FeatureEngine
from .signal_engine import SignalEngine
from .risk_engine import RiskEngine
from .order_simulator import OrderSimulator, FillModel
from .trade_ledger import TradeLedger, Trade, BacktestPosition
from .performance_engine import PerformanceEngine, PerformanceMetrics
from .orchestrator import BacktestOrchestrator
from .events import Event, EventType, MarketDataEvent, SignalEvent, OrderEvent, FillEvent

# Data module
from .data.downloader import (
    HistoricalDataDownloader,
    DataDownloadConfig,
    DataInterval,
    DownloadResult,
    DownloadSummary
)
from .data.nse_downloader import NSEHistoricalDownloader
from .data.kite_downloader import KiteHistoricalDownloader
from .data.data_manager import DataManager, DataInventory

__all__ = [
    # Config
    'BacktestConfig',
    'RiskConfig', 
    'ExecutionConfig',
    
    # Core Components
    'DataLoader',
    'DataSource',
    'FeatureEngine',
    'SignalEngine',
    'RiskEngine',
    'OrderSimulator',
    'FillModel',
    'TradeLedger',
    'Trade',
    'BacktestPosition',
    'PerformanceEngine',
    'PerformanceMetrics',
    
    # Orchestrator
    'BacktestOrchestrator',
    
    # Events
    'Event',
    'EventType',
    'MarketDataEvent',
    'SignalEvent',
    'OrderEvent',
    'FillEvent',
    
    # Data Download
    'HistoricalDataDownloader',
    'DataDownloadConfig',
    'DataInterval',
    'DownloadResult',
    'DownloadSummary',
    'NSEHistoricalDownloader',
    'KiteHistoricalDownloader',
    'DataManager',
    'DataInventory',
]
