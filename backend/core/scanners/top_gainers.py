"""
Top Gainers Scanner

Scans NSE for top gaining stocks across multiple categories.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Set
import time
import logging

from .base import IScanner, ScannerConfig, ScanResult
from backend.core.models import Candidate
from backend.config import NSEConfig, DEFAULT_NSE_CONFIG
from backend.infrastructure.data_sources.nse import NSEDataSource

logger = logging.getLogger(__name__)


@dataclass
class TopGainersConfig(ScannerConfig):
    """Configuration for Top Gainers Scanner"""
    
    name: str = "top_gainers"
    description: str = "Scans NSE for top gaining stocks"
    
    # NSE categories to scan
    categories: List[str] = field(default_factory=lambda: [
        "FOSec",  # F&O stocks (primary)
        "NIFTY",
        "BANKNIFTY",
    ])
    
    # Gain filters
    min_gain_pct: float = 2.0  # Minimum % gain to consider
    max_gain_pct: float = 20.0  # Maximum % gain (avoid circuit stocks)
    
    # Price filters
    min_price: float = 50.0  # Avoid penny stocks
    max_price: float = 10000.0  # Avoid very expensive stocks
    
    # Results
    max_results: int = 30


class TopGainersScanner(IScanner):
    """
    Scanner for top gaining stocks on NSE.
    
    Scans multiple NSE categories and returns deduplicated candidates
    sorted by % gain.
    
    Usage:
        config = TopGainersConfig(min_gain_pct=3.0, categories=['FOSec'])
        scanner = TopGainersScanner(config)
        
        result = await scanner.scan()
        for candidate in result.candidates:
            print(f"{candidate.symbol}: +{candidate.gain_pct:.2f}%")
    """
    
    def __init__(
        self,
        config: Optional[TopGainersConfig] = None,
        nse_config: Optional[NSEConfig] = None
    ):
        """
        Initialize scanner.
        
        Args:
            config: Scanner configuration
            nse_config: NSE API configuration
        """
        super().__init__(config or TopGainersConfig())
        self.nse_config = nse_config or DEFAULT_NSE_CONFIG
        self._nse_source: Optional[NSEDataSource] = None
    
    def get_name(self) -> str:
        return "top_gainers"
    
    def get_description(self) -> str:
        return f"Top gaining stocks ({self.config.min_gain_pct}%-{self.config.max_gain_pct}%)"
    
    async def initialize(self) -> None:
        """Initialize NSE data source"""
        if self._nse_source is None:
            self._nse_source = NSEDataSource()
    
    async def cleanup(self) -> None:
        """Cleanup NSE data source"""
        if self._nse_source:
            await self._nse_source.close()
            self._nse_source = None
    
    async def scan(self) -> ScanResult:
        """
        Scan NSE for top gainers.
        
        Returns:
            ScanResult with candidates sorted by % gain
        """
        start_time = time.time()
        self._log_scan_start()
        
        # Initialize if needed
        if self._nse_source is None:
            await self.initialize()
        
        result = ScanResult(
            scanner_name=self.get_name(),
            scan_time=datetime.now()
        )
        
        # Track seen symbols to avoid duplicates
        seen_symbols: Set[str] = set()
        all_gainers = []
        
        # Scan each category
        for category in self.config.categories:
            try:
                category_gainers = await self._nse_source.get_top_gainers(category=category)
                
                # Count unique additions
                unique_count = 0
                for gainer in category_gainers:
                    if gainer.symbol not in seen_symbols:
                        all_gainers.append(gainer)
                        seen_symbols.add(gainer.symbol)
                        unique_count += 1
                
                result.category_stats[category] = len(category_gainers)
                logger.debug(
                    f"  ├─ {category}: {len(category_gainers)} stocks "
                    f"({unique_count} unique)"
                )
                
            except Exception as e:
                error_msg = f"Failed to fetch {category}: {e}"
                result.errors.append(error_msg)
                logger.warning(f"  ├─ {category}: {error_msg}")
        
        result.total_scanned = len(all_gainers)
        
        if not all_gainers:
            result.duration_ms = (time.time() - start_time) * 1000
            self._log_scan_result(result)
            return result
        
        # Convert to candidates
        candidates = self._convert_to_candidates(all_gainers)
        
        # Apply base filters
        filtered = self.filter_candidates(candidates)
        
        # Sort by % gain descending
        filtered.sort(key=lambda c: c.gain_pct, reverse=True)
        
        result.candidates = filtered
        result.total_passed = len(filtered)
        result.duration_ms = (time.time() - start_time) * 1000
        
        self._log_scan_result(result)
        return result
    
    def _convert_to_candidates(self, gainers: List) -> List[Candidate]:
        """
        Convert NSE gainers to Candidate objects.
        
        Args:
            gainers: List of NSETopGainer objects
        
        Returns:
            List of Candidate objects
        """
        candidates = []
        current_time = datetime.now()
        
        for gainer in gainers:
            try:
                candidate = Candidate(
                    symbol=gainer.symbol,
                    instrument_token=0,  # Will be enriched later
                    current_price=gainer.last_price,
                    open_price=gainer.open_price,
                    high_price=gainer.high_price,
                    low_price=gainer.low_price,
                    volume=gainer.volume,
                    gain_pct=gainer.pct_change,
                    avg_volume=gainer.volume,  # Will be enriched later
                    timestamp=current_time
                )
                candidates.append(candidate)
            except Exception as e:
                logger.warning(f"Failed to convert {getattr(gainer, 'symbol', 'unknown')}: {e}")
        
        return candidates
