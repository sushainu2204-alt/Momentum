"""
Bullish Flag Strategy Worker

Scans market for bullish flag pattern opportunities and generates signals.

Entry Criteria:
- +2% pole followed by 0.3-1.5% pullback
- Breakout above flag high with volume confirmation
- Exit: +1.8% target, -0.8% SL

Usage:
    python -m backend.jobs.strategy.bullish_flag_worker
"""

import asyncio
import logging
import signal
import sys

from backend.jobs.strategy.base_strategy_worker import BaseStrategyWorker
from backend.core.strategies.bullish_flag import BullishFlagStrategy
from backend.config import BullishFlagConfig

logger = logging.getLogger(__name__)


class BullishFlagWorker(BaseStrategyWorker):
    """Bullish Flag Momentum Strategy Worker"""
    
    def get_strategy_name(self) -> str:
        """Return strategy identifier"""
        return "bullish_flag"
    
    def create_strategy(self) -> BullishFlagStrategy:
        """Create strategy instance"""
        return BullishFlagStrategy(self.config)
    
    def create_config(self) -> BullishFlagConfig:
        """Create strategy configuration"""
        return BullishFlagConfig(
            min_initial_move_pct=2.0,
            pullback_pct_min=0.3,
            pullback_pct_max=1.5,
            pullback_candles_min=2,
            pullback_candles_max=5,
            breakout_threshold_pct=0.1,
            volume_multiplier=1.3,
            stop_loss_pct=0.8,
            target_pct=1.8,
            position_size_pct=0.10
        )


def main():
    """Main entry point"""
    worker = BullishFlagWorker()
    
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
