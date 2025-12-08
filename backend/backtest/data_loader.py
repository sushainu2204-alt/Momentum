"""
Data Loader Module

Loads and normalizes historical OHLCV data from various sources.
Supports CSV, Parquet, and can be extended for API sources.

Features:
    - Load minute-level data for multiple symbols
    - Normalize timestamps to consistent timezone
    - Merge multi-day data seamlessly
    - Handle gaps and missing data
    - Memory-efficient loading for large datasets
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Union, Iterator, Tuple
from enum import Enum
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """Supported data sources."""
    CSV = "csv"
    PARQUET = "parquet"
    FEATHER = "feather"


class DataLoader:
    """
    Historical data loader for backtesting.
    
    Loads OHLCV data from files and provides:
    - Multi-symbol loading
    - Date range filtering
    - Timestamp normalization
    - Memory-efficient iteration
    
    Expected data format:
        timestamp (or date/datetime), open, high, low, close, volume
    
    Usage:
        loader = DataLoader(data_path="data/historical", frequency="1min")
        
        # Load specific symbols
        data = loader.load_symbols(['RELIANCE', 'TCS'], start_date, end_date)
        
        # Iterate by day for memory efficiency
        for day_data in loader.iterate_by_day(['RELIANCE'], start_date, end_date):
            process(day_data)
    """
    
    # Standard column names
    REQUIRED_COLUMNS = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    COLUMN_ALIASES = {
        'datetime': 'timestamp',
        'date': 'timestamp',
        'time': 'timestamp',
        'o': 'open',
        'h': 'high',
        'l': 'low',
        'c': 'close',
        'v': 'volume',
        'vol': 'volume',
    }
    
    def __init__(
        self,
        data_path: str = "data/historical",
        frequency: str = "1min",
        source_type: DataSource = None,  # Auto-detect if None
        timezone: str = "Asia/Kolkata"
    ):
        """
        Initialize data loader.
        
        Args:
            data_path: Base path to historical data files
            frequency: Data frequency (1min, 5min, 15min, 1d)
            source_type: Type of data files (auto-detected if None)
            timezone: Timezone for timestamp normalization
        """
        self.data_path = Path(data_path)
        self.frequency = frequency
        self.timezone = timezone
        
        # Auto-detect source type if not specified
        if source_type is None:
            self.source_type = self._detect_source_type()
        else:
            self.source_type = source_type
        
        # Cache for loaded data
        self._data_cache: Dict[str, pd.DataFrame] = {}
        self._symbol_files: Dict[str, Path] = {}
        
        # Scan for available data files
        self._scan_data_files()
    
    def _detect_source_type(self) -> DataSource:
        """Auto-detect source type based on files in directory."""
        if not self.data_path.exists():
            return DataSource.CSV
        
        # Check for files by extension
        parquet_files = list(self.data_path.rglob("*.parquet"))
        csv_files = list(self.data_path.rglob("*.csv"))
        feather_files = list(self.data_path.rglob("*.feather"))
        
        if parquet_files:
            logger.info(f"Auto-detected parquet files ({len(parquet_files)} files)")
            return DataSource.PARQUET
        elif feather_files:
            logger.info(f"Auto-detected feather files ({len(feather_files)} files)")
            return DataSource.FEATHER
        else:
            return DataSource.CSV
    
    def _scan_data_files(self) -> None:
        """Scan data directory for available symbol files."""
        if not self.data_path.exists():
            logger.warning(f"Data path does not exist: {self.data_path}")
            return
        
        # Look for files matching patterns
        extension = f".{self.source_type.value}"
        
        for file_path in self.data_path.rglob(f"*{extension}"):
            # Extract symbol from filename
            # Handle patterns like: RELIANCE_1minute_20251108_20251208.parquet
            filename = file_path.stem
            parts = filename.split('_')
            
            if len(parts) >= 1:
                symbol = parts[0].upper()
                
                # Store the file (prefer newer date ranges)
                if symbol not in self._symbol_files:
                    self._symbol_files[symbol] = file_path
                else:
                    # If multiple files for same symbol, keep the one with latest date
                    existing = self._symbol_files[symbol].stem
                    if filename > existing:  # Lexicographic compare favors newer dates
                        self._symbol_files[symbol] = file_path
        
        logger.info(f"Found {len(self._symbol_files)} data files")
    
    def get_available_symbols(self) -> List[str]:
        """Get list of symbols with available data."""
        return list(self._symbol_files.keys())
    
    def load_symbol(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Load OHLCV data for a single symbol.
        
        Args:
            symbol: Stock symbol
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            use_cache: Whether to use cached data
        
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
            Or None if data not available
        """
        symbol = symbol.upper()
        cache_key = f"{symbol}_{start_date}_{end_date}"
        
        # Check cache
        if use_cache and cache_key in self._data_cache:
            return self._data_cache[cache_key].copy()
        
        # Find data file
        file_path = self._symbol_files.get(symbol)
        if file_path is None:
            # Try alternative naming conventions
            file_path = self._find_symbol_file(symbol)
        
        if file_path is None or not file_path.exists():
            logger.warning(f"No data file found for {symbol}")
            return None
        
        # Load data
        try:
            df = self._load_file(file_path)
        except Exception as e:
            logger.error(f"Error loading {symbol}: {e}")
            return None
        
        if df is None or df.empty:
            return None
        
        # Normalize columns
        df = self._normalize_columns(df)
        
        # Filter by date range
        if start_date is not None:
            df = df[df['timestamp'].dt.date >= start_date]
        if end_date is not None:
            df = df[df['timestamp'].dt.date <= end_date]
        
        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Add symbol column
        df['symbol'] = symbol
        
        # Cache the result
        if use_cache:
            self._data_cache[cache_key] = df.copy()
        
        return df
    
    def _find_symbol_file(self, symbol: str) -> Optional[Path]:
        """Try to find file with alternative naming."""
        patterns = [
            f"{symbol}.*",
            f"{symbol.lower()}.*",
            f"*{symbol}*.*",
        ]
        
        extension = f".{self.source_type.value}"
        
        for pattern in patterns:
            matches = list(self.data_path.rglob(pattern + extension))
            if matches:
                return matches[0]
        
        return None
    
    def _load_file(self, file_path: Path) -> Optional[pd.DataFrame]:
        """Load data from file based on source type."""
        try:
            if self.source_type == DataSource.CSV:
                df = pd.read_csv(file_path, parse_dates=['timestamp'])
            elif self.source_type == DataSource.PARQUET:
                df = pd.read_parquet(file_path)
                # If datetime is in index, reset it to a column
                if isinstance(df.index, pd.DatetimeIndex):
                    df = df.reset_index()
                    # Rename index column to timestamp if it's named 'datetime' or similar
                    if df.columns[0] in ['datetime', 'date', 'time', 'index']:
                        df = df.rename(columns={df.columns[0]: 'timestamp'})
                    elif df.columns[0] not in ['timestamp']:
                        df = df.rename(columns={df.columns[0]: 'timestamp'})
            elif self.source_type == DataSource.FEATHER:
                df = pd.read_feather(file_path)
            else:
                raise ValueError(f"Unsupported source type: {self.source_type}")
            
            return df
        except Exception as e:
            # Try with different date column names
            try:
                df = pd.read_csv(file_path)
                return df
            except:
                raise e
    
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize column names to standard format.
        
        Handles various naming conventions from different data sources.
        """
        # Lowercase all column names
        df.columns = df.columns.str.lower().str.strip()
        
        # Rename using aliases
        df = df.rename(columns=self.COLUMN_ALIASES)
        
        # Ensure timestamp is datetime
        if 'timestamp' in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Handle separate date and time columns
        if 'timestamp' not in df.columns and 'date' in df.columns:
            if 'time' in df.columns:
                df['timestamp'] = pd.to_datetime(
                    df['date'].astype(str) + ' ' + df['time'].astype(str)
                )
            else:
                df['timestamp'] = pd.to_datetime(df['date'])
        
        # Localize to timezone if naive
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize(self.timezone)
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert(self.timezone)
        
        # Ensure numeric columns
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Select only required columns
        available_cols = [c for c in self.REQUIRED_COLUMNS if c in df.columns]
        df = df[available_cols]
        
        # Remove rows with NaN
        df = df.dropna()
        
        return df
    
    def load_symbols(
        self,
        symbols: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        parallel: bool = True,
        max_workers: int = 4
    ) -> Dict[str, pd.DataFrame]:
        """
        Load OHLCV data for multiple symbols.
        
        Args:
            symbols: List of stock symbols
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            parallel: Load in parallel for speed
            max_workers: Number of parallel workers
        
        Returns:
            Dictionary mapping symbol -> DataFrame
        """
        result: Dict[str, pd.DataFrame] = {}
        
        if parallel and len(symbols) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_symbol = {
                    executor.submit(
                        self.load_symbol, symbol, start_date, end_date
                    ): symbol
                    for symbol in symbols
                }
                
                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    try:
                        df = future.result()
                        if df is not None and not df.empty:
                            result[symbol] = df
                    except Exception as e:
                        logger.error(f"Error loading {symbol}: {e}")
        else:
            for symbol in symbols:
                df = self.load_symbol(symbol, start_date, end_date)
                if df is not None and not df.empty:
                    result[symbol] = df
        
        logger.info(f"Loaded data for {len(result)}/{len(symbols)} symbols")
        return result
    
    def iterate_by_day(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date
    ) -> Iterator[Tuple[date, Dict[str, pd.DataFrame]]]:
        """
        Iterate through data day by day.
        
        Memory efficient for large datasets.
        
        Args:
            symbols: List of symbols to load
            start_date: Start date
            end_date: End date
        
        Yields:
            Tuple of (date, {symbol: DataFrame for that day})
        """
        # Load all data first (could optimize for very large datasets)
        all_data = self.load_symbols(symbols, start_date, end_date)
        
        # Iterate through each trading day
        current_date = start_date
        while current_date <= end_date:
            day_data = {}
            
            for symbol, df in all_data.items():
                day_df = df[df['timestamp'].dt.date == current_date]
                if not day_df.empty:
                    day_data[symbol] = day_df.reset_index(drop=True)
            
            if day_data:  # Only yield if we have data for this day
                yield current_date, day_data
            
            current_date += timedelta(days=1)
    
    def iterate_by_candle(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date,
        market_open: time = time(9, 15),
        market_close: time = time(15, 30)
    ) -> Iterator[Tuple[datetime, Dict[str, pd.Series]]]:
        """
        Iterate through data candle by candle across all symbols.
        
        This is the main iteration method for the backtest engine.
        At each timestamp, yields data for all symbols at that moment.
        
        Args:
            symbols: List of symbols
            start_date: Start date
            end_date: End date
            market_open: Market open time
            market_close: Market close time
        
        Yields:
            Tuple of (timestamp, {symbol: candle_series})
        """
        # Load all data
        all_data = self.load_symbols(symbols, start_date, end_date)
        
        if not all_data:
            logger.warning("No data loaded")
            return
        
        # Get all unique timestamps
        all_timestamps = set()
        for df in all_data.values():
            all_timestamps.update(df['timestamp'].tolist())
        
        # Sort timestamps
        sorted_timestamps = sorted(all_timestamps)
        
        # Filter to market hours
        filtered_timestamps = [
            ts for ts in sorted_timestamps
            if market_open <= ts.time() <= market_close
        ]
        
        logger.info(f"Iterating through {len(filtered_timestamps)} candles")
        
        # Yield candle by candle
        for timestamp in filtered_timestamps:
            candle_data = {}
            
            for symbol, df in all_data.items():
                candle = df[df['timestamp'] == timestamp]
                if not candle.empty:
                    candle_data[symbol] = candle.iloc[0]
            
            if candle_data:
                yield timestamp, candle_data
    
    def get_historical_context(
        self,
        symbol: str,
        current_timestamp: datetime,
        lookback_candles: int = 100,
        full_data: Optional[Dict[str, pd.DataFrame]] = None
    ) -> Optional[pd.DataFrame]:
        """
        Get historical candles up to current timestamp.
        
        Used by strategies that need lookback data.
        
        Args:
            symbol: Stock symbol
            current_timestamp: Current backtest timestamp
            lookback_candles: Number of candles to return
            full_data: Pre-loaded data dict (for efficiency)
        
        Returns:
            DataFrame with historical candles up to current_timestamp
        """
        if full_data and symbol in full_data:
            df = full_data[symbol]
        else:
            df = self._data_cache.get(symbol)
            if df is None:
                df = self.load_symbol(symbol)
        
        if df is None:
            return None
        
        # Get data up to current timestamp
        historical = df[df['timestamp'] <= current_timestamp]
        
        # Limit to lookback
        if len(historical) > lookback_candles:
            historical = historical.iloc[-lookback_candles:]
        
        return historical.reset_index(drop=True)
    
    def clear_cache(self) -> None:
        """Clear the data cache."""
        self._data_cache.clear()
        logger.info("Data cache cleared")
    
    def get_universe_symbols(self, universe_file: str) -> List[str]:
        """
        Load symbol list from universe file.
        
        Args:
            universe_file: Path to CSV with symbols
        
        Returns:
            List of symbols
        """
        try:
            df = pd.read_csv(universe_file)
            
            # Try different column names
            for col in ['symbol', 'Symbol', 'SYMBOL', 'ticker', 'Ticker']:
                if col in df.columns:
                    return df[col].str.upper().tolist()
            
            # If no recognized column, use first column
            return df.iloc[:, 0].str.upper().tolist()
        
        except Exception as e:
            logger.error(f"Error loading universe file: {e}")
            return []
    
    def validate_data_quality(
        self,
        df: pd.DataFrame,
        symbol: str
    ) -> Dict[str, any]:
        """
        Check data quality and return report.
        
        Args:
            df: DataFrame to check
            symbol: Symbol name for logging
        
        Returns:
            Quality report dictionary
        """
        report = {
            'symbol': symbol,
            'total_rows': len(df),
            'date_range': (df['timestamp'].min(), df['timestamp'].max()),
            'missing_values': df.isnull().sum().to_dict(),
            'duplicates': df.duplicated(subset=['timestamp']).sum(),
            'gaps': 0,
            'suspicious_prices': 0,
        }
        
        # Check for gaps (missing candles)
        if len(df) > 1:
            time_diffs = df['timestamp'].diff()
            expected_diff = pd.Timedelta(minutes=1)  # For 1min data
            gaps = (time_diffs > expected_diff * 2).sum()
            report['gaps'] = int(gaps)
        
        # Check for suspicious price jumps
        if 'close' in df.columns:
            pct_change = df['close'].pct_change().abs()
            suspicious = (pct_change > 0.20).sum()  # 20% moves
            report['suspicious_prices'] = int(suspicious)
        
        return report


class SyntheticDataGenerator:
    """
    Generate synthetic OHLCV data for testing.
    
    Useful for testing the backtest engine without real data.
    """
    
    @staticmethod
    def generate_random_walk(
        symbol: str,
        start_date: date,
        end_date: date,
        initial_price: float = 100.0,
        volatility: float = 0.02,
        frequency: str = "1min"
    ) -> pd.DataFrame:
        """
        Generate random walk price data.
        
        Args:
            symbol: Symbol name
            start_date: Start date
            end_date: End date
            initial_price: Starting price
            volatility: Daily volatility
            frequency: Data frequency
        
        Returns:
            DataFrame with synthetic OHLCV data
        """
        # Generate timestamps
        timestamps = []
        current = datetime.combine(start_date, time(9, 15))
        end = datetime.combine(end_date, time(15, 30))
        
        freq_minutes = int(frequency.replace('min', ''))
        
        while current <= end:
            if current.weekday() < 5:  # Skip weekends
                if time(9, 15) <= current.time() <= time(15, 30):
                    timestamps.append(current)
            current += timedelta(minutes=freq_minutes)
        
        n = len(timestamps)
        
        # Generate returns
        minute_vol = volatility / np.sqrt(375)  # 375 minutes in trading day
        returns = np.random.normal(0, minute_vol, n)
        
        # Generate prices
        close = initial_price * np.exp(np.cumsum(returns))
        
        # Generate OHLC from close
        noise = np.random.uniform(0.001, 0.005, n)
        high = close * (1 + noise)
        low = close * (1 - noise)
        open_price = np.roll(close, 1)
        open_price[0] = initial_price
        
        # Generate volume
        volume = np.random.randint(10000, 100000, n)
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
            'symbol': symbol
        })
        
        return df
