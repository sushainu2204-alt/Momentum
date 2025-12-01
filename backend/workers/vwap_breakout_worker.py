"""
VWAP Breakout Strategy Worker

Scans market for VWAP breakout opportunities and generates signals.

Entry Criteria:
- Price > VWAP + 0.2%
- Volume > 1.5x average
- Exit: +1.5% target, -0.7% SL

Usage:
    python -m backend.workers.vwap_breakout_worker
"""

import asyncio
import signal
import sys

from backend.workers.base_strategy_worker import BaseStrategyWorker
from backend.core.strategies.vwap_breakout import VWAPBreakoutStrategy
from backend.core.config import VWAPBreakoutConfig


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
        return VWAPBreakoutConfig(
            volume_multiplier=1.5,
            vwap_breakout_pct=0.2,
            stop_loss_pct=0.7,
            target_pct=1.5,
            position_size_pct=0.10
        )


def main():
    """Main entry point"""
    worker = VWAPBreakoutWorker()
    
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
