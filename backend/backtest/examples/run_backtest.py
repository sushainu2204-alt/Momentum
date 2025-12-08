"""
Backtest Example Script

Demonstrates how to use the backtesting engine with different strategies.

Usage:
    python -m backend.backtest.examples.run_backtest
    
    or from the project root:
    python backend/backtest/examples/run_backtest.py
"""

import sys
from pathlib import Path
from datetime import date
import logging

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.backtest import (
    BacktestConfig,
    BacktestOrchestrator,
    RiskConfig,
    ExecutionConfig,
    StopLossConfig,
    FillModelType,
    SlippageModel
)
from backend.backtest.data_loader import SyntheticDataGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_basic_backtest():
    """
    Basic backtest example with default settings.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 1: Basic Backtest")
    print("=" * 60)
    
    config = BacktestConfig(
        # Date range
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 31),
        
        # Capital
        initial_capital=100000,
        
        # Strategies
        strategies=['vwap_breakout', 'bullish_flag', 'top_gainers'],
        
        # Data
        data_path="data/historical/1min",
        data_frequency="1min",
        
        # Symbols (or use universe file)
        symbols=['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK'],
    )
    
    # Create and run orchestrator
    orchestrator = BacktestOrchestrator(config)
    result = orchestrator.run()
    
    # Print results
    result.print_summary()
    
    return result


def run_advanced_backtest():
    """
    Advanced backtest with custom risk and execution settings.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Advanced Backtest with Custom Settings")
    print("=" * 60)
    
    # Custom risk configuration
    risk_config = RiskConfig(
        initial_capital=500000,
        per_trade_capital_pct=0.15,      # 15% per trade
        max_capital_per_trade=75000,     # Max ₹75k per trade
        max_positions=5,
        max_positions_per_strategy=2,
        max_daily_trades=15,
        max_daily_loss_pct=2.0,          # Stop at 2% daily loss
        max_drawdown_pct=8.0             # Stop at 8% drawdown
    )
    
    # Custom execution settings
    execution_config = ExecutionConfig(
        fill_model=FillModelType.NEXT_OPEN,  # Realistic fills
        slippage_model=SlippageModel.FIXED,
        slippage_pct=0.05,                   # 0.05% slippage
        commission_per_trade=20,
        commission_pct=0.0003,               # 0.03%
        stt_pct=0.001                        # 0.1% STT
    )
    
    # Custom stop loss settings
    sl_config = StopLossConfig(
        initial_sl_pct=0.8,                  # 0.8% SL
        enable_trailing_sl=True,
        trailing_sl_activation_pct=0.5,      # Start trailing at 0.5% profit
        trailing_sl_distance_pct=0.3,        # Trail by 0.3%
        initial_target_pct=1.5,              # 1.5% target
        use_rr_ratio=True,
        risk_reward_ratio=2.0                # 1:2 RR
    )
    
    config = BacktestConfig(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 30),
        initial_capital=500000,
        strategies=['vwap_breakout', 'top_gainers'],
        symbols=['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK',
                'WIPRO', 'SBIN', 'BHARTIARTL', 'KOTAKBANK', 'LT'],
        data_path="data/historical/1min",
        
        # Apply custom configs
        risk=risk_config,
        execution=execution_config,
        stop_loss=sl_config,
        
        # Output settings
        output_path="backtest_results/advanced_test"
    )
    
    orchestrator = BacktestOrchestrator(config)
    result = orchestrator.run()
    
    result.print_summary()
    
    # Save results
    result.save("backtest_results/advanced_test")
    
    return result


def run_strategy_comparison():
    """
    Compare different strategies head-to-head.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Strategy Comparison")
    print("=" * 60)
    
    strategies_to_compare = [
        'vwap_breakout',
        'bullish_flag',
        'top_gainers'
    ]
    
    symbols = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK']
    
    results = {}
    
    for strategy in strategies_to_compare:
        print(f"\nRunning backtest for: {strategy}")
        
        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            initial_capital=100000,
            strategies=[strategy],
            symbols=symbols,
            data_path="data/historical/1min"
        )
        
        orchestrator = BacktestOrchestrator(config)
        result = orchestrator.run(show_progress=False)
        results[strategy] = result
        
        print(f"  {strategy}: {result.metrics.total_trades} trades, "
              f"₹{result.metrics.total_return:,.0f} ({result.metrics.total_return_pct:+.2f}%)")
    
    # Comparison summary
    print("\n" + "-" * 60)
    print("STRATEGY COMPARISON SUMMARY")
    print("-" * 60)
    print(f"{'Strategy':<20} {'Trades':<10} {'Win Rate':<12} {'Return':<15} {'Sharpe':<10}")
    print("-" * 60)
    
    for strategy, result in results.items():
        m = result.metrics
        print(f"{strategy:<20} {m.total_trades:<10} {m.win_rate:<12.1f}% "
              f"₹{m.total_return:<14,.0f} {m.sharpe_ratio:<10.2f}")
    
    return results


def run_with_synthetic_data():
    """
    Run backtest with synthetic data (for testing without real data).
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Backtest with Synthetic Data")
    print("=" * 60)
    
    # Generate synthetic data
    symbols = ['TEST1', 'TEST2', 'TEST3']
    start_date = date(2024, 1, 1)
    end_date = date(2024, 1, 31)
    
    print("Generating synthetic data...")
    
    synthetic_data = {}
    for i, symbol in enumerate(symbols):
        df = SyntheticDataGenerator.generate_random_walk(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_price=100 + i * 50,
            volatility=0.02
        )
        synthetic_data[symbol] = df
        print(f"  {symbol}: {len(df)} candles generated")
    
    # Note: To use this data, you would need to save it or modify
    # the DataLoader to accept in-memory data
    print("\nSynthetic data generated. Save to CSV files to use with backtest.")
    
    # Example: Save to CSV
    from pathlib import Path
    output_dir = Path("data/synthetic")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for symbol, df in synthetic_data.items():
        df.to_csv(output_dir / f"{symbol}.csv", index=False)
    
    print(f"Data saved to {output_dir}")
    
    # Now run backtest with synthetic data
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=100000,
        strategies=['vwap_breakout'],
        symbols=symbols,
        data_path=str(output_dir)
    )
    
    orchestrator = BacktestOrchestrator(config)
    result = orchestrator.run()
    
    result.print_summary()
    
    return result


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("MOMENTUM BACKTESTING ENGINE - EXAMPLES")
    print("=" * 60)
    
    # Example 1: Basic backtest
    # run_basic_backtest()
    
    # Example 2: Advanced backtest with custom settings
    # run_advanced_backtest()
    
    # Example 3: Strategy comparison
    # run_strategy_comparison()
    
    # Example 4: With synthetic data (always works)
    run_with_synthetic_data()


if __name__ == "__main__":
    main()
