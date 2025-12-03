"""
Volume Breakout Scanner

Scans for stocks with unusual volume activity.
Volume breakouts often precede price breakouts.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional
import time
import logging

from .base import IScanner, ScannerConfig, ScanResult
from backend.core.models import Candidate
from backend.infrastructure.data_sources.base import IDataSource

logger = logging.getLogger(__name__)


@dataclass
class VolumeBreakoutConfig(ScannerConfig):
    """Configuration for Volume Breakout Scanner"""
    
    name: str = "volume_breakout"
    description: str = "Scans for stocks with unusual volume activity"
    
    # Volume multiplier (current volume vs average)
    volume_multiplier: float = 2.0  # At least 2x average volume
    
    # Lookback for average volume calculation
    avg_volume_days: int = 20
    
    # Price change filters (only consider stocks with positive movement)
    min_gain_pct: float = 0.5  # At least 0.5% up
    max_gain_pct: float = 15.0  # Avoid circuit stocks
    
    # Price filters
    min_price: float = 50.0
    max_price: float = 10000.0
    
    # Results
    max_results: int = 20


class VolumeBreakoutScanner(IScanner):
    """
    Scanner for volume breakout stocks.
    
    Looks for stocks where:
    - Current volume > X times average volume
    - Price is moving up (positive momentum)
    
    Useful for:
    - Breakout trading
    - Momentum strategies
    - News-driven moves
    
    Usage:
        data_source = ZerodhaDataSource(kite)
        instruments = [...]  # List of instruments to scan
        
        config = VolumeBreakoutConfig(volume_multiplier=3.0)
        scanner = VolumeBreakoutScanner(config, data_source, instruments)
        
        result = await scanner.scan()
        for candidate in result.candidates:
            vol_ratio = candidate.volume / candidate.avg_volume
            print(f"{candidate.symbol}: {vol_ratio:.1f}x volume")
    """
    
    def __init__(
        self,
        config: Optional[VolumeBreakoutConfig] = None,
        data_source: Optional[IDataSource] = None,
        instruments: Optional[List] = None
    ):
        """
        Initialize scanner.
        
        Args:
            config: Scanner configuration
            data_source: Data source for quotes and historical data
            instruments: List of instruments to scan
        """
        super().__init__(config or VolumeBreakoutConfig())
        self.data_source = data_source
        self.instruments = instruments or []
        
        # Cache for average volumes
        self._avg_volume_cache: dict = {}
        self._cache_date: Optional[datetime] = None
    
    def get_name(self) -> str:
        return "volume_breakout"
    
    def get_description(self) -> str:
        return f"Stocks with {self.config.volume_multiplier}x+ average volume"
    
    async def scan(self) -> ScanResult:
        """
        Scan for volume breakouts.
        
        Returns:
            ScanResult with candidates sorted by volume ratio
        """
        start_time = time.time()
        self._log_scan_start()
        
        result = ScanResult(
            scanner_name=self.get_name(),
            scan_time=datetime.now()
        )
        
        if not self.data_source:
            result.errors.append("No data source provided")
            result.duration_ms = (time.time() - start_time) * 1000
            self._log_scan_result(result)
            return result
        
        if not self.instruments:
            result.errors.append("No instruments to scan")
            result.duration_ms = (time.time() - start_time) * 1000
            self._log_scan_result(result)
            return result
        
        # Get instrument tokens
        instrument_tokens = [inst.instrument_token for inst in self.instruments]
        result.total_scanned = len(instrument_tokens)
        
        try:
            # Fetch current quotes
            quotes = self.data_source.get_quotes(instrument_tokens)
            
            candidates = []
            
            for token, quote in quotes.items():
                try:
                    # Get or calculate average volume
                    avg_volume = await self._get_avg_volume(token)
                    
                    if avg_volume <= 0:
                        continue
                    
                    # Calculate volume ratio
                    volume_ratio = quote.volume / avg_volume
                    
                    # Check if volume breakout
                    if volume_ratio < self.config.volume_multiplier:
                        continue
                    
                    # Check price change
                    if not (self.config.min_gain_pct <= quote.change_pct <= self.config.max_gain_pct):
                        continue
                    
                    # Check price range
                    if not (self.config.min_price <= quote.last_price <= self.config.max_price):
                        continue
                    
                    # Create candidate
                    candidate = Candidate(
                        symbol=quote.symbol,
                        instrument_token=quote.instrument_token,
                        current_price=quote.last_price,
                        open_price=quote.open_price or 0,
                        high_price=quote.high_price or 0,
                        low_price=quote.low_price or 0,
                        volume=quote.volume,
                        gain_pct=quote.change_pct,
                        avg_volume=avg_volume,
                        timestamp=datetime.now()
                    )
                    
                    # Store volume ratio for sorting
                    candidate._volume_ratio = volume_ratio
                    candidates.append(candidate)
                    
                except Exception as e:
                    logger.debug(f"Error processing {token}: {e}")
            
            # Sort by volume ratio (highest first)
            candidates.sort(key=lambda c: getattr(c, '_volume_ratio', 0), reverse=True)
            
            # Limit results
            candidates = candidates[:self.config.max_results]
            
            result.candidates = candidates
            result.total_passed = len(candidates)
            
        except Exception as e:
            result.errors.append(f"Scan failed: {e}")
            logger.error(f"Volume breakout scan failed: {e}", exc_info=True)
        
        result.duration_ms = (time.time() - start_time) * 1000
        self._log_scan_result(result)
        return result
    
    async def _get_avg_volume(self, instrument_token: int) -> float:
        """
        Get average volume for instrument.
        
        Uses cache to avoid repeated API calls.
        
        Args:
            instrument_token: Instrument token
        
        Returns:
            Average daily volume
        """
        # Check if cache is stale (new day)
        today = datetime.now().date()
        if self._cache_date != today:
            self._avg_volume_cache.clear()
            self._cache_date = today
        
        # Check cache
        if instrument_token in self._avg_volume_cache:
            return self._avg_volume_cache[instrument_token]
        
        try:
            # Fetch historical data
            from_date = datetime.now() - timedelta(days=self.config.avg_volume_days * 2)
            to_date = datetime.now()
            
            df = self.data_source.get_historical_data(
                instrument_token,
                from_date,
                to_date,
                interval='day'
            )
            
            if df is not None and not df.empty and 'volume' in df.columns:
                avg_volume = df['volume'].tail(self.config.avg_volume_days).mean()
                self._avg_volume_cache[instrument_token] = avg_volume
                return avg_volume
            
        except Exception as e:
            logger.debug(f"Could not get avg volume for {instrument_token}: {e}")
        
        return 0.0
    
    def clear_cache(self) -> None:
        """Clear the average volume cache"""
        self._avg_volume_cache.clear()
        self._cache_date = None
