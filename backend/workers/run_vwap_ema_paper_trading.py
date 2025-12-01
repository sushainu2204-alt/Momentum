"""
VWAP EMA Breakout Worker - Paper Trading Mode

Runs VWAP EMA strategy with full execution flow but in paper trading mode.
- Scans market for opportunities
- Generates signals
- Validates through 9 guardrails
- Logs decisions (no real orders)

Usage:
    python -m backend.workers.run_vwap_ema_paper_trading
"""

import asyncio
import signal
import sys
from datetime import datetime
import logging

from backend.workers.vwap_ema_breakout_worker import VWAPEMABreakoutWorker
from backend.core.services.capital_manager import TradingLimits

# Setup logging
from backend.core.logging_config import setup_logging
setup_logging('vwap_ema_paper_trading')
logger = logging.getLogger(__name__)


class VWAPEMAPaperTradingWorker(VWAPEMABreakoutWorker):
    """VWAP EMA Breakout Worker with Paper Trading Configuration"""
    
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
    # Create paper trading worker with execution enabled but in dry run mode
    worker = VWAPEMAPaperTradingWorker(
        use_execution=True,  # Enable full execution flow
        dry_run=True         # Paper trading mode (no real orders)
    )ogger.info("")
    logger.info("✅ Paper Trading Mode: No real orders will be placed")
    logger.info("💡 Capital set to: ₹10,000")
    logger.info("💡 Max position size: 20% = ₹2,000")
    logger.info("")
    logger.info("Flow:")
    logger.info("  1. Fetch top gainers from NSE")
    logger.info("  2. Apply VWAP + EMA + Volume filters")
    logger.info("  3. Generate signals")
    logger.info("  4. Validate through 9 guardrails")
    logger.info("  5. Log decisions to trade_logs table")
    logger.info("")
    logger.info("="*80)
    
    # Create worker with execution enabled but in dry run mode
    worker = VWAPEMABreakoutWorker(
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
    logger.info("  - Trade logs: SELECT * FROM trade_logs WHERE DATE(timestamp) = CURRENT_DATE ORDER BY timestamp DESC;")
    logger.info("  - Signals file: ./signals/[date]/vwap_ema_breakout_signals.json")
    logger.info("")


if __name__ == '__main__':
    asyncio.run(main())
