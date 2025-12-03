"""
Unit Tests for Scanner Factory

Tests the scanner factory pattern implementation.
"""
import pytest
from unittest.mock import Mock, patch

from backend.core.scanners.factory import ScannerFactory
from backend.core.scanners.base import IScanner, ScannerConfig, ScanResult
from backend.core.scanners.top_gainers import TopGainersScanner, TopGainersConfig
from backend.core.scanners.top_losers import TopLosersScanner, TopLosersConfig
from backend.core.scanners.volume_breakout import VolumeBreakoutScanner, VolumeBreakoutConfig


class TestScannerFactory:
    """Test ScannerFactory."""
    
    def test_create_top_gainers_scanner(self):
        """Test creating top gainers scanner."""
        scanner = ScannerFactory.create("top_gainers")
        
        assert isinstance(scanner, TopGainersScanner)
        assert scanner.get_name() == "top_gainers"
    
    def test_create_top_losers_scanner(self):
        """Test creating top losers scanner."""
        scanner = ScannerFactory.create("top_losers")
        
        assert isinstance(scanner, TopLosersScanner)
        assert scanner.get_name() == "top_losers"
    
    def test_create_volume_breakout_scanner(self):
        """Test creating volume breakout scanner."""
        scanner = ScannerFactory.create("volume_breakout")
        
        assert isinstance(scanner, VolumeBreakoutScanner)
        assert scanner.get_name() == "volume_breakout"
    
    def test_create_with_custom_config(self):
        """Test creating scanner with custom config."""
        config = TopGainersConfig(min_gain_pct=5.0, max_results=10)
        scanner = ScannerFactory.create("top_gainers", config=config)
        
        assert scanner.config.min_gain_pct == 5.0
        assert scanner.config.max_results == 10
    
    def test_create_unknown_scanner_raises_error(self):
        """Test creating unknown scanner raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            ScannerFactory.create("unknown_scanner")
        
        assert "Unknown scanner type" in str(exc_info.value)
        assert "unknown_scanner" in str(exc_info.value)
    
    def test_create_lists_available_scanners_on_error(self):
        """Test error message lists available scanners."""
        with pytest.raises(ValueError) as exc_info:
            ScannerFactory.create("nonexistent")
        
        error_msg = str(exc_info.value)
        assert "top_gainers" in error_msg
        assert "top_losers" in error_msg
        assert "volume_breakout" in error_msg
    
    def test_is_registered_returns_true_for_registered(self):
        """Test is_registered returns True for registered scanners."""
        assert ScannerFactory.is_registered("top_gainers") == True
        assert ScannerFactory.is_registered("top_losers") == True
        assert ScannerFactory.is_registered("volume_breakout") == True
    
    def test_is_registered_returns_false_for_unregistered(self):
        """Test is_registered returns False for unregistered scanners."""
        assert ScannerFactory.is_registered("unknown") == False
        assert ScannerFactory.is_registered("") == False
    
    def test_get_available_scanners(self):
        """Test get_available_scanners returns all scanners."""
        scanners = ScannerFactory.get_available_scanners()
        
        assert "top_gainers" in scanners
        assert "top_losers" in scanners
        assert "volume_breakout" in scanners
        
        # Each should have a description
        for name, description in scanners.items():
            assert isinstance(description, str)
            assert len(description) > 0


class TestScannerFactoryRegistration:
    """Test custom scanner registration."""
    
    def setup_method(self):
        """Store original registry to restore later."""
        self._original_registry = ScannerFactory._registry.copy()
        self._original_configs = ScannerFactory._default_configs.copy()
    
    def teardown_method(self):
        """Restore original registry."""
        ScannerFactory._registry = self._original_registry
        ScannerFactory._default_configs = self._original_configs
    
    def test_register_custom_scanner(self):
        """Test registering a custom scanner."""
        class CustomScanner(IScanner):
            async def scan(self):
                return ScanResult(scanner_name="custom")
            
            def get_name(self):
                return "custom"
            
            def get_description(self):
                return "Custom scanner"
        
        ScannerFactory.register("custom", CustomScanner)
        
        assert ScannerFactory.is_registered("custom")
        scanner = ScannerFactory.create("custom")
        assert isinstance(scanner, CustomScanner)
    
    def test_register_scanner_with_config(self):
        """Test registering scanner with custom config class."""
        class CustomConfig(ScannerConfig):
            name: str = "custom_scanner"
            special_param: float = 1.5
        
        class CustomScanner(IScanner):
            def __init__(self, config=None):
                super().__init__(config)
            
            async def scan(self):
                return ScanResult(scanner_name="custom")
            
            def get_name(self):
                return "custom"
            
            def get_description(self):
                return "Custom scanner"
        
        ScannerFactory.register("custom", CustomScanner, CustomConfig)
        
        # Create should use default config
        scanner = ScannerFactory.create("custom")
        assert scanner.config is not None
    
    def test_register_overwrites_existing(self):
        """Test registering overwrites existing scanner."""
        class NewTopGainers(IScanner):
            async def scan(self):
                return ScanResult(scanner_name="new_top_gainers")
            
            def get_name(self):
                return "new_top_gainers"
            
            def get_description(self):
                return "New top gainers"
        
        ScannerFactory.register("top_gainers", NewTopGainers)
        
        scanner = ScannerFactory.create("top_gainers")
        assert isinstance(scanner, NewTopGainers)


class TestTopGainersConfig:
    """Test TopGainersConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = TopGainersConfig()
        
        assert config.name == "top_gainers"
        assert config.min_gain_pct == 2.0
        assert config.max_gain_pct == 20.0
        assert config.min_price == 50.0
        assert config.max_price == 10000.0
        assert config.max_results == 30
        assert "FOSec" in config.categories
    
    def test_custom_categories(self):
        """Test custom categories configuration."""
        config = TopGainersConfig(categories=["NIFTY", "MIDCAP"])
        
        assert config.categories == ["NIFTY", "MIDCAP"]


class TestTopLosersConfig:
    """Test TopLosersConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = TopLosersConfig()
        
        assert config.name == "top_losers"
        assert config.min_loss_pct == -20.0
        assert config.max_loss_pct == -2.0
        assert config.min_price == 50.0
        assert config.max_price == 10000.0
    
    def test_loss_range(self):
        """Test loss percentage range makes sense."""
        config = TopLosersConfig()
        
        # min_loss_pct should be more negative than max_loss_pct
        assert config.min_loss_pct < config.max_loss_pct


class TestVolumeBreakoutConfig:
    """Test VolumeBreakoutConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = VolumeBreakoutConfig()
        
        assert config.name == "volume_breakout"
        assert config.volume_multiplier == 2.0
        assert config.avg_volume_days == 20
        assert config.min_gain_pct == 0.5
        assert config.max_gain_pct == 15.0
    
    def test_custom_volume_multiplier(self):
        """Test custom volume multiplier."""
        config = VolumeBreakoutConfig(volume_multiplier=3.5)
        
        assert config.volume_multiplier == 3.5
