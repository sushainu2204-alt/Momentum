#!/usr/bin/env python3
"""
Manual test script to verify sync jobs actually call Kite API.
Runs sync jobs once regardless of market hours.

Usage:
    python non-prod/scripts/manual/test_sync_manual.py
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.infrastructure.database.factory import create_database
from backend.core.services.kite_service import KiteService
from backend.infrastructure.database.order_repository import OrderRepository
from backend.infrastructure.database.position_repository import PositionRepository
from backend.core.services.order_manager import OrderManager
from backend.core.services.position_manager import PositionManager
from backend.core.services.capital_manager import CapitalManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Test sync jobs manually"""
    db = None
    try:
        logger.info("=" * 80)
        logger.info("  MANUAL SYNC JOBS TEST")
        logger.info("=" * 80)
        logger.info("")
        
        # Initialize
        db = create_database()
        await db.connect()
        logger.info("✓ Database connected")
        
        kite_service = KiteService()
        logger.info("✓ Kite service initialized")
        
        order_repo = OrderRepository(db)
        position_repo = PositionRepository(db)
        
        order_manager = OrderManager(kite_service=kite_service, order_repository=order_repo)
        position_manager = PositionManager(
            kite_service=kite_service,
            position_repository=position_repo,
            order_repository=order_repo  # Needed for sync_positions_from_kite to look up sl_order_id
        )
        capital_manager = CapitalManager(
            database=db,
            kite_service=kite_service,
            position_manager=position_manager
        )
        logger.info("✓ All managers initialized")
        logger.info("")
        
        # Test 1: Sync orders from Kite
        logger.info("TEST 1: Syncing orders from Kite...")
        try:
            await order_manager.sync_orders_from_kite()
            logger.info("✅ Order sync completed")
        except Exception as e:
            logger.error(f"❌ Order sync failed: {e}")
        logger.info("")
        
        # Test 2: Sync positions from Kite
        logger.info("TEST 2: Syncing positions from Kite...")
        try:
            await position_manager.sync_positions_from_kite()
            logger.info("✅ Position sync completed")
        except Exception as e:
            logger.error(f"❌ Position sync failed: {e}")
        logger.info("")
        
        # Test 3: Sync margins from Kite
        logger.info("TEST 3: Syncing margins from Kite...")
        try:
            await capital_manager.sync_margins_to_db()
            logger.info("✅ Margins sync completed")
        except Exception as e:
            logger.error(f"❌ Margins sync failed: {e}")
        logger.info("")
        
        # Test 4: Check database
        logger.info("TEST 4: Checking database for updates...")
        
        # Count orders
        result = await db.fetch_one("SELECT COUNT(*) as count FROM orders")
        logger.info(f"  Orders in DB: {result['count']}")
        
        # Count positions
        result = await db.fetch_one("SELECT COUNT(*) as count FROM positions")
        logger.info(f"  Positions in DB: {result['count']}")
        
        # Check capital state
        result = await db.fetch_one("SELECT * FROM capital_state ORDER BY updated_at DESC LIMIT 1")
        if result:
            logger.info(f"  Capital state: ₹{result['current_capital']:,.2f} (updated: {result['updated_at']})")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ Manual sync test completed")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Error in manual test: {e}", exc_info=True)
    finally:
        if db:
            await db.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
