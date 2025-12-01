"""
VWAP EMA Breakout Strategy Worker

Scans market for VWAP + EMA + breakout opportunities and generates signals.

Entry Criteria:
- 2-4% gain
- Price > VWAP & 20 EMA
- Volume > 1.5x average
- Breakout of previous candle high
- Exit: +1.5% target, -0.7% SL

Usage:
    python -m backend.workers.vwap_ema_breakout_worker
"""

import asyncio
import signal
import sys

from backend.workers.base_strategy_worker import BaseStrategyWorker
from backend.core.strategies.vwap_ema_breakout import VWAPEMABreakoutStrategy
from backend.core.config import VWAPEMABreakoutConfig


class VWAPEMABreakoutWorker(BaseStrategyWorker):
    """VWAP EMA Breakout Strategy Worker"""
    
    def get_strategy_name(self) -> str:
        """Return strategy identifier"""
        return "vwap_ema_breakout"
    
    def create_strategy(self) -> VWAPEMABreakoutStrategy:
        """Create strategy instance"""
        return VWAPEMABreakoutStrategy(self.config)
    
    def create_config(self) -> VWAPEMABreakoutConfig:
        """Create strategy configuration"""
        return VWAPEMABreakoutConfig(
            min_gain_pct=2.0,
            max_gain_pct=4.0,
            ema_period=20,
            vwap_enabled=True,
            volume_multiplier=1.5,
            volume_lookback=20,
            breakout_previous_high=True,
            stop_loss_pct=0.7,
            target_pct=1.5,
            position_size_pct=0.10
        )


def main():
    """Main entry point"""
    worker = VWAPEMABreakoutWorker()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        print("\n🛑 Received interrupt signal, shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start worker
    asyncio.run(worker.start())


if __name__ == '__main__':
    main()
