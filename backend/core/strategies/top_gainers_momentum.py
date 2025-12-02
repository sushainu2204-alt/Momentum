"""
Top Gainers Momentum Strategy

Strategy Logic:
1. Screen for stocks gaining 2-3%
2. Apply volume surge filter
3. Check index trend (Nifty bullish)
4. Check stock momentum (VWAP, EMA, candle break)
5. Avoid upper circuit stocks (>6% gain)
6. Enter with 1% SL, 2% target
7. Exit at target/SL or 3:20 PM
"""

from typing import Optional, Tuple
from datetime import datetime, time
import pandas as pd

from backend.core.strategies.base import BaseStrategy
from backend.core.config import TopGainersMomentumConfig
from backend.core.indicators import TechnicalIndicators, MarketIndicators
from backend.models import Signal, SignalType, Candidate, Position
from backend.infrastructure.data_sources import Quote


class TopGainersMomentumStrategy(BaseStrategy):
    """
    Top Gainers Momentum Strategy with 5 filters.
    
    Usage:
        config = TopGainersMomentumConfig()
        strategy = TopGainersMomentumStrategy(config)
        
        # Check if stock passes filters
        if strategy.apply_filters(candidate, stock_df, index_df):
            signal = strategy.should_enter(candidate, stock_df)
            if signal:
                # Execute trade
                pass
    """
    
    def __init__(self, config: TopGainersMomentumConfig):
        """
        Initialize strategy with configuration.
        
        Args:
            config: Strategy configuration with all parameters
        """
        self.config = config
        self.name = config.name
        self.description = config.description
    
    # ================================================================
    # FILTER 1: VOLUME SURGE
    # ================================================================
    
    def _check_volume_surge_candidate(self, candidate: Candidate, df: pd.DataFrame) -> bool:
        """
        Check if volume is surging using candidate's current volume vs avg_volume.
        
        Two checks:
        1. Current volume > multiplier * average volume (from candidate)
        2. OR 5-min candle volume > average of previous candles
        
        Args:
            candidate: Stock candidate with current and average volume
            df: Stock OHLCV dataframe
        
        Returns:
            True if volume is surging
        """
        # Check 1: Current volume vs average volume
        if candidate.avg_volume > 0:
            volume_ratio = candidate.volume / candidate.avg_volume
            if volume_ratio >= self.config.volume_surge_multiplier:
                return True
        
        # Check 2: Candle volume surge (fallback if avg_volume not available)
        if len(df) >= self.config.candle_volume_lookback:
            volume_surge = TechnicalIndicators.calculate_volume_surge(
                df,
                lookback=self.config.candle_volume_lookback,
                multiplier=self.config.volume_surge_multiplier
            )
            
            # Check latest candle
            if volume_surge.iloc[-1]:
                return True
        
        return False
    
    # ================================================================
    # FILTER 2: INDEX TREND
    # ================================================================
    
    def _check_index_trend(self, index_df: pd.DataFrame) -> bool:
        """
        Check if index (Nifty/BankNifty) is bullish.
        
        Conditions:
        1. Index above 50 EMA (5-min timeframe)
        2. Index RSI > 55
        
        Args:
            index_df: Index OHLCV dataframe
        
        Returns:
            True if index is bullish
        """
        if len(index_df) < self.config.index_ema_period:
            return False
        
        is_bullish = MarketIndicators.is_market_bullish(
            index_df,
            ema_period=self.config.index_ema_period,
            rsi_period=self.config.index_rsi_period,
            rsi_threshold=self.config.index_rsi_min
        )
        
        return is_bullish
    
    # ================================================================
    # FILTER 3: STOCK MOMENTUM
    # ================================================================
    
    def _check_stock_momentum_candidate(self, candidate: Candidate, df: pd.DataFrame) -> bool:
        """
        Check stock-specific momentum.
        
        Conditions:
        1. Stock above 20 EMA (5-min timeframe)
        2. Stock above VWAP (optional)
        3. Current candle breaks previous candle high (optional)
        
        Args:
            candidate: Stock candidate
            df: Stock OHLCV dataframe
        
        Returns:
            True if stock has momentum
        """
        if len(df) < self.config.stock_ema_period:
            return False
        
        # Check EMA
        ema = TechnicalIndicators.calculate_ema(df, period=self.config.stock_ema_period)
        current_price = candidate.current_price
        current_ema = ema.iloc[-1]
        
        if current_price <= current_ema:
            return False
        
        # Check VWAP (optional)
        if self.config.check_vwap:
            vwap = TechnicalIndicators.calculate_vwap(df)
            current_vwap = vwap.iloc[-1]
            
            if current_price <= current_vwap:
                return False
        
        # Check candle break (optional)
        if self.config.check_candle_break:
            is_break = TechnicalIndicators.is_candle_break(df, lookback=1)
            
            if not is_break.iloc[-1]:
                return False
        
        return True
    
    # ================================================================
    # FILTER 4: PRICE CIRCUIT CHECK
    # ================================================================
    
    def _check_price_circuit_candidate(self, candidate: Candidate) -> bool:
        """
        Check if stock is near upper circuit or already gained too much.
        
        Condition:
        - Stock gain < 6% (configurable max_open_gain_pct)
        
        Args:
            candidate: Stock candidate
        
        Returns:
            True if safe to enter
        """
        if candidate.gain_pct >= self.config.max_open_gain_pct:
            return False
        
        return True
    
    # ================================================================
    # COMBINED FILTERS
    # ================================================================
    
    def apply_filters(
        self,
        candidate: Candidate,
        stock_df: pd.DataFrame,
        index_df: pd.DataFrame
    ) -> bool:
        """
        Apply all 5 filters to candidate stock.
        
        Args:
            candidate: Stock candidate from screener
            stock_df: Stock 5-min OHLCV data
            index_df: Index 5-min OHLCV data
        
        Returns:
            True if all filters pass
        """
        # Filter 1: Volume Surge (uses candidate.volume vs candidate.avg_volume)
        if not self._check_volume_surge_candidate(candidate, stock_df):
            return False
        
        # Filter 2: Index Trend
        if not self._check_index_trend(index_df):
            return False
        
        # Filter 3: Stock Momentum
        if not self._check_stock_momentum_candidate(candidate, stock_df):
            return False
        
        # Filter 4: Price Circuit
        if not self._check_price_circuit_candidate(candidate):
            return False
        
        return True
    
    # ================================================================
    # ENTRY SIGNAL GENERATION
    # ================================================================
    
    def should_enter(
        self,
        candidate: Candidate,
        stock_df: pd.DataFrame,
        current_time: datetime
    ) -> Optional[Signal]:
        """
        Generate BUY signal if entry conditions met.
        
        Args:
            candidate: Stock candidate that passed filters
            stock_df: Stock OHLCV data
            current_time: Current time
        
        Returns:
            BUY signal if should enter, None otherwise
        """
        # Check if within trading hours
        if not self._is_entry_allowed(current_time):
            return None
        
        # Calculate entry price, SL, and target
        entry_price = candidate.current_price
        stop_loss = entry_price * (1 - self.config.stop_loss_pct / 100)
        target = entry_price * (1 + self.config.target_pct / 100)
        
        # Calculate quantity (will be set by position manager based on capital)
        # Placeholder value - actual quantity calculated in backtest/live engine
        quantity = 1
        
        signal = Signal(
            symbol=candidate.symbol,
            instrument_token=candidate.instrument_token,
            signal_type=SignalType.BUY,
            price=entry_price,
            timestamp=current_time,
            reason=f"Top gainer {candidate.gain_pct:.2f}% with volume surge and momentum",
            quantity=quantity,
            stop_loss=stop_loss,
            target=target
        )
        
        return signal
    
    # ================================================================
    # EXIT SIGNAL GENERATION
    # ================================================================
    # TODO: where is this used? How is it triggered? If we have SL ste for buy signal, do we need this?
    def should_exit(
        self,
        position: Position,
        current_price: float,
        current_time: datetime
    ) -> Optional[Signal]:
        """
        Generate SELL signal if exit conditions met.
        
        Exits:
        1. Target hit
        2. Stop loss hit
        3. Time-based exit (3:20 PM)
        4. Optional: Trailing stop loss
        
        Args:
            position: Open position
            current_price: Current stock price
            current_time: Current time
        
        Returns:
            SELL signal if should exit, None otherwise
        """
        # Get exit time from config - ensure same timezone as current_time
        exit_time = datetime.combine(current_time.date(), self.config.exit_time)
        if current_time.tzinfo is not None:
            exit_time = exit_time.replace(tzinfo=current_time.tzinfo)
        
        # Check exit conditions
        exit_reason = position.check_exit(current_price, current_time, exit_time)
        
        if exit_reason:
            signal = Signal(
                symbol=position.symbol,
                instrument_token=position.instrument_token,
                signal_type=SignalType.SELL,
                price=current_price,
                timestamp=current_time,
                reason=exit_reason,
                quantity=position.quantity
            )
            return signal
        
        # Check trailing stop loss (if enabled)
        if self.config.trailing_stop:
            if self._check_trailing_stop(position, current_price):
                signal = Signal(
                    symbol=position.symbol,
                    instrument_token=position.instrument_token,
                    signal_type=SignalType.SELL,
                    price=current_price,
                    timestamp=current_time,
                    reason="TRAILING_STOP",
                    quantity=position.quantity
                )
                return signal
        
        return None
    
    # ================================================================
    # HELPER METHODS
    # ================================================================
    
    def _is_entry_allowed(self, current_time: datetime) -> bool:
        """Check if entry is allowed at current time"""
        current_time_only = current_time.time()
        
        # Check if before no_entry_after time
        if current_time_only >= self.config.no_entry_after:
            return False
        
        # Check if after market open
        if current_time_only < self.config.market_open_time:
            return False
        
        return True
    
    # TODO : Where is this used? How can we use this better to update out SL dynamically?
    def _check_trailing_stop(self, position: Position, current_price: float) -> bool:
        """
        Check if trailing stop loss is hit.
        
        Trailing SL: If price moves favorably, move SL up by trailing_stop_pct
        """
        if position.pnl_pct > self.config.trailing_stop_pct:
            # Calculate new SL
            new_sl = position.entry_price * (1 + self.config.trailing_stop_pct / 100)
            
            if current_price < new_sl:
                return True
        
        return False
    
    def calculate_position_size(self, capital: float, price: float) -> int:
        """
        Calculate position size based on capital allocation.
        
        Args:
            capital: Available capital
            price: Stock price
        
        Returns:
            Quantity to buy
        """
        allocation = capital * self.config.position_size_pct
        quantity = int(allocation / price)
        
        return max(1, quantity)  # At least 1 share
    
    # ================================================================
    # ABSTRACT METHOD IMPLEMENTATIONS (from BaseStrategy)
    # ================================================================
    
    def calculate_indicators(self, prices: pd.Series) -> Tuple:
        """
        Calculate strategy indicators from price series.
        
        For Top Gainers strategy, we use EMA and RSI.
        
        Args:
            prices: Series of prices
            
        Returns:
            Tuple of (EMA, RSI)
        """
        df = pd.DataFrame({'close': prices})
        ema = TechnicalIndicators.calculate_ema(df, period=self.config.stock_ema_period)
        
        # RSI not directly used in entry, but useful for analysis
        rsi = pd.Series([50] * len(prices))  # Placeholder
        
        return (ema.iloc[-1], rsi.iloc[-1])
    
    def generate_signal(self, current_indicators: Tuple, previous_indicators: Tuple) -> Optional[str]:
        """
        Generate trading signal based on indicator values.
        
        Note: Top Gainers strategy uses candidate-based filtering, not pure indicators.
        This method is implemented for compatibility but not the primary signal mechanism.
        
        Args:
            current_indicators: Current indicator values
            previous_indicators: Previous indicator values
            
        Returns:
            "BUY", "SELL", or None
        """
        # This strategy primarily uses should_enter() and should_exit()
        # This method is for compatibility with BaseStrategy interface
        return None
    
    def calculate_signals_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate signals for entire DataFrame (backtesting).
        
        Adds indicator columns to dataframe.
        
        Args:
            df: DataFrame with OHLC data
            
        Returns:
            DataFrame with added indicator columns
        """
        # Add EMA
        df['ema_20'] = TechnicalIndicators.calculate_ema(df, period=self.config.stock_ema_period)
        
        # Add VWAP if needed
        if self.config.check_vwap:
            df['vwap'] = TechnicalIndicators.calculate_vwap(df)
        
        # Add volume surge indicator
        df['volume_surge'] = TechnicalIndicators.calculate_volume_surge(
            df,
            lookback=self.config.candle_volume_lookback,
            multiplier=self.config.volume_surge_multiplier
        )
        
        return df
    
    @property
    def min_data_points(self) -> int:
        """Minimum number of data points required for calculation"""
        return max(self.config.stock_ema_period, self.config.index_ema_period)
    
    def __str__(self) -> str:
        """String representation"""
        return str(self.config)
