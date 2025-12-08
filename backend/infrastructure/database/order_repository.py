"""
Order Repository

Database operations for orders table.
Also saves orders to JSON files for backup/audit.
"""

from typing import List, Optional, Dict
from datetime import datetime
from pathlib import Path
import logging
import json
import aiofiles

from .base import IDatabase

logger = logging.getLogger(__name__)


class OrderRepository:
    """Repository for orders table"""
    
    def __init__(self, database: IDatabase, orders_file_path: Optional[Path] = None):
        self.db = database
        # Default to backend/data/orders directory (relative to project root)
        # This ensures it works both locally and in Docker containers
        if orders_file_path:
            self.orders_path = orders_file_path
        else:
            # Get the backend directory (parent of infrastructure)
            backend_dir = Path(__file__).parent.parent.parent
            self.orders_path = backend_dir / "data" / "orders"
        self.orders_path.mkdir(parents=True, exist_ok=True)
    
    # ================================================================
    # FILE STORAGE (Backup/Audit)
    # ================================================================
    
    async def _save_order_to_file(
        self,
        order_data: Dict,
        strategy_name: str,
        date: datetime
    ):
        """
        Save order to JSON file for backup/audit.
        
        File structure: data/orders/{date}/{strategy}_orders.json
        """
        try:
            date_str = date.strftime("%Y-%m-%d")
            date_dir = self.orders_path / date_str
            date_dir.mkdir(parents=True, exist_ok=True)
            
            filename = f"{strategy_name}_orders.json"
            filepath = date_dir / filename
            
            # Load existing orders
            orders = []
            if filepath.exists():
                async with aiofiles.open(filepath, 'r') as f:
                    content = await f.read()
                    if content.strip():
                        orders = json.loads(content)
            
            # Check if order already exists (update vs create)
            order_id = order_data.get("order_id")
            existing_idx = next(
                (i for i, o in enumerate(orders) if o.get("order_id") == order_id),
                None
            )
            
            if existing_idx is not None:
                # Update existing order
                orders[existing_idx].update(order_data)
            else:
                # Append new order
                orders.append(order_data)
            
            # Save to file
            async with aiofiles.open(filepath, 'w') as f:
                await f.write(json.dumps(orders, indent=2, default=str))
            
            logger.debug(f"Order saved to file: {filepath}")
            
        except Exception as e:
            # Don't fail the DB operation if file save fails
            logger.warning(f"Failed to save order to file: {e}")
    
    # ================================================================
    # DB OPERATIONS
    # ================================================================
    
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
        Create new order record in DB and save to file.
        
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
        
        # Save to DB
        record_id = await self.db.insert("orders", data)
        logger.info(f"Order created: {order_id} - {transaction_type} {symbol} x {quantity}")
        
        # Save to file (non-blocking, don't fail if this fails)
        file_data = {
            "order_id": order_id,
            "symbol": symbol,
            "instrument_token": instrument_token,
            "order_type": order_type,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "price": price,
            "trigger_price": trigger_price,
            "status": status,
            "placed_at": placed_at.isoformat() if placed_at else None,
            "metadata": metadata or {}
        }
        await self._save_order_to_file(file_data, strategy_name, placed_at)
        
        return record_id
    
    async def update_order(
        self,
        order_id: str,
        status: Optional[str] = None,
        status_message: Optional[str] = None,
        filled_quantity: Optional[int] = None,
        average_price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        filled_at: Optional[datetime] = None
    ):
        """Update order status in DB and file"""
        updates = {}
        
        if status is not None:
            updates["status"] = status
        if status_message is not None:
            updates["status_message"] = status_message
        if filled_quantity is not None:
            updates["filled_quantity"] = filled_quantity
        if average_price is not None:
            updates["average_price"] = average_price
        if trigger_price is not None:
            updates["trigger_price"] = trigger_price
        if filled_at is not None:
            updates["filled_at"] = filled_at
        
        if updates:
            # Update DB
            await self.db.update(
                "orders",
                updates,
                {"order_id": order_id}
            )
            logger.debug(f"Order updated: {order_id}, status={status}")
            
            # Update file - fetch full order first to get strategy_name and date
            order = await self.get_order(order_id)
            if order:
                file_updates = {
                    "order_id": order_id,
                    "status": status,
                    "status_message": status_message,
                    "filled_quantity": filled_quantity,
                    "average_price": average_price,
                    "filled_at": filled_at.isoformat() if filled_at else None,
                    "updated_at": datetime.now().isoformat()
                }
                # Remove None values
                file_updates = {k: v for k, v in file_updates.items() if v is not None}
                
                strategy_name = order.get("strategy_name", "unknown")
                placed_at = order.get("placed_at", datetime.now())
                await self._save_order_to_file(file_updates, strategy_name, placed_at)
    
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
    
    async def get_orders_by_symbol(
        self,
        symbol: str,
        status: Optional[str] = None
    ) -> List[Dict]:
        """
        Get all orders for a symbol (for linking positions to orders).
        
        Args:
            symbol: Stock symbol
            status: Optional status filter
        
        Returns:
            List of orders ordered by placed_at descending (most recent first)
        """
        query = "SELECT * FROM orders WHERE symbol = :symbol"
        params = {"symbol": symbol}
        
        if status:
            query += " AND status = :status"
            params["status"] = status
        
        query += " ORDER BY placed_at DESC"
        
        return await self.db.fetch_all(query, params)
    
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

    # ================================================================
    # MODIFICATION COUNT METHODS (for SL order tracking)
    # ================================================================
    
    async def get_modification_count(self, order_id: str) -> int:
        """
        Get modification count for an order.
        
        Args:
            order_id: Kite order ID
            
        Returns:
            Current modification count (0 if order not found)
        """
        result = await self.db.fetch_one(
            "SELECT modification_count FROM orders WHERE order_id = :order_id",
            {"order_id": order_id}
        )
        return result["modification_count"] if result else 0
    
    async def increment_modification_count(self, order_id: str) -> int:
        """
        Increment modification count for an order.
        
        Note: trigger_price is synced from Kite via sync_orders_from_kite(),
        this only tracks the modification count.
        
        Args:
            order_id: Kite order ID
            
        Returns:
            New modification count
        """
        await self.db.execute(
            "UPDATE orders SET modification_count = modification_count + 1 WHERE order_id = :order_id",
            {"order_id": order_id}
        )
        
        # Get new value
        result = await self.db.fetch_one(
            "SELECT modification_count FROM orders WHERE order_id = :order_id",
            {"order_id": order_id}
        )
        new_count = result["modification_count"] if result else 0
        
        logger.debug(f"Order {order_id} modification count incremented to {new_count}")
        return new_count
    
    async def reset_modification_count(self, order_id: str):
        """
        Reset modification count for a new order (when SL is recreated).
        
        Args:
            order_id: Kite order ID
        """
        await self.db.update(
            "orders",
            {"modification_count": 0},
            {"order_id": order_id}
        )
        logger.debug(f"Order {order_id} modification count reset to 0")