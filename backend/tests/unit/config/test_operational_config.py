"""
Unit Tests for Operational Configuration

Tests for all operational configuration dataclasses.
"""
import pytest
from datetime import time

from backend.config.operational_config import (
    PathsConfig,
    NSEConfig,
    BrokerLimits,
    TradingHoursConfig,
    CacheConfig,
    SyncJobConfig,
    DEFAULT_PATHS,
    DEFAULT_NSE_CONFIG,
    DEFAULT_BROKER_LIMITS,
    DEFAULT_TRADING_HOURS,
    DEFAULT_CACHE_CONFIG,
    DEFAULT_SYNC_JOB_CONFIG
)


class TestPathsConfig:
    """Test PathsConfig dataclass."""
    
    def test_default_values(self):
        """Test default path values."""
        config = PathsConfig()
        
        assert config.signals_dir == "./signals"
        assert config.orders_dir == "./orders"
        assert config.logs_dir == "./logs"
        assert config.data_dir == "./backend/data"
        assert config.universes_dir == "./backend/data/universes"
    
    def test_custom_values(self):
        """Test custom path values."""
        config = PathsConfig(
            signals_dir="/custom/signals",
            orders_dir="/custom/orders",
            logs_dir="/custom/logs"
        )
        
        assert config.signals_dir == "/custom/signals"
        assert config.orders_dir == "/custom/orders"
        assert config.logs_dir == "/custom/logs"
    
    def test_default_instance(self):
        """Test DEFAULT_PATHS instance."""
        assert isinstance(DEFAULT_PATHS, PathsConfig)
        assert DEFAULT_PATHS.signals_dir == "./signals"


class TestNSEConfig:
    """Test NSEConfig dataclass."""
    
    def test_default_values(self):
        """Test default NSE configuration."""
        config = NSEConfig()
        
        assert config.default_category == "FOSec"
        assert config.base_url == "https://www.nseindia.com"
        assert len(config.valid_categories) == 7
    
    def test_valid_categories_include_all_expected(self):
        """Test all expected categories are present."""
        config = NSEConfig()
        
        expected = ["allSec", "FOSec", "NIFTY", "BANKNIFTY", "NIFTYNEXT50", "SecGtr20", "SecLwr20"]
        for cat in expected:
            assert cat in config.valid_categories
    
    def test_custom_categories(self):
        """Test custom categories."""
        config = NSEConfig(
            valid_categories=["NIFTY", "BANKNIFTY"],
            default_category="NIFTY"
        )
        
        assert len(config.valid_categories) == 2
        assert config.default_category == "NIFTY"
    
    def test_default_instance(self):
        """Test DEFAULT_NSE_CONFIG instance."""
        assert isinstance(DEFAULT_NSE_CONFIG, NSEConfig)


class TestBrokerLimits:
    """Test BrokerLimits dataclass."""
    
    def test_default_values(self):
        """Test default broker limits."""
        config = BrokerLimits()
        
        assert config.max_order_modifications == 25
        assert config.max_sl_modifications == 20
        assert config.api_requests_per_second == 10
        assert config.min_quantity == 1
        assert config.max_order_value == 2_000_000
        assert config.max_instrument_subscriptions == 3000
    
    def test_custom_values(self):
        """Test custom broker limits."""
        config = BrokerLimits(
            max_order_modifications=30,
            max_sl_modifications=25,
            max_order_value=1_000_000
        )
        
        assert config.max_order_modifications == 30
        assert config.max_sl_modifications == 25
        assert config.max_order_value == 1_000_000
    
    def test_default_instance(self):
        """Test DEFAULT_BROKER_LIMITS instance."""
        assert isinstance(DEFAULT_BROKER_LIMITS, BrokerLimits)


class TestTradingHoursConfig:
    """Test TradingHoursConfig dataclass."""
    
    def test_default_values(self):
        """Test default trading hours."""
        config = TradingHoursConfig()
        
        assert config.market_open == time(9, 15)
        assert config.market_close == time(15, 30)
        assert config.pre_market_open == time(9, 0)
        assert config.pre_market_close == time(9, 8)
        assert config.broker_square_off == time(15, 20)
        assert config.safe_exit_time == time(15, 15)
        assert config.skip_first_minutes == 10
        assert config.skip_last_minutes == 10
    
    def test_amo_session_times(self):
        """Test AMO session times."""
        config = TradingHoursConfig()
        
        assert config.amo_start == time(15, 50)
        assert config.amo_end == time(8, 57)
    
    def test_custom_values(self):
        """Test custom trading hours."""
        config = TradingHoursConfig(
            market_open=time(9, 0),
            market_close=time(16, 0),
            skip_first_minutes=15
        )
        
        assert config.market_open == time(9, 0)
        assert config.market_close == time(16, 0)
        assert config.skip_first_minutes == 15
    
    def test_default_instance(self):
        """Test DEFAULT_TRADING_HOURS instance."""
        assert isinstance(DEFAULT_TRADING_HOURS, TradingHoursConfig)


class TestCacheConfig:
    """Test CacheConfig dataclass."""
    
    def test_default_values(self):
        """Test default cache TTL values."""
        config = CacheConfig()
        
        assert config.historical_data_ttl == 86400  # 24 hours
        assert config.instruments_cache_ttl == 86400
        assert config.order_cache_ttl == 2
        assert config.position_cache_ttl == 2
        assert config.margin_cache_ttl == 5
    
    def test_custom_values(self):
        """Test custom cache TTL values."""
        config = CacheConfig(
            historical_data_ttl=3600,  # 1 hour
            order_cache_ttl=5
        )
        
        assert config.historical_data_ttl == 3600
        assert config.order_cache_ttl == 5
    
    def test_default_instance(self):
        """Test DEFAULT_CACHE_CONFIG instance."""
        assert isinstance(DEFAULT_CACHE_CONFIG, CacheConfig)


class TestSyncJobConfig:
    """Test SyncJobConfig dataclass."""
    
    def test_default_values(self):
        """Test default sync job intervals."""
        config = SyncJobConfig()
        
        assert config.order_sync_interval == 60
        assert config.position_sync_interval == 60
        assert config.margin_sync_interval == 30
        assert config.trailing_sl_interval == 30
        assert config.position_monitor_interval == 60
    
    def test_custom_values(self):
        """Test custom sync intervals."""
        config = SyncJobConfig(
            order_sync_interval=30,
            margin_sync_interval=15
        )
        
        assert config.order_sync_interval == 30
        assert config.margin_sync_interval == 15
    
    def test_default_instance(self):
        """Test DEFAULT_SYNC_JOB_CONFIG instance."""
        assert isinstance(DEFAULT_SYNC_JOB_CONFIG, SyncJobConfig)
