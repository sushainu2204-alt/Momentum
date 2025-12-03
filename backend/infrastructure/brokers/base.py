"""
Broker Interface

Abstract interface for broker operations.
Allows plug-and-play broker switching (Zerodha, Upstox, Angel One, etc.)

Usage:
    # Any broker implementation can be used
    broker: IBroker = ZerodhaBroker(kite)
    
    # Place order
    result = await broker.place_order(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=10,
        order_type="MARKET"
    )
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


class OrderStatus(str, Enum):
    """Standard order status across brokers"""
    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    TRIGGER_PENDING = "TRIGGER_PENDING"


@dataclass
class OrderResponse:
    """Standard order response from broker"""
    order_id: str
    status: OrderStatus
    symbol: str
    exchange: str
    transaction_type: str  # BUY, SELL
    quantity: int
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    average_price: Optional[float] = None
    filled_quantity: int = 0
    pending_quantity: int = 0
    order_type: str = "MARKET"  # MARKET, LIMIT, SL, SL-M
    product: str = "MIS"  # MIS, CNC, NRML
    message: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class Position:
    """Standard position data from broker"""
    symbol: str
    exchange: str
    instrument_token: int
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    pnl_pct: float
    product: str  # MIS, CNC, NRML
    overnight_quantity: int = 0
    day_buy_quantity: int = 0
    day_sell_quantity: int = 0


@dataclass
class MarginInfo:
    """Standard margin/funds data from broker"""
    available_cash: float
    available_margin: float
    used_margin: float
    total_balance: float
    collateral: float = 0.0
    

@dataclass
class OrderBook:
    """Order details from broker"""
    order_id: str
    exchange_order_id: Optional[str]
    status: OrderStatus
    symbol: str
    exchange: str
    transaction_type: str
    quantity: int
    price: Optional[float]
    trigger_price: Optional[float]
    average_price: Optional[float]
    filled_quantity: int
    pending_quantity: int
    order_type: str
    product: str
    placed_by: str
    order_timestamp: Optional[datetime]
    exchange_timestamp: Optional[datetime]
    variety: str  # regular, amo, co, iceberg
    validity: str  # DAY, IOC
    tag: Optional[str] = None  # Custom tag for tracking
    

class IBroker(ABC):
    """
    Interface for broker operations.
    
    Implementations:
    - ZerodhaBroker: Kite Connect API
    - UpstoxBroker: Upstox API
    - AngelOneBroker: Angel Broking API
    - MockBroker: For testing
    """
    
    # ================================================================
    # ORDER OPERATIONS
    # ================================================================
    
    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        product: str = "MIS",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        tag: Optional[str] = None
    ) -> OrderResponse:
        """
        Place an order.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange (NSE, BSE, NFO, etc.)
            transaction_type: BUY or SELL
            quantity: Number of shares
            order_type: MARKET, LIMIT, SL, SL-M
            product: MIS (intraday), CNC (delivery), NRML (F&O)
            price: Limit price (for LIMIT orders)
            trigger_price: Trigger price (for SL/SL-M orders)
            tag: Custom tag for tracking
        
        Returns:
            OrderResponse with order details
        """
        pass
    
    @abstractmethod
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None
    ) -> OrderResponse:
        """
        Modify an existing order.
        
        Args:
            order_id: Order ID to modify
            quantity: New quantity (optional)
            price: New price (optional)
            trigger_price: New trigger price (optional)
            order_type: New order type (optional)
        
        Returns:
            OrderResponse with updated order details
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            True if cancelled successfully
        """
        pass
    
    @abstractmethod
    async def get_order(self, order_id: str) -> Optional[OrderBook]:
        """
        Get order details by ID.
        
        Args:
            order_id: Order ID
        
        Returns:
            OrderBook or None if not found
        """
        pass
    
    @abstractmethod
    async def get_orders(self) -> List[OrderBook]:
        """
        Get all orders for the day.
        
        Returns:
            List of orders
        """
        pass
    
    # ================================================================
    # POSITION OPERATIONS
    # ================================================================
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Get all positions.
        
        Returns:
            List of positions
        """
        pass
    
    @abstractmethod
    async def get_position(self, symbol: str, exchange: str = "NSE") -> Optional[Position]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange
        
        Returns:
            Position or None if no position
        """
        pass
    
    # ================================================================
    # MARGIN/FUNDS OPERATIONS
    # ================================================================
    
    @abstractmethod
    async def get_margins(self) -> MarginInfo:
        """
        Get margin/funds information.
        
        Returns:
            MarginInfo with available funds
        """
        pass
    
    # ================================================================
    # UTILITY METHODS
    # ================================================================
    
    @abstractmethod
    async def is_connected(self) -> bool:
        """
        Check if broker connection is active.
        
        Returns:
            True if connected
        """
        pass
    
    @abstractmethod
    def get_broker_name(self) -> str:
        """
        Get broker name for logging.
        
        Returns:
            Broker name (e.g., "Zerodha", "Upstox")
        """
        pass
