"""
Multi-Strategy Worker Launcher

Launches multiple strategy workers in parallel to scan for trading opportunities.

Each worker:
- Scans market independently
- Generates signals based on its strategy
- Saves signals to files (./signals/YYYY-MM-DD/strategy_name_signals.json)

Workers:
1. VWAP Breakout Worker
2. Bullish Flag Worker
3. VWAP EMA Breakout Worker

Usage:
    # Run all workers
    python -m backend.workers.run_all_workers

    # Run specific worker
    python -m backend.workers.vwap_breakout_worker
    python -m backend.workers.bullish_flag_worker
    python -m backend.workers.vwap_ema_breakout_worker
"""

import asyncio
import signal
import sys
from datetime import datetime
import logging

from backend.workers.vwap_breakout_worker import VWAPBreakoutWorker
from backend.workers.bullish_flag_worker import BullishFlagWorker
from backend.workers.vwap_ema_breakout_worker import VWAPEMABreakoutWorker

# Setup logging
from backend.core.logging_config import setup_logging
setup_logging('all_workers')
logger = logging.getLogger(__name__)


class MultiStrategyLauncher:
    """Launcher for multiple strategy workers"""
    
    def __init__(self):
        """Initialize launcher"""
        self.workers = []
        self.running = False
    
    def create_workers(self):
        """Create all worker instances"""
        logger.info("Creating worker instances...")
        
        try:
            # Create workers
            self.workers = [
                # VWAPBreakoutWorker(),
                BullishFlagWorker(),
                # VWAPEMABreakoutWorker(),
            ]
            
            logger.info(f"✅ Created {len(self.workers)} workers")
            
        except Exception as e:
            logger.error(f"Failed to create workers: {e}", exc_info=True)
            sys.exit(1)
    
    async def start_all(self):
        """Start all workers in parallel"""
        logger.info("\n" + "=" * 70)
        logger.info("🚀 MULTI-STRATEGY WORKER LAUNCHER")
        logger.info("=" * 70)
        logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
        logger.info(f"Workers: {len(self.workers)}")
        logger.info(f"Strategies:")
        for worker in self.workers:
            logger.info(f"  - {worker.get_strategy_name()}: {worker.config.description}")
        logger.info(f"Signal Storage: ./signals/")
        logger.info("=" * 70 + "\n")
        
        self.running = True
        
        # Start all workers concurrently
        tasks = [worker.start() for worker in self.workers]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Error in workers: {e}", exc_info=True)
        finally:
            self.running = False
    
    def stop_all(self):
        """Stop all workers"""
        logger.info("\n🛑 Stopping all workers...")
        
        for worker in self.workers:
            try:
                worker.scheduler.shutdown()
            except Exception as e:
                logger.error(f"Error stopping worker: {e}")
        
        logger.info("✅ All workers stopped")


def main():
    """Main entry point"""
    launcher = MultiStrategyLauncher()
    
    # Create workers
    launcher.create_workers()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        print("\n🛑 Received interrupt signal, shutting down all workers...")
        launcher.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start all workers
    asyncio.run(launcher.start_all())


if __name__ == '__main__':
    main()
