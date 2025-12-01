"""
Order Repository

Database operations for orders table.
"""

from typing import List, Optional, Dict
from datetime import datetime
import logging

from .base import IDatabase

logger = logging.getLogger(__name__)


class OrderRepository:
    """Repository for orders table"""
    
    def __init__(self, database: IDatabase):
        self.db = database
    
    async def create_order(
        self,
        order_id: str,
        symbol: str,
        instrument_token: int,
        strategy_name: str,
        order_type: str,
        transaction_type: str,
        quantity: int,
        price: Optional[float],
        trigger_price: Optional[float],
        status: str,
        placed_at: datetime,
        position_id: Optional[int] = None,
        signal_id: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Create new order record.
        
        Returns:
            Order record ID
        """
        data = {
            "order_id": order_id,
            "symbol": symbol,
            "instrument_token": instrument_token,
            "strategy_name": strategy_name,
            "order_type": order_type,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "price": price,
            "trigger_price": trigger_price,
            "status": status,
            "placed_at": placed_at,
            "position_id": position_id,
            "signal_id": signal_id,
            "metadata": metadata or {}
        }
        
        record_id = await self.db.insert("orders", data)
        logger.info(f"Order created: {order_id} - {transaction_type} {symbol} x {quantity}")
        
        return record_id
    
    async def update_order(
        self,
        order_id: str,
        status: Optional[str] = None,
        status_message: Optional[str] = None,
        filled_quantity: Optional[int] = None,
        average_price: Optional[float] = None,
        filled_at: Optional[datetime] = None
    ):
        """Update order status"""
        updates = {}
        
        if status is not None:
            updates["status"] = status
        if status_message is not None:
            updates["status_message"] = status_message
        if filled_quantity is not None:
            updates["filled_quantity"] = filled_quantity
        if average_price is not None:
            updates["average_price"] = average_price
        if filled_at is not None:
            updates["filled_at"] = filled_at
        
        if updates:
            await self.db.update(
                "orders",
                updates,
                {"order_id": order_id}
            )
            logger.debug(f"Order updated: {order_id}, status={status}")
    
    async def get_order(self, order_id: str) -> Optional[Dict]:
        """Get order by Kite order ID"""
        result = await self.db.fetch_one(
            "SELECT * FROM orders WHERE order_id = :order_id",
            {"order_id": order_id}
        )
        return result
    
    async def get_pending_orders(
        self,
        symbol: Optional[str] = None,
        strategy_name: Optional[str] = None
    ) -> List[Dict]:
        """Get pending orders"""
        query = "SELECT * FROM orders WHERE status IN ('PENDING', 'OPEN')"
        params = {}
        
        if symbol:
            query += " AND symbol = :symbol"
            params["symbol"] = symbol
        
        if strategy_name:
            query += " AND strategy_name = :strategy_name"
            params["strategy_name"] = strategy_name
        
        query += " ORDER BY placed_at DESC"
        
        return await self.db.fetch_all(query, params)
    
    async def has_pending_order(
        self,
        symbol: str,
        transaction_type: Optional[str] = None
    ) -> bool:
        """Check if symbol has pending order"""
        query = "SELECT COUNT(*) as count FROM orders WHERE symbol = :symbol AND status IN ('PENDING', 'OPEN')"
        params = {"symbol": symbol}
        
        if transaction_type:
            query += " AND transaction_type = :transaction_type"
            params["transaction_type"] = transaction_type
        
        result = await self.db.fetch_one(query, params)
        return result["count"] > 0 if result else False
    
    async def get_orders_by_position(self, position_id: int) -> List[Dict]:
        """Get all orders for a position"""
        return await self.db.fetch_all(
            "SELECT * FROM orders WHERE position_id = :position_id ORDER BY placed_at",
            {"position_id": position_id}
        )
    
    async def get_todays_orders(
        self,
        strategy_name: Optional[str] = None
    ) -> List[Dict]:
        """Get today's orders"""
        query = "SELECT * FROM orders WHERE DATE(placed_at) = CURRENT_DATE"
        params = {}
        
        if strategy_name:
            query += " AND strategy_name = :strategy_name"
            params["strategy_name"] = strategy_name
        
        query += " ORDER BY placed_at DESC"
        
        return await self.db.fetch_all(query, params)
