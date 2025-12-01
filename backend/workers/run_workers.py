"""
Worker Initialization Example

Shows how to run workers in different modes:
1. Signal-only mode (original behavior)
2. Execution mode with dry_run (paper trading)
3. Execution mode live (real orders)
"""

import asyncio
import logging
from backend.workers.vwap_breakout_worker import VWAPBreakoutWorker
from backend.workers.vwap_ema_breakout_worker import VWAPEMABreakoutWorker

logger = logging.getLogger(__name__)


async def run_signal_only_mode():
    """
    Mode 1: Signal-only mode (original behavior)
    
    - Only generates and saves signals to file
    - No order execution
    - No guardrails checked
    - Use for backtesting or manual trading
    """
    logger.info("Starting worker in SIGNAL-ONLY mode...")
    
    worker = VWAPBreakoutWorker(
        use_execution=False  # Only save signals, don't execute
    )
    
    await worker.start()


async def run_paper_trading_mode():
    """
    Mode 2: Execution mode with dry_run (paper trading)
    
    - Generates signals
    - Runs through all 9 guardrails
    - Logs what orders WOULD be placed
    - NO actual orders placed to Zerodha
    - Records decisions to trade_logs table
    - Use for validating strategy logic and guardrails
    """
    logger.info("Starting worker in PAPER TRADING mode...")
    
    worker = VWAPBreakoutWorker(
        use_execution=True,  # Use SignalExecutor
        dry_run=True         # Don't place real orders
    )
    
    await worker.start()


async def run_live_trading_mode():
    """
    Mode 3: Execution mode LIVE (real orders)
    
    - Generates signals
    - Runs through all 9 guardrails:
      1. Market hours check
      2. Time window check (skip first/last 15 mins)
      3. No existing position
      4. No pending order
      5. Cooldown check
      6. Max positions limit
      7. Position sizing
      8. Capital availability
      9. Place order via Kite API
    - PLACES REAL ORDERS to Zerodha
    - Records all decisions to trade_logs
    - Tracks positions and P&L
    - Use ONLY after thorough paper trading validation
    """
    logger.info("Starting worker in LIVE TRADING mode...")
    logger.warning("⚠️ LIVE MODE - Real orders will be placed!")
    
    worker = VWAPBreakoutWorker(
        use_execution=True,  # Use SignalExecutor
        dry_run=False        # PLACE REAL ORDERS
    )
    
    await worker.start()


async def run_multiple_strategies():
    """
    Run multiple strategies simultaneously
    
    Each strategy runs in its own worker with independent scheduling.
    """
    logger.info("Starting multiple strategies...")
    
    # Create workers
    vwap_worker = VWAPBreakoutWorker(
        use_execution=True,
        dry_run=True  # Paper trading
    )
    
    vwap_ema_worker = VWAPEMABreakoutWorker(
        use_execution=True,
        dry_run=True  # Paper trading
    )
    
    # Start both workers concurrently
    await asyncio.gather(
        vwap_worker.start(),
        vwap_ema_worker.start()
    )


if __name__ == "__main__":
    import sys
    
    print("\n" + "=" * 70)
    print("MOMENTUM TRADING SYSTEM - Worker Startup")
    print("=" * 70)
    print("\nAvailable modes:")
    print("  1. Signal-only mode (save signals to file)")
    print("  2. Paper trading mode (dry_run=True)")
    print("  3. Live trading mode (REAL ORDERS)")
    print("  4. Multiple strategies")
    print("=" * 70)
    
    mode = input("\nSelect mode (1-4): ").strip()
    
    if mode == "1":
        print("\n✅ Starting in SIGNAL-ONLY mode...")
        asyncio.run(run_signal_only_mode())
    
    elif mode == "2":
        print("\n✅ Starting in PAPER TRADING mode (dry_run=True)...")
        asyncio.run(run_paper_trading_mode())
    
    elif mode == "3":
        confirm = input("\n⚠️ LIVE MODE will place REAL ORDERS. Type 'CONFIRM' to proceed: ")
        if confirm == "CONFIRM":
            print("\n✅ Starting in LIVE TRADING mode...")
            asyncio.run(run_live_trading_mode())
        else:
            print("❌ Live mode cancelled")
            sys.exit(0)
    
    elif mode == "4":
        print("\n✅ Starting MULTIPLE STRATEGIES in paper trading mode...")
        asyncio.run(run_multiple_strategies())
    
    else:
        print("❌ Invalid mode selected")
        sys.exit(1)
