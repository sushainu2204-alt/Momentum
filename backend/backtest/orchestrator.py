"""
Backtest Orchestrator Module

Main coordinator that runs the complete backtest simulation.
Ties together all components in an event-driven loop.

Flow:
    1. Load data for all symbols
    2. Compute features
    3. For each candle:
        a. Update features
        b. Generate signals
        c. Check risk
        d. Execute orders
        e. Manage positions
        f. Record state
    4. Calculate performance
    5. Generate report

This is the entry point for running backtests.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import logging
import time as time_module
from tqdm import tqdm

from .config import BacktestConfig, TimeConfig
from .data_loader import DataLoader, SyntheticDataGenerator
from .feature_engine import FeatureEngine, FeatureConfig
from .signal_engine import SignalEngine, BacktestSignal
from .risk_engine import RiskEngine, RiskCheckResult
from .order_simulator import OrderSimulator, BacktestPosition
from .trade_ledger import TradeLedger, Trade
from .performance_engine import PerformanceEngine, PerformanceMetrics
from .events import EventQueue

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """
    Complete backtest result.
    
    Contains all output data from a backtest run.
    """
    # Configuration used
    config: BacktestConfig
    
    # Performance metrics
    metrics: PerformanceMetrics
    
    # Raw data
    trades: pd.DataFrame
    daily_summary: pd.DataFrame
    equity_curve: pd.DataFrame
    strategy_summary: pd.DataFrame
    
    # Run info
    run_time_seconds: float
    candles_processed: int
    signals_generated: int
    
    def print_summary(self) -> None:
        """Print result summary."""
        self.metrics.print_summary()
        
        print(f"\n⏱️  Backtest completed in {self.run_time_seconds:.1f} seconds")
        print(f"📊 Candles processed: {self.candles_processed:,}")
        print(f"🎯 Signals generated: {self.signals_generated:,}")
    
    def save(self, output_dir: str) -> None:
        """Save all results to directory."""
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        
        # Save trades
        if not self.trades.empty:
            self.trades.to_csv(path / "trades.csv", index=False)
        
        # Save daily summary
        if not self.daily_summary.empty:
            self.daily_summary.to_csv(path / "daily_summary.csv", index=False)
        
        # Save equity curve
        if not self.equity_curve.empty:
            self.equity_curve.to_csv(path / "equity_curve.csv", index=False)
        
        # Save strategy summary
        if not self.strategy_summary.empty:
            self.strategy_summary.to_csv(path / "strategy_summary.csv", index=False)
        
        # Save metrics as JSON
        import json
        with open(path / "metrics.json", 'w') as f:
            json.dump(self.metrics.to_dict(), f, indent=2, default=str)
        
        logger.info(f"Results saved to {path}")


class BacktestOrchestrator:
    """
    Main backtest orchestrator.
    
    Coordinates all components to run a complete backtest.
    
    Usage:
        config = BacktestConfig(
            initial_capital=100000,
            strategies=['vwap_breakout', 'bullish_flag'],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31)
        )
        
        orchestrator = BacktestOrchestrator(config)
        result = orchestrator.run()
        result.print_summary()
    """
    
    def __init__(self, config: BacktestConfig):
        """
        Initialize orchestrator.
        
        Args:
            config: Backtest configuration
        """
        self.config = config
        config.validate()
        
        # Initialize components
        self.data_loader = DataLoader(
            data_path=config.data_path,
            frequency=config.data_frequency
        )
        
        self.feature_engine = FeatureEngine()
        self.signal_engine = SignalEngine(config)
        self.risk_engine = RiskEngine(config)
        self.order_simulator = OrderSimulator(config)
        self.ledger = TradeLedger(
            initial_capital=config.initial_capital,
            output_path=config.output_path
        )
        
        # Event queue
        self.event_queue = EventQueue()
        
        # State tracking
        self._symbols: List[str] = []
        self._data: Dict[str, pd.DataFrame] = {}
        self._features_data: Dict[str, pd.DataFrame] = {}
        self._indexed_data: Dict[str, Dict[datetime, int]] = {}  # Pre-built timestamp index
        self._candles_processed = 0
        self._signals_generated = 0
        
        logger.info(f"Orchestrator initialized with {len(config.strategies)} strategies")
    
    def run(
        self,
        symbols: Optional[List[str]] = None,
        show_progress: bool = True
    ) -> BacktestResult:
        """
        Run the complete backtest.
        
        Args:
            symbols: List of symbols to test (overrides config)
            show_progress: Show progress bar
        
        Returns:
            BacktestResult with all outputs
        """
        start_time = time_module.time()
        
        logger.info("=" * 60)
        logger.info("STARTING BACKTEST")
        logger.info("=" * 60)
        logger.info(f"Period: {self.config.start_date} to {self.config.end_date}")
        logger.info(f"Strategies: {', '.join(self.config.strategies)}")
        logger.info(f"Initial Capital: ₹{self.config.initial_capital:,.0f}")
        
        # Step 1: Load symbols
        self._symbols = self._get_symbols(symbols)
        logger.info(f"Symbols: {len(self._symbols)}")
        
        if not self._symbols:
            logger.error("No symbols to backtest")
            return self._create_empty_result(start_time)
        
        # Step 2: Load data
        logger.info("Loading historical data...")
        self._load_data()
        
        if not self._data:
            logger.error("No data loaded")
            return self._create_empty_result(start_time)
        
        # Step 3: Compute features
        logger.info("Computing features...")
        self._compute_features()
        
        # Step 4: Run simulation
        logger.info("Running simulation...")
        self._run_simulation(show_progress)
        
        # Step 5: Finalize trades
        self._finalize_trades()
        
        # Step 6: Calculate performance
        logger.info("Calculating performance metrics...")
        performance_engine = PerformanceEngine(
            self.ledger,
            self.config.initial_capital
        )
        metrics = performance_engine.calculate_all_metrics()
        
        # Create result
        result = BacktestResult(
            config=self.config,
            metrics=metrics,
            trades=self.ledger.get_trades_dataframe(),
            daily_summary=self.ledger.get_daily_summary(),
            equity_curve=self.ledger.get_equity_curve(),
            strategy_summary=self.ledger.get_strategy_summary(),
            run_time_seconds=time_module.time() - start_time,
            candles_processed=self._candles_processed,
            signals_generated=self._signals_generated
        )
        
        logger.info("Backtest completed!")
        
        return result
    
    def _get_symbols(self, symbols: Optional[List[str]] = None) -> List[str]:
        """Get symbols to backtest."""
        
        # Use provided symbols
        if symbols:
            return symbols
        
        # Use config symbols
        if self.config.symbols:
            return self.config.symbols
        
        # Load from universe file
        try:
            universe_path = Path(self.config.universe_file)
            if universe_path.exists():
                return self.data_loader.get_universe_symbols(str(universe_path))
        except Exception as e:
            logger.warning(f"Could not load universe file: {e}")
        
        # Use available data files
        return self.data_loader.get_available_symbols()
    
    def _load_data(self) -> None:
        """Load historical data for all symbols."""
        
        self._data = self.data_loader.load_symbols(
            symbols=self._symbols,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            parallel=True
        )
        
        logger.info(f"Loaded data for {len(self._data)} symbols")
    
    def _compute_features(self) -> None:
        """Compute features for all symbols."""
        
        for symbol, df in self._data.items():
            enriched_df = self.feature_engine.compute_all_features(
                df, symbol=symbol
            )
            self._features_data[symbol] = enriched_df
        
        logger.info(f"Features computed for {len(self._features_data)} symbols")
    
    def _run_simulation(self, show_progress: bool = True) -> None:
        """Run the main simulation loop."""
        
        # Get all unique timestamps
        all_timestamps = set()
        for df in self._features_data.values():
            if 'timestamp' in df.columns:
                all_timestamps.update(df['timestamp'].tolist())
        
        if not all_timestamps:
            logger.warning("No timestamps found in data")
            return
        
        # Sort and filter timestamps
        sorted_timestamps = sorted(all_timestamps)
        
        # Filter to market hours
        market_open = self.config.time.market_open
        market_close = self.config.time.market_close
        
        filtered_timestamps = [
            ts for ts in sorted_timestamps
            if market_open <= ts.time() <= market_close
        ]
        
        # Skip warmup period
        if len(filtered_timestamps) > self.config.warmup_candles:
            filtered_timestamps = filtered_timestamps[self.config.warmup_candles:]
        
        total_candles = len(filtered_timestamps)
        logger.info(f"Processing {total_candles:,} candles...")
        
        # OPTIMIZATION: Pre-index DataFrames by timestamp for O(1) lookups
        logger.info("Building timestamp index for fast lookups...")
        self._indexed_data: Dict[str, Dict[datetime, int]] = {}
        for symbol, df in self._features_data.items():
            if 'timestamp' in df.columns:
                # Create a dict mapping timestamp -> row index
                # Use .tolist() to preserve timezone info (not .values which loses tz)
                self._indexed_data[symbol] = {
                    ts: idx for idx, ts in enumerate(df['timestamp'].tolist())
                }
        
        # Progress bar
        iterator = tqdm(filtered_timestamps, desc="Backtesting") if show_progress else filtered_timestamps
        
        # Main loop
        for timestamp in iterator:
            self._process_candle_fast(timestamp)
            self._candles_processed += 1
            
            # Record equity point (every 15 minutes to reduce data)
            if self._candles_processed % 15 == 0:
                self._record_equity_point(timestamp)
    
    def _process_candle(self, timestamp: datetime) -> None:
        """Process a single candle timestamp (original - slower)."""
        
        # Get current market data for all symbols
        market_data: Dict[str, pd.Series] = {}
        features_up_to: Dict[str, pd.DataFrame] = {}
        
        for symbol, df in self._features_data.items():
            candle = df[df['timestamp'] == timestamp]
            if not candle.empty:
                market_data[symbol] = candle.iloc[0]
                
                # Get historical context for strategy evaluation
                historical = df[df['timestamp'] <= timestamp].tail(100)
                features_up_to[symbol] = historical
        
        if not market_data:
            return
        
        # 1. Process existing positions (check SL, target, trailing)
        existing_positions = self.order_simulator.get_position_symbols()
        events = self.order_simulator.process_candle(
            timestamp, market_data, features_up_to
        )
        
        # Handle exit events
        for event in events:
            if hasattr(event, 'exit_reason'):
                self._handle_position_exit(event, timestamp)
        
        # 2. Generate new signals
        signals = self.signal_engine.scan(
            timestamp=timestamp,
            market_data=market_data,
            features_data=features_up_to,
            existing_positions=existing_positions
        )
        
        # 3. Process signals through risk engine and execute
        for signal in signals:
            self._process_signal(signal)
            self._signals_generated += 1
        
        # 4. Update unrealized P&L in risk engine
        unrealized_pnl = self.order_simulator.get_unrealized_pnl()
        self.risk_engine.update_unrealized_pnl(unrealized_pnl)
    
    def _process_candle_fast(self, timestamp: datetime) -> None:
        """Process a single candle timestamp (optimized with pre-indexed lookups)."""
        
        # Get current market data for all symbols using pre-built index
        market_data: Dict[str, pd.Series] = {}
        features_up_to: Dict[str, pd.DataFrame] = {}
        
        for symbol, df in self._features_data.items():
            # O(1) lookup using pre-built index
            idx = self._indexed_data.get(symbol, {}).get(timestamp)
            if idx is not None:
                market_data[symbol] = df.iloc[idx]
                
                # Get historical context - use iloc slice (much faster)
                start_idx = max(0, idx - 99)
                features_up_to[symbol] = df.iloc[start_idx:idx + 1]
        
        if not market_data:
            return
        
        # 1. Process existing positions (check SL, target, trailing)
        existing_positions = self.order_simulator.get_position_symbols()
        events = self.order_simulator.process_candle(
            timestamp, market_data, features_up_to
        )
        
        # Handle exit events
        for event in events:
            if hasattr(event, 'exit_reason'):
                self._handle_position_exit(event, timestamp)
        
        # 2. Generate new signals
        signals = self.signal_engine.scan(
            timestamp=timestamp,
            market_data=market_data,
            features_data=features_up_to,
            existing_positions=existing_positions
        )
        
        # 3. Process signals through risk engine and execute
        for signal in signals:
            self._process_signal(signal)
            self._signals_generated += 1
        
        # 4. Update unrealized P&L in risk engine
        unrealized_pnl = self.order_simulator.get_unrealized_pnl()
        self.risk_engine.update_unrealized_pnl(unrealized_pnl)
    
    def _process_signal(self, signal: BacktestSignal) -> None:
        """Process a trading signal."""
        
        # Risk check
        result = self.risk_engine.check_signal(signal, signal.timestamp)
        
        if not result.passed:
            logger.debug(f"Signal rejected: {signal.symbol} - {result.reason}")
            return
        
        # Submit order
        order = self.order_simulator.submit_order(signal, result.allowed_quantity)
        
        # Update risk engine
        self.risk_engine.on_position_opened(
            symbol=signal.symbol,
            strategy_id=signal.strategy_id,
            quantity=result.allowed_quantity,
            entry_price=signal.price
        )
        
        logger.debug(
            f"Order placed: {signal.symbol} | Qty: {result.allowed_quantity} | "
            f"Strategy: {signal.strategy_id}"
        )
    
    def _handle_position_exit(self, event: Any, timestamp: datetime) -> None:
        """Handle position exit event."""
        
        # Find the closed position
        closed_positions = self.order_simulator.get_closed_positions()
        if not closed_positions:
            return
        
        # Get most recent closed position for this symbol
        position = None
        for pos in reversed(closed_positions):
            if pos.symbol == event.symbol:
                position = pos
                break
        
        if position is None:
            return
        
        # Calculate commission
        trade_value = position.quantity * position.exit_price
        commission = (
            self.config.execution.commission_per_trade +
            trade_value * self.config.execution.commission_pct +
            trade_value * self.config.execution.stt_pct
        )
        
        # Create trade record
        trade = Trade.from_position(
            position,
            commission=commission,
            strategy_name=position.strategy_id
        )
        
        # Record in ledger
        self.ledger.record_trade(trade)
        
        # Update risk engine
        self.risk_engine.on_position_closed(
            symbol=position.symbol,
            strategy_id=position.strategy_id,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=position.exit_price,
            pnl=trade.net_pnl
        )
    
    def _record_equity_point(self, timestamp: datetime) -> None:
        """Record point in equity curve."""
        
        portfolio = self.risk_engine.get_portfolio_state()
        
        self.ledger.record_equity_point(
            timestamp=timestamp,
            equity=self.risk_engine.get_current_equity(),
            cash=portfolio.available_capital,
            invested=portfolio.invested_capital,
            unrealized_pnl=portfolio.unrealized_pnl,
            realized_pnl=portfolio.realized_pnl
        )
    
    def _finalize_trades(self) -> None:
        """Finalize any remaining open positions."""
        
        open_positions = self.order_simulator.get_open_positions()
        
        if open_positions:
            logger.info(f"Closing {len(open_positions)} remaining positions")
            
            for position_id, position in open_positions.items():
                # Create trade record for open position (mark-to-market at last price)
                trade = Trade.from_position(
                    position,
                    commission=0,
                    strategy_name=position.strategy_id
                )
                trade.exit_reason = "BACKTEST_END"
                
                # Don't record incomplete trades in ledger
                # (they would need proper closing)
    
    def _create_empty_result(self, start_time: float) -> BacktestResult:
        """Create empty result for failed backtest."""
        
        return BacktestResult(
            config=self.config,
            metrics=PerformanceMetrics(),
            trades=pd.DataFrame(),
            daily_summary=pd.DataFrame(),
            equity_curve=pd.DataFrame(),
            strategy_summary=pd.DataFrame(),
            run_time_seconds=time_module.time() - start_time,
            candles_processed=0,
            signals_generated=0
        )
    
    def reset(self) -> None:
        """Reset orchestrator for new run."""
        
        self.risk_engine.reset()
        self.order_simulator.reset()
        self.ledger.reset()
        self.signal_engine.clear_history()
        self.feature_engine.clear_cache()
        self.data_loader.clear_cache()
        
        self._data.clear()
        self._features_data.clear()
        self._candles_processed = 0
        self._signals_generated = 0


def run_backtest(
    strategies: List[str],
    start_date: date,
    end_date: date,
    initial_capital: float = 100000,
    symbols: Optional[List[str]] = None,
    data_path: str = "data/historical",
    **kwargs
) -> BacktestResult:
    """
    Convenience function to run a backtest.
    
    Args:
        strategies: List of strategy IDs
        start_date: Start date
        end_date: End date
        initial_capital: Starting capital
        symbols: Optional list of symbols
        data_path: Path to historical data
        **kwargs: Additional config options
    
    Returns:
        BacktestResult
    
    Example:
        result = run_backtest(
            strategies=['vwap_breakout', 'bullish_flag'],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000,
            symbols=['RELIANCE', 'TCS', 'INFY']
        )
        result.print_summary()
    """
    config = BacktestConfig(
        strategies=strategies,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        symbols=symbols,
        data_path=data_path,
        **kwargs
    )
    
    orchestrator = BacktestOrchestrator(config)
    return orchestrator.run()
