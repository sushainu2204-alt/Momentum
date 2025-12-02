"""
Position Manager Service

Manages positions with Kite API integration.
- Runtime: Query Kite API directly for current state
- Background: Sync Kite positions to DB periodically
"""

from typing import List, Optional, Dict
from datetime import datetime, time
import logging

from backend.core.services.kite_service import KiteService
from backend.infrastructure.database.position_repository import PositionRepository
from backend.models import Position, PositionStatus, Signal, SignalType

logger = logging.getLogger(__name__)


class PositionManager:
    """
    Manages positions with Kite API as source of truth.
    
    Runtime Flow:
    1. Check Kite API for current positions
    2. Calculate P&L from live prices
    3. Check exit conditions
    
    Background Sync:
    - Periodically fetch positions from Kite
    - Update DB with latest P&L and status
    """
    
    def __init__(
        self,
        kite_service: KiteService,
        position_repository: PositionRepository,
        exit_time: time = time(15, 20)  # 3:20 PM
    ):
        self.kite = kite_service
        self.position_repo = position_repository
        self.exit_time = exit_time
        self._position_cache = {}  # symbol -> position_data
        self._cache_timestamp = None
    
    # ================================================================
    # RUNTIME QUERIES (Real-time from Kite)
    # ================================================================
    
    async def has_position(self, symbol: str) -> bool:
        """
        Check if position exists for symbol (query Kite API).
        
        Args:
            symbol: Stock symbol
        
        Returns:
            True if position exists
        """
        try:
            kite_positions = await self._get_kite_positions_cached()
            
            for pos in kite_positions:
                if pos['tradingsymbol'] == symbol and pos['quantity'] != 0:
                    logger.debug(f"Position found: {symbol} - Qty: {pos['quantity']}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking position for {symbol}: {e}")
            # Fallback to DB
            db_pos = await self.position_repo.get_position_by_symbol(symbol, status="OPEN")
            return db_pos is not None
    
    async def get_open_positions(self) -> List[Dict]:
        """
        Get all open positions (from Kite API).
        
        Returns:
            List of position dicts with P&L
        """
        try:
            kite_positions = await self._get_kite_positions_cached()
            
            open_positions = []
            for pos in kite_positions:
                if pos['quantity'] != 0:
                    open_positions.append(pos)
            
            return open_positions
            
        except Exception as e:
            logger.error(f"Error fetching open positions: {e}")
            # Fallback to DB
            return await self.position_repo.get_open_positions()
    
    async def get_open_positions_count(self) -> int:
        """
        Count open positions (from Kite API).
        
        Returns:
            Number of open positions
        """
        try:
            positions = await self.get_open_positions()
            return len(positions)
        except Exception as e:
            logger.error(f"Error counting open positions: {e}")
            return await self.position_repo.get_open_positions_count()
    
    async def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position for symbol from Kite"""
        try:
            kite_positions = await self._get_kite_positions_cached()
            
            for pos in kite_positions:
                if pos['tradingsymbol'] == symbol and pos['quantity'] != 0:
                    return pos
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching position for {symbol}: {e}")
            return None
    
    # ================================================================
    # POSITION CREATION (after order fill)
    # ================================================================
    
    async def create_position_record(
        self,
        symbol: str,
        instrument_token: int,
        strategy_name: str,
        entry_price: float,
        quantity: int,
        stop_loss: float,
        target: float,
        signal_id: Optional[int] = None,
        entry_order_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Create position record in DB (for audit/history).
        Called after order is filled.
        
        Returns:
            Position ID
        """
        position_id = await self.position_repo.create_position(
            symbol=symbol,
            instrument_token=instrument_token,
            strategy_name=strategy_name,
            entry_price=entry_price,
            entry_time=datetime.now(),
            quantity=quantity,
            stop_loss=stop_loss,
            target=target,
            signal_id=signal_id,
            entry_order_id=entry_order_id,
            metadata=metadata
        )
        
        self._invalidate_cache()
        
        logger.info(
            f"Position record created: {symbol} @ ₹{entry_price:.2f}, "
            f"Qty: {quantity}, SL: ₹{stop_loss:.2f}, Target: ₹{target:.2f}"
        )
        
        return position_id
    
    # ================================================================
    # POSITION CLOSING
    # ================================================================
    # NOTE: SL/Target exits are now handled automatically by exchange via bracket orders
    # Only EOD exits need manual handling (done in sync_jobs.py)
    
    async def close_position_record(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str,
        exit_order_id: Optional[str] = None
    ):
        """
        Close position record in DB.
        
        Args:
            symbol: Stock symbol
            exit_price: Exit price
            exit_reason: Reason for exit
            exit_order_id: Kite order ID for exit
        """
        try:
            # Get open position from DB
            db_pos = await self.position_repo.get_position_by_symbol(symbol, status="OPEN")
            
            if not db_pos:
                logger.warning(f"No open position found for {symbol}")
                return
            
            # Close position
            await self.position_repo.close_position(
                position_id=db_pos['id'],
                exit_price=exit_price,
                exit_time=datetime.now(),
                exit_reason=exit_reason,
                exit_order_id=exit_order_id
            )
            
            self._invalidate_cache()
            
            logger.info(f"Position closed in DB: {symbol} @ ₹{exit_price:.2f}")
            
        except Exception as e:
            logger.error(f"Error closing position record for {symbol}: {e}")
    
    # ================================================================
    # BACKGROUND SYNC (Kite → DB)
    # ================================================================
    
    async def sync_positions_from_kite(self) -> int:
        """
        Background job: Sync all positions from Kite to DB.
        Updates P&L and closes positions that are closed in Kite.
        
        Returns:
            Number of positions synced
        """
        try:
            logger.debug("Syncing positions from Kite...")
            
            # Fetch positions from Kite
            kite_data = self.kite.kite.positions()
            kite_positions = kite_data.get('day', [])
            
            # Get open positions from DB
            db_positions = await self.position_repo.get_open_positions()
            
            synced_count = 0
            
            # Update existing positions
            for db_pos in db_positions:
                symbol = db_pos['symbol']
                
                # Find corresponding Kite position
                kite_pos = next(
                    (p for p in kite_positions if p['tradingsymbol'] == symbol),
                    None
                )
                
                if kite_pos and kite_pos['quantity'] != 0:
                    # Position still open - update P&L
                    current_price = kite_pos['last_price']
                    pnl = kite_pos['pnl']
                    
                    # Calculate P&L percentage
                    entry_price = db_pos['entry_price']
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                    
                    await self.position_repo.update_position(
                        position_id=db_pos['id'],
                        current_price=current_price,
                        pnl=pnl,
                        pnl_pct=pnl_pct
                    )
                    
                    synced_count += 1
                    
                else:
                    # Position closed in Kite but still open in DB
                    # Determine exit reason based on last known price
                    #TODO : Is this right? Are we sure we want to use last known price from DB?
                    logger.info(
                        f"Position {symbol} closed in Kite - detecting exit reason and closing DB record"
                    )
                    
                    # Use last known price from DB
                    exit_price = db_pos['current_price'] or db_pos['entry_price']
                    
                    # Detect exit reason by comparing with SL/Target
                    exit_reason = self._detect_exit_reason(
                        exit_price=exit_price,
                        entry_price=db_pos['entry_price'],
                        stop_loss=db_pos['stop_loss'],
                        target=db_pos['target']
                    )
                    
                    logger.info(
                        f"Closing position {symbol}: "
                        f"Entry=₹{db_pos['entry_price']:.2f}, "
                        f"Exit=₹{exit_price:.2f}, "
                        f"Reason={exit_reason}"
                    )
                    
                    # Close position in DB
                    await self.position_repo.close_position(
                        position_id=db_pos['id'],
                        exit_price=exit_price,
                        exit_time=datetime.now(),
                        exit_reason=exit_reason
                    )
                    
                    synced_count += 1
            
            self._invalidate_cache()
            logger.info(f"Positions synced: {synced_count} updated")
            
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing positions from Kite: {e}", exc_info=True)
            return 0
    
    # ================================================================
    # KITE API WRAPPERS
    # ================================================================
    
    async def _get_kite_positions_cached(self, cache_ttl: float = 0.5) -> List[Dict]:
        """
        Get positions with short cache to reduce API calls while preventing duplicates.
        
        Args:
            cache_ttl: Cache time-to-live in seconds (default 0.5s for fast trading)
        """
        now = datetime.now()
        
        # Use cache if less than cache_ttl seconds old
        if self._cache_timestamp and (now - self._cache_timestamp).total_seconds() < cache_ttl:
            return list(self._position_cache.values())
        
        # Fetch fresh from Kite
        try:
            positions_data = self.kite.kite.positions()
            positions = positions_data.get('day', [])
            
            self._position_cache = {p['tradingsymbol']: p for p in positions if p['quantity'] != 0}
            self._cache_timestamp = now
            
            return positions
            
        except Exception as e:
            logger.error(f"Failed to fetch positions from Kite: {e}")
            return list(self._position_cache.values())  # Return stale cache
    
    def _invalidate_cache(self):
        """Clear position cache"""
        self._cache_timestamp = None
    
    def _detect_exit_reason(
        self,
        exit_price: float,
        entry_price: float,
        stop_loss: float,
        target: float
    ) -> str:
        """
        Detect exit reason based on exit price relative to SL/Target.
        
        Args:
            exit_price: Price at which position was closed
            entry_price: Original entry price
            stop_loss: Stop loss price
            target: Target price
        
        Returns:
            Exit reason: SL_HIT, TARGET_HIT, TIME_EXIT, or MANUAL_EXIT
        """
        # Define tolerance (±0.5% to account for slippage)
        sl_tolerance = abs(stop_loss - entry_price) * 0.05
        target_tolerance = abs(target - entry_price) * 0.05
        
        # Check if exit price is near stop loss
        if abs(exit_price - stop_loss) <= sl_tolerance:
            return "SL_HIT"
        
        # Check if exit price is near target
        if abs(exit_price - target) <= target_tolerance:
            return "TARGET_HIT"
        
        # Check current time for time-based exit
        current_time = datetime.now().time()
        exit_time = time(15, 15)  # 3:15 PM
        
        if current_time >= exit_time:
            return "TIME_EXIT"
        
        # Otherwise, assume manual exit
        return "MANUAL_EXIT"
    
    # ================================================================
    # STATISTICS
    # ================================================================
    
    async def get_daily_stats(self) -> Dict:
        """Get today's position statistics from DB"""
        from datetime import date
        
        stats = await self.position_repo.get_daily_stats(date.today())
        return stats or {}
    
    async def get_total_pnl(self) -> float:
        """Get total P&L from open positions (Kite)"""
        try:
            positions = await self.get_open_positions()
            total_pnl = sum(p.get('pnl', 0) for p in positions)
            return total_pnl
        except Exception as e:
            logger.error(f"Error calculating total P&L: {e}")
            return 0.0
