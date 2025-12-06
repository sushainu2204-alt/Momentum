#!/usr/bin/env python3
"""
LIVE MIS Order Testing Script

This script allows you to test MIS orders with trailing stop loss during market hours.
It places REAL orders on Kite - use with SMALL quantities for testing!

Features:
1. Place MIS order with SL-M order
2. Monitor position and order status
3. Test trailing stop loss updates
4. Test various exit scenarios (SL hit, target hit, manual exit)

Usage:
    # Place a BUY order with monitoring
    python non-prod/scripts/manual/test_mis_order_live.py --action buy --symbol RELIANCE --quantity 1
    
    # Monitor existing positions
    python non-prod/scripts/manual/test_mis_order_live.py --action monitor
    
    # Square off a specific position
    python non-prod/scripts/manual/test_mis_order_live.py --action exit --symbol RELIANCE
    
    # Square off all positions
    python non-prod/scripts/manual/test_mis_order_live.py --action exit_all
    
    # Test trailing SL (run this periodically)
    python non-prod/scripts/manual/test_mis_order_live.py --action trail
    
    # Full status report
    python non-prod/scripts/manual/test_mis_order_live.py --action status

SCENARIOS TO TEST:
==================
1. BASIC ORDER PLACEMENT
   - Place MIS BUY order for 1 share of a liquid stock
   - Verify entry order and SL order are placed
   - Check position appears in Kite
   
2. TRAILING STOP LOSS
   - Buy a stock that's trending up
   - Wait for price to rise above activation threshold
   - Run trail action to update SL
   - Verify SL order is modified on Kite
   
3. STOP LOSS HIT
   - Buy a stock
   - Wait for price to drop to SL level
   - Verify position is closed
   - Check exit recorded in DB
   
4. TARGET EXIT
   - Buy a stock near support
   - Wait for price to reach target
   - Exit manually at profit
   
5. MANUAL SQUARE OFF
   - Place order
   - Exit using exit action
   - Verify SL order is cancelled
   - Verify exit order is placed
   
6. EOD SQUARE OFF
   - Have open position near 3:15 PM
   - Run exit_all action
   - Verify all positions closed
   
7. MULTIPLE POSITIONS
   - Open positions in 2-3 different symbols
   - Monitor all together
   - Exit individually
   
⚠️ WARNING: This places REAL orders. Use small quantities!
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Create logs directory
Path(Path(__file__).parent.parent.parent.parent / 'logs').mkdir(exist_ok=True)

from backend.infrastructure.database.factory import create_database
from backend.core.services.market.kite_service import KiteService
from backend.infrastructure.database.order_repository import OrderRepository
from backend.infrastructure.database.position_repository import PositionRepository
from backend.core.services.trading.order_manager import OrderManager
from backend.core.services.trading.position_manager import PositionManager
from backend.core.services.trading.capital_manager import CapitalManager
from backend.core.services.trading.trailing_sl_service import (
    TrailingStopLossService, 
    TrailingStopLossConfig
)
from backend.core.models import Signal, SignalType
from backend.core.utils.timezone import now_ist, is_market_hours

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'logs/mis_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass 
class TestConfig:
    """Configuration for test orders"""
    # Default SL and target percentages
    sl_pct: float = 1.0      # 1% stop loss
    target_pct: float = 2.0  # 2% target
    
    # Trailing SL config
    trail_activation_pct: float = 0.5  # Start trailing after 0.5% profit
    trail_pct: float = 0.3             # Trail 0.3% below high
    trail_min_move_pct: float = 0.1    # Min SL move to trigger update
    
    # Product type
    product: str = "MIS"  # MIS for intraday


class LiveMISOrderTester:
    """
    Live MIS order testing utility.
    
    Provides methods to:
    - Place test orders
    - Monitor positions/orders
    - Test trailing SL
    - Exit positions
    """
    
    def __init__(self, config: TestConfig = None):
        self.config = config or TestConfig()
        self.db = None
        self.kite = None
        self.order_manager = None
        self.position_manager = None
        self.capital_manager = None
        self.trailing_sl_service = None
        
    async def initialize(self):
        """Initialize all services"""
        logger.info("=" * 60)
        logger.info("  LIVE MIS ORDER TESTER")
        logger.info("=" * 60)
        logger.info("")
        
        # Check market hours
        current_time = now_ist()
        if not is_market_hours(current_time):
            logger.warning("⚠️  Market is CLOSED. Orders will fail or be queued.")
            logger.warning(f"   Current time: {current_time.strftime('%H:%M:%S')}")
            logger.warning("   Market hours: 9:15 AM - 3:30 PM IST")
            response = input("\nContinue anyway? (y/n): ")
            if response.lower() != 'y':
                return False
        
        try:
            # Database
            self.db = create_database()
            await self.db.connect()
            logger.info("✓ Database connected")
            
            # Kite service
            self.kite = KiteService()
            
            # Validate Kite access token by making a test API call
            try:
                profile = self.kite.kite.profile()
                logger.info(f"✓ Kite authenticated as: {profile.get('user_name', 'Unknown')}")
            except Exception as e:
                logger.error(f"❌ Kite authentication failed: {e}")
                logger.error("   Access token may be expired. Please login again.")
                logger.error("   Run: python backend/main.py and visit /auth/login")
                return False
            
            # Repositories
            order_repo = OrderRepository(self.db)
            position_repo = PositionRepository(self.db)
            
            # Managers
            self.order_manager = OrderManager(
                kite_service=self.kite,
                order_repository=order_repo
            )
            
            self.position_manager = PositionManager(
                kite_service=self.kite,
                position_repository=position_repo,
                order_repository=order_repo
            )
            
            self.capital_manager = CapitalManager(
                database=self.db,
                kite_service=self.kite,
                position_manager=self.position_manager
            )
            
            # Trailing SL service
            trailing_config = TrailingStopLossConfig(
                enabled=True,
                activation_pct=self.config.trail_activation_pct,
                trail_pct=self.config.trail_pct,
                min_sl_move_pct=self.config.trail_min_move_pct
            )
            self.trailing_sl_service = TrailingStopLossService(
                position_repository=position_repo,
                kite_service=self.kite,
                order_repository=order_repo,
                order_manager=self.order_manager,
                config=trailing_config
            )
            
            logger.info("✓ All managers initialized")
            logger.info("")
            return True
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            raise
    
    async def close(self):
        """Close connections"""
        if self.db:
            await self.db.close()
            logger.info("Database connection closed")
    
    # ================================================================
    # PRE-FLIGHT CHECKS
    # ================================================================
    
    async def run_preflight_checks(self):
        """
        Run pre-flight checks before live testing.
        
        Validates:
        1. Database connection and required columns
        2. Kite authentication and token validity
        3. Test symbol quote (LTP + instrument token)
        4. Market hours check
        """
        logger.info("=" * 60)
        logger.info("  PRE-FLIGHT CHECKS FOR LIVE MIS TESTING")
        logger.info("=" * 60)
        logger.info("")
        
        all_passed = True
        
        # 1. Check Market Hours
        logger.info("1️⃣  MARKET HOURS CHECK")
        logger.info("-" * 40)
        current_time = now_ist()
        if is_market_hours(current_time):
            logger.info(f"   ✅ Market is OPEN")
            logger.info(f"   Current time: {current_time.strftime('%H:%M:%S')} IST")
        else:
            logger.warning(f"   ⚠️  Market is CLOSED")
            logger.warning(f"   Current time: {current_time.strftime('%H:%M:%S')} IST")
            logger.warning(f"   Market hours: 9:15 AM - 3:30 PM IST")
        logger.info("")
        
        # 2. Database Connection & Tables
        logger.info("2️⃣  DATABASE CONNECTION")
        logger.info("-" * 40)
        try:
            self.db = create_database()
            await self.db.connect()
            logger.info("   ✅ Database connected")
            
            # Check for required columns in orders table
            try:
                result = await self.db.fetch_one(
                    """
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'orders' AND column_name = 'modification_count'
                    """,
                    {}
                )
                if result:
                    logger.info("   ✅ orders.modification_count column exists")
                else:
                    logger.error("   ❌ orders.modification_count column MISSING!")
                    logger.error("      Trailing SL modifications won't work correctly.")
                    logger.error("      Run: ALTER TABLE orders ADD COLUMN modification_count INT DEFAULT 0;")
                    all_passed = False
            except Exception as e:
                logger.warning(f"   ⚠️  Could not check modification_count column: {e}")
            
            # Check positions table has required columns
            try:
                required_pos_cols = ['sl_order_id', 'highest_price', 'original_stop_loss']
                for col in required_pos_cols:
                    result = await self.db.fetch_one(
                        f"""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_name = 'positions' AND column_name = '{col}'
                        """,
                        {}
                    )
                    if result:
                        logger.info(f"   ✅ positions.{col} column exists")
                    else:
                        logger.error(f"   ❌ positions.{col} column MISSING!")
                        all_passed = False
            except Exception as e:
                logger.warning(f"   ⚠️  Could not check positions columns: {e}")
                
        except Exception as e:
            logger.error(f"   ❌ Database connection FAILED: {e}")
            all_passed = False
        logger.info("")
        
        # 3. Kite Authentication
        logger.info("3️⃣  KITE AUTHENTICATION")
        logger.info("-" * 40)
        try:
            self.kite = KiteService()
            profile = self.kite.kite.profile()
            logger.info(f"   ✅ Kite authenticated as: {profile.get('user_name', 'Unknown')}")
            logger.info(f"   User ID: {profile.get('user_id')}")
            logger.info(f"   Broker: {profile.get('broker', 'Unknown')}")
        except Exception as e:
            logger.error(f"   ❌ Kite authentication FAILED: {e}")
            logger.error("   Access token may be expired. Please login again:")
            logger.error("   1. Run: python backend/main.py")
            logger.error("   2. Visit: http://localhost:8000/auth/login")
            all_passed = False
        logger.info("")
        
        # 4. Test Quote API
        logger.info("4️⃣  QUOTE API TEST (RELIANCE)")
        logger.info("-" * 40)
        if self.kite:
            try:
                exchange_symbol = "NSE:RELIANCE"
                quotes = self.kite.kite.quote([exchange_symbol])
                
                if exchange_symbol in quotes:
                    quote = quotes[exchange_symbol]
                    logger.info(f"   ✅ Quote API working")
                    logger.info(f"   LTP: ₹{quote['last_price']:.2f}")
                    logger.info(f"   Instrument Token: {quote['instrument_token']}")
                    logger.info(f"   Volume: {quote.get('volume', 'N/A')}")
                else:
                    logger.error("   ❌ Quote API returned empty result")
                    all_passed = False
            except Exception as e:
                logger.error(f"   ❌ Quote API FAILED: {e}")
                all_passed = False
        logger.info("")
        
        # 5. Check Margins
        logger.info("5️⃣  MARGIN CHECK")
        logger.info("-" * 40)
        if self.kite:
            try:
                margins = self.kite.kite.margins()
                equity = margins.get('equity', {})
                available = equity.get('available', {}).get('cash', 0)
                logger.info(f"   ✅ Margin API working")
                logger.info(f"   Available Cash: ₹{available:,.2f}")
                
                if available < 1000:
                    logger.warning(f"   ⚠️  Low margin - may not be able to place orders")
            except Exception as e:
                logger.error(f"   ❌ Margin API FAILED: {e}")
                all_passed = False
        logger.info("")
        
        # Final Summary
        logger.info("=" * 60)
        if all_passed:
            logger.info("  ✅ ALL PRE-FLIGHT CHECKS PASSED!")
            logger.info("  You are ready for live testing.")
        else:
            logger.error("  ❌ SOME CHECKS FAILED!")
            logger.error("  Please fix the issues above before testing.")
        logger.info("=" * 60)
        
        # Close DB connection
        if self.db:
            await self.db.close()
        
        return all_passed
    
    # ================================================================
    # ORDER PLACEMENT
    # ================================================================
    
    async def place_buy_order(
        self,
        symbol: str,
        quantity: int = 1,
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
        sl_pct: Optional[float] = None,
        target_pct: Optional[float] = None
    ) -> Dict:
        """
        Place a MIS BUY order with SL order.
        
        Args:
            symbol: Stock symbol (e.g., "RELIANCE")
            quantity: Number of shares (keep small for testing!)
            stop_loss: Absolute stop loss price (if provided, sl_pct is ignored)
            target: Absolute target price (if provided, target_pct is ignored)
            sl_pct: Stop loss % below entry (default: 1%, used if stop_loss not provided)
            target_pct: Target % above entry (default: 2%, used if target not provided)
        
        Returns:
            Dict with order details
        """
        sl_pct = sl_pct or self.config.sl_pct
        target_pct = target_pct or self.config.target_pct
        
        logger.info(f"\n{'='*60}")
        logger.info(f"  PLACING BUY ORDER: {symbol}")
        logger.info(f"{'='*60}")
        
        try:
            # Get current price
            ltp = await self._get_ltp(symbol)
            if not ltp:
                logger.error(f"❌ Could not get LTP for {symbol}")
                return {"success": False, "error": "Could not get LTP"}
            
            logger.info(f"📊 Current Price (LTP): ₹{ltp:.2f}")
            
            # Use absolute values if provided, otherwise calculate from percentage
            if stop_loss:
                # Validate stop_loss is below LTP for BUY orders
                if stop_loss >= ltp:
                    logger.error(f"❌ Stop loss (₹{stop_loss:.2f}) must be below LTP (₹{ltp:.2f}) for BUY orders")
                    return {"success": False, "error": "Stop loss must be below LTP for BUY orders"}
                sl_pct_actual = ((ltp - stop_loss) / ltp) * 100
                logger.info(f"📉 Stop Loss: ₹{stop_loss:.2f} ({sl_pct_actual:.2f}% below LTP)")
            else:
                stop_loss = round(ltp * (1 - sl_pct / 100), 2)
                logger.info(f"📉 Stop Loss ({sl_pct}%): ₹{stop_loss:.2f}")
            
            if target:
                # Validate target is above LTP for BUY orders
                if target <= ltp:
                    logger.error(f"❌ Target (₹{target:.2f}) must be above LTP (₹{ltp:.2f}) for BUY orders")
                    return {"success": False, "error": "Target must be above LTP for BUY orders"}
                target_pct_actual = ((target - ltp) / ltp) * 100
                logger.info(f"📈 Target: ₹{target:.2f} ({target_pct_actual:.2f}% above LTP)")
            else:
                target = round(ltp * (1 + target_pct / 100), 2)
                logger.info(f"📈 Target ({target_pct}%): ₹{target:.2f}")
            logger.info(f"📦 Quantity: {quantity}")
            logger.info(f"💰 Est. Value: ₹{ltp * quantity:.2f}")
            logger.info("")
            
            # Confirmation
            response = input("🔴 Place REAL order? (type 'YES' to confirm): ")
            if response.strip().upper() != 'YES':
                logger.info("Order cancelled by user")
                return {"success": False, "error": "Cancelled by user"}
            
            # Get instrument token (with validation)
            logger.info("\n⏳ Getting instrument token...")
            instrument_token = await self._get_instrument_token(symbol)
            if not instrument_token:
                logger.error(f"❌ Invalid symbol: {symbol} - instrument token not found")
                return {"success": False, "error": f"Invalid symbol: {symbol}"}
            logger.info(f"   Instrument token: {instrument_token}")
            
            # Create signal
            signal = Signal(
                symbol=symbol,
                instrument_token=instrument_token,
                signal_type=SignalType.BUY,
                price=ltp,
                stop_loss=stop_loss,
                target=target,
                quantity=quantity,
                reason="Manual test order",
                timestamp=now_ist()
            )
            
            # Place order
            logger.info("\n⏳ Placing order...")
            result = await self.order_manager.place_order(
                signal=signal,
                quantity=quantity,
                strategy_name="MANUAL_TEST",
                order_type="MARKET",
                product=self.config.product
            )
            
            if result.entry_order_id:
                logger.info(f"✅ ORDER PLACED SUCCESSFULLY!")
                logger.info(f"   Entry Order ID: {result.entry_order_id}")
                logger.info(f"   SL Order ID: {result.sl_order_id}")
                logger.info(f"   Quantity: {result.quantity}")
                
                # Wait and sync position from Kite to DB with retry logic
                # Kite may take a few seconds to register the position
                logger.info("\n🔄 Syncing position from Kite to DB (with retry)...")
                pos = None
                max_retries = 3
                
                for attempt in range(max_retries):
                    wait_time = 2 + attempt  # 2s, 3s, 4s
                    logger.info(f"   Attempt {attempt + 1}/{max_retries}: waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    
                    # Sync positions from Kite to DB
                    synced = await self.position_manager.sync_positions_from_kite()
                    logger.info(f"   Positions synced: {synced}")
                    
                    # Check if position was created
                    pos = await self.position_manager.position_repo.get_position_by_symbol(
                        symbol=symbol, status="OPEN"
                    )
                    
                    if pos:
                        logger.info(f"   ✅ Position ID in DB: {pos['id']}")
                        break
                    else:
                        logger.warning(f"   Position not yet in DB, retrying...")
                
                if not pos:
                    logger.warning("   ⚠️ Position not found in DB after all retries - check Kite console")
                    logger.warning("   The order may have been placed but position sync failed.")
                    logger.warning("   Run '--action status' to verify.")
                
                return {
                    "success": True,
                    "entry_order_id": result.entry_order_id,
                    "sl_order_id": result.sl_order_id,
                    "quantity": quantity,
                    "entry_price": ltp,
                    "stop_loss": stop_loss,
                    "target": target
                }
            else:
                logger.error(f"❌ Order failed: {result.error}")
                return {"success": False, "error": result.error}
                
        except Exception as e:
            logger.error(f"❌ Error placing order: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    # ================================================================
    # MONITORING
    # ================================================================
    
    async def show_status(self):
        """Show comprehensive status of all positions and orders"""
        logger.info(f"\n{'='*60}")
        logger.info(f"  STATUS REPORT - {now_ist().strftime('%H:%M:%S')}")
        logger.info(f"{'='*60}\n")
        
        # Get positions from Kite
        await self._show_kite_positions()
        
        # Get orders from Kite
        await self._show_kite_orders()
        
        # Get positions from DB
        await self._show_db_positions()
        
        # Get margins
        await self._show_margins()
    
    async def _show_kite_positions(self):
        """Show positions from Kite"""
        logger.info("📊 KITE POSITIONS (Live)")
        logger.info("-" * 50)
        
        try:
            positions = self.kite.kite.positions()
            day_positions = positions.get('day', [])
            
            if not day_positions:
                logger.info("   No positions found")
            else:
                for pos in day_positions:
                    if pos['quantity'] != 0:
                        pnl = pos.get('pnl', 0)
                        pnl_color = "🟢" if pnl >= 0 else "🔴"
                        logger.info(
                            f"   {pos['tradingsymbol']}: "
                            f"Qty={pos['quantity']} | "
                            f"Avg=₹{pos['average_price']:.2f} | "
                            f"LTP=₹{pos['last_price']:.2f} | "
                            f"{pnl_color} P&L=₹{pnl:.2f}"
                        )
        except Exception as e:
            logger.error(f"   Error fetching positions: {e}")
        
        logger.info("")
    
    async def _show_kite_orders(self):
        """Show orders from Kite"""
        logger.info("📋 KITE ORDERS (Today)")
        logger.info("-" * 50)
        
        try:
            orders = self.kite.kite.orders()
            
            # Filter for today's active orders
            active_orders = [o for o in orders if o['status'] in ['OPEN', 'TRIGGER PENDING', 'PENDING']]
            completed_orders = [o for o in orders if o['status'] == 'COMPLETE'][-5:]  # Last 5
            
            if not active_orders:
                logger.info("   No active orders")
            else:
                logger.info("   Active Orders:")
                for order in active_orders:
                    logger.info(
                        f"     {order['order_id']}: {order['tradingsymbol']} | "
                        f"{order['transaction_type']} {order['quantity']} | "
                        f"Type={order['order_type']} | "
                        f"Status={order['status']}"
                    )
                    if order.get('trigger_price'):
                        logger.info(f"       Trigger: ₹{order['trigger_price']:.2f}")
            
            if completed_orders:
                logger.info("\n   Recent Completed:")
                for order in completed_orders:
                    logger.info(
                        f"     {order['order_id']}: {order['tradingsymbol']} | "
                        f"{order['transaction_type']} {order['quantity']} @ ₹{order.get('average_price', 0):.2f}"
                    )
        except Exception as e:
            logger.error(f"   Error fetching orders: {e}")
        
        logger.info("")
    
    async def _show_db_positions(self):
        """Show positions from DB"""
        logger.info("💾 DATABASE POSITIONS")
        logger.info("-" * 50)
        
        try:
            positions = await self.position_manager.position_repo.get_open_positions()
            
            if not positions:
                logger.info("   No open positions in DB")
            else:
                for pos in positions:
                    logger.info(
                        f"   ID={pos['id']}: {pos['symbol']} | "
                        f"Entry=₹{pos['entry_price']:.2f} | "
                        f"SL=₹{pos['stop_loss']:.2f} | "
                        f"Target=₹{pos['target']:.2f}"
                    )
                    if pos.get('highest_price'):
                        logger.info(f"       Highest Price: ₹{pos['highest_price']:.2f}")
                    if pos.get('sl_order_id'):
                        logger.info(f"       SL Order ID: {pos['sl_order_id']}")
        except Exception as e:
            logger.error(f"   Error fetching DB positions: {e}")
        
        logger.info("")
    
    async def _show_margins(self):
        """Show margin info"""
        logger.info("💰 MARGIN INFO")
        logger.info("-" * 50)
        
        try:
            margins = self.kite.kite.margins()
            equity = margins.get('equity', {})
            
            logger.info(f"   Available: ₹{equity.get('available', {}).get('cash', 0):,.2f}")
            logger.info(f"   Used: ₹{equity.get('utilised', {}).get('debits', 0):,.2f}")
            logger.info(f"   Net: ₹{equity.get('net', 0):,.2f}")
        except Exception as e:
            logger.error(f"   Error fetching margins: {e}")
        
        logger.info("")
    
    async def monitor_loop(self, interval: int = 30):
        """
        Continuously monitor positions with periodic status updates.
        
        NOTE: This is for MANUAL TESTING only. In production, background
        jobs in sync_jobs.py handle:
        - Order sync (every 1 min)
        - Position sync (every 1 min)
        - Trailing SL (every 30 sec)
        
        Args:
            interval: Seconds between updates
        """
        logger.info(f"\n🔄 Starting monitor loop (interval: {interval}s)")
        logger.info("   Press Ctrl+C to stop")
        logger.info("")
        logger.info("   ℹ️  NOTE: In production, background jobs handle sync automatically.")
        logger.info("   This monitor is for manual observation during testing.\n")
        
        try:
            while True:
                await self.show_status()
                
                logger.info(f"⏳ Next update in {interval} seconds...")
                await asyncio.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("\n⏹️  Monitor stopped by user")
    
    # ================================================================
    # TRAILING STOP LOSS
    # ================================================================
    
    async def process_trailing_sl(self):
        """Process trailing stop loss for all positions"""
        logger.info(f"\n{'='*60}")
        logger.info(f"  TRAILING STOP LOSS UPDATE")
        logger.info(f"{'='*60}\n")
        
        # First show current state
        await self._show_db_positions()
        
        # Get current prices
        logger.info("📊 Current Prices from Kite:")
        positions = await self.position_manager.position_repo.get_open_positions()
        for pos in positions:
            ltp = await self._get_ltp(pos['symbol'])
            if ltp:
                entry = float(pos['entry_price'])
                current_sl = float(pos['stop_loss'])
                profit_pct = ((ltp - entry) / entry) * 100
                profit_color = "🟢" if profit_pct >= 0 else "🔴"
                logger.info(
                    f"   {pos['symbol']}: LTP=₹{ltp:.2f} | "
                    f"Entry=₹{entry:.2f} | "
                    f"{profit_color} Profit={profit_pct:.2f}%"
                )
        
        logger.info("\n⏳ Processing trailing SL...")
        stats = await self.trailing_sl_service.process_positions()
        
        logger.info(f"\n📈 TRAILING SL RESULTS:")
        logger.info(f"   Positions checked: {stats['checked']}")
        logger.info(f"   SL orders updated: {stats['updated']}")
        logger.info(f"   Errors: {stats['errors']}")
        
        if stats['updated'] > 0:
            logger.info("\n✅ SL orders modified! Showing updated positions:")
            await self._show_db_positions()
        
        return stats
    
    # ================================================================
    # EXIT POSITIONS
    # ================================================================
    
    async def exit_position(self, symbol: str):
        """
        Exit a specific position and cancel SL order.
        
        Args:
            symbol: Stock symbol to exit
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"  EXIT POSITION: {symbol}")
        logger.info(f"{'='*60}\n")
        
        try:
            # Get position from DB
            pos = await self.position_manager.position_repo.get_position_by_symbol(
                symbol=symbol,
                status="OPEN"
            )
            
            if not pos:
                logger.error(f"❌ No open position found for {symbol}")
                return {"success": False, "error": "Position not found"}
            
            quantity = pos['quantity']
            sl_order_id = pos.get('sl_order_id')
            ltp = await self._get_ltp(symbol)
            entry_price = float(pos['entry_price'])
            
            logger.info(f"📊 Position Details:")
            logger.info(f"   Symbol: {symbol}")
            logger.info(f"   Quantity: {quantity}")
            logger.info(f"   Entry: ₹{entry_price:.2f}")
            logger.info(f"   Current: ₹{ltp:.2f}")
            logger.info(f"   P&L: ₹{(ltp - entry_price) * quantity:.2f}")
            logger.info(f"   SL Order: {sl_order_id}")
            
            # Confirmation
            response = input("\n🔴 Exit this position? (type 'YES' to confirm): ")
            if response != 'YES':
                logger.info("Exit cancelled by user")
                return {"success": False, "error": "Cancelled by user"}
            
            # Exit position
            logger.info("\n⏳ Placing exit order...")
            exit_order_id = await self.order_manager.exit_position(
                symbol=symbol,
                quantity=quantity,
                transaction_type="SELL",
                product=self.config.product,
                sl_order_id=sl_order_id
            )
            
            if exit_order_id:
                logger.info(f"✅ EXIT ORDER PLACED!")
                logger.info(f"   Exit Order ID: {exit_order_id}")
                
                # Update DB
                await self.position_manager.position_repo.close_position(
                    position_id=pos['id'],
                    exit_price=ltp,
                    exit_time=now_ist(),
                    exit_reason="MANUAL_EXIT",
                    exit_order_id=exit_order_id
                )
                logger.info(f"   Position marked closed in DB")
                
                return {
                    "success": True,
                    "exit_order_id": exit_order_id,
                    "exit_price": ltp,
                    "pnl": (ltp - entry_price) * quantity
                }
            else:
                logger.error("❌ Exit order failed")
                return {"success": False, "error": "Exit order failed"}
                
        except Exception as e:
            logger.error(f"❌ Error exiting position: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def exit_all_positions(self):
        """Exit all open positions (EOD square off)"""
        logger.info(f"\n{'='*60}")
        logger.info(f"  EXIT ALL POSITIONS")
        logger.info(f"{'='*60}\n")
        
        # Get all open positions
        positions = await self.position_manager.position_repo.get_open_positions()
        
        if not positions:
            logger.info("No open positions to exit")
            return {"success": True, "closed": 0}
        
        logger.info(f"Found {len(positions)} open position(s):")
        for pos in positions:
            logger.info(f"   - {pos['symbol']}: {pos['quantity']} shares")
        
        response = input("\n🔴 Exit ALL positions? (type 'YES' to confirm): ")
        if response != 'YES':
            logger.info("Exit all cancelled by user")
            return {"success": False, "error": "Cancelled by user"}
        
        closed = 0
        for pos in positions:
            result = await self.exit_position(pos['symbol'])
            if result.get('success'):
                closed += 1
        
        logger.info(f"\n✅ Closed {closed}/{len(positions)} positions")
        return {"success": True, "closed": closed, "total": len(positions)}
    
    # ================================================================
    # HELPER METHODS
    # ================================================================
    
    async def _get_ltp(self, symbol: str) -> Optional[float]:
        """Get last traded price for symbol"""
        try:
            exchange_symbol = f"NSE:{symbol}"
            quotes = self.kite.kite.quote([exchange_symbol])
            return quotes[exchange_symbol]['last_price']
        except Exception as e:
            logger.error(f"Error getting LTP for {symbol}: {e}")
            return None
    
    async def _get_instrument_token(self, symbol: str) -> int:
        """
        Get instrument token for symbol using quote API (faster).
        
        Uses quote API instead of fetching all instruments (~3000+),
        which is much faster (single API call vs large data fetch).
        """
        try:
            # Use quote API - much faster than fetching all instruments
            exchange_symbol = f"NSE:{symbol}"
            quotes = self.kite.kite.quote([exchange_symbol])
            
            if exchange_symbol in quotes:
                return quotes[exchange_symbol]['instrument_token']
            
            logger.warning(f"Instrument token not found for {symbol}")
            return 0
        except Exception as e:
            logger.error(f"Error getting instrument token for {symbol}: {e}")
            return 0


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Live MIS Order Testing Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ACTIONS:
  preflight  Run pre-flight checks (DB, Kite, columns)
  buy        Place a BUY order with SL
  monitor    Continuously monitor positions (read-only)
  status     Show current status once
  trail      Manually trigger trailing SL update
  exit       Exit a specific position
  exit_all   Exit all open positions

NOTE: In production, trailing SL updates happen automatically via background jobs
      in sync_jobs.py (every 30 seconds during market hours).

EXAMPLES:
  # Run pre-flight checks before testing
  python test_mis_order_live.py --action preflight
  
  # Place a test order
  python test_mis_order_live.py --action buy --symbol RELIANCE --quantity 1
  
  # Monitor with 60s interval
  python test_mis_order_live.py --action monitor --interval 60
  
  # Check status
  python test_mis_order_live.py --action status
  
  # Manually trigger trailing SL
  python test_mis_order_live.py --action trail
  
  # Exit specific position
  python test_mis_order_live.py --action exit --symbol RELIANCE
  
  # Exit all positions
  python test_mis_order_live.py --action exit_all
        """
    )
    
    parser.add_argument(
        '--action', 
        required=True,
        choices=['preflight', 'buy', 'monitor', 'status', 'trail', 'exit', 'exit_all'],
        help='Action to perform'
    )
    parser.add_argument('--symbol', help='Stock symbol (e.g., RELIANCE)')
    parser.add_argument('--quantity', type=int, default=1, help='Order quantity (default: 1)')
    parser.add_argument('--stop-loss', type=float, help='Absolute stop loss price (e.g., 1280.50)')
    parser.add_argument('--target', type=float, help='Absolute target price (e.g., 1320.00)')
    parser.add_argument('--sl-pct', type=float, default=1.0, help='Stop loss %% below LTP (default: 1.0, ignored if --stop-loss provided)')
    parser.add_argument('--target-pct', type=float, default=2.0, help='Target %% above LTP (default: 2.0, ignored if --target provided)')
    parser.add_argument('--interval', type=int, default=30, help='Monitor interval in seconds (default: 30)')
    # Trailing SL config (for testing)
    parser.add_argument('--trail-activation', type=float, default=0.5, help='Trailing SL activation %% (default: 0.5)')
    parser.add_argument('--trail-pct', type=float, default=0.3, help='Trailing SL distance %% below high (default: 0.3)')
    parser.add_argument('--trail-min-move', type=float, default=0.1, help='Min SL move %% to trigger update (default: 0.1)')
    
    args = parser.parse_args()
    
    # Create logs directory
    Path('logs').mkdir(exist_ok=True)
    
    # Initialize tester
    config = TestConfig(
        sl_pct=args.sl_pct,
        target_pct=args.target_pct,
        trail_activation_pct=args.trail_activation,
        trail_pct=args.trail_pct,
        trail_min_move_pct=args.trail_min_move
    )
    tester = LiveMISOrderTester(config)
    
    try:
        # Handle preflight separately (partial init)
        if args.action == 'preflight':
            await tester.run_preflight_checks()
            return
        
        if not await tester.initialize():
            return
        
        # Execute action
        if args.action == 'buy':
            if not args.symbol:
                logger.error("--symbol is required for buy action")
                return
            await tester.place_buy_order(
                symbol=args.symbol.upper(),
                quantity=args.quantity,
                stop_loss=args.stop_loss,
                target=args.target,
                sl_pct=args.sl_pct,
                target_pct=args.target_pct
            )
            
        elif args.action == 'monitor':
            await tester.monitor_loop(interval=args.interval)
            
        elif args.action == 'status':
            await tester.show_status()
            
        elif args.action == 'trail':
            await tester.process_trailing_sl()
            
        elif args.action == 'exit':
            if not args.symbol:
                logger.error("--symbol is required for exit action")
                return
            await tester.exit_position(args.symbol.upper())
            
        elif args.action == 'exit_all':
            await tester.exit_all_positions()
            
    except KeyboardInterrupt:
        logger.info("\n⏹️  Stopped by user")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
