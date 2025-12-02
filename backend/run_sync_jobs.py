#!/usr/bin/env python3
"""
Run Background Sync Jobs

Starts the sync jobs scheduler to keep database synchronized with Kite API.
"""

import asyncio
import signal
import sys
from datetime import time
from dotenv import load_dotenv

from backend.jobs.sync_jobs import SyncJobsScheduler
from backend.core.services.order_manager import OrderManager
from backend.core.services.position_manager import PositionManager
from backend.core.services.capital_manager import CapitalManager
from backend.core.services.signal_executor import SignalExecutor
from backend.core.services.kite_service import KiteService
from backend.core.services.trailing_sl_service import TrailingStopLossService
from backend.infrastructure.database.factory import create_database
from backend.core.logging_config import setup_logging

# Setup logging
logger = setup_logging('sync_jobs')

# Load environment
load_dotenv()

# Global scheduler instance
scheduler = None


def signal_handler(sig, frame):
    """Handle Ctrl-C gracefully"""
    logger.info("\n🛑 Received interrupt signal, shutting down sync jobs...")
    if scheduler:
        scheduler.stop()
    sys.exit(0)


async def main():
    """Main entry point"""
    global scheduler
    
    logger.info("=" * 80)
    logger.info("  BACKGROUND SYNC JOBS")
    logger.info("=" * 80)
    logger.info("")
    logger.info("Jobs:")
    logger.info("  1. Order Sync        - Every 1 minute")
    logger.info("  2. Position Sync     - Every 1 minute")
    logger.info("  3. Margins Sync      - Every 30 seconds")
    logger.info("  4. Position Monitor  - Every 1 minute (includes EOD exit at 3:15 PM)")
    logger.info("  5. Daily Init        - 9:15 AM (Mon-Fri)")
    logger.info("  6. Trailing SL       - Every 30 seconds")
    logger.info("")
    logger.info("=" * 80)
    logger.info("")
    
    # Initialize services
    db = None
    try:
        logger.info("Initializing services...")
        
        # Database (using factory - clean separation of concerns!)
        db = create_database()
        await db.connect()
        logger.info("✓ Database connected")
        
        # Kite service
        kite_service = KiteService()
        logger.info("✓ Kite service initialized")
        
        # Repositories
        from backend.infrastructure.database.order_repository import OrderRepository
        from backend.infrastructure.database.position_repository import PositionRepository
        
        order_repo = OrderRepository(db)
        position_repo = PositionRepository(db)
        logger.info("✓ Repositories initialized")
        
        # Managers
        order_manager = OrderManager(kite_service=kite_service, order_repository=order_repo)
        position_manager = PositionManager(kite_service=kite_service, position_repository=position_repo)
        capital_manager = CapitalManager(
            database=db,
            kite_service=kite_service,
            position_manager=position_manager
            # No mock_capital - sync jobs should use real Kite data
        )
        logger.info("✓ Managers initialized")
        
        # Signal executor (for exit signals)
        signal_executor = SignalExecutor(
            database=db,
            order_manager=order_manager,
            position_manager=position_manager,
            capital_manager=capital_manager
        )
        logger.info("✓ Signal executor initialized")
        
        # Trailing stop loss service
        trailing_sl_service = TrailingStopLossService(
            position_repository=position_repo,
            order_manager=order_manager,
            kite_service=kite_service
        )
        logger.info("✓ Trailing SL service initialized")
        
        # Create scheduler
        scheduler = SyncJobsScheduler(
            order_manager=order_manager,
            position_manager=position_manager,
            capital_manager=capital_manager,
            signal_executor=signal_executor,
            trailing_sl_service=trailing_sl_service,
            market_open=time(9, 15),
            market_close=time(15, 30)
        )
        
        logger.info("")
        logger.info("✅ All services initialized")
        logger.info("")
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start scheduler
        scheduler.start()
        
        logger.info("🚀 Sync jobs started successfully")
        logger.info("")
        logger.info("Press Ctrl-C to stop...")
        logger.info("")
        
        # Keep running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\n🛑 Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Error starting sync jobs: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if scheduler:
            scheduler.stop()
        if db:
            await db.disconnect()
        logger.info("✅ Sync jobs stopped")


if __name__ == '__main__':
    asyncio.run(main())
