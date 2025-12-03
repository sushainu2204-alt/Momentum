"""
Base Strategy Worker

Abstract base class for all strategy workers.
Provides common functionality:
- Market scanning (via pluggable IScanner)
- Signal generation (via pluggable BaseStrategy)
- Signal storage (file/DB)
- Scheduling
- Logging

Each concrete strategy worker extends this class and implements:
- get_strategy_name()
- create_strategy()
- create_config()
- create_scanner() (optional - defaults to TopGainersScanner)
"""

import asyncio
import signal as sig
import sys
from datetime import datetime, time, timedelta
from typing import List, Optional
from abc import ABC, abstractmethod
import logging
import pandas as pd

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.core.strategies.base import BaseStrategy
from backend.core.scanners import IScanner, TopGainersScanner, TopGainersConfig
from backend.core.services import (
    SignalStorage,
    SignalExecutor,
    OrderManager,
    PositionManager,
    CapitalManager,
    KiteService,
)
from backend.core.utils.timezone import now_ist, is_market_hours, is_trading_window, get_today_date_str
from backend.config import (
    DEFAULT_TRADING_HOURS,
    DEFAULT_PATHS,
    DEFAULT_NSE_CONFIG,
    PathsConfig,
    NSEConfig,
    TradingHoursConfig,
)
from backend.infrastructure.data_sources.nse import NSEDataSource
from backend.infrastructure.data_sources import ZerodhaDataSource
from backend.infrastructure.database.factory import create_database
from backend.core.models import Candidate, Signal
from backend.config import setup_logging

# Setup logging
logger = setup_logging('strategy_worker')


