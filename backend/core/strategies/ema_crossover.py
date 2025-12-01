"""
EMA Crossover Strategy
Shared by both live trading and backtesting systems.
"""
import pandas as pd
from typing import Optional, Tuple
from .base import BaseStrategy


class EMACrossoverStrategy(BaseStrategy):
    """
    EMA Crossover Strategy:
    - BUY when fast EMA crosses above slow EMA
    - SELL when fast EMA crosses below slow EMA
    """
    
    def __init__(self, fast_period: int = 9, slow_period: int = 21):
        super().__init__(name="EMA_CROSSOVER")
        self.fast_period = fast_period
        self.slow_period = slow_period
    
    @property
    def min_data_points(self) -> int:
        """Need at least slow_period + 2 for crossover detection"""
        return self.slow_period + 2
    
    def calculate_indicators(self, prices: pd.Series) -> Tuple[float, float]:
        """
        Calculate EMA indicators.
        
        Args:
            prices: Series of prices
            
        Returns:
            (fast_ema, slow_ema)
        """
        if len(prices) < self.slow_period:
            return None, None
        
        fast_ema = float(prices.ewm(span=self.fast_period, adjust=False).mean().iloc[-1])
        slow_ema = float(prices.ewm(span=self.slow_period, adjust=False).mean().iloc[-1])
        
        return fast_ema, slow_ema
    
    def generate_signal(
        self, 
        current_indicators: Tuple[float, float], 
        previous_indicators: Tuple[float, float]
    ) -> Optional[str]:
        """
        Generate trading signal based on EMA crossover.
        
        Args:
            current_indicators: (current_fast_ema, current_slow_ema)
            previous_indicators: (previous_fast_ema, previous_slow_ema)
            
        Returns:
            "BUY", "SELL", or None
        """
        curr_fast, curr_slow = current_indicators
        prev_fast, prev_slow = previous_indicators
        
        if None in (curr_fast, curr_slow, prev_fast, prev_slow):
            return None
        
        # Bullish crossover: fast EMA crosses above slow EMA
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return "BUY"
        
        # Bearish crossover: fast EMA crosses below slow EMA
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            return "SELL"
        
        return None
    
    def calculate_signals_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate EMA signals for entire DataFrame (backtesting).
        
        Args:
            df: DataFrame with 'close' prices
            
        Returns:
            DataFrame with columns: ema_fast, ema_slow, signal, position
        """
        df = df.copy()
        
        # Calculate EMAs
        df['ema_fast'] = df['close'].ewm(span=self.fast_period, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.slow_period, adjust=False).mean()
        
        # Generate signals: 1 for BUY, -1 for SELL, 0 for neutral
        df['signal'] = 0
        df.loc[df['ema_fast'] > df['ema_slow'], 'signal'] = 1
        df.loc[df['ema_fast'] < df['ema_slow'], 'signal'] = -1
        
        # Detect crossovers (signal changes): 2 for bullish, -2 for bearish
        df['position'] = df['signal'].diff()
        
        return df
    
    def get_indicator_series(self, prices: pd.Series) -> Tuple[pd.Series, pd.Series]:
        """
        Get full EMA series for analysis.
        
        Args:
            prices: Series of prices
            
        Returns:
            (fast_ema_series, slow_ema_series)
        """
        fast_ema = prices.ewm(span=self.fast_period, adjust=False).mean()
        slow_ema = prices.ewm(span=self.slow_period, adjust=False).mean()
        return fast_ema, slow_ema
