"""Trading services - order execution, position management, capital management"""
from .capital_manager import CapitalManager, TradingLimits
from .order_manager import OrderManager
from .position_manager import PositionManager
from .position_manager_service import PositionManagerService
from .signal_executor import SignalExecutor
from .trailing_sl_service import TrailingStopLossService

# Alias for convenience
TrailingSLService = TrailingStopLossService

__all__ = [
    "CapitalManager",
    "TradingLimits",
    "OrderManager",
    "PositionManager",
    "PositionManagerService",
    "SignalExecutor",
    "TrailingStopLossService",
    "TrailingSLService",
]
