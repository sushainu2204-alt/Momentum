"""
Order Manager Service

Manages order lifecycle with Kite API integration.
- Runtime: Query Kite API directly for current state
- Background: Sync Kite orders to DB periodically
"""

from typing import List, Optional, Dict
from datetime import datetime
import logging

from backend.core.services.kite_service import KiteService
from backend.infrastructure.database.order_repository import OrderRepository
from backend.models import Signal
from backend.core.utils.retry import retry_sync, RetryError, KITE_API_ERRORS

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Manages orders with Kite API as source of truth.
    
    Runtime Flow:
    1. Check Kite API for current order state
    2. Place orders via Kite API
    3. Record to DB for audit/history
    
    Background Sync:
    - Periodically fetch orders from Kite
    - Update DB with latest status
    """
    
    def __init__(
        self,
        kite_service: KiteService,
        order_repository: OrderRepository
    ):
        self.kite = kite_service
        self.order_repo = order_repository
        self._order_cache = {}  # order_id -> order_data
        self._cache_timestamp = None
    
    # ================================================================
    # RUNTIME QUERIES (Real-time from Kite)
    # ================================================================
    
    async def has_pending_order(
        self,
        symbol: str,
        transaction_type: Optional[str] = None
    ) -> bool:
        """
        Check if symbol has pending order (query Kite API).
        
        Args:
            symbol: Stock symbol
            transaction_type: BUY or SELL (optional filter)
        
        Returns:
            True if pending order exists
        """
        try:
            # Fetch fresh orders from Kite
            kite_orders = await self._get_kite_orders_cached()
            
            for order in kite_orders:
                # Check if order is pending/open
                if order['status'] not in ['OPEN', 'TRIGGER PENDING']:
                    continue
                
                # Match symbol
                if order['tradingsymbol'] != symbol:
                    continue
                
                # Match transaction type if specified
                if transaction_type and order['transaction_type'] != transaction_type:
                    continue
                
                logger.debug(
                    f"Pending order found: {symbol} - "
                    f"{order['transaction_type']} x {order['quantity']} @ "
                    f"Status: {order['status']}"
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking pending orders for {symbol}: {e}")
            # Fallback to DB
            return await self.order_repo.has_pending_order(symbol, transaction_type)
    
    async def get_pending_orders(
        self,
        symbol: Optional[str] = None
    ) -> List[Dict]:
        """
        Get all pending orders (from Kite API).
        
        Args:
            symbol: Optional symbol filter
        
        Returns:
            List of pending order dicts
        """
        try:
            kite_orders = await self._get_kite_orders_cached()
            
            pending = []
            for order in kite_orders:
                if order['status'] in ['OPEN', 'TRIGGER PENDING']:
                    if symbol is None or order['tradingsymbol'] == symbol:
                        pending.append(order)
            
            return pending
            
        except Exception as e:
            logger.error(f"Error fetching pending orders: {e}")
            # Fallback to DB
            return await self.order_repo.get_pending_orders(symbol)
    
    # ================================================================
    # ORDER PLACEMENT (via Kite API)
    # ================================================================
    
    async def place_order(
        self,
        signal: Signal,
        quantity: int,
        strategy_name: str,
        order_type: str = "MARKET",
        product: str = "MIS"  # Intraday
    ) -> Optional[str]:
        """
        Place bracket order via Kite API with automatic SL/Target.
        
        Args:
            signal: Trading signal (must have stop_loss and target)
            quantity: Number of shares
            strategy_name: Strategy identifier
            order_type: MARKET or LIMIT
            product: MIS (intraday) or CNC (delivery)
        
        Returns:
            Kite order_id if successful, None otherwise
        """
        try:
            # Place order via Kite
            transaction_type = signal.signal_type.value  # BUY or SELL
            
            logger.info(
                f"Placing {order_type} bracket order: {transaction_type} {signal.symbol} "
                f"x {quantity} @ ₹{signal.price:.2f} (SL: ₹{signal.stop_loss:.2f}, Target: ₹{signal.target:.2f})"
            )
            
            order_id = await self._place_kite_order(
                symbol=signal.symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=order_type,
                price=signal.price if order_type == "LIMIT" else None,
                stop_loss=signal.stop_loss,
                target=signal.target,
                product=product
            )
            
            if not order_id:
                logger.error(f"Failed to place order for {signal.symbol}")
                return None
            
            # Record to DB for audit trail
            await self.order_repo.create_order(
                order_id=order_id,
                symbol=signal.symbol,
                instrument_token=signal.instrument_token,
                strategy_name=strategy_name,
                order_type=order_type,
                transaction_type=transaction_type,
                quantity=quantity,
                price=signal.price if order_type == "LIMIT" else None,
                trigger_price=signal.stop_loss if order_type.startswith("SL") else None,
                status="PENDING",
                placed_at=datetime.now(),
                metadata={
                    "signal_reason": signal.reason,
                    "product": product
                }
            )
            
            logger.info(f"✅ Order placed successfully: {order_id}")
            self._invalidate_cache()  # Clear cache to force refresh
            
            return order_id
            
        except Exception as e:
            logger.error(f"Error placing order for {signal.symbol}: {e}", exc_info=True)
            return None
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel pending order via Kite API.
        
        Args:
            order_id: Kite order ID
        
        Returns:
            True if cancelled successfully
        """
        try:
            success = await self._cancel_kite_order(order_id)
            
            if success:
                # Update DB
                await self.order_repo.update_order(
                    order_id=order_id,
                    status="CANCELLED"
                )
                logger.info(f"Order cancelled: {order_id}")
                self._invalidate_cache()
            
            return success
            
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    # ================================================================
    # BACKGROUND SYNC (Kite → DB)
    # ================================================================
    
    async def sync_orders_from_kite(self) -> int:
        """
        Background job: Sync all orders from Kite to DB.
        
        Returns:
            Number of orders synced
        """
        try:
            logger.debug("Syncing orders from Kite...")
            
            # Fetch all orders from Kite with retry for transient failures
            try:
                kite_orders = retry_sync(
                    self.kite.kite.orders,
                    max_retries=3,
                    base_delay=2.0,
                    max_delay=15.0,
                    retryable_exceptions=KITE_API_ERRORS + (Exception,),
                )
            except RetryError as e:
                logger.error(f"Failed to fetch orders after retries: {e.last_exception}")
                return 0
            
            synced_count = 0
            
            for kite_order in kite_orders:
                order_id = kite_order['order_id']
                
                # Check if order exists in DB
                db_order = await self.order_repo.get_order(order_id)
                
                if db_order:
                    # Update if status changed
                    if db_order['status'] != kite_order['status']:
                        await self.order_repo.update_order(
                            order_id=order_id,
                            status=kite_order['status'],
                            status_message=kite_order.get('status_message'),
                            filled_quantity=kite_order.get('filled_quantity', 0),
                            average_price=kite_order.get('average_price'),
                            filled_at=datetime.now() if kite_order['status'] == 'COMPLETE' else None
                        )
                        synced_count += 1
                        
                        logger.debug(
                            f"Order updated: {order_id} - {kite_order['status']}"
                        )
                else:
                    # Order placed outside our system (manual), record it
                    await self.order_repo.create_order(
                        order_id=order_id,
                        symbol=kite_order['tradingsymbol'],
                        instrument_token=kite_order['instrument_token'],
                        strategy_name="MANUAL",  # Not from our strategy
                        order_type=kite_order['order_type'],
                        transaction_type=kite_order['transaction_type'],
                        quantity=kite_order['quantity'],
                        price=kite_order.get('price'),
                        trigger_price=kite_order.get('trigger_price'),
                        status=kite_order['status'],
                        placed_at=kite_order.get('order_timestamp', datetime.now()),
                        metadata={"source": "manual", "raw_data": kite_order}
                    )
                    synced_count += 1
                    logger.info(f"Manual order recorded: {order_id}")
            
            self._invalidate_cache()
            logger.info(f"Orders synced: {synced_count} updated/added")
            
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing orders from Kite: {e}", exc_info=True)
            return 0
    
    # ================================================================
    # KITE API WRAPPERS
    # ================================================================
    
    async def _place_kite_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str,
        price: Optional[float],
        stop_loss: float,
        target: float,
        product: str
    ) -> Optional[str]:
        """Place bracket order via Kite API with automatic SL/Target"""
        try:
            # For MARKET orders, we need a reference price to calculate SL/Target points
            # Use the current market price from stop_loss and target to derive entry estimate
            if price and price > 0:
                entry_price = price
            else:
                # For MARKET orders, estimate entry as midpoint between SL and Target
                # This gives us reasonable bracket order points
                if transaction_type == "BUY":
                    # For BUY: SL < entry < Target
                    # Estimate entry price based on typical risk:reward
                    entry_price = stop_loss + (target - stop_loss) * 0.4  # Assume 40% from SL
                else:
                    # For SELL: Target < entry < SL
                    entry_price = target + (stop_loss - target) * 0.4
            
            # For bracket orders, we need absolute points (not prices)
            # squareoff = points above entry for profit
            # stoploss = points below entry for loss
            if transaction_type == "BUY":
                squareoff = abs(target - entry_price)
                stoploss = abs(entry_price - stop_loss)
            else:  # SELL
                squareoff = abs(entry_price - target)
                stoploss = abs(stop_loss - entry_price)
            
            # Ensure minimum values (at least 0.05 points)
            squareoff = max(squareoff, 0.05)
            stoploss = max(stoploss, 0.05)
            
            order_params = {
                "tradingsymbol": symbol,
                "exchange": self.kite.kite.EXCHANGE_NSE,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "order_type": self.kite.kite.ORDER_TYPE_MARKET if order_type == "MARKET" else self.kite.kite.ORDER_TYPE_LIMIT,
                "product": self.kite.kite.PRODUCT_MIS if product == "MIS" else self.kite.kite.PRODUCT_CNC,
                "variety": self.kite.kite.VARIETY_BO,
                "squareoff": round(squareoff, 2),
                "stoploss": round(stoploss, 2)
            }
            
            if price and order_type == "LIMIT":
                order_params["price"] = price
            
            order_id = self.kite.kite.place_order(**order_params)
            logger.info(f"Bracket order placed: SL={stoploss:.2f} pts, Target={squareoff:.2f} pts (entry ref: ₹{entry_price:.2f})")
            return order_id
            
        except Exception as e:
            logger.error(f"Kite bracket order placement failed: {e}")
            return None
    
    async def _cancel_kite_order(self, order_id: str, variety: str = "bo") -> bool:
        """Cancel order via Kite API"""
        try:
            kite_variety = self.kite.kite.VARIETY_BO if variety == "bo" else self.kite.kite.VARIETY_REGULAR
            self.kite.kite.cancel_order(
                variety=kite_variety,
                order_id=order_id
            )
            return True
        except Exception as e:
            logger.error(f"Kite order cancellation failed: {e}")
            return False
    
    async def modify_sl_order(
        self,
        order_id: str,
        new_trigger_price: float,
        variety: str = "bo"
    ) -> bool:
        """
        Modify a stop loss order trigger price on Kite.
        
        Used for trailing stop loss - moves the SL trigger up as price moves favorably.
        
        Args:
            order_id: The SL order ID to modify
            new_trigger_price: New trigger price for SL
            variety: Order variety (bo for bracket orders)
            
        Returns:
            True if modification successful
        """
        try:
            kite_variety = (
                self.kite.kite.VARIETY_BO if variety == "bo" 
                else self.kite.kite.VARIETY_REGULAR
            )
            
            self.kite.kite.modify_order(
                variety=kite_variety,
                order_id=order_id,
                trigger_price=round(new_trigger_price, 2)
            )
            
            logger.info(f"SL order modified: {order_id} -> trigger ₹{new_trigger_price:.2f}")
            self._invalidate_cache()
            return True
            
        except Exception as e:
            logger.error(f"Failed to modify SL order {order_id}: {e}")
            return False
    
    async def exit_bracket_order(self, parent_order_id: str) -> bool:
        """
        Exit a bracket order position by cancelling the pending SL/Target orders.
        
        For bracket orders in Kite:
        - The entry order creates child SL and Target orders
        - To exit early, we need to place a counter order or use exit API
        
        Args:
            parent_order_id: The parent bracket order ID
            
        Returns:
            True if exit successful
        """
        try:
            # Kite's exit_order for bracket orders
            # This exits the position at market price and cancels pending SL/Target
            self.kite.kite.exit_order(
                variety=self.kite.kite.VARIETY_BO,
                order_id=parent_order_id
            )
            logger.info(f"Bracket order exited: {parent_order_id}")
            self._invalidate_cache()
            return True
        except Exception as e:
            logger.error(f"Failed to exit bracket order {parent_order_id}: {e}")
            return False
    
    async def exit_all_bracket_positions(self) -> int:
        """
        Exit all open bracket order positions.
        Used for time-based exits (3:15 PM).
        
        Returns:
            Number of positions exited
        """
        try:
            # Fetch all orders
            orders = self.kite.kite.orders()
            
            # Find parent BO orders that are COMPLETE (position opened)
            parent_orders = []
            for order in orders:
                if (order.get('variety') == 'bo' and 
                    order.get('status') == 'COMPLETE' and
                    order.get('transaction_type') == 'BUY'):  # Entry orders
                    # Check if there are still pending child orders (SL/Target)
                    parent_id = order.get('order_id')
                    has_pending_children = any(
                        o.get('parent_order_id') == parent_id and 
                        o.get('status') in ['OPEN', 'TRIGGER PENDING']
                        for o in orders
                    )
                    if has_pending_children:
                        parent_orders.append(order)
            
            exited = 0
            for order in parent_orders:
                success = await self.exit_bracket_order(order['order_id'])
                if success:
                    exited += 1
                    
                    # Update DB
                    await self.order_repo.update_order(
                        order_id=order['order_id'],
                        status="EXITED",
                        status_message="Time-based exit (3:15 PM)"
                    )
            
            logger.info(f"Exited {exited}/{len(parent_orders)} bracket positions")
            return exited
            
        except Exception as e:
            logger.error(f"Error exiting bracket positions: {e}", exc_info=True)
            return 0
    
    async def _get_kite_orders_cached(self) -> List[Dict]:
        """Get orders with 2-second cache"""
        now = datetime.now()
        
        # Use cache if less than 2 seconds old
        if self._cache_timestamp and (now - self._cache_timestamp).total_seconds() < 2:
            return list(self._order_cache.values())
        
        # Fetch fresh from Kite
        try:
            orders = self.kite.kite.orders()
            self._order_cache = {o['order_id']: o for o in orders}
            self._cache_timestamp = now
            return orders
        except Exception as e:
            logger.error(f"Failed to fetch orders from Kite: {e}")
            return list(self._order_cache.values())  # Return stale cache
    
    def _invalidate_cache(self):
        """Clear order cache"""
        self._cache_timestamp = None
    
    # ================================================================
    # QUERIES
    # ================================================================
    
    async def get_order_status(self, order_id: str) -> Optional[Dict]:
        """Get order status from Kite"""
        try:
            orders = await self._get_kite_orders_cached()
            for order in orders:
                if order['order_id'] == order_id:
                    return order
            return None
        except Exception as e:
            logger.error(f"Error fetching order status: {e}")
            return None
    
    async def get_todays_orders(self) -> List[Dict]:
        """Get today's orders from Kite"""
        try:
            return await self._get_kite_orders_cached()
        except Exception as e:
            logger.error(f"Error fetching today's orders: {e}")
            return []
