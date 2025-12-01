"""Configuration package"""

from .strategy_config import (
    BaseStrategyConfig,
    EMACrossoverConfig,
    TopGainersMomentumConfig,
    VWAPBreakoutConfig,
    BullishFlagConfig,
    VWAPEMABreakoutConfig,
    StrategyConfigFactory
)

__all__ = [
    'BaseStrategyConfig',
    'EMACrossoverConfig',
    'TopGainersMomentumConfig',
    'VWAPBreakoutConfig',
    'BullishFlagConfig',
    'VWAPEMABreakoutConfig',
    'StrategyConfigFactory',
]
