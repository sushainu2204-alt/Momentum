"""
VWAP Breakout Strategy

Strategy Logic:
1. Wait for stock to trade above VWAP
2. Confirm with volume > 1.5x average
3. Enter on breakout
4. Exit at 1.5% target or 0.7% stop loss
5. Auto-exit at 3:20 PM
"""

from typing import Optional
from datetime import datetime
import pandas as pd
import numpy as np

from backend.core.strategies.base import BaseStrategy
from backend.core.config import VWAPBreakoutConfig
from backend.core.indicators import TechnicalIndicators
from backend.models import Signal, SignalType, Candidate, Position


class VWAPBreakoutStrategy(BaseStrategy):
    """
    VWAP Breakout Strategy with volume confirmation.
    
    Usage:
        config = VWAPBreakoutConfig()
        strategy = VWAPBreakoutStrategy(config)
        
        if strategy.apply_filters(candidate, stock_df):
            signal = strategy.should_enter(candidate, stock_df, current_time)
            if signal:
                # Execute trade
                pass
    """
    
    def __init__(self, config: VWAPBreakoutConfig):
        """
        Initialize strategy with configuration.
        
        Args:
            config: Strategy configuration
        """
        self.config = config
        self.name = config.name
        self.description = config.description
    
    def apply_filters(
        self,
        candidate: Candidate,
        stock_df: pd.DataFrame
    ) -> bool:
        """
        Apply VWAP + volume filters.
        
        Args:
            candidate: Stock candidate
            stock_df: Stock OHLCV data
        
        Returns:
            True if all filters pass
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Filter 1: Price above VWAP
        vwap_pass, vwap_info = self._check_vwap_breakout_detailed(candidate, stock_df)
        if not vwap_pass:
            logger.debug(f"{candidate.symbol}: ❌ VWAP Filter - {vwap_info}")
            return False
        logger.debug(f"{candidate.symbol}: ✅ VWAP Filter - {vwap_info}")
        
        # Filter 2: Volume confirmation
        volume_pass, volume_info = self._check_volume_surge_detailed(stock_df)
        if not volume_pass:
            logger.debug(f"{candidate.symbol}: ❌ Volume Filter - {volume_info}")
            return False
        logger.debug(f"{candidate.symbol}: ✅ Volume Filter - {volume_info}")
        
        return True
    
    def _check_vwap_breakout(self, candidate: Candidate, df: pd.DataFrame) -> bool:
        """
        Check if price is above VWAP with required percentage.
        
        Args:
            candidate: Stock candidate
            df: OHLCV data
        
        Returns:
            True if price > VWAP + breakout percentage
        """
        result, _ = self._check_vwap_breakout_detailed(candidate, df)
        return result
    
    def _check_vwap_breakout_detailed(self, candidate: Candidate, df: pd.DataFrame) -> tuple:
        """
        Check if price is above VWAP with detailed info.
        
        Returns:
            (pass: bool, info: str)
        """
        if df.empty or len(df) < 2:
            return False, "Insufficient data"
        
        # Calculate VWAP
        vwap = TechnicalIndicators.calculate_vwap(df)
        
        if vwap is None or len(vwap) == 0:
            return False, "VWAP calculation failed"
        
        current_vwap = vwap.iloc[-1]
        current_price = candidate.current_price
        
        # Check if price is above VWAP by required percentage
        vwap_threshold = current_vwap * (1 + self.config.vwap_breakout_pct / 100)
        breakout_pct = ((current_price - current_vwap) / current_vwap) * 100
        
        passed = current_price >= vwap_threshold
        info = f"Price: ₹{current_price:.2f}, VWAP: ₹{current_vwap:.2f}, Breakout: {breakout_pct:+.2f}% (need {self.config.vwap_breakout_pct:.2f}%)"
        
        return passed, info
    
    def _check_volume_surge(self, df: pd.DataFrame) -> bool:
        """
        Check if current volume > multiplier * average volume.
        
        Args:
            df: OHLCV data
        
        Returns:
            True if volume surge confirmed
        """
        result, _ = self._check_volume_surge_detailed(df)
        return result
    
    def _check_volume_surge_detailed(self, df: pd.DataFrame) -> tuple:
        """
        Check if current volume > multiplier * average volume with detailed info.
        
        Returns:
            (pass: bool, info: str)
        """
        if df.empty or len(df) < self.config.volume_lookback_candles:
            return False, f"Insufficient data (need {self.config.volume_lookback_candles} candles)"
        
        # Get current and average volume
        current_volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].iloc[-self.config.volume_lookback_candles:-1].mean()
        
        if avg_volume == 0:
            return False, "Average volume is zero"
        
        volume_ratio = current_volume / avg_volume
        passed = volume_ratio >= self.config.volume_multiplier
        
        info = f"Current: {current_volume:,.0f}, Avg: {avg_volume:,.0f}, Ratio: {volume_ratio:.2f}x (need {self.config.volume_multiplier:.2f}x)"
        
        return passed, info
    
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
        
        # Calculate quantity (placeholder - actual quantity set by position manager)
        quantity = 1
        
        signal = Signal(
            symbol=candidate.symbol,
            instrument_token=candidate.instrument_token,
            signal_type=SignalType.BUY,
            price=entry_price,
            timestamp=current_time,
            reason=f"VWAP breakout with volume surge",
            quantity=quantity,
            stop_loss=stop_loss,
            target=target
        )
        
        return signal
    
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
        
        return None
    
    def _is_entry_allowed(self, current_time: datetime) -> bool:
        """Check if entry is allowed at current time"""
        # Create cutoff times - ensure same timezone as current_time
        entry_cutoff = datetime.combine(current_time.date(), self.config.no_entry_after)
        market_open = datetime.combine(current_time.date(), self.config.market_open_time)
        
        # If current_time is timezone-aware, make cutoff times timezone-aware too
        if current_time.tzinfo is not None:
            entry_cutoff = entry_cutoff.replace(tzinfo=current_time.tzinfo)
            market_open = market_open.replace(tzinfo=current_time.tzinfo)
        
        return market_open <= current_time <= entry_cutoff
    
    def calculate_position_size(self, capital: float, price: float) -> int:
        """
        Calculate position size based on capital and price.
        
        Args:
            capital: Available capital
            price: Stock price
        
        Returns:
            Number of shares to buy
        """
        position_capital = capital * self.config.position_size_pct
        quantity = int(position_capital / price)
        
        return max(1, quantity)
    
    def calculate_indicators(self, prices: pd.Series) -> tuple:
        """
        Calculate indicators (required by BaseStrategy interface).
        Not used in this strategy - filters are applied in apply_filters().
        """
        return ()
    
    def generate_signal(self, current_indicators: tuple, previous_indicators: tuple) -> Optional[str]:
        """
        Generate signal (required by BaseStrategy interface).
        Not used in this strategy - signals generated in should_enter()/should_exit().
        """
        return None
    
    def calculate_signals_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate signals for entire DataFrame (required for backtesting).
        Not used in this strategy - uses multi-position backtest engine.
        """
        return df
    
    @property
    def min_data_points(self) -> int:
        """Minimum number of data points required"""
        return max(self.config.volume_lookback_candles, self.config.lookback_candles)
