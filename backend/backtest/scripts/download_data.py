#!/usr/bin/env python
"""
Download Historical Data Script

Command-line script to download historical data for backtesting.
Supports both NSE (daily) and Zerodha Kite (intraday).

Usage:
    # Download NSE daily data
    python download_data.py --source nse --symbols RELIANCE TCS INFY --start 2023-01-01 --end 2024-06-30
    
    # Download from universe file
    python download_data.py --source nse --universe nifty500 --start 2023-01-01 --end 2024-06-30
    
    # Download Kite 1-minute data (requires API credentials)
    python download_data.py --source kite --symbols RELIANCE --start 2024-06-01 --end 2024-06-30 --interval 1minute
    
    # List available data
    python download_data.py --list-data
"""

import argparse
import asyncio
import os
import sys
from datetime import date, datetime
from pathlib import Path

# Add backend to path
backend_path = str(Path(__file__).parent.parent.parent)
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download historical data for backtesting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download daily data from NSE for Nifty 500 (default)
  python download_data.py --source nse --start 2023-01-01 --end 2024-06-30

  # Download specific symbols only
  python download_data.py --source nse --symbols RELIANCE TCS INFY \\
      --start 2023-01-01 --end 2024-06-30

  # Download from FNO universe with limit
  python download_data.py --source nse --universe fno --limit 50 \\
      --start 2023-01-01 --end 2024-06-30

  # Download 1-minute data from Kite (requires credentials)
  python download_data.py --source kite --symbols RELIANCE \\
      --start 2024-06-01 --end 2024-06-30 --interval 1minute

  # List available downloaded data
  python download_data.py --list-data

  # Validate downloaded data
  python download_data.py --validate RELIANCE
        """
    )
    
    # Main actions
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--list-data",
        action="store_true",
        help="List available downloaded data"
    )
    action_group.add_argument(
        "--validate",
        type=str,
        metavar="SYMBOL",
        help="Validate data for a symbol"
    )
    
    # Data source
    parser.add_argument(
        "--source",
        type=str,
        choices=["nse", "kite"],
        default="nse",
        help="Data source (default: nse)"
    )
    
    # Symbols
    parser.add_argument(
        "--symbols",
        type=str,
        nargs="+",
        help="Specific symbols to download (optional, defaults to universe)"
    )
    parser.add_argument(
        "--universe",
        type=str,
        choices=["nifty500", "fno"],
        default="nifty500",
        help="Download entire universe (default: nifty500)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of symbols from universe"
    )
    
    # Date range
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD)"
    )
    
    # Interval
    parser.add_argument(
        "--interval",
        type=str,
        choices=["1minute", "3minute", "5minute", "15minute", "30minute", "60minute", "day"],
        default="day",
        help="Data interval (default: day)"
    )
    
    # Output
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./data/historical",
        help="Output directory (default: ./data/historical)"
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["parquet", "csv"],
        default="parquet",
        help="Output format (default: parquet)"
    )
    
    # Options
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip already downloaded files (default: True)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download existing files"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Batch size for parallel downloads"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output"
    )
    
    # Kite credentials (for kite source)
    parser.add_argument(
        "--kite-api-key",
        type=str,
        help="Kite API key (or set KITE_API_KEY env var)"
    )
    parser.add_argument(
        "--kite-access-token",
        type=str,
        help="Kite access token (or set KITE_ACCESS_TOKEN env var)"
    )
    
    return parser.parse_args()


def load_universe(universe_name: str) -> list:
    """Load symbols from universe file."""
    import pandas as pd
    
    universe_files = {
        "nifty500": "data/universes/nifty500_stocks.csv",
        "fno": "data/universes/fno_stocks.csv"
    }
    
    file_path = os.path.join(backend_path, universe_files.get(universe_name, ""))
    
    if not os.path.exists(file_path):
        print(f"Error: Universe file not found: {file_path}")
        sys.exit(1)
    
    df = pd.read_csv(file_path)
    
    if 'symbol' in df.columns:
        return df['symbol'].tolist()
    else:
        return df.iloc[:, 0].tolist()


def list_available_data(data_dir: str):
    """List available downloaded data."""
    from backtest.data import DataManager
    
    manager = DataManager(data_dir=data_dir)
    print(manager.generate_data_report())


def validate_data(symbol: str, data_dir: str):
    """Validate downloaded data for a symbol."""
    from backtest.data import DataManager
    
    manager = DataManager(data_dir=data_dir)
    df = manager.load_symbol(symbol)
    
    if df is None:
        print(f"No data found for {symbol}")
        return
    
    report = manager.validate_data(df, symbol)
    
    print(f"\nValidation Report: {symbol}")
    print("=" * 40)
    print(f"Rows: {report['rows']:,}")
    print(f"Date range: {report['start_date']} to {report['end_date']}")
    print(f"Valid: {'✓' if report['valid'] else '✗'}")
    
    if report['issues']:
        print("\nIssues:")
        for issue in report['issues']:
            print(f"  - {issue}")
    
    if 'stats' in report:
        print(f"\nStatistics:")
        print(f"  Price range: {report['stats']['price_range']}")
        print(f"  Avg volume: {report['stats']['avg_volume']:,.0f}")
        print(f"  Trading days: {report['stats']['trading_days']}")


async def download_nse_data(args):
    """Download data from NSE."""
    from backtest.data import NSEHistoricalDownloader, DataDownloadConfig, DataInterval
    
    # Use specific symbols if provided, otherwise load universe
    if args.symbols:
        symbols = args.symbols
    else:
        symbols = load_universe(args.universe)
        if args.limit:
            symbols = symbols[:args.limit]
    
    print(f"Downloading NSE daily data for {len(symbols)} symbols")
    print(f"Date range: {args.start} to {args.end}")
    print(f"Output: {args.output_dir}")
    print()
    
    config = DataDownloadConfig(
        start_date=datetime.strptime(args.start, "%Y-%m-%d").date(),
        end_date=datetime.strptime(args.end, "%Y-%m-%d").date(),
        interval=DataInterval.DAY,
        output_dir=args.output_dir,
        save_format=args.format,
        skip_existing=not args.force,
        show_progress=not args.quiet
    )
    
    downloader = NSEHistoricalDownloader(config)
    summary = await downloader.download_batch(symbols)
    
    print()
    print(summary)
    
    if summary.failed_symbols:
        print(f"\nFailed symbols: {', '.join(summary.failed_symbols[:10])}")
        if len(summary.failed_symbols) > 10:
            print(f"  ... and {len(summary.failed_symbols) - 10} more")


async def download_kite_data(args):
    """Download data from Zerodha Kite."""
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        print("Error: kiteconnect package not installed")
        print("Install with: pip install kiteconnect")
        sys.exit(1)
    
    from backtest.data import KiteHistoricalDownloader, DataDownloadConfig, DataInterval
    
    # Get credentials
    api_key = args.kite_api_key or os.environ.get("KITE_API_KEY")
    access_token = args.kite_access_token or os.environ.get("KITE_ACCESS_TOKEN")
    
    if not api_key or not access_token:
        print("Error: Kite API credentials required")
        print("Set --kite-api-key and --kite-access-token, or")
        print("Set KITE_API_KEY and KITE_ACCESS_TOKEN environment variables")
        sys.exit(1)
    
    # Use specific symbols if provided, otherwise load universe
    if args.symbols:
        symbols = args.symbols
    else:
        symbols = load_universe(args.universe)
        if args.limit:
            symbols = symbols[:args.limit]
    
    # Map interval
    interval_map = {
        "1minute": DataInterval.MINUTE_1,
        "3minute": DataInterval.MINUTE_3,
        "5minute": DataInterval.MINUTE_5,
        "15minute": DataInterval.MINUTE_15,
        "30minute": DataInterval.MINUTE_30,
        "60minute": DataInterval.MINUTE_60,
        "day": DataInterval.DAY,
    }
    
    print(f"Downloading Kite {args.interval} data for {len(symbols)} symbols")
    print(f"Date range: {args.start} to {args.end}")
    print()
    
    # Initialize Kite
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    
    config = DataDownloadConfig(
        start_date=datetime.strptime(args.start, "%Y-%m-%d").date(),
        end_date=datetime.strptime(args.end, "%Y-%m-%d").date(),
        interval=interval_map[args.interval],
        output_dir=args.output_dir,
        save_format=args.format,
        skip_existing=not args.force,
        show_progress=not args.quiet
    )
    
    downloader = KiteHistoricalDownloader(config, kite)
    
    # Get instrument tokens
    print("Fetching instrument tokens...")
    instruments = await downloader.get_instruments("NSE")
    token_map = downloader.get_instrument_tokens(symbols, instruments)
    
    missing = [s for s in symbols if s not in token_map]
    if missing:
        print(f"Warning: No tokens found for: {missing[:5]}")
    
    summary = await downloader.download_batch(symbols, token_map)
    
    print()
    print(summary)


def main():
    args = parse_args()
    
    # Handle list-data action
    if args.list_data:
        list_available_data(args.output_dir)
        return
    
    # Handle validate action
    if args.validate:
        validate_data(args.validate, args.output_dir)
        return
    
    # Validate download arguments
    if not args.start or not args.end:
        print("Error: --start and --end dates are required for download")
        sys.exit(1)
    
    # Symbols default to universe if not specified
    # No error needed - universe has a default value
    
    # Run download
    if args.source == "nse":
        asyncio.run(download_nse_data(args))
    else:
        asyncio.run(download_kite_data(args))


if __name__ == "__main__":
    main()
