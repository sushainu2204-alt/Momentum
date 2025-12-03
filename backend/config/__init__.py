"""Configuration module"""
from .settings import settings
from .logging_config import setup_logging, get_logger, get_logs_dir
from .strategy_config import (
    BaseStrategyConfig,
    EMACrossoverConfig,
    TopGainersMomentumConfig,
    BullishFlagConfig,
    VWAPEMABreakoutConfig,
    VWAPBreakoutConfig,
    StrategyConfigFactory,
)
from .operational_config import (
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
    DEFAULT_SYNC_JOB_CONFIG,
)

__all__ = [
    "settings",
    # Logging
    "setup_logging",
    "get_logger",
    "get_logs_dir",
    # Strategy configs
    "BaseStrategyConfig",
    "EMACrossoverConfig",
    "TopGainersMomentumConfig",
    "BullishFlagConfig",
    "VWAPEMABreakoutConfig",
    "VWAPBreakoutConfig",
    "StrategyConfigFactory",
    # Operational configs
    "PathsConfig",
    "NSEConfig",
    "BrokerLimits",
    "TradingHoursConfig",
    "CacheConfig",
    "SyncJobConfig",
    "DEFAULT_PATHS",
    "DEFAULT_NSE_CONFIG",
    "DEFAULT_BROKER_LIMITS",
    "DEFAULT_TRADING_HOURS",
    "DEFAULT_CACHE_CONFIG",
    "DEFAULT_SYNC_JOB_CONFIG",
]
