"""
Top Gainers Momentum Strategy Live Worker

Executes Top Gainers Momentum Strategy in live market.

Features:
- Scans market every 1 minute
- Opens multiple positions (up to max_positions)
- Monitors positions in real-time
- Auto-exits at target/SL/3:20 PM
- Logs all trades and P&L

Usage:
    python -m backend.jobs.strategy.top_gainers_worker
"""
# TODO : Revisit this class
import asyncio
import signal
import sys
from datetime import datetime, time, timedelta
from typing import Dict, List
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.core.strategies.top_gainers_momentum import TopGainersMomentumStrategy
from backend.core.services import PositionManagerService, StockScreenerService, KiteService
from backend.core.services.market.stock_screener_service import UniverseFactory
from backend.config import TopGainersMomentumConfig, StrategyConfigFactory
from backend.infrastructure.data_sources import ZerodhaDataSource
from backend.core.models import Signal, SignalType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TopGainersWorker:
    """
    Live trading worker for Top Gainers Momentum Strategy.
    
    Workflow:
    1. Market open (9:15 AM): Initialize
    2. Every 1 minute: Scan for opportunities
    3. On opportunity: Check filters → Enter position
    4. Real-time monitoring: Update positions, check exits
    5. 3:20 PM: Square off all positions
    6. Market close (3:30 PM): Generate daily report
    """
    
    def __init__(self):
        """Initialize worker"""
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        self.market_open = time(9, 15)
        self.market_close = time(15, 30)
        
        # Initialize components
        logger.info("Initializing Top Gainers Worker...")
        
        # Load configuration
        self.config = StrategyConfigFactory.create('top_gainers_momentum')
        logger.info(f"Strategy Config: {self.config.name}")
        
        # Initialize Kite service
        self.kite_service = KiteService()
        kite = self.kite_service.get_kite_instance()
        
        if kite is None:
            logger.error("❌ Kite Connect not initialized. Please authenticate first.")
            sys.exit(1)
        
        # Initialize components
        self.data_source = ZerodhaDataSource(kite)
        self.universe = UniverseFactory.create('fno')
        self.screener = StockScreenerService(self.data_source, self.universe, self.config)
        self.strategy = TopGainersMomentumStrategy(self.config)
        self.position_manager = PositionManagerService(self.config)
        
        logger.info("✅ Worker initialized successfully")
    
    # ================================================================
    # SCHEDULED JOBS
    # ================================================================
    
    async def market_open_job(self):
        """Job to run at market open (9:15 AM)"""
        logger.info("="*70)
        logger.info("🔔 MARKET OPEN - Starting Top Gainers Momentum Strategy")
        logger.info("="*70)
        logger.info(f"Strategy: {self.config.name}")
        logger.info(f"Max Concurrent Positions: {self.config.max_positions}")
        logger.info(f"Risk-Reward Ratio: {self.config.get_risk_reward_ratio()}")
        logger.info("="*70)
        
        self.is_running = True
        
        # Reset position manager (new day)
        self.position_manager.reset()
    
    async def scan_job(self):
        """Job to scan market (runs every minute)"""
        if not self.is_running:
            return
        
        try:
            current_time = datetime.now()
            logger.info(f"\n[{current_time.time()}] 🔍 Scanning market...")
            
            # Step 1: Update existing positions
            await self._update_positions(current_time)
            
            # Step 2: Check if we can open new positions
            if self.position_manager.get_position_count() >= self.config.max_positions:
                logger.info(f"Max positions reached ({self.config.max_positions})")
                return
            
            # Step 3: Screen for candidates
            candidates = self.screener.screen_top_gainers()
            logger.info(f"Found {len(candidates)} candidates")
            
            if not candidates:
                return
            
            # Step 4: Apply filters and enter positions
            await self._process_candidates(candidates, current_time)
            
            # Step 5: Log status
            stats = self.position_manager.get_stats()
            logger.info(
                f"Status: Open={stats['open_positions']}, "
                f"P&L=₹{stats['total_pnl']:.2f}"
            )
            
        except Exception as e:
            logger.error(f"Error in scan job: {e}", exc_info=True)
    
    async def squareoff_job(self):
        """Job to square off all positions (3:20 PM)"""
        logger.info("\n" + "="*70)
        logger.info("🔔 SQUARE OFF TIME - Exiting all positions")
        logger.info("="*70)
        
        try:
            current_time = datetime.now()
            open_positions = self.position_manager.get_open_positions()
            
            if not open_positions:
                logger.info("No open positions to square off")
                return
            
            logger.info(f"Squaring off {len(open_positions)} positions...")
            
            # Fetch current quotes
            symbols = [p.symbol for p in open_positions]
            quotes = await self._fetch_quotes(symbols)
            
            # Close all positions
            for position in open_positions:
                if position.symbol in quotes:
                    current_price = quotes[position.symbol]
                    self.position_manager.close_position(
                        position.symbol,
                        current_price,
                        current_time,
                        "TIME_EXIT"
                    )
                    
                    # TODO: Place actual sell order
                    logger.info(
                        f"SQUARE OFF: {position.symbol} @ {current_price:.2f}, "
                        f"P&L=₹{position.pnl:.2f}"
                    )
            
            logger.info("✅ All positions squared off")
            
        except Exception as e:
            logger.error(f"Error in squareoff job: {e}", exc_info=True)
    
    async def market_close_job(self):
        """Job to run at market close (3:30 PM)"""
        logger.info("\n" + "="*70)
        logger.info("🔔 MARKET CLOSE - Generating Daily Report")
        logger.info("="*70)
        
        self.is_running = False
        
        # Generate report
        stats = self.position_manager.get_stats()
        
        logger.info("DAILY PERFORMANCE:")
        logger.info(f"  Total Trades:        {stats['closed_positions']}")
        logger.info(f"  Win Rate:            {stats['win_rate']:.2f}%")
        logger.info(f"  Total P&L:           ₹{stats['total_pnl']:,.2f}")
        logger.info(f"  Average Win:         ₹{stats['avg_win']:,.2f}")
        logger.info(f"  Average Loss:        ₹{stats['avg_loss']:,.2f}")
        logger.info(f"  Profit Factor:       {stats['profit_factor']:.2f}")
        
        # Export trade log
        closed = self.position_manager.get_closed_positions()
        if closed:
            import pandas as pd
            
            trade_data = []
            for pos in closed:
                trade_data.append({
                    'symbol': pos.symbol,
                    'entry_time': pos.entry_time,
                    'entry_price': pos.entry_price,
                    'exit_time': pos.exit_time,
                    'exit_price': pos.exit_price,
                    'quantity': pos.quantity,
                    'pnl': pos.pnl,
                    'pnl_pct': pos.pnl_pct,
                    'exit_reason': pos.exit_reason
                })
            
            df = pd.DataFrame(trade_data)
            filename = f'trades_{datetime.now().strftime("%Y%m%d")}.csv'
            df.to_csv(filename, index=False)
            logger.info(f"Trade log exported to: {filename}")
        
        logger.info("=" * 70)
        logger.info("Daily report generated")
    
    # ================================================================
    # CORE LOGIC
    # ================================================================
    
    async def _update_positions(self, current_time: datetime):
        """
        Update all open positions and check for exits.
        
        Args:
            current_time: Current time
        """
        open_positions = self.position_manager.get_open_positions()
        
        if not open_positions:
            return
        
        # Fetch current quotes
        symbols = [p.symbol for p in open_positions]
        quotes = await self._fetch_quotes(symbols)
        
        # Update positions
        exit_signals = self.position_manager.update_positions(quotes, current_time)
        
        # Execute exits
        for signal in exit_signals:
            await self._execute_exit(signal)
    
    async def _process_candidates(self, candidates: List, current_time: datetime):
        """
        Process candidates: apply filters and enter positions.
        
        Args:
            candidates: List of candidate stocks
            current_time: Current time
        """
        # Fetch index data
        index_df = await self._fetch_historical_data("NIFTY 50", 50)
        
        if index_df is None:
            logger.warning("Could not fetch index data, skipping scan")
            return
        
        for candidate in candidates:
            # Check if max positions reached
            if self.position_manager.get_position_count() >= self.config.max_positions:
                break
            
            # Check if position already exists
            if self.position_manager.has_position(candidate.symbol):
                continue
            
            # Fetch stock data
            stock_df = await self._fetch_historical_data(candidate.symbol, 50)
            
            if stock_df is None:
                continue
            
            # Enrich candidate with average volume from historical data
            candidate = self.screener.enrich_candidate_with_volume(candidate, lookback_days=10)
            
            # Apply filters
            if self.strategy.apply_filters(candidate, stock_df, index_df):
                # Generate entry signal
                signal = self.strategy.should_enter(candidate, stock_df, current_time)
                
                if signal:
                    await self._execute_entry(signal)
    
    async def _execute_entry(self, signal: Signal):
        """
        Execute entry signal: place order and add position.
        
        Args:
            signal: BUY signal
        """
        try:
            # TODO: Place actual buy order
            # order_id = kite.place_order(
            #     variety=kite.VARIETY_REGULAR,
            #     exchange=kite.EXCHANGE_NSE,
            #     tradingsymbol=signal.symbol,
            #     transaction_type=kite.TRANSACTION_TYPE_BUY,
            #     quantity=signal.quantity,
            #     order_type=kite.ORDER_TYPE_MARKET,
            #     product=kite.PRODUCT_MIS
            # )
            
            # For now, just log
            logger.info(
                f"📈 ENTRY: {signal.symbol} @ {signal.price:.2f}, "
                f"qty={signal.quantity}, SL={signal.stop_loss:.2f}, "
                f"Target={signal.target:.2f}"
            )
            
            # Add position
            self.position_manager.add_position(signal)
            
        except Exception as e:
            logger.error(f"Failed to execute entry: {e}", exc_info=True)
    
    async def _execute_exit(self, signal: Signal):
        """
        Execute exit signal: place order and close position.
        
        Args:
            signal: SELL signal
        """
        try:
            # TODO: Place actual sell order
            # order_id = kite.place_order(
            #     variety=kite.VARIETY_REGULAR,
            #     exchange=kite.EXCHANGE_NSE,
            #     tradingsymbol=signal.symbol,
            #     transaction_type=kite.TRANSACTION_TYPE_SELL,
            #     quantity=signal.quantity,
            #     order_type=kite.ORDER_TYPE_MARKET,
            #     product=kite.PRODUCT_MIS
            # )
            
            logger.info(
                f"📉 EXIT: {signal.symbol} @ {signal.price:.2f}, "
                f"qty={signal.quantity}, reason={signal.reason}"
            )
            
        except Exception as e:
            logger.error(f"Failed to execute exit: {e}", exc_info=True)
    
    # ================================================================
    # DATA FETCHING
    # ================================================================
    
    async def _fetch_quotes(self, symbols: List[str]) -> Dict[str, float]:
        """
        Fetch current quotes for symbols.
        
        Args:
            symbols: List of symbols
        
        Returns:
            Dict of symbol -> current_price
        """
        try:
            # Get instrument tokens for symbols
            instrument_map = {}  # symbol -> instrument_token
            for symbol in symbols:
                instruments = self.data_source.search_instruments(symbol)
                if instruments:
                    instrument_map[symbol] = instruments[0].instrument_token
            
            if not instrument_map:
                logger.warning(f"No instruments found for symbols: {symbols}")
                return {}
            
            # Fetch quotes using instrument tokens
            tokens = list(instrument_map.values())
            quotes = self.data_source.get_quotes(tokens)
            
            # Map back to symbols
            result = {}
            token_to_symbol = {v: k for k, v in instrument_map.items()}
            
            for quote in quotes:
                if quote.instrument_token in token_to_symbol:
                    symbol = token_to_symbol[quote.instrument_token]
                    result[symbol] = quote.last_price
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching quotes: {e}")
            return {}
    
    async def _fetch_historical_data(self, symbol: str, candles: int):
        """
        Fetch historical data for symbol.
        
        Args:
            symbol: Stock symbol
            candles: Number of 5-min candles to fetch
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Calculate date range
            # 5-min candles: ~75 candles per trading day (6.25 hours)
            # To get 'candles' worth of data, we need roughly candles/75 days
            # Add buffer for holidays/weekends
            from_date = datetime.now() - timedelta(days=int(candles/50) + 10)
            to_date = datetime.now()
            
            # Get instrument token
            instruments = self.data_source.search_instruments(symbol)
            if not instruments:
                logger.warning(f"No instrument found for {symbol}")
                return None
            
            instrument = instruments[0]
            
            # Fetch historical data
            df = self.data_source.get_historical_data(
                instrument.instrument_token,
                from_date,
                to_date,
                interval='5minute'
            )
            
            if df is None or df.empty:
                logger.warning(f"No historical data for {symbol}")
                return None
            
            # Return last 'candles' rows
            if len(df) > candles:
                df = df.tail(candles)
            
            logger.debug(f"Fetched {len(df)} candles for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
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
        
        # Square off job (3:20 PM)
        self.scheduler.add_job(
            self.squareoff_job,
            CronTrigger(hour=15, minute=20, day_of_week='mon-fri'),
            id='squareoff',
            name='Square Off Job'
        )
        
        # Market close job (3:30 PM)
        self.scheduler.add_job(
            self.market_close_job,
            CronTrigger(hour=15, minute=30, day_of_week='mon-fri'),
            id='market_close',
            name='Market Close Job'
        )
        
        logger.info("✅ Scheduler configured with all jobs")
    
    async def start(self):
        """Start the worker"""
        logger.info("\n" + "="*70)
        logger.info("🚀 TOP GAINERS MOMENTUM WORKER STARTING")
        logger.info("="*70)
        logger.info(f"Strategy: {self.config.name}")
        logger.info(f"Universe: FnO stocks")
        logger.info(f"Scan Interval: 1 minute")
        logger.info("="*70 + "\n")
        
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


def main():
    """Main entry point"""
    worker = TopGainersWorker()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("\n🛑 Received interrupt signal, shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start worker
    asyncio.run(worker.start())


if __name__ == '__main__':
    main()
