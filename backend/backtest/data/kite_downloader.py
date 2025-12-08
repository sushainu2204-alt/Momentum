"""
Kite Connect Historical Data Downloader

Downloads intraday and historical data from Zerodha Kite Connect API.
Supports 1-minute to monthly intervals.

Requirements:
    - Valid Kite Connect API credentials
    - kiteconnect package installed

Kite Historical Data Limits:
    - 1-minute: 60 days
    - 3-minute: 100 days
    - 5-minute: 100 days
    - 10-minute: 100 days
    - 15-minute: 200 days
    - 30-minute: 200 days
    - 60-minute: 400 days
    - day: 2000 days
"""

import asyncio
import logging
import time
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
import pandas as pd

from .downloader import (
    HistoricalDataDownloader,
    DataDownloadConfig,
    DataInterval,
    DataSource,
    DownloadResult,
    DownloadSummary
)

logger = logging.getLogger(__name__)


# Kite API interval limits (in days)
KITE_INTERVAL_LIMITS = {
    DataInterval.MINUTE_1: 60,
    DataInterval.MINUTE_3: 100,
    DataInterval.MINUTE_5: 100,
    DataInterval.MINUTE_10: 100,
    DataInterval.MINUTE_15: 200,
    DataInterval.MINUTE_30: 200,
    DataInterval.MINUTE_60: 400,
    DataInterval.HOUR_1: 400,
    DataInterval.DAY: 2000,
    DataInterval.WEEK: 2000,
    DataInterval.MONTH: 2000,
}

# Map our intervals to Kite API format
KITE_INTERVAL_MAP = {
    DataInterval.MINUTE_1: "minute",
    DataInterval.MINUTE_3: "3minute",
    DataInterval.MINUTE_5: "5minute",
    DataInterval.MINUTE_10: "10minute",
    DataInterval.MINUTE_15: "15minute",
    DataInterval.MINUTE_30: "30minute",
    DataInterval.MINUTE_60: "60minute",
    DataInterval.HOUR_1: "60minute",
    DataInterval.DAY: "day",
    DataInterval.WEEK: "week",
    DataInterval.MONTH: "month",
}


