"""
Zerodha Broker Implementation

Implements IBroker using Kite Connect API.
"""

from typing import List, Optional
from datetime import datetime
import logging
from kiteconnect import KiteConnect

from .base import (
    IBroker,
    OrderResponse,
    OrderStatus,
    OrderBook,
    Position,
    MarginInfo
)
from backend.core.utils.retry import retry_async, KITE_API_ERRORS

logger = logging.getLogger(__name__)


class ZerodhaBroker(IBroker):
    """
    Zerodha Kite Connect implementation of IBroker.
    
    Usage:
        kite = KiteConnect(api_key=settings.KITE_API_KEY)
        kite.set_access_token(settings.KITE_ACCESS_TOKEN)
        broker = ZerodhaBroker(kite)
        
        # Place order
        result = await broker.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=10
        )
    """
    
    # Map Kite status to standard status
    STATUS_MAP = {
        "OPEN": OrderStatus.OPEN,
        "COMPLETE": OrderStatus.COMPLETE,
        "CANCELLED": OrderStatus.CANCELLED,
        "REJECTED": OrderStatus.REJECTED,
        "TRIGGER PENDING": OrderStatus.TRIGGER_PENDING,
        "PENDING": OrderStatus.PENDING,
    }
    
    def __init__(self, kite: KiteConnect):
        """
        Initialize with KiteConnect instance.
        
        Args:
            kite: Authenticated KiteConnect instance
        """
        self.kite = kite
        self._user_id: Optional[str] = None
    
    def get_broker_name(self) -> str:
        return "Zerodha"
    
    async def is_connected(self) -> bool:
        """Check if Kite session is active."""
        try:
            profile = self.kite.profile()
            self._user_id = profile.get("user_id")
            return True
        except Exception as e:
            logger.error(f"Kite connection check failed: {e}")
            return False
    
    # ================================================================
    # ORDER OPERATIONS
    # ================================================================
    
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
        """Place order via Kite API."""
        try:
            # Build order params
            params = {
                "tradingsymbol": symbol,
                "exchange": exchange,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "order_type": order_type,
                "product": product,
                "variety": "regular",
            }
            
            if price is not None:
                params["price"] = price
            
            if trigger_price is not None:
                params["trigger_price"] = trigger_price
            
            if tag:
                params["tag"] = tag
            
            # Place order with retry
            order_id = await retry_async(
                lambda: self.kite.place_order(**params),
                retryable_exceptions=KITE_API_ERRORS,
                max_retries=3,
                base_delay=1.0
            )
            
            logger.info(
                f"Order placed: {transaction_type} {quantity} x {symbol} @ {order_type} - "
                f"Order ID: {order_id}"
            )
            
            return OrderResponse(
                order_id=str(order_id),
                status=OrderStatus.PENDING,
                symbol=symbol,
                exchange=exchange,
                transaction_type=transaction_type,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                order_type=order_type,
                product=product,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return OrderResponse(
                order_id="",
                status=OrderStatus.REJECTED,
                symbol=symbol,
                exchange=exchange,
                transaction_type=transaction_type,
                quantity=quantity,
                message=str(e)
            )
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None
    ) -> OrderResponse:
        """Modify existing order."""
        try:
            params = {"order_id": order_id, "variety": "regular"}
            
            if quantity is not None:
                params["quantity"] = quantity
            if price is not None:
                params["price"] = price
            if trigger_price is not None:
                params["trigger_price"] = trigger_price
            if order_type is not None:
                params["order_type"] = order_type
            
            await retry_async(
                lambda: self.kite.modify_order(**params),
                retryable_exceptions=KITE_API_ERRORS,
                max_retries=3,
                base_delay=1.0
            )
            
            # Fetch updated order
            order = await self.get_order(order_id)
            if order:
                return OrderResponse(
                    order_id=order.order_id,
                    status=order.status,
                    symbol=order.symbol,
                    exchange=order.exchange,
                    transaction_type=order.transaction_type,
                    quantity=order.quantity,
                    price=order.price,
                    trigger_price=order.trigger_price,
                    average_price=order.average_price,
                    filled_quantity=order.filled_quantity,
                    pending_quantity=order.pending_quantity,
                    order_type=order.order_type,
                    product=order.product
                )
            
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.PENDING,
                symbol="",
                exchange="",
                transaction_type="",
                quantity=quantity or 0
            )
            
        except Exception as e:
            logger.error(f"Order modification failed: {e}")
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                symbol="",
                exchange="",
                transaction_type="",
                quantity=0,
                message=str(e)
            )
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order."""
        try:
            await retry_async(
                lambda: self.kite.cancel_order(
                    order_id=order_id,
                    variety="regular"
                ),
                retryable_exceptions=KITE_API_ERRORS,
                max_retries=3,
                base_delay=1.0
            )
            
            logger.info(f"Order cancelled: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Order cancellation failed: {e}")
            return False
    
    async def get_order(self, order_id: str) -> Optional[OrderBook]:
        """Get order details."""
        try:
            orders = await self.get_orders()
            for order in orders:
                if order.order_id == order_id:
                    return order
            return None
            
        except Exception as e:
            logger.error(f"Failed to get order: {e}")
            return None
    
    async def get_orders(self) -> List[OrderBook]:
        """Get all orders for the day."""
        try:
            kite_orders = await retry_async(
                lambda: self.kite.orders(),
                retryable_exceptions=KITE_API_ERRORS,
                max_retries=3,
                base_delay=1.0
            )
            
            orders = []
            for o in kite_orders:
                status = self.STATUS_MAP.get(o.get("status", ""), OrderStatus.PENDING)
                
                order = OrderBook(
                    order_id=str(o.get("order_id", "")),
                    exchange_order_id=o.get("exchange_order_id"),
                    status=status,
                    symbol=o.get("tradingsymbol", ""),
                    exchange=o.get("exchange", ""),
                    transaction_type=o.get("transaction_type", ""),
                    quantity=o.get("quantity", 0),
                    price=o.get("price"),
                    trigger_price=o.get("trigger_price"),
                    average_price=o.get("average_price"),
                    filled_quantity=o.get("filled_quantity", 0),
                    pending_quantity=o.get("pending_quantity", 0),
                    order_type=o.get("order_type", "MARKET"),
                    product=o.get("product", "MIS"),
                    placed_by=o.get("placed_by", ""),
                    order_timestamp=o.get("order_timestamp"),
                    exchange_timestamp=o.get("exchange_timestamp"),
                    variety=o.get("variety", "regular"),
                    validity=o.get("validity", "DAY"),
                    tag=o.get("tag")
                )
                orders.append(order)
            
            return orders
            
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []
    
    # ================================================================
    # POSITION OPERATIONS
    # ================================================================
    
    async def get_positions(self) -> List[Position]:
        """Get all positions."""
        try:
            kite_positions = await retry_async(
                lambda: self.kite.positions(),
                retryable_exceptions=KITE_API_ERRORS,
                max_retries=3,
                base_delay=1.0
            )
            
            positions = []
            
            # Net positions
            for p in kite_positions.get("net", []):
                if p.get("quantity", 0) == 0:
                    continue
                
                avg_price = p.get("average_price", 0)
                last_price = p.get("last_price", 0)
                quantity = p.get("quantity", 0)
                
                pnl = (last_price - avg_price) * quantity
                pnl_pct = ((last_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
                
                position = Position(
                    symbol=p.get("tradingsymbol", ""),
                    exchange=p.get("exchange", ""),
                    instrument_token=p.get("instrument_token", 0),
                    quantity=quantity,
                    average_price=avg_price,
                    last_price=last_price,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    product=p.get("product", "MIS"),
                    overnight_quantity=p.get("overnight_quantity", 0),
                    day_buy_quantity=p.get("day_buy_quantity", 0),
                    day_sell_quantity=p.get("day_sell_quantity", 0)
                )
                positions.append(position)
            
            return positions
            
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    async def get_position(self, symbol: str, exchange: str = "NSE") -> Optional[Position]:
        """Get position for specific symbol."""
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol and pos.exchange == exchange:
                return pos
        return None
    
    # ================================================================
    # MARGIN OPERATIONS
    # ================================================================
    
    async def get_margins(self) -> MarginInfo:
        """Get margin/funds information."""
        try:
            margins = await retry_async(
                lambda: self.kite.margins(),
                retryable_exceptions=KITE_API_ERRORS,
                max_retries=3,
                base_delay=1.0
            )
            
            equity = margins.get("equity", {})
            
            return MarginInfo(
                available_cash=equity.get("available", {}).get("cash", 0),
                available_margin=equity.get("available", {}).get("live_balance", 0),
                used_margin=equity.get("utilised", {}).get("debits", 0),
                total_balance=equity.get("net", 0),
                collateral=equity.get("available", {}).get("collateral", 0)
            )
            
        except Exception as e:
            logger.error(f"Failed to get margins: {e}")
            return MarginInfo(
                available_cash=0,
                available_margin=0,
                used_margin=0,
                total_balance=0
            )
