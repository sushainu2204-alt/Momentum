"""
Scanner Factory

Factory for creating scanner instances.
Supports registration of custom scanners.
"""

from typing import Dict, Type, Optional, Any
import logging

from .base import IScanner, ScannerConfig
from .top_gainers import TopGainersScanner, TopGainersConfig
from .top_losers import TopLosersScanner, TopLosersConfig
from .volume_breakout import VolumeBreakoutScanner, VolumeBreakoutConfig

logger = logging.getLogger(__name__)


class ScannerFactory:
    """
    Factory for creating scanner instances.
    
    Supports built-in scanners and custom scanner registration.
    
    Usage:
        # Create scanner with defaults
        scanner = ScannerFactory.create("top_gainers")
        
        # Create scanner with custom config
        config = TopGainersConfig(min_gain_pct=5.0)
        scanner = ScannerFactory.create("top_gainers", config=config)
        
        # Register custom scanner
        ScannerFactory.register("my_scanner", MyScanner)
        scanner = ScannerFactory.create("my_scanner")
    """
    
    # Registry of scanner types
    _registry: Dict[str, Type[IScanner]] = {
        "top_gainers": TopGainersScanner,
        "top_losers": TopLosersScanner,
        "volume_breakout": VolumeBreakoutScanner,
    }
    
    # Default configs for each scanner type
    _default_configs: Dict[str, Type[ScannerConfig]] = {
        "top_gainers": TopGainersConfig,
        "top_losers": TopLosersConfig,
        "volume_breakout": VolumeBreakoutConfig,
    }
    
    @classmethod
    def register(
        cls,
        name: str,
        scanner_class: Type[IScanner],
        config_class: Optional[Type[ScannerConfig]] = None
    ) -> None:
        """
        Register a custom scanner.
        
        Args:
            name: Scanner name (used in create())
            scanner_class: Scanner class that implements IScanner
            config_class: Optional config class for this scanner
        """
        cls._registry[name] = scanner_class
        if config_class:
            cls._default_configs[name] = config_class
        
        logger.info(f"Registered scanner: {name}")
    
    @classmethod
    def create(
        cls,
        scanner_type: str,
        config: Optional[ScannerConfig] = None,
        **kwargs: Any
    ) -> IScanner:
        """
        Create a scanner instance.
        
        Args:
            scanner_type: Type of scanner ('top_gainers', 'top_losers', etc.)
            config: Optional scanner configuration
            **kwargs: Additional arguments passed to scanner constructor
        
        Returns:
            Scanner instance
        
        Raises:
            ValueError: If scanner type is not registered
        """
        if scanner_type not in cls._registry:
            available = ", ".join(cls._registry.keys())
            raise ValueError(
                f"Unknown scanner type: '{scanner_type}'. "
                f"Available: {available}"
            )
        
        scanner_class = cls._registry[scanner_type]
        
        # Use provided config or create default
        if config is None and scanner_type in cls._default_configs:
            config = cls._default_configs[scanner_type]()
        
        return scanner_class(config=config, **kwargs)
    
    @classmethod
    def get_available_scanners(cls) -> Dict[str, str]:
        """
        Get list of available scanners with descriptions.
        
        Returns:
            Dict of scanner_name -> description
        """
        scanners = {}
        
        for name, scanner_class in cls._registry.items():
            try:
                # Create temporary instance to get description
                scanner = scanner_class()
                scanners[name] = scanner.get_description()
            except Exception:
                scanners[name] = "No description available"
        
        return scanners
    
    @classmethod
    def is_registered(cls, scanner_type: str) -> bool:
        """Check if scanner type is registered"""
        return scanner_type in cls._registry
