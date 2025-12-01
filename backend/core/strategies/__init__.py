"""Trading strategies"""
from .base import BaseStrategy
from .ema_crossover import EMACrossoverStrategy
from .top_gainers_momentum import TopGainersMomentumStrategy
from .vwap_breakout import VWAPBreakoutStrategy
from .bullish_flag import BullishFlagStrategy
from .vwap_ema_breakout import VWAPEMABreakoutStrategy

__all__ = [
    "BaseStrategy",
    "EMACrossoverStrategy",
    "TopGainersMomentumStrategy",
    "VWAPBreakoutStrategy",
    "BullishFlagStrategy",
    "VWAPEMABreakoutStrategy",
]
