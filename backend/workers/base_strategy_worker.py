"""
Base Strategy Worker

Abstract base class for all strategy workers.
Provides common functionality:
- Market scanning
- Signal generation
- Signal storage (file/DB)
- Scheduling
- Logging

Each concrete strategy worker extends this class and implements:
- get_strategy_name()
- create_strategy()
- create_config()
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
from backend.core.services.signal_storage import SignalStorage
from backend.core.services.signal_executor import SignalExecutor
from backend.core.services.order_manager import OrderManager
from backend.core.services.position_manager import PositionManager
from backend.core.services.capital_manager import CapitalManager
from backend.infrastructure.data_sources.nse import NSEDataSource
from backend.infrastructure.data_sources import ZerodhaDataSource
from backend.core.services.kite_service import KiteService
from backend.infrastructure.database.postgres import PostgresDatabase
from backend.models import Candidate, Signal
from backend.core.logging_config import setup_logging

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
        self.market_open_time = time(9, 15)
        self.market_close_time = time(15, 30)
        self.scan_end_time = time(15, 20)
        
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
        
        # Initialize signal storage (always available for backup)
        self.signal_storage = SignalStorage(storage_type="file", base_path="./signals", orders_path="./orders")
        
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
            
            # Initialize database
            db_config = {
                "host": "127.0.0.1",
                "port": 5432,
                "database": "appdb",
                "user": "appuser",
                "password": "secret"
            }
            self.database = PostgresDatabase(db_config)
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
                position_repository=position_repo
            )
            logger.info("✅ PositionManager initialized")
            
            # Initialize CapitalManager with default limits
            # Subclasses can override get_trading_limits() and get_mock_capital() for custom behavior
            from backend.core.services.capital_manager import TradingLimits
            
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
        
        current_time = datetime.now()
        
        # Check if we're within market scanning hours (9:16 AM - 3:20 PM)
        if current_time.hour < 9 or (current_time.hour == 9 and current_time.minute < 16):
            return  # Too early
        if current_time.hour > 15 or (current_time.hour == 15 and current_time.minute > 20):
            return  # Too late
        
        # Set is_running if not already set (handles case where worker starts after 9:15)
        if not self.is_running:
            self.is_running = True
            self.signals_generated = 0
        
        try:
            logger.info(f"\n[{current_time.strftime('%H:%M:%S')}] 🔍 Scanning market...")
            
            # Step 1: Get ALL top gainers from ALL categories
            all_categories = ['allSec', 'FOSec', 'NIFTY', 'BANKNIFTY', 'NIFTYNEXT50', 'SecGtr20', 'SecLwr20']
            all_gainers = []
            seen_symbols = set()
            
            for category in all_categories:
                try:
                    category_gainers = self.nse_data_source.get_top_gainers(category=category)
                    
                    # Add only unique symbols (avoid duplicates across categories)
                    for gainer in category_gainers:
                        if gainer.symbol not in seen_symbols:
                            all_gainers.append(gainer)
                            seen_symbols.add(gainer.symbol)
                    
                    logger.info(f"  ├─ {category}: {len(category_gainers)} stocks ({len([g for g in category_gainers if g.symbol not in seen_symbols])} unique)")
                except Exception as e:
                    logger.warning(f"  ├─ {category}: Failed to fetch - {e}")
            
            if not all_gainers:
                logger.info("No top gainers found in any category")
                return
            
            # Sort by % gain descending
            all_gainers.sort(key=lambda g: g.pct_change, reverse=True)
            
            # Print summary
            gainer_symbols = [g.symbol for g in all_gainers]
            logger.info(f"📊 Total Unique Gainers ({len(all_gainers)}): {', '.join(gainer_symbols[:10])}{'...' if len(gainer_symbols) > 10 else ''}")
            
            top_gainers = all_gainers
            
            # Step 2: Convert to candidates
            candidates = self._convert_to_candidates(top_gainers, current_time)
            
            # Step 3: Process candidates and track filtering
            await self._process_candidates(candidates, current_time)
            
            # Step 4: Log status
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
        print(f"\n📊 DAILY SUMMARY - {self.get_strategy_name().upper()}:")
        print(f"  Total Signals Generated: {self.signals_generated}")
        
        if self.use_execution:
            print(f"  ✅ Signals Executed: {self.signals_executed}")
            print(f"  ⚠️ Signals Ignored: {self.signals_ignored}")
            print(f"  ❌ Signals Failed: {self.signals_generated - self.signals_executed - self.signals_ignored}")
            
            # Get execution statistics from SignalExecutor
            if self.signal_executor:
                try:
                    exec_stats = await self.signal_executor.get_execution_stats()
                    print(f"\n  Execution Breakdown:")
                    print(f"    - Total signals processed: {exec_stats.get('total_signals', 0)}")
                    print(f"    - Orders placed: {exec_stats.get('executed', 0)}")
                    print(f"    - Signals ignored: {exec_stats.get('ignored', 0)}")
                    print(f"    - Execution failures: {exec_stats.get('failed', 0)}")
                except Exception as e:
                    logger.error(f"Error getting execution stats: {e}")
            
            # Get capital summary
            if self.capital_manager:
                try:
                    capital_summary = await self.capital_manager.get_capital_summary()
                    print(f"\n  💰 Capital Summary:")
                    print(f"    - Starting capital: ₹{capital_summary.get('starting_capital', 0):,.2f}")
                    print(f"    - Current capital: ₹{capital_summary.get('current_capital', 0):,.2f}")
                    print(f"    - Total P&L: ₹{capital_summary.get('total_pnl', 0):,.2f}")
                    print(f"    - Open positions: {capital_summary.get('open_positions', 0)}")
                except Exception as e:
                    logger.error(f"Error getting capital summary: {e}")
        
        # Export signals to CSV (if in signal-only mode or as backup)
        today = datetime.now()
        report_file = self.signal_storage.export_daily_report(today)
        
        if report_file:
            print(f"\n  📄 Report saved: {report_file}")
        
        print("=" * 70 + "\n")
        logger.info("✅ Daily report generated")
    
    # ================================================================
    # CORE LOGIC
    # ================================================================
    
    def _convert_to_candidates(
        self,
        top_gainers: List,  # List[NSETopGainer]
        current_time: datetime
    ) -> List[Candidate]:
        """
        Convert NSE top gainers to Candidate objects.
        
        Args:
            top_gainers: List of NSETopGainer objects from NSE
            current_time: Current timestamp
        
        Returns:
            List of Candidate objects
        """
        candidates = []
        
        for gainer in top_gainers:
            try:
                candidate = Candidate(
                    symbol=gainer.symbol,
                    instrument_token=0,  # Not needed for signal generation
                    current_price=gainer.last_price,
                    open_price=gainer.open_price,
                    high_price=gainer.high_price,
                    low_price=gainer.low_price,
                    volume=gainer.volume,
                    gain_pct=gainer.pct_change,
                    avg_volume=gainer.volume,  # Will be enriched if needed
                    timestamp=current_time
                )
                candidates.append(candidate)
            except Exception as e:
                logger.warning(f"Failed to convert {getattr(gainer, 'symbol', 'unknown')}: {e}")
        
        return candidates
    
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
                            
                            # Save executed order to separate file
                            self.signal_storage.save_executed_order(
                                signal=signal,
                                strategy_name=self.get_strategy_name(),
                                order_id=result.order_id,
                                quantity=result.quantity,
                                execution_result={
                                    "status": result.status,
                                    "reason": result.reason,
                                    "metadata": metadata
                                }
                            )
                            
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
            from_date = datetime.now() - timedelta(days=days + 5)  # Buffer for holidays
            to_date = datetime.now()
            
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
            self.scheduler.shutdown()
            logger.info("✅ Worker stopped")
