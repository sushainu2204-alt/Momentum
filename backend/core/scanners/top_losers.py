"""
Top Losers Scanner

Scans NSE for top losing stocks across multiple categories.
Useful for mean-reversion or short-selling strategies.
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
class TopLosersConfig(ScannerConfig):
    """Configuration for Top Losers Scanner"""
    
    name: str = "top_losers"
    description: str = "Scans NSE for top losing stocks"
    
    # NSE categories to scan
    categories: List[str] = field(default_factory=lambda: [
        "FOSec",  # F&O stocks (primary)
        "NIFTY",
    ])
    
    # Loss filters (note: negative values)
    min_loss_pct: float = -20.0  # Maximum loss (most negative)
    max_loss_pct: float = -2.0   # Minimum loss to consider
    
    # Price filters
    min_price: float = 50.0
    max_price: float = 10000.0
    
    # Results
    max_results: int = 30


class TopLosersScanner(IScanner):
    """
    Scanner for top losing stocks on NSE.
    
    Useful for:
    - Mean reversion strategies
    - Bounce plays
    - Short selling candidates
    
    Usage:
        config = TopLosersConfig(max_loss_pct=-3.0)
        scanner = TopLosersScanner(config)
        
        result = await scanner.scan()
        for candidate in result.candidates:
            print(f"{candidate.symbol}: {candidate.gain_pct:.2f}%")
    """
    
    def __init__(
        self,
        config: Optional[TopLosersConfig] = None,
        nse_config: Optional[NSEConfig] = None
    ):
        """
        Initialize scanner.
        
        Args:
            config: Scanner configuration
            nse_config: NSE API configuration
        """
        super().__init__(config or TopLosersConfig())
        self.nse_config = nse_config or DEFAULT_NSE_CONFIG
        self._nse_source: Optional[NSEDataSource] = None
    
    def get_name(self) -> str:
        return "top_losers"
    
    def get_description(self) -> str:
        return f"Top losing stocks ({self.config.min_loss_pct}% to {self.config.max_loss_pct}%)"
    
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
        Scan NSE for top losers.
        
        Returns:
            ScanResult with candidates sorted by % loss
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
        all_losers = []
        
        # Scan each category
        for category in self.config.categories:
            try:
                category_losers = await self._nse_source.get_top_losers()
                
                # Count unique additions
                unique_count = 0
                for loser in category_losers:
                    if loser.symbol not in seen_symbols:
                        all_losers.append(loser)
                        seen_symbols.add(loser.symbol)
                        unique_count += 1
                
                result.category_stats[category] = len(category_losers)
                logger.debug(
                    f"  ├─ {category}: {len(category_losers)} stocks "
                    f"({unique_count} unique)"
                )
                
            except Exception as e:
                error_msg = f"Failed to fetch {category}: {e}"
                result.errors.append(error_msg)
                logger.warning(f"  ├─ {category}: {error_msg}")
        
        result.total_scanned = len(all_losers)
        
        if not all_losers:
            result.duration_ms = (time.time() - start_time) * 1000
            self._log_scan_result(result)
            return result
        
        # Convert to candidates
        candidates = self._convert_to_candidates(all_losers)
        
        # Apply filters (loss range)
        filtered = self._filter_by_loss(candidates)
        
        # Sort by % loss (most negative first)
        filtered.sort(key=lambda c: c.gain_pct)
        
        # Limit results
        filtered = filtered[:self.config.max_results]
        
        result.candidates = filtered
        result.total_passed = len(filtered)
        result.duration_ms = (time.time() - start_time) * 1000
        
        self._log_scan_result(result)
        return result
    
    def _filter_by_loss(self, candidates: List[Candidate]) -> List[Candidate]:
        """
        Filter candidates by loss range.
        
        Args:
            candidates: Raw candidates
        
        Returns:
            Filtered candidates within loss range
        """
        filtered = []
        
        for candidate in candidates:
            # Price filter
            if not (self.config.min_price <= candidate.current_price <= self.config.max_price):
                continue
            
            # Loss filter (gain_pct will be negative)
            if not (self.config.min_loss_pct <= candidate.gain_pct <= self.config.max_loss_pct):
                continue
            
            filtered.append(candidate)
        
        return filtered
    
    def _convert_to_candidates(self, losers: List) -> List[Candidate]:
        """
        Convert NSE losers to Candidate objects.
        
        Args:
            losers: List of NSETopGainer objects (with negative changes)
        
        Returns:
            List of Candidate objects
        """
        candidates = []
        current_time = datetime.now()
        
        for loser in losers:
            try:
                candidate = Candidate(
                    symbol=loser.symbol,
                    instrument_token=0,
                    current_price=loser.last_price,
                    open_price=loser.open_price,
                    high_price=loser.high_price,
                    low_price=loser.low_price,
                    volume=loser.volume,
                    gain_pct=loser.pct_change,  # Will be negative
                    avg_volume=loser.volume,
                    timestamp=current_time
                )
                candidates.append(candidate)
            except Exception as e:
                logger.warning(f"Failed to convert {getattr(loser, 'symbol', 'unknown')}: {e}")
        
        return candidates
