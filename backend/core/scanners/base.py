"""
Scanner Base Interface

Abstract interface for market scanners.
Implements Strategy Pattern for pluggable scanning algorithms.

Usage:
    class MyScanner(IScanner):
        async def scan(self) -> ScanResult:
            # Custom scanning logic
            return ScanResult(candidates=[...])
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging

from backend.core.models import Candidate

logger = logging.getLogger(__name__)


@dataclass
class ScannerConfig:
    """
    Base configuration for scanners.
    
    Subclass this for scanner-specific configuration.
    """
    
    # Scanner identity
    name: str = "base_scanner"
    description: str = "Base scanner configuration"
    
    # Filtering criteria
    min_gain_pct: float = 0.0  # Minimum % gain
    max_gain_pct: float = 100.0  # Maximum % gain
    min_price: float = 20.0  # Minimum stock price
    max_price: float = 50000.0  # Maximum stock price
    min_volume: int = 0  # Minimum volume
    
    # Results
    max_results: int = 50  # Maximum candidates to return
    
    # Logging
    debug: bool = False


@dataclass
class ScanResult:
    """
    Result of a market scan.
    
    Contains candidates and metadata about the scan.
    """
    
    # Scan results
    candidates: List[Candidate] = field(default_factory=list)
    
    # Metadata
    scanner_name: str = ""
    scan_time: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    
    # Stats
    total_scanned: int = 0
    total_passed: int = 0
    
    # Categories breakdown (for multi-category scanners)
    category_stats: Dict[str, int] = field(default_factory=dict)
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        """Check if scan was successful (found at least one candidate)"""
        return len(self.candidates) > 0
    
    def __str__(self) -> str:
        return (
            f"ScanResult({self.scanner_name}: "
            f"{len(self.candidates)} candidates, "
            f"{self.duration_ms:.0f}ms)"
        )


class IScanner(ABC):
    """
    Interface for market scanners.
    
    Implementations:
    - TopGainersScanner: Scans for top gaining stocks
    - TopLosersScanner: Scans for top losing stocks
    - VolumeBreakoutScanner: Scans for volume breakouts
    - PreMarketScanner: Scans pre-market movers
    - CustomScanner: User-defined scanning criteria
    
    Usage:
        scanner = TopGainersScanner(config)
        result = await scanner.scan()
        
        for candidate in result.candidates:
            print(f"{candidate.symbol}: {candidate.gain_pct}%")
    """
    
    def __init__(self, config: Optional[ScannerConfig] = None):
        """
        Initialize scanner with configuration.
        
        Args:
            config: Scanner configuration (uses defaults if None)
        """
        self.config = config or ScannerConfig()
    
    @abstractmethod
    async def scan(self) -> ScanResult:
        """
        Execute market scan.
        
        Returns:
            ScanResult with candidates and metadata
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Get scanner name for logging.
        
        Returns:
            Scanner name (e.g., 'top_gainers', 'volume_breakout')
        """
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """
        Get scanner description.
        
        Returns:
            Human-readable description of what scanner looks for
        """
        pass
    
    # ================================================================
    # OPTIONAL METHODS (override if needed)
    # ================================================================
    
    async def initialize(self) -> None:
        """
        Initialize scanner resources (e.g., API sessions).
        
        Override this to set up connections, caches, etc.
        Called once before first scan.
        """
        pass
    
    async def cleanup(self) -> None:
        """
        Cleanup scanner resources.
        
        Override this to close connections, flush caches, etc.
        Called on shutdown.
        """
        pass
    
    def filter_candidates(self, candidates: List[Candidate]) -> List[Candidate]:
        """
        Apply base filters to candidates.
        
        Args:
            candidates: Raw candidates from scan
        
        Returns:
            Filtered candidates
        """
        filtered = []
        
        for candidate in candidates:
            # Price filter
            if not (self.config.min_price <= candidate.current_price <= self.config.max_price):
                continue
            
            # Gain filter
            if not (self.config.min_gain_pct <= candidate.gain_pct <= self.config.max_gain_pct):
                continue
            
            # Volume filter
            if candidate.volume < self.config.min_volume:
                continue
            
            filtered.append(candidate)
        
        # Limit results
        return filtered[:self.config.max_results]
    
    def _log_scan_start(self) -> None:
        """Log scan start"""
        logger.info(f"🔍 {self.get_name()}: Starting scan...")
    
    def _log_scan_result(self, result: ScanResult) -> None:
        """Log scan result"""
        if result.success:
            logger.info(
                f"✅ {self.get_name()}: Found {len(result.candidates)} candidates "
                f"in {result.duration_ms:.0f}ms"
            )
        else:
            logger.warning(f"⚠️ {self.get_name()}: No candidates found")
        
        if result.errors:
            for error in result.errors:
                logger.error(f"❌ {self.get_name()}: {error}")
