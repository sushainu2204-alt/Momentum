"""
Multi-Position Backtest Engine

Enhanced backtesting engine that supports:
- Multiple concurrent positions
- Intraday scanning at regular intervals
- Time-based exits (3:20 PM squareoff)
- Position manager integration
- Realistic market simulation
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, time, timedelta
import pandas as pd
import numpy as np
import logging

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.core.models import Signal, SignalType, Position, Candidate
from backend.core.strategies.top_gainers_momentum import TopGainersMomentumStrategy
from backend.core.services.position_manager_service import PositionManagerService
from backend.core.services.stock_screener_service import StockScreenerService
from backend.infrastructure.data_sources import IDataSource, Quote

logger = logging.getLogger(__name__)


class MultiPositionBacktestEngine:
    """
    Backtesting engine for intraday multi-position strategies.
    
    Features:
    - Scan market at configurable intervals (e.g., every 1 minute)
    - Open multiple concurrent positions
    - Track each position independently
    - Time-based exits (3:20 PM)
    - Realistic commission and slippage
    - Comprehensive metrics
    
    Usage:
        engine = MultiPositionBacktestEngine(
            data_source=data_source,
            strategy=strategy,
            screener=screener,
            position_manager=position_manager,
            initial_capital=100000,
            commission=0.001,
            slippage=0.0005
        )
        
        results = engine.run_backtest(
            start_date='2024-01-01',
            end_date='2024-06-30',
            scan_interval_minutes=1
        )
        
        engine.print_results(results)
    """
    
    def __init__(
        self,
        data_source: IDataSource,
        strategy: TopGainersMomentumStrategy,
        screener: StockScreenerService,
        position_manager: PositionManagerService,
        initial_capital: float = 100000,
        commission: float = 0.001,  # 0.1%
        slippage: float = 0.0005,  # 0.05%
    ):
        """
        Initialize backtest engine.
        
        Args:
            data_source: Data source for historical data
            strategy: Trading strategy
            screener: Stock screener service
            position_manager: Position manager
            initial_capital: Starting capital
            commission: Commission per trade (as fraction, e.g., 0.001 = 0.1%)
            slippage: Slippage per trade (as fraction)
        """
        self.data_source = data_source
        self.strategy = strategy
        self.screener = screener
        self.position_manager = position_manager
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        
        self.capital = initial_capital
        self.equity_curve: List[Dict] = []
        self.scan_log: List[Dict] = []
    
    # ================================================================
    # MAIN BACKTEST LOOP
    # ================================================================
    
    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        scan_interval_minutes: int = 1,
        index_symbol: str = "NIFTY 50"
    ) -> Dict:
        """
        Run multi-day backtest with intraday scanning.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            scan_interval_minutes: How often to scan (minutes)
            index_symbol: Index symbol for trend filter
        
        Returns:
            Dict with backtest results
        """
        logger.info("="*60)
        logger.info("STARTING MULTI-POSITION BACKTEST")
        logger.info("="*60)
        logger.info(f"Strategy: {self.strategy.name}")
        logger.info(f"Period: {start_date} to {end_date}")
        logger.info(f"Initial capital: ₹{self.initial_capital:,.2f}")
        logger.info(f"Commission: {self.commission*100:.3f}%")
        logger.info(f"Slippage: {self.slippage*100:.3f}%")
        logger.info(f"Scan interval: {scan_interval_minutes} min")
        logger.info("="*60)
        
        # Reset state
        self.capital = self.initial_capital
        self.position_manager.reset()
        self.equity_curve = []
        self.scan_log = []
        
        # Get trading days
        trading_days = self._get_trading_days(start_date, end_date)
        
        # Simulate each day
        for day in trading_days:
            logger.info(f"\n--- Trading Day: {day.date()} ---")
            self._simulate_trading_day(day, scan_interval_minutes, index_symbol)
            
            # Record end-of-day equity
            stats = self.position_manager.get_stats()
            self.equity_curve.append({
                'timestamp': day.replace(hour=15, minute=30),
                'capital': self.capital,
                'open_positions': stats['open_positions'],
                'total_pnl': stats['total_pnl']
            })
        
        # Calculate metrics
        results = self._calculate_metrics()
        
        logger.info("\n" + "="*60)
        logger.info("BACKTEST COMPLETED")
        logger.info("="*60)
        
        return results
    
    def _simulate_trading_day(
        self,
        day: datetime,
        scan_interval_minutes: int,
        index_symbol: str
    ):
        """
        Simulate single trading day with periodic scans.
        
        Args:
            day: Trading day
            scan_interval_minutes: Scan frequency
            index_symbol: Index for trend filter
        """
        # Market hours: 9:15 AM to 3:30 PM
        market_open = day.replace(hour=9, minute=15)
        market_close = day.replace(hour=15, minute=30)
        
        # Generate scan times
        scan_times = []
        current = market_open
        while current <= market_close:
            scan_times.append(current)
            current += timedelta(minutes=scan_interval_minutes)
        
        # Fetch index data once for the day (for trend filter)
        index_df = self._fetch_historical_data(
            index_symbol,
            day - timedelta(days=30),  # Get 30 days for indicators
            day,
            interval='5minute'
        )
        
        # Scan at each interval
        for scan_time in scan_times:
            self._process_scan(scan_time, index_df)
    
    def _process_scan(self, scan_time: datetime, index_df: pd.DataFrame):
        """
        Process single scan: screen stocks, check filters, generate signals.
        
        Args:
            scan_time: Current scan time
            index_df: Index historical data
        """
        # Update existing positions first
        self._update_open_positions(scan_time)
        
        # Only scan for new entries if we have capacity
        if self.position_manager.get_position_count() >= self.strategy.config.max_positions:
            return
        
        # Screen for candidates
        candidates = self.screener.screen_top_gainers()
        
        self.scan_log.append({
            'timestamp': scan_time,
            'candidates_found': len(candidates),
            'open_positions': self.position_manager.get_position_count()
        })
        
        if not candidates:
            return
        
        # Apply filters and generate signals
        for candidate in candidates:
            # Check if we already have position
            if self.position_manager.has_position(candidate.symbol):
                continue
            
            # Check if max positions reached
            if self.position_manager.get_position_count() >= self.strategy.config.max_positions:
                break
            
            # Fetch stock data
            stock_df = self._fetch_historical_data(
                candidate.symbol,
                scan_time - timedelta(days=30),
                scan_time,
                interval='5minute'
            )
            
            if stock_df is None or len(stock_df) < 50:
                continue
            
            # Enrich candidate with average volume from historical data
            candidate = self.screener.enrich_candidate_with_volume(candidate, lookback_days=10)
            
            # Apply filters
            if self.strategy.apply_filters(candidate, stock_df, index_df):
                # Generate entry signal
                signal = self.strategy.should_enter(candidate, stock_df, scan_time)
                
                if signal:
                    # Apply commission and slippage
                    entry_price = signal.price * (1 + self.slippage)
                    
                    # Calculate quantity based on capital
                    quantity = self.strategy.calculate_position_size(
                        self.capital,
                        entry_price
                    )
                    
                    signal.quantity = quantity
                    signal.price = entry_price
                    
                    # Deduct capital
                    cost = entry_price * quantity
                    commission_cost = cost * self.commission
                    total_cost = cost + commission_cost
                    
                    if total_cost <= self.capital:
                        self.capital -= total_cost
                        
                        # Add position
                        self.position_manager.add_position(signal)
                        
                        logger.info(
                            f"[{scan_time.time()}] ENTRY: {signal.symbol} @ "
                            f"{entry_price:.2f}, qty={quantity}, "
                            f"cost={total_cost:.2f}"
                        )
    
    def _update_open_positions(self, current_time: datetime):
        """
        Update all open positions and check for exits.
        
        Args:
            current_time: Current time
        """
        open_positions = self.position_manager.get_open_positions()
        
        if not open_positions:
            return
        
        # Fetch current quotes for all open positions
        symbols = [p.symbol for p in open_positions]
        quotes = self._fetch_current_quotes(symbols, current_time)
        
        # Update positions
        exit_signals = self.position_manager.update_positions(quotes, current_time)
        
        # Execute exits
        for signal in exit_signals:
            self._execute_exit(signal, current_time)
    
    def _execute_exit(self, signal: Signal, current_time: datetime):
        """
        Execute exit signal.
        
        Args:
            signal: SELL signal
            current_time: Current time
        """
        # Apply slippage
        exit_price = signal.price * (1 - self.slippage)
        
        # Calculate proceeds
        proceeds = exit_price * signal.quantity
        commission_cost = proceeds * self.commission
        net_proceeds = proceeds - commission_cost
        
        # Add to capital
        self.capital += net_proceeds
        
        logger.info(
            f"[{current_time.time()}] EXIT: {signal.symbol} @ "
            f"{exit_price:.2f}, qty={signal.quantity}, "
            f"proceeds={net_proceeds:.2f}, reason={signal.reason}"
        )
    
    # ================================================================
    # DATA FETCHING
    # ================================================================
    
    def _fetch_historical_data(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        interval: str = '5minute'
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLCV data for symbol.
        
        Args:
            symbol: Stock symbol
            from_date: Start date
            to_date: End date
            interval: Candle interval
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Get instrument token
            instruments = self.data_source.search_instruments(symbol)
            if not instruments:
                logger.warning(f"No instrument found for {symbol}")
                return None
            
            # Use first match (NSE preferred)
            instrument = instruments[0]
            
            # Fetch historical data
            df = self.data_source.get_historical_data(
                instrument.instrument_token,
                from_date,
                to_date,
                interval
            )
            
            if df is None or df.empty:
                logger.warning(f"No data returned for {symbol}")
                return None
            
            # Ensure required columns
            required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required_cols):
                logger.warning(f"Missing required columns for {symbol}")
                return None
            
            logger.debug(f"Fetched {len(df)} candles for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return None
    
    def _fetch_current_quotes(
        self,
        symbols: List[str],
        current_time: datetime
    ) -> Dict[str, float]:
        """
        Fetch current quotes for symbols.
        
        For backtesting, we fetch the OHLC data at current_time and use close price.
        
        Args:
            symbols: List of symbols
            current_time: Current time
        
        Returns:
            Dict of symbol -> current_price
        """
        quotes = {}
        
        try:
            # For backtesting, fetch 5-min candle at current time
            for symbol in symbols:
                # Get 1 candle at current time
                df = self._fetch_historical_data(
                    symbol,
                    current_time - timedelta(minutes=10),  # Lookback to ensure we get data
                    current_time,
                    interval='5minute'
                )
                
                if df is not None and not df.empty:
                    # Use most recent close price
                    quotes[symbol] = df['close'].iloc[-1]
                else:
                    logger.warning(f"No quote data for {symbol}")
            
            logger.debug(f"Fetched quotes for {len(quotes)}/{len(symbols)} symbols")
            
        except Exception as e:
            logger.error(f"Error fetching current quotes: {e}")
        
        return quotes
    
    def _get_trading_days(self, start_date: str, end_date: str) -> List[datetime]:
        """
        Get list of trading days between start and end date.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            List of trading days
        """
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Generate all days
        days = []
        current = start
        while current <= end:
            # Skip weekends (5=Saturday, 6=Sunday)
            if current.weekday() < 5:
                days.append(current)
            current += timedelta(days=1)
        
        return days
    
    # ================================================================
    # METRICS & REPORTING
    # ================================================================
    
    def _calculate_metrics(self) -> Dict:
        """Calculate comprehensive backtest metrics"""
        stats = self.position_manager.get_stats()
        closed_positions = self.position_manager.get_closed_positions()
        
        if not closed_positions:
            return {
                'initial_capital': self.initial_capital,
                'total_trades': 0,
                'final_capital': self.capital,
                'total_return_pct': 0,
                'total_pnl': 0,
                'open_positions': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'max_drawdown_pct': 0,
                'total_scans': len(self.scan_log)
            }
        
        # Calculate equity curve metrics
        equity_df = pd.DataFrame(self.equity_curve)
        
        if len(equity_df) > 0:
            equity_series = equity_df['capital'] + equity_df['total_pnl']
            
            # Drawdown
            running_max = equity_series.expanding().max()
            drawdown = equity_series - running_max
            max_drawdown = drawdown.min()
            max_drawdown_pct = (max_drawdown / running_max.max()) * 100 if running_max.max() > 0 else 0
            
            # Sharpe ratio (annualized)
            returns = equity_series.pct_change().dropna()
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0
        else:
            max_drawdown = 0
            max_drawdown_pct = 0
            sharpe_ratio = 0
        
        # Total return
        final_capital = self.capital + stats['open_pnl']
        total_return_pct = ((final_capital - self.initial_capital) / self.initial_capital) * 100
        
        return {
            'initial_capital': self.initial_capital,
            'final_capital': final_capital,
            'total_return_pct': total_return_pct,
            'total_pnl': stats['total_pnl'],
            'total_trades': stats['closed_positions'],
            'open_positions': stats['open_positions'],
            'win_rate': stats['win_rate'],
            'avg_win': stats['avg_win'],
            'avg_loss': stats['avg_loss'],
            'profit_factor': stats['profit_factor'],
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'total_scans': len(self.scan_log)
        }
    
    def print_results(self, results: Dict):
        """Pretty print backtest results"""
        print("\n" + "="*70)
        print("MULTI-POSITION BACKTEST RESULTS")
        print("="*70)
        
        print(f"\n📊 PERFORMANCE:")
        print(f"  Initial Capital:     ₹{results['initial_capital']:,.2f}")
        print(f"  Final Capital:       ₹{results['final_capital']:,.2f}")
        print(f"  Total Return:        {results['total_return_pct']:.2f}%")
        print(f"  Total P&L:           ₹{results['total_pnl']:,.2f}")
        
        print(f"\n📈 TRADES:")
        print(f"  Total Trades:        {results['total_trades']}")
        print(f"  Open Positions:      {results['open_positions']}")
        print(f"  Win Rate:            {results['win_rate']:.2f}%")
        
        print(f"\n💰 WIN/LOSS:")
        print(f"  Average Win:         ₹{results['avg_win']:,.2f}")
        print(f"  Average Loss:        ₹{results['avg_loss']:,.2f}")
        print(f"  Profit Factor:       {results['profit_factor']:.2f}")
        
        print(f"\n📉 RISK:")
        print(f"  Sharpe Ratio:        {results['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown:        ₹{results['max_drawdown']:,.2f}")
        print(f"  Max Drawdown %:      {results['max_drawdown_pct']:.2f}%")
        
        print(f"\n🔍 SCANNING:")
        print(f"  Total Scans:         {results['total_scans']}")
        
        print("\n" + "="*70 + "\n")
    
    def get_equity_curve(self) -> pd.DataFrame:
        """Export equity curve to DataFrame"""
        return pd.DataFrame(self.equity_curve)
    
    def get_scan_log(self) -> pd.DataFrame:
        """Export scan log to DataFrame"""
        return pd.DataFrame(self.scan_log)
    
    def get_trade_log(self) -> pd.DataFrame:
        """Export closed positions to DataFrame"""
        closed = self.position_manager.get_closed_positions()
        
        if not closed:
            return pd.DataFrame()
        
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
                'exit_reason': pos.exit_reason,
                'status': pos.status.value
            })
        
        return pd.DataFrame(trade_data)
