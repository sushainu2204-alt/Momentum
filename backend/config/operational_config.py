"""
Operational Configuration

System-level configurations for trading operations.
Not strategy-specific, but used across the trading system.

These are operational limits and thresholds imposed by:
- Broker APIs (Zerodha)
- System architecture decisions
- Risk management policies
"""

from dataclasses import dataclass, field
from datetime import time
from typing import List


@dataclass
class PathsConfig:
    """
    File system paths for data storage.
    
    All paths are relative to project root.
    """
    
    # Signal storage
    signals_dir: str = "./signals"
    orders_dir: str = "./orders"
    
    # Logs
    logs_dir: str = "./logs"
    
    # Data
    data_dir: str = "./backend/data"
    universes_dir: str = "./backend/data/universes"


@dataclass
class NSEConfig:
    """
    NSE API configuration.
    
    Categories available from NSE live analysis API.
    """
    
    # Available categories for top gainers/losers
    valid_categories: List[str] = field(default_factory=lambda: [
        "allSec",       # All Securities (default)
        "NIFTY",        # Nifty 50
        "BANKNIFTY",    # Bank Nifty
        "NIFTYNEXT50",  # Nifty Next 50
        "SecGtr20",     # Securities > Rs 20
        "SecLwr20",     # Securities < Rs 20
    ])
    
    # Default category
    default_category: str = "allSec"
    
    # API base URL
    base_url: str = "https://www.nseindia.com"


@dataclass
class BrokerLimits:
    """
    Zerodha/Kite API operational limits.
    
    These are imposed by the broker and should not be exceeded.
    """
    
    # Order modification limits
    max_order_modifications: int = 25  # Zerodha's hard limit
    max_sl_modifications: int = 20     # Buffer before hitting broker limit
    
    # API rate limits
    api_requests_per_second: int = 10
    
    # Order quantity limits
    min_quantity: int = 1
    max_order_value: float = 2_000_000  # ₹20 lakhs per order
    
    # WebSocket limits
    max_instrument_subscriptions: int = 3000


@dataclass 
class TradingHoursConfig:
    """
    Indian stock market trading hours configuration.
    
    IST timezone assumed throughout.
    """
    
    # Standard market hours
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    
    # Pre-market session
    pre_market_open: time = time(9, 0)
    pre_market_close: time = time(9, 8)
    
    # Post-market/AMO session
    amo_start: time = time(15, 50)
    amo_end: time = time(8, 57)  # Next day
    
    # Auto square-off times (intraday MIS)
    broker_square_off: time = time(15, 20)  # Zerodha's square-off time
    safe_exit_time: time = time(15, 15)     # Our exit before broker
    
    # Buffer periods
    skip_first_minutes: int = 10  # Avoid volatile opening
    skip_last_minutes: int = 10   # Exit before close


@dataclass
class CacheConfig:
    """
    Caching configuration for various data sources.
    """
    
    # Historical data cache TTL (seconds)
    historical_data_ttl: int = 86400  # 24 hours
    
    # Instrument cache TTL
    instruments_cache_ttl: int = 86400  # 24 hours
    
    # Order cache TTL (for rate limiting)
    order_cache_ttl: int = 2  # 2 seconds
    
    # Position cache TTL
    position_cache_ttl: int = 2  # 2 seconds
    
    # Margin cache TTL
    margin_cache_ttl: int = 5  # 5 seconds


@dataclass
class SyncJobConfig:
    """
    Configuration for background sync jobs.
    """
    
    # Sync intervals (seconds)
    order_sync_interval: int = 60       # 1 minute
    position_sync_interval: int = 60    # 1 minute
    margin_sync_interval: int = 30      # 30 seconds
    trailing_sl_interval: int = 30      # 30 seconds
    
    # Monitor intervals
    position_monitor_interval: int = 60  # 1 minute


# ================================================================
# DEFAULT INSTANCES
# ================================================================

DEFAULT_PATHS = PathsConfig()
DEFAULT_NSE_CONFIG = NSEConfig()
DEFAULT_BROKER_LIMITS = BrokerLimits()
DEFAULT_TRADING_HOURS = TradingHoursConfig()
DEFAULT_CACHE_CONFIG = CacheConfig()
DEFAULT_SYNC_JOB_CONFIG = SyncJobConfig()
