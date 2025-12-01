"""
VWAP Breakout Worker - Paper Trading Mode

Runs VWAP Breakout strategy with full execution flow but in paper trading mode.
- Scans market for opportunities
- Generates signals (only 2 filters: VWAP + Volume)
- Validates through 9 guardrails
- Logs decisions (no real orders)

Strategy Filters (much simpler than VWAP EMA):
1. Price > VWAP + 0.2%
2. Volume > 1.5x average

Usage:
    python -m backend.workers.run_vwap_breakout_paper_trading
"""

import asyncio
import signal
import sys
from datetime import datetime
import logging

from backend.workers.vwap_breakout_worker import VWAPBreakoutWorker
from backend.core.services.capital_manager import TradingLimits

# Setup logging
from backend.core.logging_config import setup_logging
setup_logging('vwap_breakout_paper_trading')
logger = logging.getLogger(__name__)


class VWAPBreakoutPaperTradingWorker(VWAPBreakoutWorker):
    """VWAP Breakout Worker with Paper Trading Configuration"""
    
    def get_trading_limits(self):
        """Override to provide paper trading limits (only when dry_run=True)"""
        if self.dry_run:
            return TradingLimits(
                starting_capital=10000,  # Mock capital for paper trading
                max_positions=5,
                position_size_pct=20,
                risk_per_trade_pct=2
            )
        return None  # Use CapitalManager defaults for live mode
    
    def get_mock_capital(self):
        """Override to provide mock capital (only when dry_run=True)"""
        return 10000.0 if self.dry_run else None


async def main():
    """Main entry point"""
    logger.info("="*80)
    logger.info("  VWAP BREAKOUT - PAPER TRADING MODE")
    logger.info("="*80)
    logger.info("")
    logger.info("✅ Paper Trading Mode: No real orders will be placed")
    logger.info("💡 Capital set to: ₹10,000")
    logger.info("💡 Max position size: 20% = ₹2,000")
    logger.info("")
    logger.info("Strategy: VWAP Breakout (Simplified - Only 2 Filters)")
    logger.info("  Filter 1: Price > VWAP + 0.2%")
    logger.info("  Filter 2: Volume > 1.5x average")
    logger.info("")
    logger.info("Flow:")
    logger.info("  1. Fetch top gainers from NSE")
    logger.info("  2. Apply VWAP + Volume filters")
    logger.info("  3. Generate signals")
    logger.info("  4. Validate through 9 guardrails")
    logger.info("  5. Log decisions to trade_logs table")
    logger.info("")
    logger.info("="*80)
    
    # Create paper trading worker with execution enabled but in dry run mode
    worker = VWAPBreakoutPaperTradingWorker(
        use_execution=True,  # Enable full execution flow
        dry_run=True         # Paper trading mode (no real orders)
    )
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("\n🛑 Received interrupt signal, shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run one scan immediately for testing
    logger.info("🚀 Starting immediate scan...")
    await worker.scan_job()
    
    logger.info("")
    logger.info("="*80)
    logger.info("  SCAN COMPLETED")
    logger.info("="*80)
    logger.info("")
    logger.info("📊 Check results:")
    logger.info("  - Trade logs: docker exec momentum-postgres-1 psql -U appuser -d appdb -c \"SELECT * FROM trade_logs WHERE strategy_name = 'vwap_breakout' AND DATE(timestamp) = CURRENT_DATE ORDER BY timestamp DESC;\"")
    logger.info("  - Signals file: ./signals/[date]/vwap_breakout_signals.json")
    logger.info("")


if __name__ == '__main__':
    asyncio.run(main())
