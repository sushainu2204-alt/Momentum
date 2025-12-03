"""
VWAP Breakout Strategy Worker

Scans market for VWAP breakout opportunities and generates signals.

Entry Criteria:
- Price > VWAP + 0.2%
- Volume > 1.5x average
- Exit: +1.5% target, -0.7% SL

Usage:
    python -m backend.jobs.strategy.vwap_breakout_worker
"""

import asyncio
import logging
import signal
import sys

from backend.jobs.strategy.base_strategy_worker import BaseStrategyWorker
from backend.core.strategies.vwap_breakout import VWAPBreakoutStrategy
from backend.config import VWAPBreakoutConfig

logger = logging.getLogger(__name__)


class VWAPBreakoutWorker(BaseStrategyWorker):
    """VWAP Breakout Strategy Worker"""
    
    def get_strategy_name(self) -> str:
        """Return strategy identifier"""
        return "vwap_breakout"
    
    def create_strategy(self) -> VWAPBreakoutStrategy:
        """Create strategy instance"""
        return VWAPBreakoutStrategy(self.config)
    
    def create_config(self) -> VWAPBreakoutConfig:
        """Create strategy configuration"""
        from datetime import time
        return VWAPBreakoutConfig(
            volume_multiplier=1.5,
            vwap_breakout_pct=0.2,
            stop_loss_pct=0.7,
            target_pct=1.5,
            position_size_pct=0.10,
            no_entry_after=time(15, 20)  # Allow entries until 3:20 PM for testing
        )


def main():
    """Main entry point"""
    worker = VWAPBreakoutWorker()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("Received interrupt signal, shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start worker
    asyncio.run(worker.start())


if __name__ == '__main__':
    main()
