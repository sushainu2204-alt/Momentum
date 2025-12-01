#!/usr/bin/env python3
"""
Backtest Runner CLI
Run backtests with different parameters from command line.
"""
import argparse
from datetime import datetime
from backend.config import settings
from backend.core.strategies import EMACrossoverStrategy
from backend.core.services import MarketDataService, KiteService
from backend.backtesting.engine import BacktestEngine


def main():
    parser = argparse.ArgumentParser(description="Run backtests on historical data")
    
    parser.add_argument("--instrument", type=int, default=256265, help="Instrument token (default: 256265 = NIFTY 50)")
    parser.add_argument("--interval", type=str, default="5minute", choices=["minute", "5minute", "15minute", "hour", "day"], help="Candle interval")
    parser.add_argument("--days", type=int, default=30, help="Number of days to backtest")
    parser.add_argument("--capital", type=float, default=100000, help="Initial capital in INR")
    parser.add_argument("--fast-ema", type=int, default=9, help="Fast EMA period")
    parser.add_argument("--slow-ema", type=int, default=21, help="Slow EMA period")
    parser.add_argument("--position-size", type=float, default=0.95, help="Position size as % of capital (0.95 = 95%)")
    parser.add_argument("--commission", type=float, default=0.0003, help="Commission per trade (0.0003 = 0.03%)")
    parser.add_argument("--export-trades", action="store_true", help="Export trade log to CSV")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("BACKTEST RUNNER")
    print("="*60)
    print(f"Instrument: {args.instrument}")
    print(f"Interval: {args.interval}")
    print(f"Days: {args.days}")
    print(f"Capital: ₹{args.capital:,.2f}")
    print(f"EMAs: {args.fast_ema}/{args.slow_ema}")
    print("="*60 + "\n")
    
    # Initialize services
    kite_service = KiteService()
    market_data_service = MarketDataService(kite_service=kite_service)
    
    # Fetch historical data
    print("Fetching historical data...")
    df = market_data_service.fetch_intraday_data(
        instrument_token=args.instrument,
        days=args.days,
        interval=args.interval
    )
    
    if df.empty:
        print("⚠ No data available. Please check:")
        print("  1. KITE_ACCESS_TOKEN is set in .env")
        print("  2. Instrument token is valid")
        print("  3. Market is open or you're fetching past data")
        return
    
    print(f"✓ Loaded {len(df)} candles\n")
    
    # Create strategy
    strategy = EMACrossoverStrategy(
        fast_period=args.fast_ema,
        slow_period=args.slow_ema
    )
    
    # Create backtest engine
    engine = BacktestEngine(
        initial_capital=args.capital,
        commission=args.commission,
        slippage=settings.DEFAULT_SLIPPAGE
    )
    
    # Run backtest
    results = engine.run_backtest(
        df=df,
        strategy=strategy,
        position_size_pct=args.position_size
    )
    
    # Print results
    engine.print_results(results)
    
    # Export trades if requested
    if args.export_trades:
        trade_log = engine.get_trade_log()
        if not trade_log.empty:
            filename = f"backtest_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            trade_log.to_csv(filename, index=False)
            print(f"✓ Trade log exported to {filename}")
        else:
            print("⚠ No trades to export")


if __name__ == "__main__":
    main()
