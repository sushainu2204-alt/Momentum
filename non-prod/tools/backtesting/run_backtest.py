#!/usr/bin/env python
"""
Command-line tool to run backtests on historical data

Usage:
    python non-prod/tools/backtesting/run_backtest.py --instrument 256265 --days 30
"""
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.historical_data import HistoricalDataFetcher
from non-prod.tools.backtesting.backtest_engine import BacktestEngine, EMAStrategy

load_dotenv()

def main():
    parser = argparse.ArgumentParser(description='Run backtest on EMA crossover strategy')
    
    parser.add_argument(
        '--instrument',
        type=int,
        default=256265,
        help='Instrument token (default: 256265 for NIFTY 50)'
    )
    
    parser.add_argument(
        '--interval',
        type=str,
        default='5minute',
        choices=['minute', '3minute', '5minute', '10minute', '15minute', '30minute', '60minute', 'day'],
        help='Candle interval (default: 5minute)'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Number of days to backtest (default: 30)'
    )
    
    parser.add_argument(
        '--capital',
        type=float,
        default=100000,
        help='Initial capital in INR (default: 100000)'
    )
    
    parser.add_argument(
        '--fast-ema',
        type=int,
        default=9,
        help='Fast EMA period (default: 9)'
    )
    
    parser.add_argument(
        '--slow-ema',
        type=int,
        default=21,
        help='Slow EMA period (default: 21)'
    )
    
    parser.add_argument(
        '--position-size',
        type=float,
        default=0.95,
        help='Position size as % of capital (default: 0.95)'
    )
    
    parser.add_argument(
        '--commission',
        type=float,
        default=0.0003,
        help='Commission per trade as decimal (default: 0.0003 = 0.03%%)'
    )
    
    parser.add_argument(
        '--export-trades',
        action='store_true',
        help='Export trade log to CSV'
    )
    
    args = parser.parse_args()
    
    # Get credentials
    API_KEY = os.environ.get("KITE_API_KEY")
    ACCESS_TOKEN = os.environ.get("KITE_ACCESS_TOKEN")
    
    if not API_KEY or not ACCESS_TOKEN:
        print("❌ ERROR: KITE_API_KEY and KITE_ACCESS_TOKEN must be set in .env")
        print("\nTo get your access token:")
        print("  1. Run: uvicorn backend.main:app --reload")
        print("  2. Visit: http://localhost:8000/connect")
        print("  3. Login and copy the access_token from the response")
        print("  4. Add to .env: KITE_ACCESS_TOKEN=your_token_here")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("BACKTEST CONFIGURATION")
    print("="*60)
    print(f"  Instrument:          {args.instrument}")
    print(f"  Interval:            {args.interval}")
    print(f"  Period:              {args.days} days")
    print(f"  Initial Capital:     ₹{args.capital:,.2f}")
    print(f"  EMA Periods:         {args.fast_ema}/{args.slow_ema}")
    print(f"  Position Size:       {args.position_size * 100:.0f}%")
    print(f"  Commission:          {args.commission * 100:.2f}%")
    print("="*60 + "\n")
    
    # Fetch historical data
    print("📥 Fetching historical data from Kite API...")
    fetcher = HistoricalDataFetcher(API_KEY, ACCESS_TOKEN)
    
    df = fetcher.fetch_intraday_data(
        instrument_token=args.instrument,
        interval=args.interval,
        days_back=args.days
    )
    
    if df.empty:
        print("❌ No data fetched. Check your instrument token and date range.")
        sys.exit(1)
    
    print(f"✓ Fetched {len(df)} candles")
    print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
    
    # Run backtest
    print("\n🔬 Running backtest...")
    strategy = EMAStrategy(fast_period=args.fast_ema, slow_period=args.slow_ema)
    engine = BacktestEngine(
        initial_capital=args.capital,
        commission=args.commission,
        slippage=0.0001
    )
    
    results = engine.run_backtest(
        df=df,
        strategy=strategy,
        position_size_pct=args.position_size
    )
    
    if not results:
        print("❌ Backtest failed")
        sys.exit(1)
    
    # Print results
    engine.print_results(results)
    
    # Export trades if requested
    if args.export_trades:
        trade_log = engine.get_trade_log()
        if not trade_log.empty:
            filename = f"backtest_trades_{args.instrument}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            trade_log.to_csv(filename, index=False)
            print(f"✓ Trade log exported to {filename}")
    
    # Print sample trades
    if engine.trades:
        print("📋 RECENT TRADES (last 5):")
        trade_log = engine.get_trade_log()
        print(trade_log.tail(5).to_string(index=False))
    
    print("\n✅ Backtest complete!\n")


if __name__ == "__main__":
    main()
