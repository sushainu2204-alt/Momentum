"""
Technical Indicators

Separated indicator calculations following Single Responsibility Principle.
"""

import pandas as pd
import numpy as np
from typing import Optional


class TechnicalIndicators:
    """
    Technical indicator calculations.
    
    All methods are static for easy testing and reuse.
    """
    
    @staticmethod
    def calculate_ema(df: pd.DataFrame, column: str = 'close', period: int = 9) -> pd.Series:
        """
        Calculate Exponential Moving Average.
        
        Args:
            df: DataFrame with OHLCV data
            column: Column to calculate EMA on
            period: EMA period
        
        Returns:
            Series with EMA values
        """
        return df[column].ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_sma(df: pd.DataFrame, column: str = 'close', period: int = 20) -> pd.Series:
        """Calculate Simple Moving Average"""
        return df[column].rolling(window=period).mean()
    
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, column: str = 'close', period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index.
        
        Args:
            df: DataFrame with OHLCV data
            column: Column to calculate RSI on
            period: RSI period (typically 14)
        
        Returns:
            Series with RSI values (0-100)
        """
        delta = df[column].diff()
        
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> pd.Series:
        """
        Calculate Volume Weighted Average Price.
        
        Args:
            df: DataFrame with OHLCV data
        
        Returns:
            Series with VWAP values
        """
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
        
        return vwap
    
    @staticmethod
    def calculate_volume_surge(
        df: pd.DataFrame,
        lookback: int = 10,
        multiplier: float = 2.0
    ) -> pd.Series:
        """
        Check if current volume is surge compared to average.
        
        Args:
            df: DataFrame with OHLCV data
            lookback: Number of periods to compare
            multiplier: Volume surge multiplier (e.g., 2.0 = 2x average)
        
        Returns:
            Boolean Series indicating volume surge
        """
        avg_volume = df['volume'].rolling(window=lookback).mean()
        current_volume = df['volume']
        
        is_surge = current_volume > (avg_volume * multiplier)
        
        return is_surge
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Average True Range.
        
        Used for volatility-based stop losses.
        
        Args:
            df: DataFrame with OHLCV data
            period: ATR period
        
        Returns:
            Series with ATR values
        """
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        
        return atr
    
    @staticmethod
    def calculate_bollinger_bands(
        df: pd.DataFrame,
        column: str = 'close',
        period: int = 20,
        std_dev: float = 2.0
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands.
        
        Args:
            df: DataFrame with OHLCV data
            column: Column to calculate bands on
            period: Moving average period
            std_dev: Standard deviation multiplier
        
        Returns:
            Tuple of (upper_band, middle_band, lower_band)
        """
        middle_band = df[column].rolling(window=period).mean()
        std = df[column].rolling(window=period).std()
        
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        
        return upper_band, middle_band, lower_band
    
    @staticmethod
    def is_candle_break(df: pd.DataFrame, lookback: int = 1) -> pd.Series:
        """
        Check if current candle breaks previous candle high.
        
        Args:
            df: DataFrame with OHLCV data
            lookback: How many candles back to check
        
        Returns:
            Boolean Series indicating breakout
        """
        current_high = df['high']
        previous_high = df['high'].shift(lookback)
        
        is_break = current_high > previous_high
        
        return is_break
    
    @staticmethod
    def calculate_supertrend(
        df: pd.DataFrame,
        period: int = 10,
        multiplier: float = 3.0
    ) -> tuple[pd.Series, pd.Series]:
        """
        Calculate Supertrend indicator.
        
        Args:
            df: DataFrame with OHLCV data
            period: ATR period
            multiplier: ATR multiplier
        
        Returns:
            Tuple of (supertrend, direction)
        """
        atr = TechnicalIndicators.calculate_atr(df, period=period)
        hl_avg = (df['high'] + df['low']) / 2
        
        upper_band = hl_avg + (multiplier * atr)
        lower_band = hl_avg - (multiplier * atr)
        
        supertrend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)
        
        for i in range(period, len(df)):
            if i == period:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            else:
                if df['close'].iloc[i] > supertrend.iloc[i-1]:
                    supertrend.iloc[i] = lower_band.iloc[i]
                    direction.iloc[i] = 1
                else:
                    supertrend.iloc[i] = upper_band.iloc[i]
                    direction.iloc[i] = -1
        
        return supertrend, direction


class MarketIndicators:
    """
    Market-wide indicators and calculations.
    """
    
    @staticmethod
    def calculate_advance_decline_ratio(advances: int, declines: int) -> float:
        """Calculate advance/decline ratio"""
        if declines == 0:
            return float('inf')
        return advances / declines
    
    @staticmethod
    def is_market_bullish(
        df: pd.DataFrame,
        ema_period: int = 50,
        rsi_period: int = 14,
        rsi_threshold: float = 55.0
    ) -> bool:
        """
        Check if market (index) is in bullish mode.
        
        Args:
            df: Index OHLCV data
            ema_period: EMA period for trend
            rsi_period: RSI period
            rsi_threshold: Minimum RSI value
        
        Returns:
            True if market is bullish
        """
        if len(df) < ema_period:
            return False
        
        # Calculate indicators
        ema = TechnicalIndicators.calculate_ema(df, period=ema_period)
        rsi = TechnicalIndicators.calculate_rsi(df, period=rsi_period)
        
        # Get latest values
        current_price = df['close'].iloc[-1]
        current_ema = ema.iloc[-1]
        current_rsi = rsi.iloc[-1]
        
        # Check conditions
        price_above_ema = current_price > current_ema
        rsi_above_threshold = current_rsi > rsi_threshold
        
        return price_above_ema and rsi_above_threshold