class KiteHistoricalDownloader(HistoricalDataDownloader):
    """
    Zerodha Kite Connect historical data downloader.
    
    Usage:
        from kiteconnect import KiteConnect
        
        kite = KiteConnect(api_key="your_api_key")
        kite.set_access_token("your_access_token")
        
        config = DataDownloadConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            interval=DataInterval.MINUTE_1,
            output_dir="./data/historical"
        )
        
        downloader = KiteHistoricalDownloader(config, kite)
        
        # Download single symbol
        result = await downloader.download_symbol("RELIANCE", instrument_token=738561)
        
        # Download batch
        symbols = ["RELIANCE", "TCS", "INFY"]
        tokens = {"RELIANCE": 738561, "TCS": 2953217, "INFY": 408065}
        summary = await downloader.download_batch(symbols, tokens)
    """
    
    def __init__(self, config: DataDownloadConfig, kite_client):
        """
        Initialize Kite downloader.
        
        Args:
            config: Download configuration
            kite_client: Authenticated KiteConnect instance
        """
        super().__init__(config)
        self.kite = kite_client
        self._validate_date_range()
    
    def _validate_date_range(self) -> None:
        """Validate date range against Kite API limits."""
        max_days = KITE_INTERVAL_LIMITS.get(self.config.interval, 60)
        requested_days = (self.config.end_date - self.config.start_date).days
        
        if requested_days > max_days:
            logger.warning(
                f"Requested {requested_days} days exceeds Kite limit of {max_days} days "
                f"for {self.config.interval.value} interval. Data will be fetched in chunks."
            )
    
    def get_data_source(self) -> DataSource:
        return DataSource.ZERODHA
    
    def _get_date_chunks(self) -> List[tuple]:
        """
        Split date range into chunks based on Kite API limits.
        
        Returns:
            List of (start_date, end_date) tuples
        """
        max_days = KITE_INTERVAL_LIMITS.get(self.config.interval, 60)
        
        chunks = []
        current_start = self.config.start_date
        
        while current_start < self.config.end_date:
            current_end = min(
                current_start + timedelta(days=max_days - 1),
                self.config.end_date
            )
            chunks.append((current_start, current_end))
            current_start = current_end + timedelta(days=1)
        
        return chunks
    
    def _fetch_historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime
    ) -> pd.DataFrame:
        """
        Fetch historical data from Kite API (synchronous).
        
        Args:
            instrument_token: Kite instrument token
            from_date: Start datetime
            to_date: End datetime
        
        Returns:
            DataFrame with OHLCV data
        """
        interval = KITE_INTERVAL_MAP[self.config.interval]
        
        records = self.kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
        
        if not records:
            return pd.DataFrame()
        
        df = pd.DataFrame(records)
        return df
    
    async def download_symbol(
        self,
        symbol: str,
        instrument_token: Optional[int] = None
    ) -> DownloadResult:
        """
        Download historical data for a single symbol.
        
        Args:
            symbol: Trading symbol
            instrument_token: Kite instrument token (REQUIRED)
        
        Returns:
            DownloadResult
        """
        start_time = time.time()
        
        if instrument_token is None:
            return DownloadResult(
                symbol=symbol,
                success=False,
                error_message="instrument_token is required for Kite downloads"
            )
        
        # Check if file exists
        if self.config.skip_existing and self._file_exists(symbol):
            logger.info(f"Skipping {symbol} - file already exists")
            return DownloadResult(
                symbol=symbol,
                success=True,
                rows_downloaded=0,
                file_path=self._get_file_path(symbol),
                error_message="Skipped - file exists"
            )
        
        try:
            # Get date chunks
            date_chunks = self._get_date_chunks()
            all_data = []
            
            for i, (chunk_start, chunk_end) in enumerate(date_chunks):
                logger.debug(f"{symbol}: Fetching chunk {i+1}/{len(date_chunks)}: {chunk_start} to {chunk_end}")
                
                # Convert to datetime
                from_dt = datetime.combine(chunk_start, datetime.min.time())
                to_dt = datetime.combine(chunk_end, datetime.max.time().replace(microsecond=0))
                
                # Fetch data (run in executor to not block)
                loop = asyncio.get_event_loop()
                chunk_df = await loop.run_in_executor(
                    None,
                    self._fetch_historical_data,
                    instrument_token,
                    from_dt,
                    to_dt
                )
                
                if not chunk_df.empty:
                    all_data.append(chunk_df)
                
                # Rate limiting between chunks
                if i < len(date_chunks) - 1:
                    await asyncio.sleep(self.config.rate_limit_delay)
            
            if not all_data:
                return DownloadResult(
                    symbol=symbol,
                    success=False,
                    error_message="No data returned from Kite API"
                )
            
            # Combine all chunks
            df = pd.concat(all_data, ignore_index=True)
            
            # Standardize columns
            df = self.standardize_columns(df)
            
            # Save data
            file_path = self._get_file_path(symbol)
            self._save_data(df, file_path)
            
            elapsed = time.time() - start_time
            
            return DownloadResult(
                symbol=symbol,
                success=True,
                rows_downloaded=len(df),
                file_path=file_path,
                start_date=df.index.min(),
                end_date=df.index.max(),
                download_time_seconds=elapsed
            )
            
        except Exception as e:
            logger.error(f"Error downloading {symbol}: {e}")
            return DownloadResult(
                symbol=symbol,
                success=False,
                error_message=str(e),
                download_time_seconds=time.time() - start_time
            )
    
    async def download_batch(
        self,
        symbols: List[str],
        instrument_tokens: Optional[Dict[str, int]] = None
    ) -> DownloadSummary:
        """
        Download historical data for multiple symbols.
        
        Args:
            symbols: List of trading symbols
            instrument_tokens: Mapping of symbol to instrument_token (REQUIRED)
        
        Returns:
            DownloadSummary
        """
        if instrument_tokens is None:
            raise ValueError("instrument_tokens mapping is required for Kite downloads")
        
        start_time = time.time()
        results = []
        failed_symbols = []
        total_rows = 0
        
        logger.info(f"Starting download of {len(symbols)} symbols")
        
        for i, symbol in enumerate(symbols):
            if self.config.show_progress:
                print(f"[{i+1}/{len(symbols)}] Downloading {symbol}...", end=" ", flush=True)
            
            token = instrument_tokens.get(symbol)
            if token is None:
                result = DownloadResult(
                    symbol=symbol,
                    success=False,
                    error_message="Missing instrument_token"
                )
                if self.config.show_progress:
                    print("✗ Missing token")
            else:
                result = await self.download_symbol(symbol, token)
                if self.config.show_progress:
                    if result.success:
                        print(f"✓ {result.rows_downloaded:,} rows")
                    else:
                        print(f"✗ {result.error_message}")
            
            results.append(result)
            
            if result.success:
                total_rows += result.rows_downloaded
            else:
                failed_symbols.append(symbol)
            
            # Rate limiting between symbols
            if i < len(symbols) - 1:
                await asyncio.sleep(self.config.rate_limit_delay)
        
        elapsed = time.time() - start_time
        
        summary = DownloadSummary(
            total_symbols=len(symbols),
            successful=len(symbols) - len(failed_symbols),
            failed=len(failed_symbols),
            total_rows=total_rows,
            total_time_seconds=elapsed,
            results=results,
            failed_symbols=failed_symbols
        )
        
        logger.info(str(summary))
        return summary
    
    async def get_instruments(self, exchange: str = "NSE") -> pd.DataFrame:
        """
        Get all instruments for an exchange.
        
        Args:
            exchange: Exchange code (NSE, BSE, NFO, etc.)
        
        Returns:
            DataFrame with instrument details including instrument_token
        """
        loop = asyncio.get_event_loop()
        instruments = await loop.run_in_executor(
            None,
            self.kite.instruments,
            exchange
        )
        
        df = pd.DataFrame(instruments)
        return df
    
    def get_instrument_tokens(
        self,
        symbols: List[str],
        instruments_df: pd.DataFrame
    ) -> Dict[str, int]:
        """
        Map symbols to instrument tokens.
        
        Args:
            symbols: List of trading symbols
            instruments_df: DataFrame from get_instruments()
        
        Returns:
            Dict mapping symbol to instrument_token
        """
        # Filter for equity segment
        equity = instruments_df[instruments_df['segment'] == 'NSE']
        
        token_map = {}
        for symbol in symbols:
            matches = equity[equity['tradingsymbol'] == symbol]
            if not matches.empty:
                token_map[symbol] = matches.iloc[0]['instrument_token']
            else:
                logger.warning(f"No instrument found for {symbol}")
        
        return token_map


