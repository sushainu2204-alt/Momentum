"""
Top Gainers Momentum Strategy Backtest Runner

Run backtests for Top Gainers Momentum Strategy with historical data.

Usage:
    python non-prod/tools/backtesting/top_gainers_backtest.py --start 2024-01-01 --end 2024-06-30
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
import logging

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from backend.core.strategies.top_gainers_momentum import TopGainersMomentumStrategy
from backend.core.services.position_manager_service import PositionManagerService
from backend.core.services.stock_screener_service import StockScreenerService, UniverseFactory
from backend.core.config import TopGainersMomentumConfig, StrategyConfigFactory
from non-prod.tools.backtesting.multi_position_engine import MultiPositionBacktestEngine
from backend.infrastructure.data_sources import ZerodhaDataSource
from backend.core.services.kite_service import KiteService


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Backtest Top Gainers Momentum Strategy'
    )
    
    parser.add_argument(
        '--start',
        type=str,
        required=True,
        help='Start date (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--end',
        type=str,
        required=True,
        help='End date (YYYY-MM-DD)'
    )
    
    parser.add_argument(
        '--capital',
        type=float,
        default=100000,
        help='Initial capital (default: 100000)'
    )
    
    parser.add_argument(
        '--universe',
        type=str,
        choices=['fno', 'nifty500', 'nifty200', 'custom'],
        default='fno',
        help='Stock universe (default: fno)'
    )
    
    parser.add_argument(
        '--scan-interval',
        type=int,
        default=1,
        help='Scan interval in minutes (default: 1)'
    )
    
    parser.add_argument(
        '--commission',
        type=float,
        default=0.001,
        help='Commission rate (default: 0.001 = 0.1%%)'
    )
    
    parser.add_argument(
        '--slippage',
        type=float,
        default=0.0005,
        help='Slippage rate (default: 0.0005 = 0.05%%)'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        help='Path to custom strategy config JSON file'
    )
    
    return parser.parse_args()


def load_custom_config(config_path: str) -> TopGainersMomentumConfig:
    """
    Load custom strategy configuration from JSON file.
    
    Args:
        config_path: Path to JSON config file
    
    Returns:
        Strategy configuration
    """
    import json
    
    with open(config_path, 'r') as f:
        config_dict = json.load(f)
    
    return StrategyConfigFactory.create('top_gainers_momentum', **config_dict)


def main():
    """Main backtest execution"""
    args = parse_args()
    
    print("\n" + "="*70)
    print("TOP GAINERS MOMENTUM STRATEGY BACKTEST")
    print("="*70)
    print(f"Period: {args.start} to {args.end}")
    print(f"Capital: ₹{args.capital:,.2f}")
    print(f"Universe: {args.universe}")
    print(f"Scan Interval: {args.scan_interval} minutes")
    print(f"Commission: {args.commission*100:.3f}%")
    print(f"Slippage: {args.slippage*100:.3f}%")
    print("="*70 + "\n")
    
    # Load configuration
    if args.config:
        logger.info(f"Loading custom config from {args.config}")
        config = load_custom_config(args.config)
    else:
        logger.info("Using default configuration")
        config = StrategyConfigFactory.create('top_gainers_momentum')
    
    print("Strategy Configuration:")
    print(str(config))
    print()
    
    # Initialize Kite service (requires OAuth tokens)
    try:
        kite_service = KiteService()
        kite = kite_service.kite
        
        if kite is None:
            logger.error("❌ Kite Connect not initialized. Please authenticate first.")
            logger.error("Run: python -m backend.main_new")
            logger.error("Then visit: http://localhost:8000/login")
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize Kite: {e}")
        sys.exit(1)
    
    # Initialize components
    logger.info("Initializing backtest components...")
    
    data_source = ZerodhaDataSource(kite)
    universe = UniverseFactory.create(args.universe)
    screener = StockScreenerService(data_source, universe, config)
    strategy = TopGainersMomentumStrategy(config)
    position_manager = PositionManagerService(config)
    
    # Initialize backtest engine
    engine = MultiPositionBacktestEngine(
        data_source=data_source,
        strategy=strategy,
        screener=screener,
        position_manager=position_manager,
        initial_capital=args.capital,
        commission=args.commission,
        slippage=args.slippage
    )
    
    logger.info("✅ Components initialized\n")
    
    # Run backtest
    try:
        results = engine.run_backtest(
            start_date=args.start,
            end_date=args.end,
            scan_interval_minutes=args.scan_interval,
            index_symbol="NIFTY 50"
        )
        
        # Print results
        engine.print_results(results)
        
        # Export trade log
        trade_log = engine.get_trade_log()
        if not trade_log.empty:
            output_file = f'backtest_trades_{args.start}_{args.end}.csv'
            trade_log.to_csv(output_file, index=False)
            logger.info(f"📄 Trade log exported to: {output_file}")
        
        # Export equity curve
        equity_curve = engine.get_equity_curve()
        if not equity_curve.empty:
            output_file = f'backtest_equity_{args.start}_{args.end}.csv'
            equity_curve.to_csv(output_file, index=False)
            logger.info(f"📈 Equity curve exported to: {output_file}")
        
        # Export scan log
        scan_log = engine.get_scan_log()
        if not scan_log.empty:
            output_file = f'backtest_scans_{args.start}_{args.end}.csv'
            scan_log.to_csv(output_file, index=False)
            logger.info(f"🔍 Scan log exported to: {output_file}")
        
        print("\n✅ Backtest completed successfully!\n")
        
        # Validation checks
        print("="*70)
        print("VALIDATION CHECKS")
        print("="*70)
        
        win_rate = results.get('win_rate', 0)
        profit_factor = results.get('profit_factor', 0)
        sharpe_ratio = results.get('sharpe_ratio', 0)
        
        print(f"\n📋 Minimum Requirements:")
        print(f"  Win Rate:        > 50%   {'✅' if win_rate > 50 else '❌'} ({win_rate:.2f}%)")
        print(f"  Profit Factor:   > 1.5   {'✅' if profit_factor > 1.5 else '❌'} ({profit_factor:.2f})")
        print(f"  Sharpe Ratio:    > 1.0   {'✅' if sharpe_ratio > 1.0 else '❌'} ({sharpe_ratio:.2f})")
        
        if win_rate > 50 and profit_factor > 1.5 and sharpe_ratio > 1.0:
            print("\n✅ Strategy meets all validation criteria - READY FOR LIVE TRADING")
        else:
            print("\n⚠️  Strategy needs optimization - DO NOT use in live trading yet")
        
        print("="*70 + "\n")
        
    except Exception as e:
        logger.error(f"❌ Backtest failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
