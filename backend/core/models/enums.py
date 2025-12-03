"""
Domain Enums

Enumerations used across the trading system.
"""
from enum import Enum


class SignalType(str, Enum):
    """Signal types for trading."""
    BUY = "BUY"
    SELL = "SELL"


class PositionStatus(str, Enum):
    """Position lifecycle status."""
    OPEN = "OPEN"
    TARGET_HIT = "TARGET_HIT"
    SL_HIT = "SL_HIT"
    TIME_EXIT = "TIME_EXIT"
    MANUAL_EXIT = "MANUAL_EXIT"


class OrderStatus(str, Enum):
    """Order status from broker."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderType(str, Enum):
    """Order type for trading."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"
