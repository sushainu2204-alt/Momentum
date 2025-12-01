"""
Background Sync Jobs

Scheduled tasks to keep database synchronized with Zerodha Kite.
- Order sync: Update order status from Kite
- Position sync: Update P&L and detect manual closures
- Margins sync: Update capital state from Kite
- Position monitoring: Check exit conditions and generate exit signals
- Daily initialization: Initialize capital at market open
"""

from datetime import datetime, time
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.core.services.order_manager import OrderManager
from backend.core.services.position_manager import PositionManager
from backend.core.services.capital_manager import CapitalManager
from backend.core.services.signal_executor import SignalExecutor

logger = logging.getLogger(__name__)


class SyncJobsScheduler:
    """
    Manages background sync jobs for trading system.
    
    Jobs:
    1. Order sync - Every 1 minute during market hours
    2. Position sync - Every 1 minute during market hours
    3. Margins sync - Every 30 seconds during market hours
    4. Position monitoring - Every 1 minute during market hours
    5. Daily initialization - At market open (9:15 AM)
    """
    
    def __init__(
        self,
        order_manager: OrderManager,
        position_manager: PositionManager,
        capital_manager: CapitalManager,
        signal_executor: SignalExecutor,
        market_open: time = time(9, 15),
        market_close: time = time(15, 30)
    ):
        self.order_manager = order_manager
        self.position_manager = position_manager
        self.capital_manager = capital_manager
        self.signal_executor = signal_executor
        
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
            trigger=IntervalTrigger(minutes=1),
            id="sync_orders",
            name="Sync Orders from Kite",
            max_instances=1,
            coalesce=True
        )
        
        # Job 2: Position sync - Every 1 minute
        self.scheduler.add_job(
            self._sync_positions_job,
            trigger=IntervalTrigger(minutes=1),
            id="sync_positions",
            name="Sync Positions from Kite",
            max_instances=1,
            coalesce=True
        )
        
        # Job 3: Margins sync - Every 30 seconds
        self.scheduler.add_job(
            self._sync_margins_job,
            trigger=IntervalTrigger(seconds=30),
            id="sync_margins",
            name="Sync Margins from Kite",
            max_instances=1,
            coalesce=True
        )
        
        # Job 4: Position monitoring - Every 1 minute
        self.scheduler.add_job(
            self._monitor_positions_job,
            trigger=IntervalTrigger(minutes=1),
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
        """
        if not self._is_market_hours():
            logger.debug("Outside market hours - skipping order sync")
            return
        
        try:
            logger.debug("Starting order sync job...")
            await self.order_manager.sync_orders_from_kite()
            logger.debug("✅ Order sync completed")
            
        except Exception as e:
            logger.error(f"Error in order sync job: {e}", exc_info=True)
    
    async def _sync_positions_job(self):
        """
        Job 2: Sync positions from Kite to database.
        
        Updates P&L, detects manual closures.
        """
        if not self._is_market_hours():
            logger.debug("Outside market hours - skipping position sync")
            return
        
        try:
            logger.debug("Starting position sync job...")
            await self.position_manager.sync_positions_from_kite()
            logger.debug("✅ Position sync completed")
            
        except Exception as e:
            logger.error(f"Error in position sync job: {e}", exc_info=True)
    
    async def _sync_margins_job(self):
        """
        Job 3: Sync margins from Kite to database.
        
        Updates capital state, available funds.
        """
        if not self._is_market_hours():
            logger.debug("Outside market hours - skipping margins sync")
            return
        
        try:
            logger.debug("Starting margins sync job...")
            await self.capital_manager.sync_margins_to_db()
            logger.debug("✅ Margins sync completed")
            
        except Exception as e:
            logger.error(f"Error in margins sync job: {e}", exc_info=True)
    
    async def _monitor_positions_job(self):
        """
        Job 4: Monitor positions and check exit conditions.
        
        Places exit orders when needed, but DB closure happens via sync.
        Position records are closed ONLY when Kite confirms position is closed.
        """
        if not self._is_market_hours():
            logger.debug("Outside market hours - skipping position monitoring")
            return
        
        try:
            logger.debug("Starting position monitoring job...")
            
            current_time = datetime.now()
            
            # Check if it's time to exit all positions (3:15 PM - before Zerodha's 3:20 PM auto square-off)
            if self.signal_executor.should_exit_all_positions(current_time):
                logger.info("🔔 Auto-exit time reached (3:15 PM) - placing exit orders (before Zerodha's 3:20 PM square-off)")
                
                # Get all open positions from Kite (not DB - source of truth)
                positions = await self.position_manager.get_open_positions()
                
                if positions:
                    logger.info(f"Placing exit orders for {len(positions)} open positions")
                    
                    # Generate exit signals for all positions
                    exit_signals = []
                    for pos in positions:
                        from backend.models.signal import Signal
                        
                        exit_signal = Signal(
                            symbol=pos['tradingsymbol'],
                            signal_type="SELL",
                            price=pos['last_price'],
                            stop_loss=0,  # Not relevant for exit
                            target=0,     # Not relevant for exit
                            quantity=abs(pos['quantity']),
                            reason="Time-based exit (3:15 PM - before auto square-off)",
                            timestamp=current_time
                        )
                        exit_signals.append(exit_signal)
                    
                    # Execute exit signals (places orders on Kite)
                    results = await self.signal_executor.execute_exit_signals(
                        exit_signals,
                        strategy_name="AUTO_EXIT"
                    )
                    
                    executed = sum(1 for r in results if r.status == "EXECUTED")
                    logger.info(f"✅ Placed {executed}/{len(exit_signals)} exit orders")
                    logger.info(f"⏳ Position records will be closed when Kite confirms exits (next sync)")
                else:
                    logger.info("No open positions to exit")
            
            # Always sync positions to update P&L and detect closures
            # This will close DB positions when Kite shows quantity=0
            logger.debug("Syncing positions from Kite (updates P&L, detects closures)")
            await self.position_manager.sync_positions_from_kite()
            
            logger.debug("✅ Position monitoring completed")
            
        except Exception as e:
            logger.error(f"Error in position monitoring job: {e}", exc_info=True)
    
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
    
    # ================================================================
    # HELPER METHODS
    # ================================================================
    
    def _is_market_hours(self) -> bool:
        """Check if currently in market hours"""
        now = datetime.now()
        current_time = now.time()
        
        # Check weekday
        if now.weekday() >= 5:  # Saturday or Sunday
            return False
        
        # Check time range
        if current_time < self.market_open or current_time > self.market_close:
            return False
        
        return True
    
    def _log_job_schedule(self):
        """Log scheduled jobs"""
        logger.info("📋 Scheduled Jobs:")
        logger.info(f"  1. Order Sync        - Every 1 minute")
        logger.info(f"  2. Position Sync     - Every 1 minute")
        logger.info(f"  3. Margins Sync      - Every 30 seconds")
        logger.info(f"  4. Position Monitor  - Every 1 minute")
        logger.info(f"  5. Daily Init        - {self.market_open} (Mon-Fri)")
    
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
