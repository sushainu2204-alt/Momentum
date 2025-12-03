"""
Broker Abstractions

Pluggable broker interfaces for order execution.
Allows switching between Zerodha, Upstox, Angel One, etc.
"""

from .base import IBroker, OrderResponse, OrderStatus, MarginInfo
from .zerodha import ZerodhaBroker

__all__ = [
    "IBroker",
    "OrderResponse",
    "OrderStatus",
    "MarginInfo",
    "ZerodhaBroker",
]
