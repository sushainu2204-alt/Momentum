"""
Base Historical Data Downloader

Abstract interface and configuration for historical data downloading.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import List, Optional, Dict, Any
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class DataInterval(Enum):
    """Supported data intervals."""
    MINUTE_1 = "1minute"
    MINUTE_3 = "3minute"
    MINUTE_5 = "5minute"
    MINUTE_10 = "10minute"
    MINUTE_15 = "15minute"
    MINUTE_30 = "30minute"
    MINUTE_60 = "60minute"
    HOUR_1 = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class DataSource(Enum):
    """Data source providers."""
    NSE = "nse"
    ZERODHA = "zerodha"
    YAHOO = "yahoo"
    SYNTHETIC = "synthetic"


@dataclass
class DataDownloadConfig:
    """Configuration for data download operations."""
    
    # Date range
    start_date: date
    end_date: date
    
    # Data parameters
    interval: DataInterval = DataInterval.MINUTE_1
    exchange: str = "NSE"
    
    # Storage
    output_dir: str = "./data/historical"
    save_format: str = "parquet"  # parquet, csv
    
    # Download settings
    batch_size: int = 10  # Symbols per batch
    rate_limit_delay: float = 0.5  # Seconds between requests
    max_retries: int = 3
    retry_delay: float = 2.0
    
    # Progress
    show_progress: bool = True
    
    # Filters
    skip_existing: bool = True
    
    def validate(self) -> None:
        """Validate configuration."""
        if self.start_date > self.end_date:
            raise ValueError("start_date must be before end_date")
        
        if self.end_date > date.today():
            raise ValueError("end_date cannot be in the future")
        
        if self.save_format not in ['parquet', 'csv']:
            raise ValueError("save_format must be 'parquet' or 'csv'")
        
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")


@dataclass
class DownloadResult:
    """Result of a data download operation."""
    
    symbol: str
    success: bool
    rows_downloaded: int = 0
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    download_time_seconds: float = 0.0
    
    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        if self.success:
            return f"{status} {self.symbol}: {self.rows_downloaded:,} rows"
        return f"{status} {self.symbol}: {self.error_message}"


@dataclass
class DownloadSummary:
    """Summary of batch download operation."""
    
    total_symbols: int
    successful: int
    failed: int
    total_rows: int
    total_time_seconds: float
    results: List[DownloadResult] = field(default_factory=list)
    failed_symbols: List[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        if self.total_symbols == 0:
            return 0.0
        return self.successful / self.total_symbols * 100
    
    def __repr__(self) -> str:
        return (
            f"Download Summary:\n"
            f"  Total symbols: {self.total_symbols}\n"
            f"  Successful: {self.successful}\n"
            f"  Failed: {self.failed}\n"
            f"  Success rate: {self.success_rate:.1f}%\n"
            f"  Total rows: {self.total_rows:,}\n"
            f"  Time: {self.total_time_seconds:.1f}s"
        )


class HistoricalDataDownloader(ABC):
    """Abstract base class for historical data downloaders."""
    
    def __init__(self, config: DataDownloadConfig):
        self.config = config
        config.validate()
    
    @abstractmethod
    async def download_symbol(
        self,
        symbol: str,
        instrument_token: Optional[int] = None
    ) -> DownloadResult:
        """
        Download historical data for a single symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'RELIANCE')
            instrument_token: Optional instrument token (required for some sources)
        
        Returns:
            DownloadResult with status and metadata
        """
        pass
    
    @abstractmethod
    async def download_batch(
        self,
        symbols: List[str],
        instrument_tokens: Optional[Dict[str, int]] = None
    ) -> DownloadSummary:
        """
        Download historical data for multiple symbols.
        
        Args:
            symbols: List of trading symbols
            instrument_tokens: Optional mapping of symbol to instrument_token
        
        Returns:
            DownloadSummary with aggregated results
        """
        pass
    
    @abstractmethod
    def get_data_source(self) -> DataSource:
        """Return the data source type."""
        pass
    
    def _get_file_path(self, symbol: str) -> str:
        """Get output file path for symbol."""
        import os
        os.makedirs(self.config.output_dir, exist_ok=True)
        
        # Format: SYMBOL_INTERVAL_STARTDATE_ENDDATE.parquet
        interval_str = self.config.interval.value
        start_str = self.config.start_date.strftime("%Y%m%d")
        end_str = self.config.end_date.strftime("%Y%m%d")
        
        filename = f"{symbol}_{interval_str}_{start_str}_{end_str}.{self.config.save_format}"
        return os.path.join(self.config.output_dir, filename)
    
    def _save_data(self, df: pd.DataFrame, file_path: str) -> None:
        """Save DataFrame to file."""
        import os
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        if self.config.save_format == 'parquet':
            df.to_parquet(file_path, index=True)
        else:
            df.to_csv(file_path, index=True)
        
        logger.debug(f"Saved {len(df)} rows to {file_path}")
    
    def _file_exists(self, symbol: str) -> bool:
        """Check if data file already exists."""
        import os
        file_path = self._get_file_path(symbol)
        return os.path.exists(file_path)
    
    @staticmethod
    def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize column names to backtest engine format.
        
        Expected columns:
            - datetime (index)
            - open
            - high
            - low
            - close
            - volume
        """
        column_map = {
            # Common variations
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
            'Adj Close': 'adj_close',
            'Date': 'datetime',
            'Datetime': 'datetime',
            'Time': 'datetime',
            'Timestamp': 'datetime',
            # Kite format
            'date': 'datetime',
            # NSE format
            'CH_OPENING_PRICE': 'open',
            'CH_TRADE_HIGH_PRICE': 'high',
            'CH_TRADE_LOW_PRICE': 'low',
            'CH_CLOSING_PRICE': 'close',
            'CH_TOT_TRADED_QTY': 'volume',
            'CH_TIMESTAMP': 'datetime',
        }
        
        df = df.rename(columns=column_map)
        
        # Ensure required columns exist
        required = ['open', 'high', 'low', 'close', 'volume']
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        # Set datetime as index if not already
        if 'datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.set_index('datetime')
        
        # Ensure index is datetime
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        
        # Sort by datetime
        df = df.sort_index()
        
        # Remove duplicates
        df = df[~df.index.duplicated(keep='first')]
        
        # Select only required columns
        columns_to_keep = [col for col in required + ['adj_close'] if col in df.columns]
        df = df[columns_to_keep]
        
        return df
