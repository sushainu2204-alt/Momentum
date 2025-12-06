"""
Background Sync Jobs

Scheduled tasks to keep database synchronized with Zerodha Kite.

ALWAYS RUN (anytime, even after market hours):
- Order sync: Update order status from Kite
- Position sync: Update P&L and detect manual closures
- Margins sync: Update capital state from Kite

MARKET HOURS ONLY (9:15 AM - 3:30 PM):
- Position monitoring: Check exit conditions and generate exit signals
- Trailing stop loss: Adjust SL orders based on profit
- Daily initialization: Initialize capital at market open
"""

from datetime import datetime, time
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.core.services import (
    OrderManager,
    PositionManager,
    CapitalManager,
    SignalExecutor,
    TrailingSLService as TrailingStopLossService,
)
from backend.core.utils.timezone import now_ist, is_market_hours
from backend.config.logging_config import setup_logging

# Use configured logging
logger = setup_logging(name="sync_jobs", log_to_file=True)


class SyncJobsScheduler:
    """
    Manages background sync jobs for trading system.
    
    ALWAYS RUN (even outside market hours):
    1. Order sync - Every 1 minute
    2. Position sync - Every 1 minute  
    3. Margins sync - Every 30 seconds
    
    MARKET HOURS ONLY (9:15 AM - 3:30 PM):
    4. Position monitoring - Every 1 minute
    5. Trailing stop loss - Every 30 seconds
    6. Daily initialization - At market open (9:15 AM)
    """
    
    def __init__(
        self,
        order_manager: OrderManager,
        position_manager: PositionManager,
        capital_manager: CapitalManager,
        signal_executor: SignalExecutor,
        trailing_sl_service: Optional[TrailingStopLossService] = None,
        market_open: time = time(9, 15),
        market_close: time = time(15, 30),
    ):
        self.order_manager = order_manager
        self.position_manager = position_manager
        self.capital_manager = capital_manager
        self.signal_executor = signal_executor
        self.trailing_sl_service = trailing_sl_service
        
        self.market_open = market_open
        self.market_close = market_close
        
        self.scheduler = AsyncIOScheduler()
        self._is_running = False
    
    # ================================================================
    # SCHEDULER CONTROL
    # ================================================================
    
    def start(self):
        """Start all background jobs"""
        if self._is_running:
            logger.warning("Sync jobs already running")
            return
        
        logger.info("Starting background sync jobs...")
        
        # Job 1: Order sync - Every 1 minute
        self.scheduler.add_job(
            self._sync_orders_job,
            trigger=IntervalTrigger(seconds=5),
            id="sync_orders",
            name="Sync Orders from Kite",
            max_instances=1,
            coalesce=True
        )
        
        # Job 2: Position sync - Every 1 minute
        self.scheduler.add_job(
            self._sync_positions_job,
            trigger=IntervalTrigger(seconds=5),
            id="sync_positions",
            name="Sync Positions from Kite",
            max_instances=1,
            coalesce=True
        )
        
        # Job 3: Margins sync - Every 30 seconds
        self.scheduler.add_job(
            self._sync_margins_job,
            trigger=IntervalTrigger(seconds=5),
            id="sync_margins",
            name="Sync Margins from Kite",
            max_instances=1,
            coalesce=True
        )
        
        # Job 4: Position monitoring - Every 1 minute
        self.scheduler.add_job(
            self._monitor_positions_job,
            trigger=IntervalTrigger(seconds=5),
            id="monitor_positions",
            name="Monitor Positions and Check Exits",
            max_instances=1,
            coalesce=True
        )
        
        # Job 5: Daily initialization - At 9:15 AM
        self.scheduler.add_job(
            self._daily_initialization_job,
            trigger=CronTrigger(
                hour=self.market_open.hour,
                minute=self.market_open.minute,
                day_of_week='mon-fri'
            ),
            id="daily_init",
            name="Daily Capital Initialization",
            max_instances=1,
            coalesce=True
        )
        
        # Job 6: Trailing stop loss - Every 30 seconds
        if self.trailing_sl_service:
            self.scheduler.add_job(
                self._trailing_sl_job,
                trigger=IntervalTrigger(seconds=5),
                id="trailing_sl",
                name="Update Trailing Stop Losses",
                max_instances=1,
                coalesce=True
            )
        
        # Start scheduler
        self.scheduler.start()
        self._is_running = True
        
        logger.info("✅ All background sync jobs started")
        self._log_job_schedule()
    
    def stop(self):
        """Stop all background jobs"""
        if not self._is_running:
            logger.warning("Sync jobs not running")
            return
        
        logger.info("Stopping background sync jobs...")
        self.scheduler.shutdown(wait=True)
        self._is_running = False
        logger.info("✅ All background sync jobs stopped")
    
    def pause(self):
        """Pause all jobs"""
        self.scheduler.pause()
        logger.info("Background sync jobs paused")
    
    def resume(self):
        """Resume all jobs"""
        self.scheduler.resume()
        logger.info("Background sync jobs resumed")
    
    # ================================================================
    # JOB IMPLEMENTATIONS
    # ================================================================
    
    async def _sync_orders_job(self):
        """
        Job 1: Sync orders from Kite to database.
        
        Updates order status, detects fills/rejections.
        RUNS ANYTIME - order status can be checked even after market hours.
        """
        try:
            logger.info("📋 [SYNC] Syncing orders from Kite...")
            result = await self.order_manager.sync_orders_from_kite()
            if result:
                logger.info(f"✅ [SYNC] Order sync: {result}")
            else:
                logger.info("✅ [SYNC] Order sync completed (no changes)")
            
        except Exception as e:
            logger.error(f"❌ [SYNC] Order sync failed: {e}", exc_info=True)
    
    async def _sync_positions_job(self):
        """
        Job 2: Sync positions from Kite to database.
        
        Updates P&L, detects manual closures.
        RUNS ANYTIME - position data can be synced even after market hours.
        """
        try:
            logger.info("📊 [SYNC] Syncing positions from Kite...")
            result = await self.position_manager.sync_positions_from_kite()
            if result:
                logger.info(f"✅ [SYNC] Position sync: {result}")
            else:
                logger.info("✅ [SYNC] Position sync completed (no changes)")
            
        except Exception as e:
            logger.error(f"❌ [SYNC] Position sync failed: {e}", exc_info=True)
    
    async def _sync_margins_job(self):
        """
        Job 3: Sync margins from Kite to database.
        
        Updates capital state, available funds.
        RUNS ANYTIME - margin data can be synced even after market hours.
        """
        try:
            logger.info("💰 [SYNC] Syncing margins from Kite...")
            result = await self.capital_manager.sync_margins_to_db()
            if result:
                logger.info(f"✅ [SYNC] Margins sync: available=₹{result.get('available', 0):,.2f}")
            else:
                logger.info("✅ [SYNC] Margins sync completed")
            
        except Exception as e:
            logger.error(f"❌ [SYNC] Margins sync failed: {e}", exc_info=True)
    
    async def _monitor_positions_job(self):
        """
        Job 4: Monitor positions and check exit conditions.
        
        Places exit orders when needed, but DB closure happens via sync.
        Position records are closed ONLY when Kite confirms position is closed.
        
        MARKET HOURS ONLY - no point monitoring when market is closed.
        """
        if not self._is_market_hours():
            logger.debug("⏸️ [MONITOR] Skipping position monitoring (market closed)")
            return
        
        try:
            logger.info("👁️ [MONITOR] Monitoring positions...")
            
            current_time = now_ist()
            
            # Check if it's time to exit all positions (3:15 PM - before Zerodha's 3:20 PM auto square-off)
            if self.signal_executor.should_exit_all_positions(current_time):
                logger.info("🔔 Auto-exit time reached (3:15 PM) - exiting all positions (before Zerodha's 3:20 PM square-off)")
                
                # Get DB positions first (to get sl_order_ids for cancellation)
                # TODO : Get from kite directly
                db_positions = await self.position_manager.get_open_positions()
                
                # Exit all positions (this also cancels SL orders)
                exited = await self.order_manager.exit_all_positions(db_positions=db_positions)
                logger.info(f"✅ Exited {exited} positions (SL orders cancelled)")
                
                if db_positions:
                    logger.info(f"⏳ {len(db_positions)} position records will be closed when Kite confirms exits (next sync)")
            
            # Always sync positions to update P&L and detect closures
            # This will close DB positions when Kite shows quantity=0
            logger.debug("Syncing positions from Kite (updates P&L, detects closures)")
            
            # Get DB positions before sync (to have sl_order_ids)
            db_positions_for_cleanup = await self.position_manager.get_open_positions()
            
            # Sync positions (updates P&L, closes DB records for closed positions)
            await self.position_manager.sync_positions_from_kite()
            
            # Clean up orphaned SL orders (positions closed in Kite but SL order still pending)
            if db_positions_for_cleanup:
                # Get current open positions from Kite to find which ones closed
                kite_positions = self.position_manager.kite.kite.positions().get('day', [])
                open_symbols = [p['tradingsymbol'] for p in kite_positions if p.get('quantity', 0) != 0]
                
                # Cancel SL orders for positions that are no longer open
                await self.order_manager.cancel_orphaned_sl_orders(
                    open_position_symbols=open_symbols,
                    db_positions=db_positions_for_cleanup
                )
            
            logger.info("✅ [MONITOR] Position monitoring completed")
            
        except Exception as e:
            logger.error(f"❌ [MONITOR] Position monitoring failed: {e}", exc_info=True)
    
    async def _daily_initialization_job(self):
        """
        Job 5: Daily initialization at market open.
        
        Initializes capital state from Kite opening balance.
        """
        try:
            logger.info("🌅 Market open - initializing daily capital...")
            await self.capital_manager.initialize_daily_capital()
            
            # Get summary
            summary = await self.capital_manager.get_capital_summary()
            logger.info(
                f"✅ Daily capital initialized: ₹{summary.get('starting_capital', 0):,.2f}"
            )
            
        except Exception as e:
            logger.error(f"Error in daily initialization job: {e}", exc_info=True)
    
    async def _trailing_sl_job(self):
        """
        Job 6: Update trailing stop losses for open positions.
        
        Monitors price movements and adjusts stop loss orders on Kite
        when positions reach configured profit thresholds.
        
        MARKET HOURS ONLY - trailing SL only makes sense when market is live.
        """
        if not self._is_market_hours():
            logger.debug("⏸️ [TRAIL] Skipping trailing SL (market closed)")
            return
        
        if not self.trailing_sl_service:
            return
        
        try:
            logger.info("📈 [TRAIL] Processing trailing stop losses...")
            result = await self.trailing_sl_service.process_positions()
            
            if result["updated"] > 0:
                logger.info(
                    f"✅ [TRAIL] Trailing SL: {result['updated']} updated, "
                    f"{result['checked']} checked, {result['errors']} errors"
                )
            else:
                logger.info(f"✅ [TRAIL] Trailing SL: no updates needed ({result['checked']} positions checked)")
            
        except Exception as e:
            logger.error(f"❌ [TRAIL] Trailing SL failed: {e}", exc_info=True)
    
    # ================================================================
    # HELPER METHODS
    # ================================================================
    
    def _is_market_hours(self) -> bool:
        """Check if currently in market hours"""
        return is_market_hours()
    
    def _log_job_schedule(self):
        """Log scheduled jobs"""
        logger.info("📋 Scheduled Jobs:")
        logger.info("  ── ALWAYS RUN (anytime) ──")
        logger.info(f"  1. Order Sync        - Every 1 minute")
        logger.info(f"  2. Position Sync     - Every 1 minute")
        logger.info(f"  3. Margins Sync      - Every 30 seconds")
        logger.info("  ── MARKET HOURS ONLY (9:15-15:30) ──")
        logger.info(f"  4. Position Monitor  - Every 1 minute")
        if self.trailing_sl_service:
            logger.info(f"  5. Trailing SL       - Every 30 seconds")
        logger.info(f"  6. Daily Init        - {self.market_open} (Mon-Fri)")
    
    # ================================================================
    # MANUAL TRIGGERS (FOR TESTING)
    # ================================================================
    
    async def trigger_order_sync(self):
        """Manually trigger order sync"""
        logger.info("Manual trigger: Order sync")
        await self._sync_orders_job()
    
    async def trigger_position_sync(self):
        """Manually trigger position sync"""
        logger.info("Manual trigger: Position sync")
        await self._sync_positions_job()
    
    async def trigger_margins_sync(self):
        """Manually trigger margins sync"""
        logger.info("Manual trigger: Margins sync")
        await self._sync_margins_job()
    
    async def trigger_position_monitoring(self):
        """Manually trigger position monitoring"""
        logger.info("Manual trigger: Position monitoring")
        await self._monitor_positions_job()
    
    async def trigger_daily_init(self):
        """Manually trigger daily initialization"""
        logger.info("Manual trigger: Daily initialization")
        await self._daily_initialization_job()
    
    async def trigger_trailing_sl(self):
        """Manually trigger trailing stop loss update"""
        logger.info("Manual trigger: Trailing stop loss")
        await self._trailing_sl_job()
    
    # ================================================================
    # STATUS AND MONITORING
    # ================================================================
    
    def get_job_status(self) -> dict:
        """Get status of all jobs"""
        jobs = self.scheduler.get_jobs()
        
        return {
            "running": self._is_running,
            "paused": self.scheduler.state == 2,  # STATE_PAUSED
            "market_hours": self._is_market_hours(),
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    "pending": job.pending
                }
                for job in jobs
            ]
        }
    
    def get_job_history(self) -> list:
        """Get execution history (if available)"""
        # APScheduler doesn't store history by default
        # You could add a JobListener to track execution history
        return []
