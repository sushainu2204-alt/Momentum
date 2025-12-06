"""
Trailing Stop Loss Service

Monitors positions and updates stop loss as price moves favorably.
This service implements a trailing stop loss mechanism that:
1. Tracks the highest price reached for each position
2. When price moves up by a threshold, moves the SL up
3. Modifies the SL order on Kite to reflect the new stop loss

IMPORTANT (Post-2020 Zerodha):
- Bracket Orders are DISCONTINUED
- We use Regular Orders + Separate SL-M Orders
- SL-M orders can be modified up to 25 times
- After ~20 modifications, we cancel and recreate the SL order
"""

from typing import Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime
import logging

from backend.infrastructure.database.position_repository import PositionRepository
from backend.infrastructure.database.order_repository import OrderRepository
from backend.core.services.market.kite_service import KiteService

# Avoid circular import
if TYPE_CHECKING:
    from backend.core.services.trading.order_manager import OrderManager

logger = logging.getLogger(__name__)


@dataclass
class TrailingStopLossConfig:
    """Configuration for trailing stop loss"""
    
    # Enable trailing stop loss
    enabled: bool = True
    
    # Minimum profit % before trailing starts (e.g., 0.5 = start trailing after 0.5% profit)
    activation_pct: float = 0.5
    
    # Trail distance as % of entry price (e.g., 0.3 = SL trails 0.3% below highest price)
    trail_pct: float = 0.3
    
    # Minimum SL move increment (to avoid too frequent updates)
    min_sl_move_pct: float = 0.1


