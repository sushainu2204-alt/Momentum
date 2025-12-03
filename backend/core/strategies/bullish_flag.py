"""
Bullish Flag Momentum Strategy

Strategy Logic:
1. Detect +2% initial move (flag pole)
2. Wait for pullback (0.3-1.0%, 2-5 candles)
3. Enter on breakout above flag high
4. Confirm with volume > 1.3x average
5. Exit at 1.8% target or 0.8% stop loss
6. Auto-exit at 3:20 PM
"""

from typing import Optional, Tuple
from datetime import datetime
import pandas as pd
import numpy as np
import logging

from backend.core.strategies.base import BaseStrategy
from backend.config import BullishFlagConfig
from backend.core.models import Signal, SignalType, Candidate, Position

logger = logging.getLogger(__name__)


class BullishFlagStrategy(BaseStrategy):
    """
    Bullish Flag Momentum Strategy.
    
    Detects bullish flag patterns (strong move + consolidation + breakout)
    and enters on breakout confirmation.
    
    Usage:
        config = BullishFlagConfig()
        strategy = BullishFlagStrategy(config)
        
        if strategy.detect_flag_pattern(stock_df):
            signal = strategy.should_enter(candidate, stock_df, current_time)
            if signal:
                # Execute trade
                pass
    """
    
    def __init__(self, config: BullishFlagConfig):
        """Initialize strategy with configuration"""
        super().__init__(config)
        # Store flag levels detected during filtering
        self._flag_high: Optional[float] = None
        self._flag_low: Optional[float] = None
    
    def detect_flag_pattern(self, df: pd.DataFrame) -> Tuple[bool, Optional[float], Optional[float]]:
        """
        Detect bullish flag pattern in recent candles.
        
        Returns:
            (pattern_detected, flag_high, flag_low)
        """
        if df.empty or len(df) < self.config.pullback_candles_max + 5:
            return False, None, None
        
        # Get recent candles - reset index for easy indexing
        # Look at last 20 candles to ensure we capture the pole
        lookback = min(20, len(df))
        recent = df.iloc[-lookback:].copy().reset_index(drop=True)
        
        # Step 1: Find flag pole (strong upward move using close prices)
        pole_start_idx = -1
        pole_end_idx = -1
        max_gain = 0
        
        # Scan for upward price moves using close prices
        for i in range(len(recent) - self.config.pullback_candles_min - 1):
            for j in range(i + 1, min(i + 7, len(recent))):  # Limit pole to 6 candles
                start_price = recent['close'].iloc[i]
                end_price = recent['close'].iloc[j]
                gain_pct = ((end_price - start_price) / start_price) * 100
                
                if gain_pct >= self.config.min_initial_move_pct and gain_pct > max_gain:
                    max_gain = gain_pct
                    pole_start_idx = i
                    pole_end_idx = j
        
        # No pole found
        if pole_end_idx == -1:
            return False, None, None
        
        # Flag high is the highest point during/after pole
        flag_high = recent['high'].iloc[pole_start_idx:pole_end_idx+1].max()
        
        # Step 2: Check for pullback after pole
        # Pullback starts from candle after pole ends
        pullback_start = pole_end_idx + 1
        
        # Need at least min pullback candles after pole
        if pullback_start + self.config.pullback_candles_min > len(recent):
            return False, None, None
        
        # Look for pullback in next few candles
        pullback_candles = recent.iloc[pullback_start:pullback_start + self.config.pullback_candles_max].copy()
        
        if len(pullback_candles) < self.config.pullback_candles_min:
            return False, None, None
        
        # Check if pullback is within valid range
        pullback_low = pullback_candles['low'].min()
        pullback_pct = ((flag_high - pullback_low) / flag_high) * 100
        
        if pullback_pct < self.config.pullback_pct_min or pullback_pct > self.config.pullback_pct_max:
            return False, None, None
        
        # Check pullback duration (number of candles from pole end to lowest low)
        pullback_low_idx = pullback_candles['low'].idxmin()
        pullback_duration = pullback_low_idx - pole_end_idx
        
        if pullback_duration < self.config.pullback_candles_min or pullback_duration > self.config.pullback_candles_max:
            return False, None, None
        
        # Valid flag pattern detected
        return True, flag_high, pullback_low
    
    def apply_filters(
        self,
        candidate: Candidate,
        stock_df: pd.DataFrame
    ) -> bool:
        """
        Apply flag pattern detection and volume filters.
        
        Args:
            candidate: Stock candidate
            stock_df: Stock OHLCV data
        
        Returns:
            True if all filters pass
        """
        # Filter 1: Detect flag pattern
        pattern_found, flag_high, flag_low = self.detect_flag_pattern(stock_df)
        
        if not pattern_found:
            self._log_filter_result(
                candidate.symbol,
                "Pattern Filter",
                False,
                "No bullish flag detected"
            )
            return False
        
        self._log_filter_result(
            candidate.symbol,
            "Pattern Filter",
            True,
            f"Flag detected (High: ₹{flag_high:.2f}, Low: ₹{flag_low:.2f})"
        )
        
        # Store flag levels for entry signal
        self._flag_high = flag_high
        self._flag_low = flag_low
        
        # Filter 2: Check if price is breaking out above flag
        current_price = candidate.current_price
        breakout_threshold = flag_high * (1 + self.config.breakout_threshold_pct / 100)
        breakout_pct = ((current_price - flag_high) / flag_high) * 100
        breakout_pass = current_price >= breakout_threshold
        
        self._log_filter_result(
            candidate.symbol,
            "Breakout Filter",
            breakout_pass,
            f"Price: ₹{current_price:.2f}, Flag High: ₹{flag_high:.2f}, Breakout: {breakout_pct:+.2f}% (need {self.config.breakout_threshold_pct:.2f}%)"
        )
        
        if not breakout_pass:
            return False
        
        # Filter 3: Volume confirmation
        volume_pass, volume_info = self._check_volume_surge_detailed(stock_df)
        self._log_filter_result(candidate.symbol, "Volume Filter", volume_pass, volume_info)
        if not volume_pass:
            return False
        
        return True
    
    def _check_volume_surge(self, df: pd.DataFrame) -> bool:
        """Check if current volume > multiplier * average volume"""
        result, _ = self._check_volume_surge_detailed(df)
        return result
    
    def _check_volume_surge_detailed(self, df: pd.DataFrame) -> tuple:
        """Check volume surge with detailed info"""
        if df.empty or len(df) < 20:
            return False, "Insufficient data (need 20 candles)"
        
        current_volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].iloc[-20:-1].mean()
        
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
        
        # Calculate quantity (placeholder)
        quantity = 1
        
        signal = Signal(
            symbol=candidate.symbol,
            instrument_token=candidate.instrument_token,
            signal_type=SignalType.BUY,
            price=entry_price,
            timestamp=current_time,
            reason=f"Bullish flag breakout (flag high: ₹{self._flag_high:.2f})",
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
        # Use base class implementation
        return super()._is_entry_allowed(current_time)
    
    @property
    def min_data_points(self) -> int:
        """Minimum number of data points required"""
        return max(self.config.pullback_candles_max + 10, self.config.lookback_candles)
