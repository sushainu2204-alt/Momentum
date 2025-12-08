#!/usr/bin/env python
"""
Generate Synthetic Data for Backtesting

Creates realistic synthetic OHLCV data for backtesting when historical data
is not available. Uses configurable parameters for trend, volatility, and patterns.

Usage:
    # Generate data for a single symbol
    python generate_synthetic_data.py --symbol TESTSTOCK --days 365 --output ./data/synthetic
    
    # Generate data for multiple symbols
    python generate_synthetic_data.py --symbols TEST1 TEST2 TEST3 --days 180
    
    # Generate with specific parameters
    python generate_synthetic_data.py --symbol TESTSTOCK --days 365 \\
        --trend 0.1 --volatility 0.02 --start-price 1000
    
    # Generate with trending patterns
    python generate_synthetic_data.py --symbol BULLSTOCK --days 365 --pattern bullish
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional
import numpy as np
import pandas as pd

# Add backend to path
backend_path = str(Path(__file__).parent.parent.parent)
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


class SyntheticOHLCVGenerator:
    """
    Generate realistic synthetic OHLCV data.
    
    Uses geometric Brownian motion with configurable parameters
    to simulate realistic price movements.
    """
    
    def __init__(
        self,
        start_price: float = 1000.0,
        annual_return: float = 0.0,  # Expected annual return (drift)
        annual_volatility: float = 0.30,  # Annual volatility (30% typical for stocks)
        avg_volume: int = 1_000_000,
        volume_volatility: float = 0.5,
        seed: Optional[int] = None
    ):
        """
        Initialize generator.
        
        Args:
            start_price: Starting price
            annual_return: Expected annual return (0.0 = no trend, 0.1 = 10% annual growth)
            annual_volatility: Annual volatility (0.30 = 30%)
            avg_volume: Average daily volume
            volume_volatility: Volume variation (0.5 = +/- 50%)
            seed: Random seed for reproducibility
        """
        self.start_price = start_price
        self.annual_return = annual_return
        self.annual_volatility = annual_volatility
        self.avg_volume = avg_volume
        self.volume_volatility = volume_volatility
        
        if seed is not None:
            np.random.seed(seed)
    
    def generate_daily(
        self,
        start_date: date,
        end_date: date,
        skip_weekends: bool = True
    ) -> pd.DataFrame:
        """
        Generate daily OHLCV data.
        
        Args:
            start_date: Start date
            end_date: End date
            skip_weekends: Skip Saturday and Sunday
        
        Returns:
            DataFrame with daily OHLCV data
        """
        # Generate date range
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        
        if skip_weekends:
            dates = dates[dates.dayofweek < 5]  # Monday=0, Friday=4
        
        n_days = len(dates)
        
        # Daily parameters
        daily_return = self.annual_return / 252
        daily_vol = self.annual_volatility / np.sqrt(252)
        
        # Generate returns using geometric Brownian motion
        returns = np.random.normal(daily_return, daily_vol, n_days)
        
        # Generate prices
        prices = self.start_price * np.exp(np.cumsum(returns))
        
        # Generate OHLC from close prices
        opens = np.roll(prices, 1)
        opens[0] = self.start_price
        
        # Intraday range
        intraday_range = prices * daily_vol * np.random.uniform(0.5, 2.0, n_days)
        
        highs = np.maximum(opens, prices) + intraday_range * np.random.uniform(0, 1, n_days)
        lows = np.minimum(opens, prices) - intraday_range * np.random.uniform(0, 1, n_days)
        lows = np.maximum(lows, 0.01)  # Prevent negative prices
        
        # Generate volume
        volumes = self.avg_volume * np.exp(
            np.random.normal(0, self.volume_volatility, n_days)
        )
        volumes = volumes.astype(int)
        
        # Create DataFrame
        df = pd.DataFrame({
            'datetime': dates,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': prices,
            'volume': volumes
        })
        
        df = df.set_index('datetime')
        
        return df
    
    def generate_intraday(
        self,
        trade_date: date,
        interval_minutes: int = 1,
        market_open: str = "09:15",
        market_close: str = "15:30"
    ) -> pd.DataFrame:
        """
        Generate intraday OHLCV data for a single day.
        
        Args:
            trade_date: Date to generate data for
            interval_minutes: Candle interval in minutes
            market_open: Market open time (HH:MM)
            market_close: Market close time (HH:MM)
        
        Returns:
            DataFrame with intraday OHLCV data
        """
        # Parse times
        open_time = datetime.strptime(market_open, "%H:%M").time()
        close_time = datetime.strptime(market_close, "%H:%M").time()
        
        # Generate timestamps
        start_dt = datetime.combine(trade_date, open_time)
        end_dt = datetime.combine(trade_date, close_time)
        
        timestamps = pd.date_range(
            start=start_dt,
            end=end_dt,
            freq=f'{interval_minutes}min'
        )
        
        n_bars = len(timestamps)
        
        # Intraday volatility is lower
        intraday_vol = self.annual_volatility / np.sqrt(252 * (375 / interval_minutes))
        
        # Generate returns
        returns = np.random.normal(0, intraday_vol, n_bars)
        
        # Generate prices
        prices = self.start_price * np.exp(np.cumsum(returns))
        
        # OHLC
        opens = np.roll(prices, 1)
        opens[0] = self.start_price
        
        bar_range = prices * intraday_vol * np.random.uniform(0.5, 1.5, n_bars)
        
        highs = np.maximum(opens, prices) + bar_range * np.random.uniform(0, 1, n_bars)
        lows = np.minimum(opens, prices) - bar_range * np.random.uniform(0, 1, n_bars)
        lows = np.maximum(lows, 0.01)
        
        # Volume distribution (higher at open/close)
        time_of_day = np.array([(t.hour * 60 + t.minute - 9*60 - 15) / 375 for t in timestamps])
        volume_curve = 1 + 0.5 * (np.exp(-10 * time_of_day) + np.exp(-10 * (1 - time_of_day)))
        
        volumes = (self.avg_volume / n_bars) * volume_curve
        volumes = volumes * np.exp(np.random.normal(0, 0.3, n_bars))
        volumes = volumes.astype(int)
        
        df = pd.DataFrame({
            'datetime': timestamps,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': prices,
            'volume': volumes
        })
        
        df = df.set_index('datetime')
        
        return df
    
    def generate_minute_data(
        self,
        start_date: date,
        end_date: date,
        interval_minutes: int = 1
    ) -> pd.DataFrame:
        """
        Generate minute-level data for a date range.
        
        Args:
            start_date: Start date
            end_date: End date
            interval_minutes: Candle interval
        
        Returns:
            DataFrame with minute-level OHLCV data
        """
        all_data = []
        current_price = self.start_price
        current_date = start_date
        
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() < 5:
                # Generate day's data
                day_gen = SyntheticOHLCVGenerator(
                    start_price=current_price,
                    annual_return=self.annual_return,
                    annual_volatility=self.annual_volatility,
                    avg_volume=self.avg_volume,
                    volume_volatility=self.volume_volatility
                )
                
                day_df = day_gen.generate_intraday(
                    current_date,
                    interval_minutes=interval_minutes
                )
                
                all_data.append(day_df)
                
                # Update price for next day
                if len(day_df) > 0:
                    current_price = day_df['close'].iloc[-1]
            
            current_date += timedelta(days=1)
        
        if not all_data:
            return pd.DataFrame()
        
        return pd.concat(all_data)


def generate_with_pattern(
    pattern: str,
    start_date: date,
    end_date: date,
    start_price: float = 1000.0,
    interval: str = "day"
) -> pd.DataFrame:
    """
    Generate data with specific patterns.
    
    Patterns:
        - bullish: Steady uptrend
        - bearish: Steady downtrend
        - sideways: Range-bound
        - volatile: High volatility
        - breakout: Consolidation then breakout
    """
    pattern_params = {
        "bullish": {"annual_return": 0.50, "annual_volatility": 0.25},
        "bearish": {"annual_return": -0.30, "annual_volatility": 0.30},
        "sideways": {"annual_return": 0.0, "annual_volatility": 0.15},
        "volatile": {"annual_return": 0.10, "annual_volatility": 0.60},
        "breakout": {"annual_return": 0.20, "annual_volatility": 0.20},
    }
    
    if pattern not in pattern_params:
        raise ValueError(f"Unknown pattern: {pattern}. Valid: {list(pattern_params.keys())}")
    
    params = pattern_params[pattern]
    
    generator = SyntheticOHLCVGenerator(
        start_price=start_price,
        annual_return=params["annual_return"],
        annual_volatility=params["annual_volatility"]
    )
    
    if interval == "day":
        return generator.generate_daily(start_date, end_date)
    else:
        interval_minutes = int(interval.replace("minute", ""))
        return generator.generate_minute_data(start_date, end_date, interval_minutes)


def save_data(df: pd.DataFrame, symbol: str, output_dir: str, format: str = "parquet"):
    """Save data to file."""
    os.makedirs(output_dir, exist_ok=True)
    
    start_str = df.index.min().strftime("%Y%m%d")
    end_str = df.index.max().strftime("%Y%m%d")
    
    # Detect interval
    if len(df) > 1:
        time_diff = (df.index[1] - df.index[0]).total_seconds()
        if time_diff < 86400:  # Less than a day
            interval = f"{int(time_diff / 60)}minute"
        else:
            interval = "day"
    else:
        interval = "unknown"
    
    filename = f"{symbol}_{interval}_{start_str}_{end_str}.{format}"
    file_path = os.path.join(output_dir, filename)
    
    if format == "parquet":
        df.to_parquet(file_path)
    else:
        df.to_csv(file_path)
    
    print(f"Saved: {file_path} ({len(df):,} rows)")
    return file_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic OHLCV data for backtesting"
    )
    
    # Symbols
    parser.add_argument(
        "--symbol",
        type=str,
        help="Symbol name for the generated data"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Multiple symbols to generate"
    )
    
    # Date range
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Number of days of data to generate"
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD), default: days ago from today"
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
        default="day",
        choices=["1minute", "5minute", "15minute", "day"],
        help="Data interval"
    )
    
    # Parameters
    parser.add_argument(
        "--start-price",
        type=float,
        default=1000.0,
        help="Starting price"
    )
    parser.add_argument(
        "--trend",
        type=float,
        default=0.0,
        help="Annual trend/drift (0.1 = 10%% annual growth)"
    )
    parser.add_argument(
        "--volatility",
        type=float,
        default=0.30,
        help="Annual volatility (0.30 = 30%%)"
    )
    parser.add_argument(
        "--volume",
        type=int,
        default=1_000_000,
        help="Average daily volume"
    )
    
    # Pattern
    parser.add_argument(
        "--pattern",
        choices=["bullish", "bearish", "sideways", "volatile", "breakout"],
        help="Generate with a specific pattern (overrides trend/volatility)"
    )
    
    # Output
    parser.add_argument(
        "--output",
        default="./data/synthetic",
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
        "--seed",
        type=int,
        help="Random seed for reproducibility"
    )
    
    args = parser.parse_args()
    
    # Determine symbols
    symbols = []
    if args.symbol:
        symbols = [args.symbol]
    elif args.symbols:
        symbols = args.symbols
    else:
        print("Error: --symbol or --symbols required")
        sys.exit(1)
    
    # Determine date range
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    
    if args.start:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    else:
        start_date = end_date - timedelta(days=args.days)
    
    print(f"Generating synthetic data for {len(symbols)} symbol(s)")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Interval: {args.interval}")
    print(f"Output: {args.output}\n")
    
    # Generate data for each symbol
    for i, symbol in enumerate(symbols):
        print(f"[{i+1}/{len(symbols)}] Generating {symbol}...", end=" ")
        
        if args.pattern:
            df = generate_with_pattern(
                pattern=args.pattern,
                start_date=start_date,
                end_date=end_date,
                start_price=args.start_price,
                interval=args.interval
            )
        else:
            if args.seed is not None:
                seed = args.seed + i  # Different seed for each symbol
            else:
                seed = None
            
            generator = SyntheticOHLCVGenerator(
                start_price=args.start_price,
                annual_return=args.trend,
                annual_volatility=args.volatility,
                avg_volume=args.volume,
                seed=seed
            )
            
            if args.interval == "day":
                df = generator.generate_daily(start_date, end_date)
            else:
                interval_minutes = int(args.interval.replace("minute", ""))
                df = generator.generate_minute_data(start_date, end_date, interval_minutes)
        
        save_data(df, symbol, args.output, args.format)
    
    print(f"\nDone! Generated data saved to {args.output}")


if __name__ == "__main__":
    main()