class TrailingStopLossService:
    """
    Service to manage trailing stop losses for open positions.
    
    How it works:
    1. For each open position, track the highest price reached
    2. When current_price > highest_price, update highest_price
    3. If position is in profit by activation_pct, start trailing
    4. New SL = highest_price * (1 - trail_pct/100)
    5. Only update if new SL > current SL (never move SL down)
    6. Modify the SL order on Kite
    
    IMPORTANT: Zerodha allows max 25 modifications per order.
    After ~20 modifications, the order is cancelled and recreated.
    
    Example:
        Entry: ₹100, Initial SL: ₹98 (2% SL)
        Config: activation_pct=0.5%, trail_pct=0.3%
        
        Price moves to ₹101 (+1%):
        - Profit 1% > activation 0.5%, trailing active
        - New SL = 101 * (1 - 0.3/100) = ₹100.70
        - SL moved from ₹98 to ₹100.70 (locked in profit!)
        
        Price moves to ₹102:
        - New SL = 102 * 0.997 = ₹101.69
        - SL moved up again
    """
    
    def __init__(
        self,
        position_repository: PositionRepository,
        kite_service: KiteService,
        order_repository: Optional[OrderRepository] = None,
        order_manager: Optional["OrderManager"] = None,
        config: Optional[TrailingStopLossConfig] = None
    ):
        self.position_repo = position_repository
        self.order_repo = order_repository
        self.kite = kite_service
        self.order_manager = order_manager
        self.config = config or TrailingStopLossConfig()
    
    async def process_positions(self) -> Dict[str, int]:
        """
        Process all open positions and update trailing stop losses.
        
        HYBRID APPROACH:
        - Positions: Read from Kite (source of truth for what's actually open)
        - Tracking data (highest_price, sl_order_id): Read from DB
        - SL modifications: Write to Kite
        
        IMPORTANT: Kite does NOT provide position IDs!
        Kite identifies positions by (tradingsymbol + exchange + product).
        Multiple orders for same symbol are AGGREGATED into one position.
        
        MATCHING: We match by symbol. If DB has no matching record, skip that position.
        
        Returns:
            Dict with counts: {"checked": N, "updated": N, "errors": N, "not_in_db": N}
        """
        if not self.config.enabled:
            logger.debug("Trailing SL disabled, skipping")
            return {"checked": 0, "updated": 0, "errors": 0, "not_in_db": 0}
        
        stats = {"checked": 0, "updated": 0, "errors": 0, "not_in_db": 0}
        
        try:
            # Get LIVE positions from Kite (source of truth)
            kite_positions = self._get_kite_positions()
            
            # Filter for open positions (quantity != 0)
            open_kite_positions = [p for p in kite_positions if p['quantity'] != 0]
            
            if not open_kite_positions:
                logger.debug("No open positions in Kite to process for trailing SL")
                return stats
            
            logger.debug(f"Processing {len(open_kite_positions)} positions from Kite for trailing SL")
            
            for kite_pos in open_kite_positions:
                symbol = kite_pos['tradingsymbol']
                current_price = kite_pos['last_price']
                stats["checked"] += 1
                
                try:
                    # Get corresponding DB position by symbol
                    # Note: Kite aggregates all orders for same symbol+product into ONE position
                    # So we only need to match by symbol
                    db_position = await self.position_repo.get_position_by_symbol(symbol, status="OPEN")
                    
                    if not db_position:
                        # Position in Kite but not in DB - needs sync
                        logger.warning(
                            f"{symbol}: Position in Kite but not in DB - run sync_positions_from_kite()"
                        )
                        stats["not_in_db"] += 1
                        continue
                    
                    # Process with combined data: live price from Kite + tracking from DB
                    result = await self._process_single_position(db_position, current_price)
                    if result:
                        stats["updated"] += 1
                        
                except Exception as e:
                    logger.error(f"Error processing trailing SL for {symbol}: {e}")
                    stats["errors"] += 1
            
            if stats["updated"] > 0 or stats["not_in_db"] > 0:
                logger.info(
                    f"Trailing SL: Checked {stats['checked']}, "
                    f"Updated {stats['updated']}, Not in DB {stats['not_in_db']}, "
                    f"Errors {stats['errors']}"
                )
            
            return stats
            
        except Exception as e:
            logger.error(f"Error in trailing SL processing: {e}", exc_info=True)
            return stats
    
    async def _process_single_position(
        self,
        position: Dict,
        current_price: float
    ) -> bool:
        """
        Process trailing SL for a single position.
        
        Args:
            position: DB position record (has highest_price, sl_order_id, etc.)
            current_price: Live price from Kite
        
        DB operations (optimized):
        - 1 write only when SL is actually updated (includes highest_price)
        - 1 write if SL order is recreated (new order ID)
        
        Returns:
            True if SL was updated, False otherwise
        """
        symbol = position['symbol']
        position_id = position['id']
        entry_price = float(position['entry_price'])
        current_sl = float(position['stop_loss'])
        
        # Get highest_price from DB (essential persistent state for trailing)
        highest_price = float(position.get('highest_price') or entry_price)
        
        # Track if highest_price changed (for single batched DB write)
        highest_price_updated = False
        if current_price > highest_price:
            highest_price = current_price
            highest_price_updated = True
        
        # Check if we should trail (based on current profit)
        profit_pct = ((current_price - entry_price) / entry_price) * 100
        
        if profit_pct < self.config.activation_pct:
            # Not trailing yet, but still persist highest_price if it changed
            if highest_price_updated:
                await self.position_repo.update_position(
                    position_id=position_id,
                    highest_price=highest_price
                )
            logger.debug(
                f"{symbol}: Profit {profit_pct:.2f}% < activation {self.config.activation_pct}%, "
                f"not trailing yet"
            )
            return False
        
        # Calculate new trailing SL based on highest price reached
        new_sl = highest_price * (1 - self.config.trail_pct / 100)
        
        # Only update if new SL is higher than current SL (never move down)
        if new_sl <= current_sl:
            logger.debug(
                f"{symbol}: New SL ₹{new_sl:.2f} <= current SL ₹{current_sl:.2f}, no update"
            )
            return False
        
        # Check minimum move threshold (avoid excessive Kite API calls)
        sl_move_pct = ((new_sl - current_sl) / entry_price) * 100
        if sl_move_pct < self.config.min_sl_move_pct:
            logger.debug(
                f"{symbol}: SL move {sl_move_pct:.2f}% < min {self.config.min_sl_move_pct}%, skipping"
            )
            return False
        
        # Determine original SL (for record keeping on first trail)
        original_sl = position.get('original_stop_loss')
        is_first_trail = original_sl is None
        if is_first_trail:
            original_sl = current_sl
        
        # === SINGLE DB WRITE: Update SL + highest_price together ===
        await self.position_repo.update_trailing_stop_loss(
            position_id=position_id,
            new_stop_loss=round(new_sl, 2),
            highest_price=highest_price,
            original_stop_loss=original_sl if is_first_trail else None
        )
        
        # Modify SL order on Kite (if we have the order ID)
        sl_order_id = position.get('sl_order_id')
        if sl_order_id:
            new_order_id = await self._modify_sl_order_on_kite(
                sl_order_id, new_sl, position, position_id
            )
            # If order was recreated, update position with new order ID
            if new_order_id and new_order_id != sl_order_id:
                await self.position_repo.update_position(
                    position_id=position_id,
                    sl_order_id=new_order_id
                )
        else:
            logger.warning(
                f"{symbol}: No SL order ID stored, can't modify order on Kite. "
                f"DB updated but Kite order unchanged."
            )
        
        logger.info(
            f"📈 TRAILING SL: {symbol} - "
            f"Entry: ₹{entry_price:.2f}, High: ₹{highest_price:.2f}, "
            f"SL: ₹{current_sl:.2f} → ₹{new_sl:.2f} (+{sl_move_pct:.2f}%)"
        )
        
        return True
    
    async def _modify_sl_order_on_kite(
        self,
        sl_order_id: str,
        new_trigger_price: float,
        position: Dict,
        position_id: int
    ) -> Optional[str]:
        """
        Modify the SL order on Kite with new trigger price.
        
        Uses OrderManager which handles:
        - Regular order modification
        - Order recreation when modification limit (25) is reached
        
        Modification count is tracked on the ORDER, not the position.
        When order is recreated, new order starts at modification_count=0.
        
        Returns:
            New order ID if order was recreated, else None
        """
        try:
            # Get current modification count from the ORDER (not position)
            sl_modification_count = 0
            if self.order_repo:
                sl_modification_count = await self.order_repo.get_modification_count(sl_order_id)
            
            if self.order_manager:
                # Use OrderManager for proper handling of modification limits
                success, new_order_id = await self.order_manager.modify_sl_order(
                    order_id=sl_order_id,
                    new_trigger_price=new_trigger_price,
                    modification_count=sl_modification_count
                )
                
                if success:
                    if new_order_id:
                        # Order was recreated - new order starts at count=0 (by default)
                        # Update position to point to new SL order
                        await self.position_repo.update_position(
                            position_id=position_id,
                            sl_order_id=new_order_id
                        )
                        logger.info(f"✅ SL order recreated: {sl_order_id} -> {new_order_id}")
                        return new_order_id
                    else:
                        # Order was modified, increment count on the ORDER
                        # Note: trigger_price is synced from Kite via sync_orders_from_kite()
                        if self.order_repo:
                            new_count = await self.order_repo.increment_modification_count(sl_order_id)
                            logger.info(
                                f"✅ SL order modified on Kite: {sl_order_id} -> ₹{new_trigger_price:.2f} "
                                f"(mod #{new_count})"
                            )
                        else:
                            logger.info(
                                f"✅ SL order modified on Kite: {sl_order_id} -> ₹{new_trigger_price:.2f}"
                            )
                else:
                    logger.error(f"Failed to modify SL order {sl_order_id}")
            else:
                # Fallback: Direct Kite API call (no modification limit handling)
                self.kite.kite.modify_order(
                    variety=self.kite.kite.VARIETY_REGULAR,
                    order_id=sl_order_id,
                    trigger_price=round(new_trigger_price, 2)
                )
                # Increment count if we have order_repo
                # Note: trigger_price is synced from Kite via sync_orders_from_kite()
                if self.order_repo:
                    new_count = await self.order_repo.increment_modification_count(sl_order_id)
                    logger.info(
                        f"✅ SL order modified on Kite: {sl_order_id} -> ₹{new_trigger_price:.2f} "
                        f"(mod #{new_count})"
                    )
                else:
                    logger.info(f"✅ SL order modified on Kite: {sl_order_id} -> ₹{new_trigger_price:.2f}")
            
            return None
            
        except Exception as e:
            # Log but don't fail - DB is updated, manual intervention may be needed
            logger.error(
                f"Failed to modify SL order {sl_order_id} on Kite: {e}. "
                f"DB updated but Kite order may need manual update."
            )
            return None
    
    def _get_kite_positions(self) -> List[Dict]:
        """Get current positions from Kite"""
        try:
            positions_data = self.kite.kite.positions()
            return positions_data.get('day', [])
        except Exception as e:
            logger.error(f"Failed to fetch positions from Kite: {e}")
            return []
    
    # ================================================================
    # CONFIGURATION METHODS
    # ================================================================
    
    def update_config(
        self,
        enabled: Optional[bool] = None,
        activation_pct: Optional[float] = None,
        trail_pct: Optional[float] = None,
        min_sl_move_pct: Optional[float] = None
    ):
        """Update trailing SL configuration"""
        if enabled is not None:
            self.config.enabled = enabled
        if activation_pct is not None:
            self.config.activation_pct = activation_pct
        if trail_pct is not None:
            self.config.trail_pct = trail_pct
        if min_sl_move_pct is not None:
            self.config.min_sl_move_pct = min_sl_move_pct
        
        logger.info(
            f"Trailing SL config updated: enabled={self.config.enabled}, "
            f"activation={self.config.activation_pct}%, "
            f"trail={self.config.trail_pct}%"
        )
    
    def get_config(self) -> Dict:
        """Get current configuration"""
        return {
            "enabled": self.config.enabled,
            "activation_pct": self.config.activation_pct,
            "trail_pct": self.config.trail_pct,
            "min_sl_move_pct": self.config.min_sl_move_pct
        }
