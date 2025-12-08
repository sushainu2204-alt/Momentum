"""
Data Manager

Centralized management of historical data for backtesting.
Handles data discovery, loading, validation, and caching.
"""

import os
import glob
import logging
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DataFileInfo:
    """Information about a data file."""
    symbol: str
    file_path: str
    interval: str
    start_date: date
    end_date: date
    format: str
    size_bytes: int
    row_count: Optional[int] = None
    
    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


@dataclass
class DataInventory:
    """Inventory of available data files."""
    files: List[DataFileInfo] = field(default_factory=list)
    
    @property
    def symbols(self) -> List[str]:
        return sorted(set(f.symbol for f in self.files))
    
    @property
    def total_size_mb(self) -> float:
        return sum(f.size_mb for f in self.files)
    
    def get_files_for_symbol(self, symbol: str) -> List[DataFileInfo]:
        return [f for f in self.files if f.symbol == symbol]
    
    def get_files_for_interval(self, interval: str) -> List[DataFileInfo]:
        return [f for f in self.files if f.interval == interval]
    
    def __repr__(self) -> str:
        return (
            f"DataInventory:\n"
            f"  Files: {len(self.files)}\n"
            f"  Symbols: {len(self.symbols)}\n"
            f"  Total size: {self.total_size_mb:.1f} MB"
        )


