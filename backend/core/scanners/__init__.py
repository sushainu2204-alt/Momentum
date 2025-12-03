"""
Scanners Module

Pluggable market scanners for discovering trading opportunities.
Similar to Strategy Pattern - each scanner implements IScanner interface.

Available Scanners:
- TopGainersScanner: Scans NSE for top gaining stocks
- TopLosersScanner: Scans NSE for top losing stocks  
- VolumeBreakoutScanner: Scans for unusual volume spikes
- PreMarketScanner: Scans pre-market movers

Usage:
    scanner = TopGainersScanner(nse_config=DEFAULT_NSE_CONFIG)
    candidates = await scanner.scan()
    
    # Or use factory:
    scanner = ScannerFactory.create("top_gainers")
    result = await scanner.scan()
"""

from .base import IScanner, ScannerConfig, ScanResult
from .top_gainers import TopGainersScanner, TopGainersConfig
from .top_losers import TopLosersScanner, TopLosersConfig
from .volume_breakout import VolumeBreakoutScanner, VolumeBreakoutConfig
from .factory import ScannerFactory

__all__ = [
    # Base
    "IScanner",
    "ScannerConfig",
    "ScanResult",
    # Scanners
    "TopGainersScanner",
    "TopGainersConfig",
    "TopLosersScanner",
    "TopLosersConfig",
    "VolumeBreakoutScanner",
    "VolumeBreakoutConfig",
    # Factory
    "ScannerFactory",
]