# Convenience function for command-line usage
async def download_kite_data(
    kite_client,
    symbols: List[str],
    instrument_tokens: Dict[str, int],
    start_date: date,
    end_date: date,
    interval: str = "1minute",
    output_dir: str = "./data/historical"
) -> DownloadSummary:
    """
    Convenience function to download Kite historical data.
    
    Args:
        kite_client: Authenticated KiteConnect instance
        symbols: List of symbols to download
        instrument_tokens: Mapping of symbol to instrument_token
        start_date: Start date
        end_date: End date
        interval: Data interval (1minute, 5minute, 15minute, day, etc.)
        output_dir: Output directory
    
    Returns:
        DownloadSummary
    """
    # Map interval string to enum
    interval_map = {
        "1minute": DataInterval.MINUTE_1,
        "3minute": DataInterval.MINUTE_3,
        "5minute": DataInterval.MINUTE_5,
        "10minute": DataInterval.MINUTE_10,
        "15minute": DataInterval.MINUTE_15,
        "30minute": DataInterval.MINUTE_30,
        "60minute": DataInterval.MINUTE_60,
        "hour": DataInterval.HOUR_1,
        "day": DataInterval.DAY,
        "week": DataInterval.WEEK,
        "month": DataInterval.MONTH,
    }
    
    if interval not in interval_map:
        raise ValueError(f"Invalid interval: {interval}. Valid: {list(interval_map.keys())}")
    
    config = DataDownloadConfig(
        start_date=start_date,
        end_date=end_date,
        interval=interval_map[interval],
        output_dir=output_dir
    )
    
    downloader = KiteHistoricalDownloader(config, kite_client)
    return await downloader.download_batch(symbols, instrument_tokens)
