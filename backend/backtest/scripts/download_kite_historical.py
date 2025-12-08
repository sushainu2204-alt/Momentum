#!/usr/bin/env python
"""
Download Kite Historical Data with Authentication Helper

This script handles the full Kite authentication flow and downloads historical data.
Run this interactively to complete the OAuth login.

Usage:
    # First time - complete login flow
    python download_kite_historical.py --login
    
    # After login, download data
    python download_kite_historical.py --symbols RELIANCE TCS --start 2024-06-01 --end 2024-06-30

    # Download from universe
    python download_kite_historical.py --universe nifty500 --start 2024-06-01 --end 2024-06-30 --interval 5minute
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

# Add backend to path
backend_path = str(Path(__file__).parent.parent.parent)
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Token file location
TOKEN_FILE = os.path.join(backend_path, ".kite_token.json")


def load_config():
    """Load Kite config from settings or environment."""
    # Try to use existing settings module
    try:
        import sys
        sys.path.insert(0, backend_path)
        from backend.config import settings
        
        config = {
            "api_key": settings.KITE_API_KEY,
            "api_secret": settings.KITE_API_SECRET,
            "access_token": settings.KITE_ACCESS_TOKEN
        }
        
        if config["access_token"]:
            return config
    except Exception:
        pass
    
    # Fallback to environment
    config = {
        "api_key": os.environ.get("KITE_API_KEY"),
        "api_secret": os.environ.get("KITE_API_SECRET"),
        "access_token": os.environ.get("KITE_ACCESS_TOKEN")
    }
    
    # Try to load from .env file directly
    env_file = os.path.join(backend_path, "..", ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key == "KITE_API_KEY" and not config["api_key"]:
                        config["api_key"] = value
                    elif key == "KITE_API_SECRET" and not config["api_secret"]:
                        config["api_secret"] = value
                    elif key == "KITE_ACCESS_TOKEN" and value:
                        config["access_token"] = value
    
    return config


def save_token(access_token: str):
    """Save access token to file."""
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "access_token": access_token,
            "date": datetime.now().isoformat()
        }, f)
    print(f"Token saved to {TOKEN_FILE}")


def kite_login():
    """Interactive Kite login flow."""
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        print("Error: kiteconnect not installed. Run: pip install kiteconnect")
        sys.exit(1)
    
    config = load_config()
    
    if not config["api_key"]:
        print("KITE_API_KEY environment variable not set")
        config["api_key"] = input("Enter API Key: ").strip()
    
    if not config["api_secret"]:
        print("KITE_API_SECRET environment variable not set")
        config["api_secret"] = input("Enter API Secret: ").strip()
    
    kite = KiteConnect(api_key=config["api_key"])
    
    # Generate login URL
    login_url = kite.login_url()
    print("\n" + "=" * 60)
    print("KITE LOGIN")
    print("=" * 60)
    print("\n1. Open this URL in your browser:")
    print(f"\n   {login_url}\n")
    print("2. Login with your Zerodha credentials")
    print("3. After login, you'll be redirected to a URL like:")
    print("   https://127.0.0.1/?request_token=XXXXXXX&action=login")
    print("4. Copy the 'request_token' value from the URL")
    print("=" * 60)
    
    request_token = input("\nEnter the request_token: ").strip()
    
    try:
        data = kite.generate_session(request_token, api_secret=config["api_secret"])
        access_token = data["access_token"]
        
        print(f"\n✓ Login successful!")
        print(f"  User: {data.get('user_name', 'Unknown')}")
        print(f"  Email: {data.get('email', 'Unknown')}")
        
        save_token(access_token)
        
        return access_token
        
    except Exception as e:
        print(f"\n✗ Login failed: {e}")
        sys.exit(1)


def load_universe(universe_name: str, kite=None) -> list:
    """Load symbols from universe file or fetch all NSE stocks."""
    import pandas as pd
    import re
    
    # Handle 'all' - fetch all NSE equity stocks from Kite
    if universe_name.lower() == 'all':
        if kite is None:
            print("Error: Kite connection required for 'all' universe")
            sys.exit(1)
        
        print("Fetching all NSE equity stocks from Kite...")
        instruments = kite.instruments('NSE')
        
        # Filter for actual stocks (not bonds, ETFs, indices)
        def is_stock(i):
            symbol = i['tradingsymbol']
            if re.match(r'^[0-9]', symbol):
                return False
            if re.search(r'-N[0-9A-Z]*$', symbol):
                return False
            if 'NIFTY' in symbol or 'SENSEX' in symbol:
                return False
            if symbol.endswith('BEES') or symbol.endswith('ETF'):
                return False
            return True
        
        equities = [i for i in instruments if i['instrument_type'] == 'EQ' and is_stock(i)]
        symbols = [e['tradingsymbol'] for e in equities]
        print(f"Found {len(symbols)} NSE equity stocks")
        return symbols
    
    # Check if it's a file path
    if os.path.exists(universe_name):
        df = pd.read_csv(universe_name)
        return df.iloc[:, 0].tolist()
    
    # Predefined universes
    universe_files = {
        "nifty500": "data/universes/nifty500_stocks.csv",
        "fno": "data/universes/fno_stocks.csv"
    }
    
    file_path = os.path.join(backend_path, universe_files.get(universe_name, ""))
    
    if not os.path.exists(file_path):
        print(f"Error: Universe file not found: {file_path}")
        print("Use 'all' to download all NSE stocks, or provide a path to a CSV file")
        sys.exit(1)
    
    df = pd.read_csv(file_path)
    return df.iloc[:, 0].tolist()


async def download_data(args, kite):
    """Download historical data using Kite."""
    from backend.backtest.data import KiteHistoricalDownloader, DataDownloadConfig, DataInterval
    
    # Use specific symbols if provided, otherwise load universe
    if args.symbols:
        symbols = args.symbols
    else:
        symbols = load_universe(args.universe, kite)
        if args.limit:
            symbols = symbols[:args.limit]
    
    # Map interval
    interval_map = {
        "1minute": DataInterval.MINUTE_1,
        "3minute": DataInterval.MINUTE_3,
        "5minute": DataInterval.MINUTE_5,
        "10minute": DataInterval.MINUTE_10,
        "15minute": DataInterval.MINUTE_15,
        "30minute": DataInterval.MINUTE_30,
        "60minute": DataInterval.MINUTE_60,
        "day": DataInterval.DAY,
    }
    
    if args.interval not in interval_map:
        print(f"Error: Invalid interval: {args.interval}")
        sys.exit(1)
    
    print(f"\nDownloading {args.interval} data for {len(symbols)} symbols")
    print(f"Date range: {args.start} to {args.end}")
    print(f"Output: {args.output_dir}\n")
    
    config = DataDownloadConfig(
        start_date=datetime.strptime(args.start, "%Y-%m-%d").date(),
        end_date=datetime.strptime(args.end, "%Y-%m-%d").date(),
        interval=interval_map[args.interval],
        output_dir=args.output_dir,
        save_format=args.format,
        skip_existing=not args.force,
        show_progress=True,
        rate_limit_delay=args.delay
    )
    
    downloader = KiteHistoricalDownloader(config, kite)
    
    # Get instrument tokens
    print("Fetching instrument list from Kite...")
    instruments = await downloader.get_instruments("NSE")
    print(f"Found {len(instruments)} instruments")
    
    token_map = downloader.get_instrument_tokens(symbols, instruments)
    found = len(token_map)
    missing = len(symbols) - found
    
    print(f"Mapped {found} symbols to instrument tokens")
    if missing > 0:
        missing_symbols = [s for s in symbols if s not in token_map]
        print(f"Warning: {missing} symbols not found: {missing_symbols[:5]}...")
    
    print("\nStarting download...\n")
    
    # Download
    summary = await downloader.download_batch(symbols, token_map)
    
    print("\n" + "=" * 60)
    print(summary)
    print("=" * 60)
    
    if summary.failed_symbols:
        print(f"\nFailed: {', '.join(summary.failed_symbols[:10])}")


def main():
    parser = argparse.ArgumentParser(
        description="Download historical data from Zerodha Kite"
    )
    
    # Actions
    parser.add_argument(
        "--login",
        action="store_true",
        help="Perform Kite login flow"
    )
    
    # Symbols
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Specific symbols to download (optional, defaults to universe)"
    )
    parser.add_argument(
        "--universe",
        default="nifty500",
        help="Download universe: 'nifty500', 'fno', 'all' (all NSE stocks), or path to CSV file"
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
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date (YYYY-MM-DD)"
    )
    
    # Interval
    parser.add_argument(
        "--interval",
        default="1minute",
        choices=["1minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"],
        help="Data interval"
    )
    
    # Output
    parser.add_argument(
        "--output-dir",
        default="./data/historical",
        help="Output directory"
    )
    parser.add_argument(
        "--format",
        choices=["parquet", "csv"],
        default="parquet",
        help="Output format"
    )
    
    # Options
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download existing files"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between requests (seconds)"
    )
    
    args = parser.parse_args()
    
    # Handle login
    if args.login:
        kite_login()
        return
    
    # Load token
    config = load_config()
    
    if not config["access_token"]:
        print("No saved access token. Run with --login first")
        sys.exit(1)
    
    if not config["api_key"]:
        print("KITE_API_KEY not set")
        sys.exit(1)
    
    # Validate download args
    if not args.start:
        print("Error: --start date required")
        sys.exit(1)
    
    # No need to check symbols - universe has default value
    
    # Initialize Kite
    try:
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=config["api_key"])
        kite.set_access_token(config["access_token"])
        
        # Test connection
        profile = kite.profile()
        print(f"Logged in as: {profile.get('user_name', 'Unknown')}")
        
    except Exception as e:
        print(f"Error connecting to Kite: {e}")
        print("Try running with --login to refresh token")
        sys.exit(1)
    
    # Download
    asyncio.run(download_data(args, kite))


if __name__ == "__main__":
    main()
