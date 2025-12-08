#!/usr/bin/env python
"""
Simple Backtest Runner

Run a backtest using downloaded historical data.

Usage:
    python -m backend.backtest.scripts.run_simple_backtest
"""

import sys
import os
from pathlib import Path
from datetime import date
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def find_available_symbols(data_path: str, interval: str = "1minute") -> list:
    """Find symbols with available data."""
    data_dir = Path(data_path)
    if not data_dir.exists():
        return []
    
    symbols = set()
    for f in data_dir.glob(f"*_{interval}_*.parquet"):
        # Extract symbol from filename like "RELIANCE_1minute_20251108_20251208.parquet"
        parts = f.stem.split('_')
        if len(parts) >= 2:
            symbols.add(parts[0])
    
    return sorted(list(symbols))


def run_backtest():
    """Run a simple backtest with available data."""
    from backend.backtest import (
        BacktestConfig,
        BacktestOrchestrator,
        RiskConfig,
        ExecutionConfig,
    )
    from backend.backtest.config import StopLossConfig, FillModelType, SlippageModel
    
    # Data path - inside container
    data_path = os.environ.get('DATA_PATH', '/app/data/historical')
    
    # Find available symbols
    available_symbols = find_available_symbols(data_path)
    
    if not available_symbols:
        print(f"No data found in {data_path}")
        print("Please run the download script first.")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print("MOMENTUM STRATEGIES BACKTEST")
    print(f"{'='*60}")
    print(f"Data path: {data_path}")
    print(f"Available symbols: {len(available_symbols)}")
    
    # Select top liquid stocks for backtest
    target_symbols = [
        'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
        'SBIN', 'BHARTIARTL', 'ITC', 'KOTAKBANK', 'LT',
        'AXISBANK', 'BAJFINANCE', 'HINDUNILVR', 'MARUTI', 'TITAN',
        'SUNPHARMA', 'WIPRO', 'HCLTECH', 'ASIANPAINT', 'ULTRACEMCO'
    ]
    
    # Filter to only available symbols
    symbols = [s for s in target_symbols if s in available_symbols]
    
    if not symbols:
        # Fall back to first 20 available
        symbols = available_symbols[:20]
    
    print(f"Using {len(symbols)} symbols: {symbols[:5]}...")
    
    # Risk configuration
    risk_config = RiskConfig(
        initial_capital=1000000,          # 10 lakh
        per_trade_capital_pct=0.10,       # 10% per trade
        max_capital_per_trade=100000,     # Max 1 lakh per trade
        max_positions=5,
        max_positions_per_strategy=2,
        max_daily_trades=10,
        max_daily_loss_pct=2.0,           # Stop at 2% daily loss
        max_drawdown_pct=10.0             # Stop at 10% drawdown
    )
    
    # Execution settings (realistic)
    execution_config = ExecutionConfig(
        fill_model=FillModelType.NEXT_OPEN,
        slippage_model=SlippageModel.FIXED,
        slippage_pct=0.05,                # 0.05% slippage
        commission_per_trade=20,          # ₹20 per trade
        commission_pct=0.0003,            # 0.03% brokerage
        stt_pct=0.001                     # 0.1% STT on sell
    )
    
    # Stop loss settings
    sl_config = StopLossConfig(
        initial_sl_pct=1.0,               # 1% SL
        enable_trailing_sl=True,
        trailing_sl_activation_pct=0.5,   # Trail after 0.5% profit
        trailing_sl_distance_pct=0.3,     # Trail by 0.3%
        initial_target_pct=2.0,           # 2% target
        use_rr_ratio=True,
        risk_reward_ratio=2.0             # 1:2 R:R
    )
    
    # Backtest configuration
    config = BacktestConfig(
        # Date range (use last month's data)
        start_date=date(2025, 11, 8),
        end_date=date(2025, 12, 8),
        
        # Capital
        initial_capital=1000000,
        
        # Strategies to test
        strategies=['vwap_breakout', 'bullish_flag', 'top_gainers'],
        
        # Data settings
        data_path=data_path,
        data_frequency="1min",
        symbols=symbols,
        
        # Risk and execution
        risk=risk_config,
        execution=execution_config,
        stop_loss=sl_config,
        
        # Output
        output_path="/app/data/backtest_results"
    )
    
    print(f"\nStrategies: {config.strategies}")
    print(f"Date range: {config.start_date} to {config.end_date}")
    print(f"Initial capital: ₹{config.initial_capital:,.0f}")
    print(f"\nStarting backtest...")
    print(f"{'='*60}\n")
    
    # Run backtest
    orchestrator = BacktestOrchestrator(config)
    result = orchestrator.run()
    
    # Print summary
    print(f"\n{'='*60}")
    print("BACKTEST RESULTS")
    print(f"{'='*60}")
    result.print_summary()
    
    # Save results
    try:
        result.save("/app/data/backtest_results")
        print(f"\nResults saved to /app/data/backtest_results")
    except Exception as e:
        logger.warning(f"Could not save results: {e}")
    
    return result


if __name__ == "__main__":
    run_backtest()