class DataManager:
    """
    Centralized data manager for backtesting.
    
    Responsibilities:
        - Discover available data files
        - Load and cache data
        - Validate data quality
        - Merge data from multiple sources
    
    Usage:
        manager = DataManager(data_dir="./data/historical")
        
        # Discover available data
        inventory = manager.scan_data_directory()
        print(f"Available symbols: {inventory.symbols}")
        
        # Load data for a symbol
        df = manager.load_symbol("RELIANCE", interval="1minute")
        
        # Load data for multiple symbols
        data = manager.load_symbols(["RELIANCE", "TCS"], interval="1minute")
        
        # Validate data
        report = manager.validate_data(df)
    """
    
    def __init__(
        self,
        data_dir: str = "./data/historical",
        cache_data: bool = True,
        max_cache_mb: float = 1000.0
    ):
        """
        Initialize DataManager.
        
        Args:
            data_dir: Root directory for data files
            cache_data: Whether to cache loaded data in memory
            max_cache_mb: Maximum cache size in MB
        """
        self.data_dir = data_dir
        self.cache_data = cache_data
        self.max_cache_mb = max_cache_mb
        
        self._cache: Dict[str, pd.DataFrame] = {}
        self._cache_size_mb: float = 0.0
        self._inventory: Optional[DataInventory] = None
    
    def scan_data_directory(self, refresh: bool = False) -> DataInventory:
        """
        Scan data directory and build inventory of available files.
        
        Args:
            refresh: Force rescan even if inventory exists
        
        Returns:
            DataInventory with file information
        """
        if self._inventory is not None and not refresh:
            return self._inventory
        
        files = []
        
        # Scan for parquet and csv files
        patterns = [
            os.path.join(self.data_dir, "**", "*.parquet"),
            os.path.join(self.data_dir, "**", "*.csv"),
        ]
        
        for pattern in patterns:
            for file_path in glob.glob(pattern, recursive=True):
                info = self._parse_file_info(file_path)
                if info:
                    files.append(info)
        
        self._inventory = DataInventory(files=files)
        logger.info(f"Scanned {len(files)} data files")
        
        return self._inventory
    
    def _parse_file_info(self, file_path: str) -> Optional[DataFileInfo]:
        """
        Parse file information from filename.
        
        Expected format: SYMBOL_INTERVAL_STARTDATE_ENDDATE.parquet
        Example: RELIANCE_1minute_20240101_20240630.parquet
        """
        try:
            filename = os.path.basename(file_path)
            name, ext = os.path.splitext(filename)
            parts = name.split("_")
            
            if len(parts) < 4:
                # Try simpler format: SYMBOL.parquet
                if len(parts) == 1:
                    symbol = parts[0]
                    interval = "unknown"
                    start_date = date(1900, 1, 1)
                    end_date = date(2100, 12, 31)
                else:
                    return None
            else:
                symbol = parts[0]
                interval = parts[1]
                start_date = datetime.strptime(parts[2], "%Y%m%d").date()
                end_date = datetime.strptime(parts[3], "%Y%m%d").date()
            
            size_bytes = os.path.getsize(file_path)
            
            return DataFileInfo(
                symbol=symbol,
                file_path=file_path,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                format=ext.lstrip("."),
                size_bytes=size_bytes
            )
            
        except Exception as e:
            logger.warning(f"Could not parse file info for {file_path}: {e}")
            return None
    
    def load_symbol(
        self,
        symbol: str,
        interval: str = "1minute",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Load data for a single symbol.
        
        Args:
            symbol: Trading symbol
            interval: Data interval (1minute, 5minute, day, etc.)
            start_date: Filter start date
            end_date: Filter end date
            use_cache: Use cached data if available
        
        Returns:
            DataFrame with OHLCV data, or None if not found
        """
        cache_key = f"{symbol}_{interval}"
        
        # Check cache
        if use_cache and self.cache_data and cache_key in self._cache:
            df = self._cache[cache_key]
            return self._filter_date_range(df, start_date, end_date)
        
        # Find data file
        inventory = self.scan_data_directory()
        matching_files = [
            f for f in inventory.files
            if f.symbol == symbol and (f.interval == interval or f.interval == "unknown")
        ]
        
        if not matching_files:
            logger.warning(f"No data file found for {symbol} ({interval})")
            return None
        
        # Load most recent file if multiple exist
        file_info = max(matching_files, key=lambda f: f.end_date)
        
        df = self._load_file(file_info.file_path)
        if df is None:
            return None
        
        # Cache if enabled
        if self.cache_data:
            self._add_to_cache(cache_key, df)
        
        return self._filter_date_range(df, start_date, end_date)
    
    def load_symbols(
        self,
        symbols: List[str],
        interval: str = "1minute",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        parallel: bool = True
    ) -> Dict[str, pd.DataFrame]:
        """
        Load data for multiple symbols.
        
        Args:
            symbols: List of trading symbols
            interval: Data interval
            start_date: Filter start date
            end_date: Filter end date
            parallel: Use parallel loading (for large datasets)
        
        Returns:
            Dict mapping symbol to DataFrame
        """
        data = {}
        
        for symbol in symbols:
            df = self.load_symbol(symbol, interval, start_date, end_date)
            if df is not None:
                data[symbol] = df
        
        logger.info(f"Loaded data for {len(data)}/{len(symbols)} symbols")
        return data
    
    def _load_file(self, file_path: str) -> Optional[pd.DataFrame]:
        """Load data from file."""
        try:
            if file_path.endswith(".parquet"):
                df = pd.read_parquet(file_path)
            else:
                df = pd.read_csv(file_path, parse_dates=True, index_col=0)
            
            # Ensure datetime index
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            
            df = df.sort_index()
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return None
    
    def _filter_date_range(
        self,
        df: pd.DataFrame,
        start_date: Optional[date],
        end_date: Optional[date]
    ) -> pd.DataFrame:
        """Filter DataFrame to date range."""
        if start_date:
            df = df[df.index >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df.index <= pd.Timestamp(end_date)]
        return df
    
    def _add_to_cache(self, key: str, df: pd.DataFrame) -> None:
        """Add DataFrame to cache with size management."""
        size_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
        
        # Evict old entries if needed
        while self._cache_size_mb + size_mb > self.max_cache_mb and self._cache:
            oldest_key = next(iter(self._cache))
            evicted_df = self._cache.pop(oldest_key)
            self._cache_size_mb -= evicted_df.memory_usage(deep=True).sum() / (1024 * 1024)
        
        self._cache[key] = df
        self._cache_size_mb += size_mb
    
    def clear_cache(self) -> None:
        """Clear the data cache."""
        self._cache.clear()
        self._cache_size_mb = 0.0
    
    def validate_data(
        self,
        df: pd.DataFrame,
        symbol: str = "Unknown"
    ) -> Dict[str, Any]:
        """
        Validate data quality.
        
        Checks:
            - Required columns exist
            - No negative prices
            - OHLC relationship (high >= low)
            - Volume non-negative
            - Missing values
            - Duplicate timestamps
            - Data gaps
        
        Args:
            df: DataFrame to validate
            symbol: Symbol name for logging
        
        Returns:
            Validation report dict
        """
        report = {
            "symbol": symbol,
            "rows": len(df),
            "start_date": df.index.min() if len(df) > 0 else None,
            "end_date": df.index.max() if len(df) > 0 else None,
            "issues": [],
            "valid": True
        }
        
        # Check required columns
        required = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [c for c in required if c not in df.columns]
        if missing_cols:
            report["issues"].append(f"Missing columns: {missing_cols}")
            report["valid"] = False
            return report
        
        # Check for negative prices
        for col in ['open', 'high', 'low', 'close']:
            neg_count = (df[col] < 0).sum()
            if neg_count > 0:
                report["issues"].append(f"Negative {col} values: {neg_count}")
                report["valid"] = False
        
        # Check OHLC relationship
        invalid_ohlc = ((df['high'] < df['low']) | 
                        (df['high'] < df['open']) | 
                        (df['high'] < df['close']) |
                        (df['low'] > df['open']) | 
                        (df['low'] > df['close'])).sum()
        if invalid_ohlc > 0:
            report["issues"].append(f"Invalid OHLC relationships: {invalid_ohlc}")
        
        # Check volume
        neg_volume = (df['volume'] < 0).sum()
        if neg_volume > 0:
            report["issues"].append(f"Negative volume: {neg_volume}")
        
        zero_volume = (df['volume'] == 0).sum()
        if zero_volume > 0:
            report["issues"].append(f"Zero volume bars: {zero_volume}")
        
        # Check missing values
        missing = df[required].isnull().sum().to_dict()
        total_missing = sum(missing.values())
        if total_missing > 0:
            report["issues"].append(f"Missing values: {missing}")
        
        # Check duplicates
        duplicates = df.index.duplicated().sum()
        if duplicates > 0:
            report["issues"].append(f"Duplicate timestamps: {duplicates}")
        
        # Check data gaps (for minute data)
        if len(df) > 1:
            time_diffs = df.index.to_series().diff()
            median_diff = time_diffs.median()
            
            # Gaps more than 5x median
            large_gaps = (time_diffs > median_diff * 5).sum()
            if large_gaps > 10:  # Allow some gaps for overnight, weekends
                report["issues"].append(f"Large time gaps: {large_gaps}")
        
        # Summary stats
        report["stats"] = {
            "price_range": (df['low'].min(), df['high'].max()),
            "avg_volume": df['volume'].mean(),
            "total_volume": df['volume'].sum(),
            "trading_days": df.index.normalize().nunique()
        }
        
        return report
    
    def merge_data_files(
        self,
        symbol: str,
        output_path: Optional[str] = None,
        remove_duplicates: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Merge multiple data files for a symbol into one.
        
        Args:
            symbol: Trading symbol
            output_path: Output file path (optional)
            remove_duplicates: Remove duplicate timestamps
        
        Returns:
            Merged DataFrame
        """
        inventory = self.scan_data_directory()
        files = inventory.get_files_for_symbol(symbol)
        
        if not files:
            logger.warning(f"No files found for {symbol}")
            return None
        
        all_data = []
        for file_info in files:
            df = self._load_file(file_info.file_path)
            if df is not None:
                all_data.append(df)
        
        if not all_data:
            return None
        
        merged = pd.concat(all_data)
        merged = merged.sort_index()
        
        if remove_duplicates:
            merged = merged[~merged.index.duplicated(keep='first')]
        
        if output_path:
            if output_path.endswith(".parquet"):
                merged.to_parquet(output_path)
            else:
                merged.to_csv(output_path)
            logger.info(f"Saved merged data to {output_path}")
        
        return merged
    
    def get_available_date_range(
        self,
        symbols: List[str],
        interval: str = "1minute"
    ) -> Tuple[Optional[date], Optional[date]]:
        """
        Get common date range available for all symbols.
        
        Args:
            symbols: List of symbols
            interval: Data interval
        
        Returns:
            Tuple of (start_date, end_date) or (None, None) if no overlap
        """
        inventory = self.scan_data_directory()
        
        start_dates = []
        end_dates = []
        
        for symbol in symbols:
            files = [
                f for f in inventory.files
                if f.symbol == symbol and f.interval == interval
            ]
            if files:
                start_dates.append(min(f.start_date for f in files))
                end_dates.append(max(f.end_date for f in files))
        
        if not start_dates or not end_dates:
            return None, None
        
        common_start = max(start_dates)
        common_end = min(end_dates)
        
        if common_start > common_end:
            return None, None
        
        return common_start, common_end
    
    def generate_data_report(self) -> str:
        """Generate a human-readable data inventory report."""
        inventory = self.scan_data_directory()
        
        lines = [
            "=" * 60,
            "DATA INVENTORY REPORT",
            "=" * 60,
            f"Data directory: {self.data_dir}",
            f"Total files: {len(inventory.files)}",
            f"Total symbols: {len(inventory.symbols)}",
            f"Total size: {inventory.total_size_mb:.1f} MB",
            "",
            "By Interval:",
        ]
        
        # Group by interval
        intervals = set(f.interval for f in inventory.files)
        for interval in sorted(intervals):
            files = inventory.get_files_for_interval(interval)
            size = sum(f.size_mb for f in files)
            lines.append(f"  {interval}: {len(files)} files ({size:.1f} MB)")
        
        lines.extend(["", "Symbols:"])
        for symbol in inventory.symbols[:20]:  # First 20
            files = inventory.get_files_for_symbol(symbol)
            lines.append(f"  {symbol}: {len(files)} files")
        
        if len(inventory.symbols) > 20:
            lines.append(f"  ... and {len(inventory.symbols) - 20} more")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