class BaseStrategyWorker(ABC):
    """
    Base class for strategy workers.
    
    Workflow:
    1. Market open (9:15 AM): Initialize
    2. Every 1 minute (9:16-3:20): Scan for opportunities → Generate signals → Save
    3. Market close (3:30 PM): Generate daily report
    """
    
    def __init__(self, use_execution: bool = False, dry_run: bool = True):
        """Initialize worker
        
        Args:
            use_execution: If True, use SignalExecutor to place orders. If False, only save signals to file.
            dry_run: If True, SignalExecutor logs decisions without placing real orders (paper trading)
        """
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        
        # Use configurable trading hours
        self.trading_hours = DEFAULT_TRADING_HOURS
        self.market_open_time = self.trading_hours.market_open
        self.market_close_time = self.trading_hours.market_close
        self.scan_end_time = self.trading_hours.broker_square_off
        
        # Use configurable paths
        self.paths_config = DEFAULT_PATHS
        
        # Use configurable NSE settings
        self.nse_config = DEFAULT_NSE_CONFIG
        
        self.use_execution = use_execution
        self.dry_run = dry_run
        
        logger.info(f"Initializing {self.get_strategy_name()} Worker...")
        logger.info(f"Mode: {'EXECUTION' if use_execution else 'SIGNAL_ONLY'} {'(DRY RUN)' if dry_run else '(LIVE)'}")
        
        # Load configuration
        self.config = self.create_config()
        logger.info(f"Strategy Config: {self.config.name}")
        
        # Initialize Kite service (optional - only if needed for live data)
        self.kite_service = None
        self.zerodha_data_source = None
        
        try:
            self.kite_service = KiteService()
            # KiteService.kite is the KiteConnect instance (not a method)
            kite = self.kite_service.kite
            
            if kite and kite.access_token:
                self.zerodha_data_source = ZerodhaDataSource(kite)
                logger.info("✅ Zerodha data source initialized")
            else:
                logger.warning("Zerodha not available: No access token")
        except Exception as e:
            logger.warning(f"Zerodha not available: {e}")
        
        # Initialize NSE data source (for top gainers)
        self.nse_data_source = NSEDataSource()
        
        # Initialize strategy
        self.strategy = self.create_strategy()
        
        # Initialize scanner (pluggable - defaults to TopGainersScanner)
        self.scanner = self.create_scanner()
        logger.info(f"Scanner: {self.scanner.get_name()}")
        
        # Initialize signal storage (always available for backup)
        self.signal_storage = SignalStorage(
            storage_type="file",
            paths_config=self.paths_config
        )
        
        # Initialize execution components (if enabled)
        self.signal_executor = None
        self.database = None
        self._execution_services_initialized = False
        
        # Signal counter
        self.signals_generated = 0
        self.signals_executed = 0
        self.signals_ignored = 0
        
        logger.info("✅ Worker initialized successfully")
    
    # ================================================================
    # ABSTRACT METHODS (must be implemented by subclasses)
    # ================================================================
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """
        Return strategy identifier.
        
        Returns:
            Strategy name (e.g., 'vwap_breakout')
        """
        pass
    
    @abstractmethod
    def create_strategy(self) -> BaseStrategy:
        """
        Create and return strategy instance.
        
        Returns:
            Strategy instance
        """
        pass
    
    @abstractmethod
    def create_config(self):
        """
        Create and return strategy configuration.
        
        Returns:
            Strategy config instance
        """
        pass
    
    def create_scanner(self) -> IScanner:
        """
        Create and return scanner instance.
        
        Override this in subclasses for different scanning strategies.
        Default: TopGainersScanner with all NSE categories.
        
        Returns:
            Scanner instance implementing IScanner
        """
        config = TopGainersConfig(
            categories=self.nse_config.valid_categories,
            min_gain_pct=2.0,
            max_gain_pct=20.0,
            max_results=100,
            deduplicate=True
        )
        return TopGainersScanner(
            nse_data_source=self.nse_data_source,
            config=config
        )
    
    def get_trading_limits(self):
        """
        Get trading limits for CapitalManager.
        
        Override this in subclasses to customize limits.
        Default: None (CapitalManager uses its default TradingLimits)
        
        Returns:
            TradingLimits instance or None
        """
        return None  # Use CapitalManager defaults
    
    def get_mock_capital(self) -> Optional[float]:
        """
        Get mock capital for paper trading.
        
        Override this in subclasses for paper trading workers.
        Default: None (use live Kite API)
        
        Returns:
            Mock capital amount or None for live trading
        """
        return None  # Live mode - use Kite API
    
    # ================================================================
    # EXECUTION SERVICES INITIALIZATION
    # ================================================================
    
    async def _initialize_execution_services(self):
        """Initialize execution services"""
        try:
            logger.info("Initializing execution services...")
            
            # Initialize database using factory (gets config from settings)
            self.database = create_database()
            await self.database.connect()
            logger.info("✅ Database connected")
            
            # Initialize managers
            from backend.infrastructure.database.order_repository import OrderRepository
            from backend.infrastructure.database.position_repository import PositionRepository
            
            order_repo = OrderRepository(self.database)
            position_repo = PositionRepository(self.database)
            
            self.order_manager = OrderManager(
                kite_service=self.kite_service,
                order_repository=order_repo
            )
            logger.info("✅ OrderManager initialized")
            
            self.position_manager = PositionManager(
                kite_service=self.kite_service,
                position_repository=position_repo,
                order_repository=order_repo  # Needed for sync_positions_from_kite to look up sl_order_id
            )
            logger.info("✅ PositionManager initialized")
            
            # Initialize CapitalManager with default limits
            # Subclasses can override get_trading_limits() and get_mock_capital() for custom behavior
            from backend.core.services import TradingLimits
            
            limits = self.get_trading_limits()
            mock_capital = self.get_mock_capital()
            
            self.capital_manager = CapitalManager(
                database=self.database,
                kite_service=self.kite_service,
                position_manager=self.position_manager,
                limits=limits,
                mock_capital=mock_capital
            )
            
            mode_info = f"mock_capital=₹{mock_capital:,.2f}" if mock_capital else "live_mode"
            logger.info(f"✅ CapitalManager initialized ({mode_info})")
            
            # Initialize signal executor
            self.signal_executor = SignalExecutor(
                order_manager=self.order_manager,
                position_manager=self.position_manager,
                capital_manager=self.capital_manager,
                database=self.database,
                dry_run=self.dry_run
            )
            logger.info(f"✅ SignalExecutor initialized (dry_run={self.dry_run})")
            
        except Exception as e:
            logger.error(f"Failed to initialize execution services: {e}", exc_info=True)
            self.signal_executor = None
    
    # ================================================================
    # SCHEDULED JOBS
    # ================================================================
    
    async def market_open_job(self):
        """Job to run at market open (9:15 AM)"""
        logger.info("=" * 70)
        logger.info(f"🔔 MARKET OPEN - Starting {self.get_strategy_name()}")
        logger.info("=" * 70)
        logger.info(f"Strategy: {self.config.name}")
        logger.info(f"Description: {self.config.description}")
        logger.info(f"Risk-Reward: 1:{self.config.target_pct/self.config.stop_loss_pct:.2f}")
        logger.info(f"Mode: {'EXECUTION' if self.use_execution else 'SIGNAL_ONLY'} {'(DRY RUN)' if self.dry_run else '(LIVE)'}")
        logger.info("=" * 70)
        
        self.is_running = True
        self.signals_generated = 0
        self.signals_executed = 0
        self.signals_ignored = 0
        
        # Initialize daily capital if execution enabled
        if self.use_execution and self.capital_manager:
            try:
                await self.capital_manager.initialize_daily_capital()
                summary = await self.capital_manager.get_capital_summary()
                logger.info(f"💰 Starting Capital: ₹{summary.get('starting_capital', 0):,.2f}")
            except Exception as e:
                logger.error(f"Failed to initialize daily capital: {e}")
    
    async def scan_job(self):
        """Job to scan market (runs every minute)"""
        # Initialize execution services on first run (async initialization)
        if self.use_execution and not self._execution_services_initialized:
            await self._initialize_execution_services()
            self._execution_services_initialized = True
        
        current_time = now_ist()
        
        # Check if we're within market scanning hours using timezone utility
        if not is_trading_window(current_time, skip_first_minutes=1, skip_last_minutes=10):
            return  # Outside trading window
        
        # Set is_running if not already set (handles case where worker starts after 9:15)
        if not self.is_running:
            self.is_running = True
            self.signals_generated = 0
        
        try:
            logger.info(f"\n[{current_time.strftime('%H:%M:%S')}] 🔍 Scanning market...")
            
            # Step 1: Use scanner to find candidates (pluggable scanning logic)
            scan_result = await self.scanner.scan()
            
            if not scan_result.candidates:
                logger.info(f"No candidates found by {self.scanner.get_name()}")
                return
            
            # Log scan results
            logger.info(f"📊 {self.scanner.get_name()}: Found {scan_result.total_found} candidates")
            candidate_symbols = [c.symbol for c in scan_result.candidates]
            logger.info(f"  └─ Top: {', '.join(candidate_symbols[:10])}{'...' if len(candidate_symbols) > 10 else ''}")
            
            candidates = scan_result.candidates
            
            # Step 2: Process candidates and track filtering
            await self._process_candidates(candidates, current_time)
            
            # Step 3: Log status
            logger.info(f"Signals generated today: {self.signals_generated}")
            
        except Exception as e:
            logger.error(f"Error in scan job: {e}", exc_info=True)
    
    async def market_close_job(self):
        """Job to run at market close (3:30 PM)"""
        logger.info("\n" + "=" * 70)
        logger.info("🔔 MARKET CLOSE - Generating Daily Report")
        logger.info("=" * 70)
        
        self.is_running = False
        
        # Generate report
        logger.info(f"DAILY SUMMARY - {self.get_strategy_name().upper()}:")
        logger.info(f"  Total Signals Generated: {self.signals_generated}")
        
        if self.use_execution:
            logger.info(f"  Signals Executed: {self.signals_executed}")
            logger.info(f"  Signals Ignored: {self.signals_ignored}")
            logger.info(f"  Signals Failed: {self.signals_generated - self.signals_executed - self.signals_ignored}")
            
            # Get execution statistics from SignalExecutor
            if self.signal_executor:
                try:
                    exec_stats = await self.signal_executor.get_execution_stats()
                    logger.info("  Execution Breakdown:")
                    logger.info(f"    - Total signals processed: {exec_stats.get('total_signals', 0)}")
                    logger.info(f"    - Orders placed: {exec_stats.get('executed', 0)}")
                    logger.info(f"    - Signals ignored: {exec_stats.get('ignored', 0)}")
                    logger.info(f"    - Execution failures: {exec_stats.get('failed', 0)}")
                except Exception as e:
                    logger.error(f"Error getting execution stats: {e}")
            
            # Get capital summary
            if self.capital_manager:
                try:
                    capital_summary = await self.capital_manager.get_capital_summary()
                    logger.info("  Capital Summary:")
                    logger.info(f"    - Starting capital: ₹{capital_summary.get('starting_capital', 0):,.2f}")
                    logger.info(f"    - Current capital: ₹{capital_summary.get('current_capital', 0):,.2f}")
                    logger.info(f"    - Total P&L: ₹{capital_summary.get('total_pnl', 0):,.2f}")
                    logger.info(f"    - Open positions: {capital_summary.get('open_positions', 0)}")
                except Exception as e:
                    logger.error(f"Error getting capital summary: {e}")
        
        # Export signals to CSV (if in signal-only mode or as backup)
        today = now_ist()
        report_file = self.signal_storage.export_daily_report(today)
        
        if report_file:
            logger.info(f"  Report saved: {report_file}")
        
        logger.info("=" * 70)
        logger.info("Daily report generated")
    
    # ================================================================
    # CORE LOGIC
    # ================================================================
    
    async def _process_candidates(
        self,
        candidates: List[Candidate],
        current_time: datetime
    ):
        """
        Process candidates: apply filters and generate signals.
        
        Args:
            candidates: List of candidate stocks
            current_time: Current time
        """
        # Track filtering stages
        with_historical_data = []
        passed_filters = []
        generated_signals = []
        
        for candidate in candidates:
            try:
                # Fetch historical data (if available)
                stock_df = await self._fetch_historical_data(candidate.symbol)
                
                if stock_df is None or stock_df.empty:
                    logger.debug(f"{candidate.symbol}: No historical data")
                    continue
                
                with_historical_data.append(candidate.symbol)
                
                # Calculate indicators (if strategy returns DataFrame, use it; otherwise keep original)
                indicators_result = self.strategy.calculate_indicators(stock_df)
                if isinstance(indicators_result, pd.DataFrame):
                    stock_df = indicators_result
                
                # Apply filters
                if not self.strategy.apply_filters(candidate, stock_df):
                    logger.debug(f"{candidate.symbol}: Filters failed")
                    continue
                
                passed_filters.append(candidate.symbol)
                
                # Generate entry signal
                signal = self.strategy.should_enter(candidate, stock_df, current_time)
                
                if signal:
                    generated_signals.append(candidate.symbol)
                    
                    # Prepare metadata
                    metadata = self._prepare_metadata(candidate, stock_df)
                    
                    # Save signal to file (always save for record-keeping)
                    await self.signal_storage.save_signal(
                        signal,
                        self.get_strategy_name(),
                        metadata
                    )
                    
                    self.signals_generated += 1
                    
                    # Execute signal if execution enabled
                    if self.use_execution and self.signal_executor:
                        # Execute via SignalExecutor (with guardrails)
                        result = await self.signal_executor.execute_signal(
                            signal=signal,
                            strategy_name=self.get_strategy_name(),
                            metadata=metadata
                        )
                        
                        if result.status == "EXECUTED":
                            self.signals_executed += 1
                            # Order is saved to file via OrderRepository when DB insert happens
                            logger.info(
                                f"✅ ORDER PLACED: {signal.symbol} x{result.quantity} @ ₹{signal.price:.2f}, "
                                f"SL: ₹{signal.stop_loss:.2f}, Target: ₹{signal.target:.2f}, "
                                f"Order ID: {result.order_id}"
                            )
                        elif result.status == "IGNORED":
                            self.signals_ignored += 1
                            logger.warning(
                                f"⚠️ SIGNAL IGNORED: {signal.symbol} - {result.reason}"
                            )
                        else:  # FAILED
                            logger.error(
                                f"❌ EXECUTION FAILED: {signal.symbol} - {result.reason} - {result.error}"
                            )
                    else:
                        # No execution - just log that signal was saved
                        logger.info(
                            f"📈 SIGNAL SAVED: {signal.symbol} @ ₹{signal.price:.2f}, "
                            f"SL: ₹{signal.stop_loss:.2f}, "
                            f"Target: ₹{signal.target:.2f}, "
                            f"Reason: {signal.reason}"
                        )
            
            except Exception as e:
                logger.error(f"Error processing {candidate.symbol}: {e}", exc_info=True)
        
        # Print filtering summary
        logger.info(f"🔍 Filtering Results:")
        logger.info(f"  ├─ With Historical Data ({len(with_historical_data)}): {', '.join(with_historical_data) if with_historical_data else 'None'}")
        logger.info(f"  ├─ Passed Filters ({len(passed_filters)}): {', '.join(passed_filters) if passed_filters else 'None'}")
        logger.info(f"  └─ Generated Signals ({len(generated_signals)}): {', '.join(generated_signals) if generated_signals else 'None'}")
    
    def _prepare_metadata(self, candidate: Candidate, stock_df) -> dict:
        """
        Prepare metadata for signal storage.
        
        Args:
            candidate: Stock candidate
            stock_df: Stock dataframe with indicators
        
        Returns:
            Metadata dictionary
        """
        metadata = {
            "gain_pct": candidate.gain_pct,
            "volume": candidate.volume,
            "avg_volume": candidate.avg_volume,
        }
        
        # Add strategy-specific metadata
        if 'vwap' in stock_df.columns:
            metadata['vwap'] = float(stock_df['vwap'].iloc[-1])
        
        if 'ema_20' in stock_df.columns:
            metadata['ema_20'] = float(stock_df['ema_20'].iloc[-1])
        
        return metadata
    
    async def _fetch_historical_data(self, symbol: str, days: int = 5):
        """
        Fetch historical data for symbol.
        
        Args:
            symbol: Stock symbol
            days: Number of days of data to fetch
        
        Returns:
            DataFrame with OHLCV data or None
        """
        if not self.zerodha_data_source:
            logger.debug("Zerodha data source not available")
            return None
        
        try:
            # Calculate date range
            from_date = now_ist() - timedelta(days=days + 5)  # Buffer for holidays
            to_date = now_ist()
            
            # Search for instrument
            instruments = self.zerodha_data_source.search_instruments(symbol)
            if not instruments:
                logger.debug(f"No instrument found for {symbol}")
                return None
            
            instrument = instruments[0]
            
            # Fetch historical data
            df = self.zerodha_data_source.get_historical_data(
                instrument.instrument_token,
                from_date,
                to_date,
                interval='5minute'
            )
            
            if df is None or df.empty:
                return None
            
            logger.debug(f"Fetched {len(df)} candles for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None
    
    # ================================================================
    # SCHEDULER SETUP
    # ================================================================
    
    def setup_scheduler(self):
        """Setup scheduler with all jobs"""
        # Market open job (9:15 AM)
        self.scheduler.add_job(
            self.market_open_job,
            CronTrigger(hour=9, minute=15, day_of_week='mon-fri'),
            id='market_open',
            name='Market Open Job'
        )
        
        # Scan job (every minute from 9:16 AM to 3:20 PM)
        self.scheduler.add_job(
            self.scan_job,
            CronTrigger(minute='*', hour='9-14,15', day_of_week='mon-fri'),
            id='scan',
            name='Market Scan Job'
        )
        
        # Market close job (3:30 PM)
        self.scheduler.add_job(
            self.market_close_job,
            CronTrigger(hour=15, minute=30, day_of_week='mon-fri'),
            id='market_close',
            name='Market Close Job'
        )
        
        logger.info("✅ Scheduler configured")
    
    async def start(self):
        """Start the worker"""
        logger.info("\n" + "=" * 70)
        logger.info(f"🚀 {self.get_strategy_name().upper()} WORKER STARTING")
        logger.info("=" * 70)
        logger.info(f"Strategy: {self.config.name}")
        logger.info(f"Scan Interval: 1 minute")
        logger.info(f"Signals saved to: ./signals/")
        logger.info("=" * 70 + "\n")
        
        # Setup scheduler
        self.setup_scheduler()
        
        # Start scheduler
        self.scheduler.start()
        logger.info("✅ Scheduler started")
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            logger.info("\n🛑 Stopping worker...")
            await self._cleanup()
            logger.info("✅ Worker stopped")
    
    async def _cleanup(self):
        """Cleanup all resources on shutdown"""
        # Stop scheduler
        if self.scheduler:
            self.scheduler.shutdown()
        
        # Cleanup scanner resources
        if self.scanner:
            await self.scanner.close()
        
        # Cleanup NSE data source session
        if self.nse_data_source:
            await self.nse_data_source.close()
        
        # Disconnect database
        if self.database:
            await self.database.disconnect()
            logger.info("✅ Database disconnected")
