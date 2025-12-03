"""
VWAP EMA Breakout Strategy 
(Custom strategy given by AI combining VWAP and EMA filters for breakout trades)

Entry Conditions:
1. Stock in top gainers (2-4% gain)
2. Price > VWAP
3. Price > 20 EMA
4. Volume > 1.5x average
5. Current price breaks previous candle high

Exit Conditions:
- Target: +1.5%
- Stop Loss: -0.7%
- Time: Auto-exit at 3:20 PM

Strategy Logic:
- Combines trend confirmation (VWAP, EMA) with momentum (volume) and breakout
- Tight SL and reasonable target for intraday moves
"""

from typing import Optional
from datetime import datetime, time
import pandas as pd
import numpy as np
import logging

from backend.core.strategies.base import BaseStrategy
from backend.config import VWAPEMABreakoutConfig
from backend.core.models import Candidate, Signal, SignalType, Position

logger = logging.getLogger(__name__)


class VWAPEMABreakoutStrategy(BaseStrategy):
    """
    VWAP EMA Breakout Strategy - breakout confirmation with trend filters.
    
    Example usage:
        config = VWAPEMABreakoutConfig(
            min_gain_pct=2.0,
            max_gain_pct=4.0,
            ema_period=20,
            volume_multiplier=1.5
        )
        
        strategy = VWAPEMABreakoutStrategy(config)
        
        # Check if candidate passes filters
        if strategy.apply_filters(candidate, stock_df):
            signal = strategy.should_enter(candidate, stock_df, current_time)
            if signal:
                # Execute trade
                pass
    """
    
    def __init__(self, config: VWAPEMABreakoutConfig):
        """Initialize strategy with configuration"""
        super().__init__(config)
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate VWAP and EMA indicators.
        
        Args:
            df: OHLCV data
        
        Returns:
            DataFrame with indicators added
        """
        if df.empty or len(df) < self.config.ema_period:
            return df
        
        df = df.copy()
        
        # Calculate VWAP
        df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
        
        # Calculate EMA
        df[f'ema_{self.config.ema_period}'] = df['close'].ewm(span=self.config.ema_period, adjust=False).mean()
        
        return df
    
    def _check_price_range(self, candidate: Candidate) -> bool:
        """Check if gain is within valid range (2-4%)"""
        result, _ = self._check_price_range_detailed(candidate)
        return result
    
    def _check_price_range_detailed(self, candidate: Candidate) -> tuple:
        """Check gain range with detailed info"""
        passed = self.config.min_gain_pct <= candidate.gain_pct <= self.config.max_gain_pct
        info = f"Gain: {candidate.gain_pct:.2f}% (range: {self.config.min_gain_pct:.1f}%-{self.config.max_gain_pct:.1f}%)"
        return passed, info
    
    def _check_vwap_filter(self, df: pd.DataFrame) -> bool:
        """Check if current price > VWAP"""
        result, _ = self._check_vwap_filter_detailed(df)
        return result
    
    def _check_vwap_filter_detailed(self, df: pd.DataFrame) -> tuple:
        """Check VWAP filter with detailed info"""
        if not self.config.vwap_enabled or df.empty:
            return True, "VWAP filter disabled"
        
        if 'vwap' not in df.columns:
            return False, "VWAP not calculated"
        
        current_price = df['close'].iloc[-1]
        current_vwap = df['vwap'].iloc[-1]
        diff_pct = ((current_price - current_vwap) / current_vwap) * 100
        
        passed = current_price > current_vwap
        info = f"Price: ₹{current_price:.2f}, VWAP: ₹{current_vwap:.2f}, Diff: {diff_pct:+.2f}%"
        return passed, info
    
    def _check_ema_filter(self, df: pd.DataFrame) -> bool:
        """Check if current price > EMA"""
        result, _ = self._check_ema_filter_detailed(df)
        return result
    
    def _check_ema_filter_detailed(self, df: pd.DataFrame) -> tuple:
        """Check EMA filter with detailed info"""
        if df.empty or len(df) < self.config.ema_period:
            return False, f"Insufficient data (need {self.config.ema_period} candles)"
        
        ema_col = f'ema_{self.config.ema_period}'
        if ema_col not in df.columns:
            return False, "EMA not calculated"
        
        current_price = df['close'].iloc[-1]
        current_ema = df[ema_col].iloc[-1]
        diff_pct = ((current_price - current_ema) / current_ema) * 100
        
        passed = current_price > current_ema
        info = f"Price: ₹{current_price:.2f}, EMA{self.config.ema_period}: ₹{current_ema:.2f}, Diff: {diff_pct:+.2f}%"
        return passed, info
    
    def _check_volume_surge(self, df: pd.DataFrame) -> bool:
        """Check if current volume > multiplier * average volume"""
        result, _ = self._check_volume_surge_detailed(df)
        return result
    
    def _check_volume_surge_detailed(self, df: pd.DataFrame) -> tuple:
        """Check volume surge with detailed info"""
        if df.empty or len(df) < self.config.volume_lookback:
            return False, f"Insufficient data (need {self.config.volume_lookback} candles)"
        
        current_volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].iloc[-self.config.volume_lookback:-1].mean()
        
        if avg_volume == 0:
            return False, "Average volume is zero"
        
        volume_ratio = current_volume / avg_volume
        passed = volume_ratio >= self.config.volume_multiplier
        
        info = f"Current: {current_volume:,.0f}, Avg: {avg_volume:,.0f}, Ratio: {volume_ratio:.2f}x (need {self.config.volume_multiplier:.2f}x)"
        return passed, info
    
    def _check_breakout_previous_high(self, df: pd.DataFrame) -> bool:
        """Check if current price breaks previous candle high"""
        result, _ = self._check_breakout_previous_high_detailed(df)
        return result
    
    def _check_breakout_previous_high_detailed(self, df: pd.DataFrame) -> tuple:
        """Check breakout with detailed info"""
        if not self.config.breakout_previous_high or df.empty or len(df) < 2:
            return True, "Breakout filter disabled" if not self.config.breakout_previous_high else "Passed"
        
        current_price = df['close'].iloc[-1]
        previous_high = df['high'].iloc[-2]
        diff_pct = ((current_price - previous_high) / previous_high) * 100
        
        passed = current_price > previous_high
        info = f"Current: ₹{current_price:.2f}, Prev High: ₹{previous_high:.2f}, Breakout: {diff_pct:+.2f}%"
        return passed, info
    
    def apply_filters(
        self,
        candidate: Candidate,
        stock_df: pd.DataFrame
    ) -> bool:
        """
        Apply all entry filters.
        
        Filters:
        1. Gain is 2-4%
        2. Price > VWAP
        3. Price > 20 EMA
        4. Volume > 1.5x average
        5. Price breaks previous candle high
        
        Args:
            candidate: Stock candidate
            stock_df: Stock OHLCV data with indicators
        
        Returns:
            True if all filters pass
        """
        # Filter 1: Price range (2-4%)
        gain_pass, gain_info = self._check_price_range_detailed(candidate)
        self._log_filter_result(candidate.symbol, "Gain Filter", gain_pass, gain_info)
        if not gain_pass:
            return False
        
        # Filter 2: VWAP
        vwap_pass, vwap_info = self._check_vwap_filter_detailed(stock_df)
        self._log_filter_result(candidate.symbol, "VWAP Filter", vwap_pass, vwap_info)
        if not vwap_pass:
            return False
        
        # Filter 3: EMA
        ema_pass, ema_info = self._check_ema_filter_detailed(stock_df)
        self._log_filter_result(candidate.symbol, "EMA Filter", ema_pass, ema_info)
        if not ema_pass:
            return False
        
        # Filter 4: Volume
        volume_pass, volume_info = self._check_volume_surge_detailed(stock_df)
        self._log_filter_result(candidate.symbol, "Volume Filter", volume_pass, volume_info)
        if not volume_pass:
            return False
        
        # Filter 5: Breakout of previous high
        breakout_pass, breakout_info = self._check_breakout_previous_high_detailed(stock_df)
        self._log_filter_result(candidate.symbol, "Breakout Filter", breakout_pass, breakout_info)
        if not breakout_pass:
            return False
        
        return True
    
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
        
        # Get VWAP and EMA values for reason
        vwap = stock_df['vwap'].iloc[-1] if 'vwap' in stock_df.columns else 0
        ema_col = f'ema_{self.config.ema_period}'
        ema = stock_df[ema_col].iloc[-1] if ema_col in stock_df.columns else 0
        prev_high = stock_df['high'].iloc[-2] if len(stock_df) >= 2 else 0
        
        # Calculate quantity (placeholder)
        quantity = 1
        
        signal = Signal(
            symbol=candidate.symbol,
            instrument_token=candidate.instrument_token,
            signal_type=SignalType.BUY,
            price=entry_price,
            timestamp=current_time,
            reason=f"VWAP/EMA breakout (price: ₹{entry_price:.2f} > VWAP: ₹{vwap:.2f}, EMA: ₹{ema:.2f}, prev_high: ₹{prev_high:.2f})",
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
        1. Target hit (+1.5%)
        2. Stop loss hit (-0.7%)
        3. Time-based exit (3:20 PM)
        
        Args:
            position: Open position
            current_price: Current stock price
            current_time: Current time
        
        Returns:
            SELL signal if should exit, None otherwise
        """
        reason = None
        
        # Check target
        if current_price >= position.target:
            reason = f"Target hit (₹{current_price:.2f} >= ₹{position.target:.2f})"
        
        # Check stop loss
        elif current_price <= position.stop_loss:
            reason = f"Stop loss hit (₹{current_price:.2f} <= ₹{position.stop_loss:.2f})"
        
        # Check time-based exit
        elif current_time.time() >= self.config.exit_time:
            reason = f"Time-based exit ({current_time.time()})"
        
        if reason:
            signal = Signal(
                symbol=position.symbol,
                instrument_token=position.instrument_token,
                signal_type=SignalType.SELL,
                price=current_price,
                timestamp=current_time,
                reason=reason,
                quantity=position.quantity
            )
            return signal
        
        return None
    
    def _is_entry_allowed(self, current_time: datetime) -> bool:
        """Check if entry is allowed at current time"""
        # Use base class implementation
        return super()._is_entry_allowed(current_time)
    
    def generate_signal(
        self,
        candidate: Candidate,
        stock_df: pd.DataFrame,
        current_time: datetime
    ) -> Optional[Signal]:
        """
        Generate trading signal for candidate.
        
        Args:
            candidate: Stock candidate
            stock_df: Stock OHLCV data
            current_time: Current timestamp
        
        Returns:
            Signal if conditions met, None otherwise
        """
        # Calculate indicators
        stock_df = self.calculate_indicators(stock_df)
        
        # Apply filters
        if not self.apply_filters(candidate, stock_df):
            return None
        
        # Generate entry signal
        return self.should_enter(candidate, stock_df, current_time)
    
    def calculate_signals_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate signals for entire dataframe (for backtesting).
        
        Args:
            df: OHLCV data
        
        Returns:
            DataFrame with signal column added
        """
        df = df.copy()
        df = self.calculate_indicators(df)
        
        # Initialize signal column
        df['signal'] = 0
        
        # Check conditions for each row
        for i in range(self.config.ema_period, len(df)):
            # Check VWAP
            if self.config.vwap_enabled:
                if df['close'].iloc[i] <= df['vwap'].iloc[i]:
                    continue
            
            # Check EMA
            ema_col = f'ema_{self.config.ema_period}'
            if df['close'].iloc[i] <= df[ema_col].iloc[i]:
                continue
            
            # Check volume
            if i >= self.config.volume_lookback:
                avg_vol = df['volume'].iloc[i-self.config.volume_lookback:i].mean()
                if df['volume'].iloc[i] < avg_vol * self.config.volume_multiplier:
                    continue
            
            # Check breakout of previous high
            if self.config.breakout_previous_high and i > 0:
                if df['close'].iloc[i] <= df['high'].iloc[i-1]:
                    continue
            
            # All conditions met - BUY signal
            df.loc[df.index[i], 'signal'] = 1
        
        return df
    
    @property
    def min_data_points(self) -> int:
        """Minimum data points needed for strategy"""
        return max(self.config.ema_period, self.config.volume_lookback) + 1
