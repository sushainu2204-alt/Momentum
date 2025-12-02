"""
Position Repository

Database operations for positions table.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date
import logging

from .base import IDatabase
from backend.models import Position, PositionStatus

logger = logging.getLogger(__name__)


class PositionRepository:
    """Repository for positions table"""
    
    def __init__(self, database: IDatabase):
        self.db = database
    
    async def create_position(
        self,
        symbol: str,
        instrument_token: int,
        strategy_name: str,
        entry_price: float,
        entry_time: datetime,
        quantity: int,
        stop_loss: float,
        target: float,
        signal_id: Optional[int] = None,
        entry_order_id: Optional[str] = None,
        sl_order_id: Optional[str] = None,
        target_order_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Create new position.
        
        Returns:
            Position ID
        """
        data = {
            "symbol": symbol,
            "instrument_token": instrument_token,
            "strategy_name": strategy_name,
            "entry_price": entry_price,
            "entry_time": entry_time,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "target": target,
            "current_price": entry_price,
            "highest_price": entry_price,  # Initialize highest_price to entry
            "status": PositionStatus.OPEN.value,
            "signal_id": signal_id,
            "entry_order_id": entry_order_id,
            "sl_order_id": sl_order_id,
            "target_order_id": target_order_id,
            "metadata": metadata or {}
        }
        
        position_id = await self.db.insert("positions", data)
        logger.info(f"Position created: {symbol} @ {entry_price}, ID={position_id}")
        
        return position_id
    
    async def update_position(
        self,
        position_id: int,
        current_price: Optional[float] = None,
        pnl: Optional[float] = None,
        pnl_pct: Optional[float] = None,
        status: Optional[PositionStatus] = None,
        exit_price: Optional[float] = None,
        exit_time: Optional[datetime] = None,
        exit_reason: Optional[str] = None,
        exit_order_id: Optional[str] = None,
        # Trailing SL fields
        stop_loss: Optional[float] = None,
        original_stop_loss: Optional[float] = None,
        highest_price: Optional[float] = None,
        sl_order_id: Optional[str] = None,
        target_order_id: Optional[str] = None
    ):
        """Update position fields"""
        updates = {}
        
        if current_price is not None:
            updates["current_price"] = current_price
        if pnl is not None:
            updates["pnl"] = pnl
        if pnl_pct is not None:
            updates["pnl_pct"] = pnl_pct
        if status is not None:
            updates["status"] = status.value
        if exit_price is not None:
            updates["exit_price"] = exit_price
        if exit_time is not None:
            updates["exit_time"] = exit_time
        if exit_reason is not None:
            updates["exit_reason"] = exit_reason
        if exit_order_id is not None:
            updates["exit_order_id"] = exit_order_id
        # Trailing SL fields
        if stop_loss is not None:
            updates["stop_loss"] = stop_loss
        if original_stop_loss is not None:
            updates["original_stop_loss"] = original_stop_loss
        if highest_price is not None:
            updates["highest_price"] = highest_price
        if sl_order_id is not None:
            updates["sl_order_id"] = sl_order_id
        if target_order_id is not None:
            updates["target_order_id"] = target_order_id
        
        if updates:
            await self.db.update(
                "positions",
                updates,
                {"id": position_id}
            )
    
    async def update_trailing_stop_loss(
        self,
        position_id: int,
        new_stop_loss: float,
        highest_price: float,
        original_stop_loss: Optional[float] = None
    ):
        """
        Update trailing stop loss for a position.
        
        Args:
            position_id: Position ID
            new_stop_loss: New (higher) stop loss price
            highest_price: Current highest price reached
            original_stop_loss: Original SL (set only on first trail)
        """
        updates = {
            "stop_loss": new_stop_loss,
            "highest_price": highest_price
        }
        
        # Set original_stop_loss only if provided (first time trailing)
        if original_stop_loss is not None:
            updates["original_stop_loss"] = original_stop_loss
        
        await self.db.update(
            "positions",
            updates,
            {"id": position_id}
        )
        
        logger.info(
            f"Trailing SL updated: Position {position_id}, "
            f"New SL: ₹{new_stop_loss:.2f}, Highest: ₹{highest_price:.2f}"
        )
    
    async def get_position(self, position_id: int) -> Optional[Dict]:
        """Get position by ID"""
        result = await self.db.fetch_one(
            "SELECT * FROM positions WHERE id = :id",
            {"id": position_id}
        )
        return result
    
    async def get_open_positions(
        self,
        strategy_name: Optional[str] = None
    ) -> List[Dict]:
        """Get all open positions"""
        query = "SELECT * FROM positions WHERE status = 'OPEN'"
        params = {}
        
        if strategy_name:
            query += " AND strategy_name = :strategy_name"
            params["strategy_name"] = strategy_name
        
        query += " ORDER BY entry_time DESC"
        
        return await self.db.fetch_all(query, params)
    
    async def get_position_by_symbol(
        self,
        symbol: str,
        status: str = "OPEN"
    ) -> Optional[Dict]:
        """Get position for symbol"""
        result = await self.db.fetch_one(
            "SELECT * FROM positions WHERE symbol = :symbol AND status = :status",
            {"symbol": symbol, "status": status}
        )
        return result
    
    async def get_positions_by_date(
        self,
        date: date,
        strategy_name: Optional[str] = None
    ) -> List[Dict]:
        """Get all positions for a date"""
        query = "SELECT * FROM positions WHERE DATE(entry_time) = :date"
        params = {"date": date}
        
        if strategy_name:
            query += " AND strategy_name = :strategy_name"
            params["strategy_name"] = strategy_name
        
        query += " ORDER BY entry_time DESC"
        
        return await self.db.fetch_all(query, params)
    
    async def get_open_positions_count(
        self,
        strategy_name: Optional[str] = None
    ) -> int:
        """Count open positions"""
        query = "SELECT COUNT(*) as count FROM positions WHERE status = 'OPEN'"
        params = {}
        
        if strategy_name:
            query += " AND strategy_name = :strategy_name"
            params["strategy_name"] = strategy_name
        
        result = await self.db.fetch_one(query, params)
        return result["count"] if result else 0
    
    async def close_position(
        self,
        position_id: int,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str,
        exit_order_id: Optional[str] = None
    ):
        """Close position"""
        # Get position to calculate P&L
        position = await self.get_position(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")
        
        # Calculate P&L
        pnl = (exit_price - position["entry_price"]) * position["quantity"]
        pnl_pct = ((exit_price - position["entry_price"]) / position["entry_price"]) * 100
        
        # Determine status from reason
        status_map = {
            "SL_HIT": PositionStatus.SL_HIT,
            "TARGET_HIT": PositionStatus.TARGET_HIT,
            "TIME_EXIT": PositionStatus.TIME_EXIT,
            "MANUAL_EXIT": PositionStatus.MANUAL_EXIT
        }
        status = status_map.get(exit_reason, PositionStatus.MANUAL_EXIT)
        
        # Update position
        await self.update_position(
            position_id,
            exit_price=exit_price,
            exit_time=exit_time,
            exit_reason=exit_reason,
            exit_order_id=exit_order_id,
            current_price=exit_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            status=status
        )
        
        logger.info(
            f"Position closed: {position['symbol']} @ {exit_price}, "
            f"P&L: {pnl:.2f} ({pnl_pct:.2f}%), Reason: {exit_reason}"
        )
    
    async def get_daily_stats(
        self,
        date: date,
        strategy_name: Optional[str] = None
    ) -> Dict:
        """Get daily statistics"""
        query = """
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winners,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losers,
                SUM(pnl) as total_pnl,
                AVG(pnl) as avg_pnl,
                AVG(pnl_pct) as avg_pnl_pct,
                MAX(pnl) as max_win,
                MIN(pnl) as max_loss
            FROM positions
            WHERE DATE(entry_time) = :date
            AND status IN ('TARGET_HIT', 'SL_HIT', 'TIME_EXIT', 'MANUAL_EXIT')
        """
        params = {"date": date}
        
        if strategy_name:
            query += " AND strategy_name = :strategy_name"
            params["strategy_name"] = strategy_name
        
        result = await self.db.fetch_one(query, params)
        return result or {}
