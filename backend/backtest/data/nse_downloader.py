"""
NSE Historical Data Downloader

Downloads daily OHLCV data from NSE India website.

Note: NSE does not provide free intraday historical data.
For 1-minute data, use Kite Connect (ZerodhaHistoricalDownloader).

This downloader fetches daily data from NSE's public API.
"""

import asyncio
import aiohttp
import logging
import time
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
import pandas as pd
import io

from .downloader import (
    HistoricalDataDownloader,
    DataDownloadConfig,
    DataInterval,
    DataSource,
    DownloadResult,
    DownloadSummary
)

logger = logging.getLogger(__name__)


class NSEHistoricalDownloader(HistoricalDataDownloader):
    """
    NSE India historical data downloader.
    
    Downloads daily OHLCV data from NSE's public website.
    
    Note: NSE limits historical data to approximately 2 years.
    For longer history or intraday data, use Kite Connect.
    
    Usage:
        config = DataDownloadConfig(
            start_date=date(2023, 1, 1),
            end_date=date(2024, 6, 30),
            interval=DataInterval.DAY,  # Only daily supported
            output_dir="./data/historical"
        )
        
        downloader = NSEHistoricalDownloader(config)
        
        # Download single symbol
        result = await downloader.download_symbol("RELIANCE")
        
        # Download batch
        symbols = ["RELIANCE", "TCS", "INFY"]
        summary = await downloader.download_batch(symbols)
    """
    
    BASE_URL = "https://www.nseindia.com"
    
    # Browser-like headers to avoid blocking
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    def __init__(self, config: DataDownloadConfig):
        """
        Initialize NSE downloader.
        
        Args:
            config: Download configuration
        """
        # Force daily interval for NSE
        if config.interval != DataInterval.DAY:
            logger.warning(
                f"NSE only supports daily data. Changing interval from {config.interval.value} to 'day'"
            )
            config.interval = DataInterval.DAY
        
        super().__init__(config)
        self._session: Optional[aiohttp.ClientSession] = None
        self._cookies_initialized = False
    
    def get_data_source(self) -> DataSource:
        return DataSource.NSE
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10, force_close=True)
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(
                headers=self.HEADERS,
                connector=connector,
                timeout=timeout
            )
        return self._session
    
    async def _init_cookies(self) -> None:
        """Initialize session with NSE cookies."""
        if self._cookies_initialized:
            return
        
        try:
            session = await self._get_session()
            async with session.get(self.BASE_URL) as response:
                await response.read()
                self._cookies_initialized = True
                logger.debug("NSE session cookies initialized")
        except Exception as e:
            logger.warning(f"Could not initialize NSE session: {e}")
    
    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self._cookies_initialized = False
    
    async def _fetch_historical_data(self, symbol: str) -> pd.DataFrame:
        """
        Fetch historical data from NSE for a symbol.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            DataFrame with OHLCV data
        """
        await self._init_cookies()
        session = await self._get_session()
        
        # Format dates for NSE API
        from_date = self.config.start_date.strftime("%d-%m-%Y")
        to_date = self.config.end_date.strftime("%d-%m-%Y")
        
        # NSE historical data API endpoint
        url = (
            f"{self.BASE_URL}/api/historical/cm/equity"
            f"?symbol={symbol}"
            f"&series=[%22EQ%22]"
            f"&from={from_date}"
            f"&to={to_date}"
        )
        
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()
        
        if 'data' not in data or not data['data']:
            logger.warning(f"No data returned for {symbol}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        records = data['data']
        df = pd.DataFrame(records)
        
        return df
    
    async def download_symbol(
        self,
        symbol: str,
        instrument_token: Optional[int] = None  # Not used for NSE
    ) -> DownloadResult:
        """
        Download historical data for a single symbol.
        
        Args:
            symbol: Trading symbol
            instrument_token: Ignored for NSE downloads
        
        Returns:
            DownloadResult
        """
        start_time = time.time()
        
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
            # Fetch data with retries
            df = None
            last_error = None
            
            for attempt in range(self.config.max_retries):
                try:
                    df = await self._fetch_historical_data(symbol)
                    break
                except aiohttp.ClientResponseError as e:
                    if e.status == 401:
                        # Session expired, reinitialize
                        self._cookies_initialized = False
                        await asyncio.sleep(self.config.retry_delay)
                    else:
                        raise
                except Exception as e:
                    last_error = e
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay)
            
            if df is None or df.empty:
                return DownloadResult(
                    symbol=symbol,
                    success=False,
                    error_message=f"No data returned: {last_error}"
                )
            
            # Standardize columns
            df = self._standardize_nse_columns(df)
            
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
    
    def _standardize_nse_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize NSE API column names."""
        # NSE API column mappings
        column_map = {
            'CH_SYMBOL': 'symbol',
            'CH_TIMESTAMP': 'datetime',
            'CH_OPENING_PRICE': 'open',
            'CH_TRADE_HIGH_PRICE': 'high',
            'CH_TRADE_LOW_PRICE': 'low',
            'CH_CLOSING_PRICE': 'close',
            'CH_LAST_TRADED_PRICE': 'ltp',
            'CH_PREVIOUS_CLS_PRICE': 'prev_close',
            'CH_TOT_TRADED_QTY': 'volume',
            'CH_TOT_TRADED_VAL': 'value',
            'CH_52WEEK_HIGH_PRICE': '52w_high',
            'CH_52WEEK_LOW_PRICE': '52w_low',
            'VWAP': 'vwap',
        }
        
        df = df.rename(columns=column_map)
        
        # Parse datetime
        if 'datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.set_index('datetime')
        
        # Sort by date
        df = df.sort_index()
        
        # Remove duplicates
        df = df[~df.index.duplicated(keep='first')]
        
        # Select required columns
        required = ['open', 'high', 'low', 'close', 'volume']
        optional = ['vwap', 'ltp', 'prev_close', 'value']
        
        columns_to_keep = [c for c in required + optional if c in df.columns]
        df = df[columns_to_keep]
        
        # Convert to numeric
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    
    async def download_batch(
        self,
        symbols: List[str],
        instrument_tokens: Optional[Dict[str, int]] = None  # Not used for NSE
    ) -> DownloadSummary:
        """
        Download historical data for multiple symbols.
        
        Args:
            symbols: List of trading symbols
            instrument_tokens: Ignored for NSE downloads
        
        Returns:
            DownloadSummary
        """
        start_time = time.time()
        results = []
        failed_symbols = []
        total_rows = 0
        
        logger.info(f"Starting NSE download of {len(symbols)} symbols")
        
        try:
            for i, symbol in enumerate(symbols):
                if self.config.show_progress:
                    print(f"[{i+1}/{len(symbols)}] Downloading {symbol}...", end=" ", flush=True)
                
                result = await self.download_symbol(symbol)
                results.append(result)
                
                if self.config.show_progress:
                    if result.success:
                        print(f"✓ {result.rows_downloaded:,} rows")
                    else:
                        print(f"✗ {result.error_message}")
                
                if result.success:
                    total_rows += result.rows_downloaded
                else:
                    failed_symbols.append(symbol)
                
                # Rate limiting
                if i < len(symbols) - 1:
                    await asyncio.sleep(self.config.rate_limit_delay)
            
        finally:
            await self.close()
        
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


class NSEBhavCopyDownloader:
    """
    Download NSE Bhavcopy (end-of-day) files.
    
    Bhavcopy contains OHLCV data for all traded securities for a given day.
    This is useful for bulk downloads of historical data.
    
    Usage:
        downloader = NSEBhavCopyDownloader(output_dir="./data/bhavcopy")
        
        # Download single day
        df = await downloader.download_bhavcopy(date(2024, 1, 15))
        
        # Download date range
        await downloader.download_range(date(2024, 1, 1), date(2024, 1, 31))
    """
    
    BASE_URL = "https://www.nseindia.com"
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    
    def __init__(self, output_dir: str = "./data/bhavcopy"):
        self.output_dir = output_dir
        self._session: Optional[aiohttp.ClientSession] = None
        self._cookies_initialized = False
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=5)
            timeout = aiohttp.ClientTimeout(total=60)
            self._session = aiohttp.ClientSession(
                headers=self.HEADERS,
                connector=connector,
                timeout=timeout
            )
        return self._session
    
    async def _init_cookies(self) -> None:
        if self._cookies_initialized:
            return
        
        try:
            session = await self._get_session()
            async with session.get(self.BASE_URL) as response:
                await response.read()
                self._cookies_initialized = True
        except Exception as e:
            logger.warning(f"Could not initialize NSE session: {e}")
    
    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def download_bhavcopy(self, trade_date: date) -> Optional[pd.DataFrame]:
        """
        Download bhavcopy for a specific date.
        
        Args:
            trade_date: Date to download
        
        Returns:
            DataFrame with OHLCV data for all securities
        """
        await self._init_cookies()
        session = await self._get_session()
        
        # Format date for URL
        date_str = trade_date.strftime("%d-%m-%Y")
        
        # Bhavcopy API endpoint
        url = f"{self.BASE_URL}/api/reports?archives=%5B%7B%22name%22%3A%22CM%20-%20Bhavcopy(csv)%22%2C%22type%22%3A%22archives%22%2C%22category%22%3A%22capital-market%22%2C%22section%22%3A%22equities%22%7D%5D&date={date_str}&type=equities&mode=single"
        
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
            
            if not data or 'data' not in data:
                logger.warning(f"No bhavcopy data for {trade_date}")
                return None
            
            # Parse CSV content
            csv_content = data.get('data', '')
            if not csv_content:
                return None
            
            df = pd.read_csv(io.StringIO(csv_content))
            
            # Add trade date
            df['trade_date'] = trade_date
            
            logger.info(f"Downloaded bhavcopy for {trade_date}: {len(df)} securities")
            return df
            
        except Exception as e:
            logger.error(f"Error downloading bhavcopy for {trade_date}: {e}")
            return None
    
    async def download_range(
        self,
        start_date: date,
        end_date: date,
        save_individual: bool = True,
        combine: bool = False
    ) -> Optional[pd.DataFrame]:
        """
        Download bhavcopy for a date range.
        
        Args:
            start_date: Start date
            end_date: End date
            save_individual: Save each day's file separately
            combine: Return combined DataFrame
        
        Returns:
            Combined DataFrame if combine=True, else None
        """
        import os
        os.makedirs(self.output_dir, exist_ok=True)
        
        all_data = []
        current = start_date
        
        while current <= end_date:
            # Skip weekends
            if current.weekday() < 5:  # Monday=0, Friday=4
                df = await self.download_bhavcopy(current)
                
                if df is not None and not df.empty:
                    if save_individual:
                        file_path = os.path.join(
                            self.output_dir,
                            f"bhavcopy_{current.strftime('%Y%m%d')}.csv"
                        )
                        df.to_csv(file_path, index=False)
                    
                    if combine:
                        all_data.append(df)
                
                # Rate limiting
                await asyncio.sleep(0.5)
            
            current += timedelta(days=1)
        
        await self.close()
        
        if combine and all_data:
            return pd.concat(all_data, ignore_index=True)
        
        return None


# Convenience function
async def download_nse_data(
    symbols: List[str],
    start_date: date,
    end_date: date,
    output_dir: str = "./data/historical"
) -> DownloadSummary:
    """
    Convenience function to download NSE daily historical data.
    
    Args:
        symbols: List of symbols to download
        start_date: Start date
        end_date: End date
        output_dir: Output directory
    
    Returns:
        DownloadSummary
    """
    config = DataDownloadConfig(
        start_date=start_date,
        end_date=end_date,
        interval=DataInterval.DAY,
        output_dir=output_dir
    )
    
    downloader = NSEHistoricalDownloader(config)
    return await downloader.download_batch(symbols)
