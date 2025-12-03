"""
Order Manager Service

Manages order lifecycle with Kite API integration.
- Runtime: Query Kite API directly for current state
- Background: Sync Kite orders to DB periodically

Order Strategy (Post-2020 Zerodha):
- Bracket Orders (BO) are DISCONTINUED since Jan 2020
- We use Regular Orders + Separate SL-M Orders
- This allows trailing stop loss via order modifications
- Max 25 modifications per order (then cancel and recreate)
"""

from typing import List, Optional, Dict, Tuple
from datetime import datetime
from dataclasses import dataclass
import logging

from backend.core.services.market.kite_service import KiteService
from backend.config import DEFAULT_BROKER_LIMITS
from backend.infrastructure.database.order_repository import OrderRepository
from backend.core.models import Signal
from backend.core.utils.retry import retry_sync, RetryError, KITE_API_ERRORS

logger = logging.getLogger(__name__)


# Maximum SL order modifications before recreating (from broker config)
MAX_SL_MODIFICATIONS = DEFAULT_BROKER_LIMITS.max_sl_modifications


@dataclass
class OrderResult:
    """Result of order placement"""
    entry_order_id: Optional[str] = None
    sl_order_id: Optional[str] = None
    target_order_id: Optional[str] = None
    quantity: Optional[int] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    success: bool = False
    error: Optional[str] = None


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
    ) -> Optional[OrderResult]:
        """
        Place entry order + separate SL order via Kite API.
        
        Strategy (Post-2020 Zerodha - no Bracket Orders):
        1. Place entry order (MARKET/LIMIT)
        2. Once filled, place SL-M order for stop loss
        3. Optionally place limit order for target (or let trailing SL handle exit)
        
        Args:
            signal: Trading signal (must have stop_loss and target)
            quantity: Number of shares
            strategy_name: Strategy identifier
            order_type: MARKET or LIMIT
            product: MIS (intraday) or CNC (delivery)
        
        Returns:
            OrderResult with entry_order_id and sl_order_id if successful, None otherwise
        """
        try:
            transaction_type = signal.signal_type.value  # BUY or SELL
            
            logger.info(
                f"Placing {order_type} order: {transaction_type} {signal.symbol} "
                f"x {quantity} @ ₹{signal.price:.2f} (SL: ₹{signal.stop_loss:.2f}, Target: ₹{signal.target:.2f})"
            )
            
            # Step 1: Place entry order
            entry_order_id = await self._place_entry_order(
                symbol=signal.symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=order_type,
                price=signal.price if order_type == "LIMIT" else None,
                product=product
            )
            
            if not entry_order_id:
                logger.error(f"Failed to place entry order for {signal.symbol}")
                return None
            
            # Step 2: Place SL order immediately (will become active when entry fills)
            # For BUY entry -> SELL SL; For SELL entry -> BUY SL
            sl_transaction = "SELL" if transaction_type == "BUY" else "BUY"
            
            sl_order_id = await self._place_sl_order(
                symbol=signal.symbol,
                transaction_type=sl_transaction,
                quantity=quantity,
                trigger_price=signal.stop_loss,
                product=product
            )
            
            # Record entry order to DB (now with sl_order_id in metadata)
            await self.order_repo.create_order(
                order_id=entry_order_id,
                symbol=signal.symbol,
                instrument_token=signal.instrument_token,
                strategy_name=strategy_name,
                order_type=order_type,
                transaction_type=transaction_type,
                quantity=quantity,
                price=signal.price if order_type == "LIMIT" else None,
                trigger_price=None,
                status="PENDING",
                placed_at=datetime.now(),
                metadata={
                    "signal_reason": signal.reason,
                    "product": product,
                    "order_role": "ENTRY",
                    "stop_loss": signal.stop_loss,
                    "target": signal.target,
                    "sl_order_id": sl_order_id  # Link to SL order for position sync
                }
            )
            
            if sl_order_id:
                # Record SL order to DB
                await self.order_repo.create_order(
                    order_id=sl_order_id,
                    symbol=signal.symbol,
                    instrument_token=signal.instrument_token,
                    strategy_name=strategy_name,
                    order_type="SL-M",
                    transaction_type=sl_transaction,
                    quantity=quantity,
                    price=None,
                    trigger_price=signal.stop_loss,
                    status="TRIGGER PENDING",
                    placed_at=datetime.now(),
                    metadata={
                        "product": product,
                        "order_role": "STOP_LOSS",
                        "parent_order_id": entry_order_id,
                        "modification_count": 0
                    }
                )
                logger.info(f"✅ SL order placed: {sl_order_id} @ trigger ₹{signal.stop_loss:.2f}")
            else:
                logger.warning(f"⚠️ Failed to place SL order for {signal.symbol}")
            
            # Step 3: Optionally place target order (limit sell/buy)
            # For now, we rely on trailing SL for exits rather than fixed target
            # This gives more flexibility and captures momentum
            
            logger.info(f"✅ Entry order placed: {entry_order_id}")
            self._invalidate_cache()
            
            return OrderResult(
                entry_order_id=entry_order_id,
                sl_order_id=sl_order_id,
                quantity=quantity,
                stop_loss=signal.stop_loss,
                target=signal.target
            )
            
        except Exception as e:
            logger.error(f"Error placing order for {signal.symbol}: {e}", exc_info=True)
            return None
    
    async def place_target_order(
        self,
        symbol: str,
        instrument_token: int,
        transaction_type: str,
        quantity: int,
        target_price: float,
        product: str,
        strategy_name: str,
        parent_order_id: str
    ) -> Optional[str]:
        """
        Place a target (take-profit) limit order.
        
        Args:
            symbol: Stock symbol
            instrument_token: Kite instrument token
            transaction_type: SELL (for long) or BUY (for short)
            quantity: Number of shares
            target_price: Target price for limit order
            product: MIS or CNC
            strategy_name: Strategy identifier
            parent_order_id: Entry order ID this target belongs to
            
        Returns:
            Target order_id if successful
        """
        try:
            kite_product = (
                self.kite.kite.PRODUCT_MIS if product == "MIS" 
                else self.kite.kite.PRODUCT_CNC
            )
            
            order_id = self.kite.kite.place_order(
                variety=self.kite.kite.VARIETY_REGULAR,
                exchange=self.kite.kite.EXCHANGE_NSE,
                tradingsymbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=self.kite.kite.ORDER_TYPE_LIMIT,
                product=kite_product,
                price=round(target_price, 2)
            )
            
            # Record to DB
            await self.order_repo.create_order(
                order_id=order_id,
                symbol=symbol,
                instrument_token=instrument_token,
                strategy_name=strategy_name,
                order_type="LIMIT",
                transaction_type=transaction_type,
                quantity=quantity,
                price=target_price,
                trigger_price=None,
                status="OPEN",
                placed_at=datetime.now(),
                metadata={
                    "product": product,
                    "order_role": "TARGET",
                    "parent_order_id": parent_order_id
                }
            )
            
            logger.info(f"Target order placed: {order_id} @ ₹{target_price:.2f}")
            return order_id
            
        except Exception as e:
            logger.error(f"Failed to place target order: {e}")
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
    # KITE API WRAPPERS (Regular Orders - No Bracket Orders)
    # ================================================================
    
    async def _place_entry_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str,
        price: Optional[float],
        product: str
    ) -> Optional[str]:
        """
        Place entry order via Kite API (Regular variety).
        
        Args:
            symbol: Stock symbol
            transaction_type: BUY or SELL
            quantity: Number of shares
            order_type: MARKET or LIMIT
            price: Price for LIMIT orders
            product: MIS or CNC
            
        Returns:
            Order ID if successful
        """
        try:
            kite_order_type = (
                self.kite.kite.ORDER_TYPE_MARKET if order_type == "MARKET" 
                else self.kite.kite.ORDER_TYPE_LIMIT
            )
            kite_product = (
                self.kite.kite.PRODUCT_MIS if product == "MIS" 
                else self.kite.kite.PRODUCT_CNC
            )
            
            order_params = {
                "variety": self.kite.kite.VARIETY_REGULAR,
                "exchange": self.kite.kite.EXCHANGE_NSE,
                "tradingsymbol": symbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "order_type": kite_order_type,
                "product": kite_product
            }
            
            if price and order_type == "LIMIT":
                order_params["price"] = round(price, 2)
            
            order_id = self.kite.kite.place_order(**order_params)
            logger.info(f"Entry order placed: {order_id} - {transaction_type} {symbol} x {quantity}")
            return order_id
            
        except Exception as e:
            logger.error(f"Kite entry order placement failed: {e}")
            return None
    
    async def _place_sl_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        trigger_price: float,
        product: str
    ) -> Optional[str]:
        """
        Place SL-M (Stop Loss Market) order via Kite API.
        
        SL-M order: When trigger_price is hit, executes at market price.
        This is used for stop loss protection.
        
        Args:
            symbol: Stock symbol
            transaction_type: SELL (for long positions) or BUY (for short)
            quantity: Number of shares
            trigger_price: Price at which SL triggers
            product: MIS or CNC
            
        Returns:
            Order ID if successful
        """
        try:
            kite_product = (
                self.kite.kite.PRODUCT_MIS if product == "MIS" 
                else self.kite.kite.PRODUCT_CNC
            )
            
            order_id = self.kite.kite.place_order(
                variety=self.kite.kite.VARIETY_REGULAR,
                exchange=self.kite.kite.EXCHANGE_NSE,
                tradingsymbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=self.kite.kite.ORDER_TYPE_SLM,  # SL-M order
                product=kite_product,
                trigger_price=round(trigger_price, 2)
            )
            
            logger.info(f"SL-M order placed: {order_id} - trigger @ ₹{trigger_price:.2f}")
            return order_id
            
        except Exception as e:
            logger.error(f"Kite SL order placement failed: {e}")
            return None
    
    async def _cancel_kite_order(self, order_id: str, variety: str = "regular") -> bool:
        """Cancel order via Kite API"""
        try:
            kite_variety = self.kite.kite.VARIETY_REGULAR
            self.kite.kite.cancel_order(
                variety=kite_variety,
                order_id=order_id
            )
            return True
        except Exception as e:
            logger.error(f"Kite order cancellation failed: {e}")
            return False
    
    async def cancel_sl_order(self, sl_order_id: str) -> bool:
        """
        Cancel a stop loss order by its order ID.
        
        Call this when:
        - Position is manually squared off
        - Position hits target
        - Time-based exit (EOD)
        - Any position closure where we no longer need the SL
        
        Args:
            sl_order_id: The SL order ID to cancel
            
        Returns:
            True if cancelled successfully, False otherwise
        """
        if not sl_order_id:
            logger.warning("No SL order ID provided to cancel")
            return False
            
        try:
            # Check if order is still open/pending
            orders = await self._get_kite_orders_cached()
            sl_order = next((o for o in orders if o['order_id'] == sl_order_id), None)
            
            if not sl_order:
                logger.info(f"SL order {sl_order_id} not found in orders, may already be executed/cancelled")
                return True  # Not an error, just already gone
                
            status = sl_order.get('status', '')
            if status in ['COMPLETE', 'CANCELLED', 'REJECTED']:
                logger.info(f"SL order {sl_order_id} already {status}")
                return True
                
            if status not in ['OPEN', 'TRIGGER PENDING']:
                logger.warning(f"SL order {sl_order_id} in unexpected status: {status}")
                return False
                
            # Cancel the order
            success = await self._cancel_kite_order(sl_order_id)
            
            if success:
                logger.info(f"✅ SL order cancelled: {sl_order_id}")
                self._invalidate_cache()
            
            return success
            
        except Exception as e:
            logger.error(f"Error cancelling SL order {sl_order_id}: {e}")
            return False
    
    async def modify_sl_order(
        self,
        order_id: str,
        new_trigger_price: float,
        modification_count: int = 0
    ) -> Tuple[bool, Optional[str]]:
        """
        Modify a stop loss order trigger price on Kite.
        
        Used for trailing stop loss - moves the SL trigger up as price moves favorably.
        
        IMPORTANT: Zerodha allows max 25 modifications per order.
        After ~20 modifications, we cancel and create a new SL order.
        
        Args:
            order_id: The SL order ID to modify
            new_trigger_price: New trigger price for SL
            modification_count: Current modification count for this order
            
        Returns:
            Tuple of (success, new_order_id if recreated else None)
        """
        try:
            # Check if we need to recreate the order
            if modification_count >= MAX_SL_MODIFICATIONS:
                logger.info(f"SL order {order_id} reached {modification_count} modifications, recreating...")
                return await self._recreate_sl_order(order_id, new_trigger_price)
            
            # Modify existing order
            self.kite.kite.modify_order(
                variety=self.kite.kite.VARIETY_REGULAR,
                order_id=order_id,
                trigger_price=round(new_trigger_price, 2)
            )
            
            logger.info(f"SL order modified: {order_id} -> trigger ₹{new_trigger_price:.2f} (mod #{modification_count + 1})")
            self._invalidate_cache()
            return True, None
            
        except Exception as e:
            logger.error(f"Failed to modify SL order {order_id}: {e}")
            return False, None
    
    async def _recreate_sl_order(
        self,
        old_order_id: str,
        new_trigger_price: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Cancel old SL order and create new one with updated trigger price.
        
        Used when modification limit is reached.
        
        Args:
            old_order_id: The SL order to cancel
            new_trigger_price: Trigger price for new order
            
        Returns:
            Tuple of (success, new_order_id)
        """
        try:
            # Get old order details
            old_order = await self.order_repo.get_order(old_order_id)
            if not old_order:
                logger.error(f"Old SL order {old_order_id} not found in DB")
                return False, None
            
            # Cancel old order
            cancelled = await self._cancel_kite_order(old_order_id)
            if not cancelled:
                logger.error(f"Failed to cancel old SL order {old_order_id}")
                return False, None
            
            # Update old order status
            await self.order_repo.update_order(
                order_id=old_order_id,
                status="CANCELLED",
                status_message="Recreated due to modification limit"
            )
            
            # Place new SL order
            product = old_order.get("metadata", {}).get("product", "MIS")
            new_order_id = await self._place_sl_order(
                symbol=old_order["symbol"],
                transaction_type=old_order["transaction_type"],
                quantity=old_order["quantity"],
                trigger_price=new_trigger_price,
                product=product
            )
            
            if new_order_id:
                # Record new SL order
                await self.order_repo.create_order(
                    order_id=new_order_id,
                    symbol=old_order["symbol"],
                    instrument_token=old_order["instrument_token"],
                    strategy_name=old_order["strategy_name"],
                    order_type="SL-M",
                    transaction_type=old_order["transaction_type"],
                    quantity=old_order["quantity"],
                    price=None,
                    trigger_price=new_trigger_price,
                    status="TRIGGER PENDING",
                    placed_at=datetime.now(),
                    metadata={
                        "product": product,
                        "order_role": "STOP_LOSS",
                        "parent_order_id": old_order.get("metadata", {}).get("parent_order_id"),
                        "modification_count": 0,  # Reset counter
                        "previous_order_id": old_order_id
                    }
                )
                logger.info(f"SL order recreated: {old_order_id} -> {new_order_id} @ ₹{new_trigger_price:.2f}")
                return True, new_order_id
            
            return False, None
            
        except Exception as e:
            logger.error(f"Failed to recreate SL order: {e}")
            return False, None
    
    async def cancel_sl_and_target_orders(self, parent_order_id: str) -> int:
        """
        Cancel SL and target orders associated with a parent entry order.
        
        Args:
            parent_order_id: The entry order ID
            
        Returns:
            Number of orders cancelled
        """
        try:
            # Find associated orders from DB
            orders = await self._get_kite_orders_cached()
            cancelled = 0
            
            # Look for SL and Target orders in our DB
            # They have parent_order_id in metadata
            for order in orders:
                order_id = order['order_id']
                db_order = await self.order_repo.get_order(order_id)
                
                if db_order:
                    metadata = db_order.get("metadata", {})
                    if metadata.get("parent_order_id") == parent_order_id:
                        if order['status'] in ['OPEN', 'TRIGGER PENDING']:
                            success = await self._cancel_kite_order(order_id)
                            if success:
                                await self.order_repo.update_order(
                                    order_id=order_id,
                                    status="CANCELLED",
                                    status_message="Parent position closed"
                                )
                                cancelled += 1
            
            logger.info(f"Cancelled {cancelled} SL/Target orders for {parent_order_id}")
            return cancelled
            
        except Exception as e:
            logger.error(f"Error cancelling SL/Target orders: {e}")
            return 0
    
    async def exit_position(
        self,
        symbol: str,
        quantity: int,
        transaction_type: str,
        product: str = "MIS",
        sl_order_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Exit a position by placing a market order.
        
        IMPORTANT: Also cancels the SL order if provided!
        
        Args:
            symbol: Stock symbol
            quantity: Number of shares
            transaction_type: SELL (to close long) or BUY (to close short)
            product: MIS or CNC
            sl_order_id: SL order ID to cancel (important!)
            
        Returns:
            Order ID if successful
        """
        try:
            # First, cancel the SL order if we have one
            if sl_order_id:
                await self.cancel_sl_order(sl_order_id)
            
            order_id = await self._place_entry_order(
                symbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type="MARKET",
                price=None,
                product=product
            )
            
            if order_id:
                logger.info(f"Position exit order placed: {order_id} - {transaction_type} {symbol} x {quantity}")
            
            return order_id
            
        except Exception as e:
            logger.error(f"Failed to exit position: {e}")
            return None
    
    async def exit_all_positions(self, db_positions: Optional[List[Dict]] = None) -> int:
        """
        Exit all open positions by placing market orders.
        Used for time-based exits (3:15 PM).
        
        IMPORTANT: Also cancels SL orders for each position!
        
        Args:
            db_positions: Optional list of DB position records containing sl_order_id.
                          If provided, will cancel SL orders before exiting.
        
        Returns:
            Number of positions exited
        """
        try:
            # Build lookup for sl_order_id from DB positions
            sl_order_lookup = {}
            if db_positions:
                for pos in db_positions:
                    symbol = pos.get('symbol')
                    sl_order_id = pos.get('sl_order_id')
                    if symbol and sl_order_id:
                        sl_order_lookup[symbol] = sl_order_id
            
            # Fetch positions from Kite
            positions = self.kite.kite.positions()
            day_positions = positions.get("day", [])
            
            exited = 0
            for pos in day_positions:
                qty = pos.get("quantity", 0)
                if qty == 0:
                    continue
                
                symbol = pos.get("tradingsymbol")
                product = pos.get("product", "MIS")
                
                # Determine exit direction
                if qty > 0:  # Long position
                    transaction_type = "SELL"
                    exit_qty = qty
                else:  # Short position
                    transaction_type = "BUY"
                    exit_qty = abs(qty)
                
                # Get sl_order_id from lookup
                sl_order_id = sl_order_lookup.get(symbol)
                
                # Place exit order (this will also cancel SL order if provided)
                order_id = await self.exit_position(
                    symbol=symbol,
                    quantity=exit_qty,
                    transaction_type=transaction_type,
                    product=product,
                    sl_order_id=sl_order_id
                )
                
                if order_id:
                    exited += 1
            
            logger.info(f"Exited {exited} positions (with SL orders cancelled)")
            return exited
            
        except Exception as e:
            logger.error(f"Error exiting positions: {e}", exc_info=True)
            return 0
    
    async def cancel_orphaned_sl_orders(
        self,
        open_position_symbols: List[str],
        db_positions: List[Dict]
    ) -> int:
        """
        Cancel SL orders for positions that are no longer open in Kite.
        
        Called during position sync to clean up SL orders when positions close
        (via target hit, manual square off, or SL triggered elsewhere).
        
        Args:
            open_position_symbols: List of symbols still open in Kite
            db_positions: DB position records with sl_order_id
            
        Returns:
            Number of SL orders cancelled
        """
        try:
            cancelled = 0
            
            for pos in db_positions:
                symbol = pos.get('symbol')
                sl_order_id = pos.get('sl_order_id')
                
                # Skip if no SL order or if position is still open
                if not sl_order_id or symbol in open_position_symbols:
                    continue
                
                # Position is closed but we have an SL order - cancel it
                logger.info(f"Position {symbol} closed - cancelling orphaned SL order {sl_order_id}")
                success = await self.cancel_sl_order(sl_order_id)
                if success:
                    cancelled += 1
            
            if cancelled > 0:
                logger.info(f"✅ Cancelled {cancelled} orphaned SL orders")
            
            return cancelled
            
        except Exception as e:
            logger.error(f"Error cancelling orphaned SL orders: {e}")
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
