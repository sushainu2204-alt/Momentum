"""
Strategy Worker Runner

Single script to run any strategy in any mode.

Usage:
    # Signal-only mode (save to files, no guardrails)
    python -m backend.workers.run_strategy vwap_breakout --mode signals
    
    # Paper trading mode (guardrails, no real orders)
    python -m backend.workers.run_strategy vwap_breakout --mode paper
    
    # Live trading mode (REAL ORDERS)
    python -m backend.workers.run_strategy vwap_breakout --mode live
    
    # Run all strategies
    python -m backend.workers.run_strategy all --mode paper

Available strategies:
    - vwap_breakout
    - vwap_ema
    - bullish_flag
    - all (runs all strategies)
"""

import argparse
import asyncio
import signal as sig_module
import sys
import logging
from typing import Optional

from backend.core.logging_config import setup_logging
from backend.core.services.capital_manager import TradingLimits

# Available strategies (imported lazily to avoid circular imports)
AVAILABLE_STRATEGIES = ['vwap_breakout', 'vwap_ema', 'bullish_flag', 'all']


def get_worker_class(strategy_name: str):
    """Get worker class for strategy name"""
    if strategy_name == 'vwap_breakout':
        from backend.workers.vwap_breakout_worker import VWAPBreakoutWorker
        return VWAPBreakoutWorker
    elif strategy_name == 'vwap_ema':
        from backend.workers.vwap_ema_breakout_worker import VWAPEMABreakoutWorker
        return VWAPEMABreakoutWorker
    elif strategy_name == 'bullish_flag':
        from backend.workers.bullish_flag_worker import BullishFlagWorker
        return BullishFlagWorker
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")


def create_paper_trading_worker(strategy_name: str):
    """Create a worker with paper trading configuration"""
    
    WorkerClass = get_worker_class(strategy_name)
    
    # Create a subclass that overrides capital methods for paper trading
    class PaperTradingWorker(WorkerClass):
        """Worker with paper trading configuration"""
        
        def get_trading_limits(self) -> Optional[TradingLimits]:
            """Paper trading limits (only when dry_run=True)"""
            if self.dry_run:
                return TradingLimits(
                    starting_capital=10000,  # Mock capital for paper trading
                    max_positions=5,
                    position_size_pct=20,
                    risk_per_trade_pct=2
                )
            return None  # Use CapitalManager defaults for live mode
        
        def get_mock_capital(self) -> Optional[float]:
            """Mock capital (only when dry_run=True)"""
            return 10000.0 if self.dry_run else None
    
    return PaperTradingWorker


async def run_single_strategy(
    strategy_name: str,
    use_execution: bool,
    dry_run: bool,
    logger: logging.Logger
):
    """Run a single strategy worker"""
    
    if use_execution and dry_run:
        # Paper trading mode - use special class with mock capital
        WorkerClass = create_paper_trading_worker(strategy_name)
    else:
        # Signal-only or live mode - use base class
        WorkerClass = get_worker_class(strategy_name)
    
    worker = WorkerClass(use_execution=use_execution, dry_run=dry_run)
    
    logger.info(f"Starting {strategy_name} worker...")
    await worker.start()


async def run_all_strategies(
    use_execution: bool,
    dry_run: bool,
    logger: logging.Logger
):
    """Run all strategies concurrently"""
    
    strategies = ['vwap_breakout', 'vwap_ema', 'bullish_flag']
    
    tasks = []
    for strategy_name in strategies:
        if use_execution and dry_run:
            WorkerClass = create_paper_trading_worker(strategy_name)
        else:
            WorkerClass = get_worker_class(strategy_name)
        
        worker = WorkerClass(use_execution=use_execution, dry_run=dry_run)
        tasks.append(worker.start())
        logger.info(f"Created {strategy_name} worker")
    
    logger.info(f"Starting {len(tasks)} workers concurrently...")
    await asyncio.gather(*tasks)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Run trading strategy workers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Signal-only mode (save to files, no guardrails)
    python -m backend.workers.run_strategy vwap_breakout --mode signals
    
    # Paper trading mode (guardrails, no real orders)
    python -m backend.workers.run_strategy vwap_breakout --mode paper
    
    # Live trading mode (REAL ORDERS)
    python -m backend.workers.run_strategy vwap_breakout --mode live
    
    # Run all strategies in paper trading mode
    python -m backend.workers.run_strategy all --mode paper
"""
    )
    
    parser.add_argument(
        'strategy',
        choices=AVAILABLE_STRATEGIES,
        help='Strategy to run (or "all" for all strategies)'
    )
    
    parser.add_argument(
        '--mode',
        choices=['signals', 'paper', 'live'],
        default='signals',
        help='Execution mode (default: signals)'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_name = f"{args.strategy}_{args.mode}"
    setup_logging(log_name)
    logger = logging.getLogger(__name__)
    
    # Determine execution settings based on mode
    if args.mode == 'signals':
        use_execution = False
        dry_run = True
        mode_desc = "SIGNAL-ONLY (save to files, no guardrails)"
    elif args.mode == 'paper':
        use_execution = True
        dry_run = True
        mode_desc = "PAPER TRADING (guardrails, no real orders)"
    elif args.mode == 'live':
        use_execution = True
        dry_run = False
        mode_desc = "⚠️ LIVE TRADING (REAL ORDERS)"
    
    # Print banner
    logger.info("=" * 70)
    logger.info("  MOMENTUM TRADING SYSTEM - Strategy Runner")
    logger.info("=" * 70)
    logger.info(f"  Strategy: {args.strategy.upper()}")
    logger.info(f"  Mode:     {mode_desc}")
    logger.info("=" * 70)
    
    # Live mode confirmation
    if args.mode == 'live':
        confirm = input("\n⚠️ LIVE MODE will place REAL ORDERS. Type 'CONFIRM' to proceed: ")
        if confirm != "CONFIRM":
            logger.info("❌ Live mode cancelled")
            sys.exit(0)
        logger.warning("🔴 LIVE MODE CONFIRMED - Real orders will be placed!")
    
    # Paper trading mode info
    if args.mode == 'paper':
        logger.info("")
        logger.info("📊 Paper Trading Configuration:")
        logger.info("   - Mock Capital: ₹10,000")
        logger.info("   - Max Positions: 5")
        logger.info("   - Position Size: 20%")
        logger.info("   - Risk per Trade: 2%")
        logger.info("")
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("\n🛑 Received interrupt signal, shutting down...")
        sys.exit(0)
    
    sig_module.signal(sig_module.SIGINT, signal_handler)
    sig_module.signal(sig_module.SIGTERM, signal_handler)
    
    # Run strategy/strategies
    if args.strategy == 'all':
        logger.info("🚀 Starting all strategies...")
        asyncio.run(run_all_strategies(use_execution, dry_run, logger))
    else:
        logger.info(f"🚀 Starting {args.strategy} strategy...")
        asyncio.run(run_single_strategy(args.strategy, use_execution, dry_run, logger))


if __name__ == '__main__':
    main()
