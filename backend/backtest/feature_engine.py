"""
Feature Engine Module

Computes technical indicators and features for strategy evaluation.
This is the central indicator pipeline that enriches raw OHLCV data.

Features Computed:
    - VWAP (Volume Weighted Average Price)
    - EMA (Exponential Moving Averages - 9, 20, 50)
    - RSI (Relative Strength Index)
    - ATR (Average True Range)
    - Volume surge factors
    - % change calculations
    - Intraday returns
    - Bollinger Bands
    - Supertrend
    - Flag pattern detection helpers
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date, time
import logging

# Reuse existing technical indicators
from backend.core.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


@dataclass
class FeatureConfig:
    """Configuration for feature computation."""
    
    # EMA periods to calculate
    ema_periods: List[int] = field(default_factory=lambda: [9, 20, 50])
    
    # RSI settings
    rsi_period: int = 14
    
    # ATR settings
    atr_period: int = 14
    
    # Volume analysis
    volume_lookback: int = 20
    volume_surge_threshold: float = 1.5
    
    # Bollinger Bands
    bb_period: int = 20
    bb_std: float = 2.0
    
    # VWAP reset (daily for intraday)
    reset_vwap_daily: bool = True


class FeatureEngine:
    """
    Feature computation engine for backtesting.
    
    Computes all technical indicators and derived features
    that strategies need for signal generation.
    
    Usage:
        engine = FeatureEngine(config)
        
        # Compute all features for a symbol
        enriched_df = engine.compute_all_features(df)
        
        # Get features for current candle
        features = engine.get_current_features(df, timestamp)
    """
    
    def __init__(self, config: Optional[FeatureConfig] = None):
        """
        Initialize feature engine.
        
        Args:
            config: Feature computation configuration
        """
        self.config = config or FeatureConfig()
        
        # Cache for computed features
        self._feature_cache: Dict[str, pd.DataFrame] = {}
    
    def compute_all_features(
        self,
        df: pd.DataFrame,
        symbol: Optional[str] = None,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Compute all features for a DataFrame.
        
        Args:
            df: OHLCV DataFrame
            symbol: Symbol for caching
            use_cache: Whether to cache results
        
        Returns:
            DataFrame with all features added
        """
        if df.empty:
            return df
        
        # Check cache
        cache_key = f"{symbol}_{len(df)}" if symbol else None
        if use_cache and cache_key and cache_key in self._feature_cache:
            return self._feature_cache[cache_key].copy()
        
        # Make a copy to avoid modifying original
        df = df.copy()
        
        # Compute each feature group
        df = self._compute_moving_averages(df)
        df = self._compute_vwap(df)
        df = self._compute_momentum_indicators(df)
        df = self._compute_volatility_indicators(df)
        df = self._compute_volume_features(df)
        df = self._compute_price_features(df)
        df = self._compute_pattern_features(df)
        
        # Cache result
        if use_cache and cache_key:
            self._feature_cache[cache_key] = df.copy()
        
        return df
    
    def _compute_moving_averages(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all EMA and SMA indicators."""
        
        for period in self.config.ema_periods:
            df[f'ema_{period}'] = TechnicalIndicators.calculate_ema(
                df, column='close', period=period
            )
        
        # SMA 20 for Bollinger Bands
        df['sma_20'] = TechnicalIndicators.calculate_sma(
            df, column='close', period=20
        )
        
        # EMA crossover signals
        if 20 in self.config.ema_periods and 50 in self.config.ema_periods:
            df['ema_20_above_50'] = df['ema_20'] > df['ema_50']
            df['ema_cross_up'] = (
                (df['ema_20'] > df['ema_50']) & 
                (df['ema_20'].shift(1) <= df['ema_50'].shift(1))
            )
            df['ema_cross_down'] = (
                (df['ema_20'] < df['ema_50']) & 
                (df['ema_20'].shift(1) >= df['ema_50'].shift(1))
            )
        
        return df
    
    def _compute_vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute VWAP with optional daily reset."""
        
        if self.config.reset_vwap_daily and 'timestamp' in df.columns:
            # Group by date and compute VWAP for each day
            df['date'] = df['timestamp'].dt.date
            
            vwap_values = []
            for _, day_df in df.groupby('date'):
                day_vwap = TechnicalIndicators.calculate_vwap(day_df)
                vwap_values.extend(day_vwap.tolist())
            
            df['vwap'] = vwap_values
            df = df.drop('date', axis=1)
        else:
            df['vwap'] = TechnicalIndicators.calculate_vwap(df)
        
        # VWAP-derived features
        df['price_above_vwap'] = df['close'] > df['vwap']
        df['vwap_distance_pct'] = ((df['close'] - df['vwap']) / df['vwap']) * 100
        
        return df
    
    def _compute_momentum_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute RSI and other momentum indicators."""
        
        # RSI
        df['rsi'] = TechnicalIndicators.calculate_rsi(
            df, column='close', period=self.config.rsi_period
        )
        
        # RSI zones
        df['rsi_oversold'] = df['rsi'] < 30
        df['rsi_overbought'] = df['rsi'] > 70
        
        # Rate of change
        df['roc_1'] = df['close'].pct_change(1) * 100
        df['roc_5'] = df['close'].pct_change(5) * 100
        df['roc_10'] = df['close'].pct_change(10) * 100
        
        return df
    
    def _compute_volatility_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute ATR and Bollinger Bands."""
        
        # ATR
        df['atr'] = TechnicalIndicators.calculate_atr(
            df, period=self.config.atr_period
        )
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        
        # Bollinger Bands
        upper, middle, lower = TechnicalIndicators.calculate_bollinger_bands(
            df,
            column='close',
            period=self.config.bb_period,
            std_dev=self.config.bb_std
        )
        df['bb_upper'] = upper
        df['bb_middle'] = middle
        df['bb_lower'] = lower
        df['bb_width'] = ((upper - lower) / middle) * 100
        
        # BB position
        df['bb_position'] = (df['close'] - lower) / (upper - lower)
        
        return df
    
    def _compute_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute volume analysis features."""
        
        # Volume moving averages
        df['volume_sma_20'] = df['volume'].rolling(window=20).mean()
        df['volume_sma_10'] = df['volume'].rolling(window=10).mean()
        
        # Volume ratio (current vs average)
        df['volume_ratio'] = df['volume'] / df['volume_sma_20']
        df['volume_ratio_10'] = df['volume'] / df['volume_sma_10']
        
        # Volume surge detection
        df['volume_surge'] = df['volume_ratio'] >= self.config.volume_surge_threshold
        
        # Volume trend
        df['volume_increasing'] = df['volume'] > df['volume'].shift(1)
        
        # Relative volume (vs same time yesterday would need more complex logic)
        df['volume_pct_change'] = df['volume'].pct_change() * 100
        
        # Volume-price relationship
        df['up_volume'] = np.where(df['close'] > df['open'], df['volume'], 0)
        df['down_volume'] = np.where(df['close'] < df['open'], df['volume'], 0)
        
        return df
    
    def _compute_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute price-based features."""
        
        # Percentage change from previous close
        df['pct_change'] = df['close'].pct_change() * 100
        
        # Intraday return (from day's open)
        if 'timestamp' in df.columns:
            df['date'] = df['timestamp'].dt.date
            df['day_open'] = df.groupby('date')['open'].transform('first')
            df['intraday_return'] = ((df['close'] - df['day_open']) / df['day_open']) * 100
            df = df.drop(['date', 'day_open'], axis=1)
        else:
            df['intraday_return'] = df['pct_change'].cumsum()
        
        # Candle features
        df['candle_body'] = df['close'] - df['open']
        df['candle_body_pct'] = (df['candle_body'] / df['open']) * 100
        df['candle_range'] = df['high'] - df['low']
        df['candle_range_pct'] = (df['candle_range'] / df['low']) * 100
        
        # Upper and lower wicks
        df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
        
        # Green/Red candle
        df['is_green'] = df['close'] > df['open']
        
        # High/Low breakouts
        df['breaks_prev_high'] = df['high'] > df['high'].shift(1)
        df['breaks_prev_low'] = df['low'] < df['low'].shift(1)
        
        # N-period high/low
        df['high_5'] = df['high'].rolling(5).max()
        df['low_5'] = df['low'].rolling(5).min()
        df['high_10'] = df['high'].rolling(10).max()
        df['low_10'] = df['low'].rolling(10).min()
        
        # Distance from high/low
        df['from_high_5_pct'] = ((df['close'] - df['high_5']) / df['high_5']) * 100
        df['from_low_5_pct'] = ((df['close'] - df['low_5']) / df['low_5']) * 100
        
        return df
    
    def _compute_pattern_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute pattern detection helper features."""
        
        # Consecutive green/red candles
        df['green_streak'] = self._count_consecutive(df['is_green'], True)
        df['red_streak'] = self._count_consecutive(df['is_green'], False)
        
        # Higher highs / Higher lows (trend)
        df['higher_high'] = df['high'] > df['high'].shift(1)
        df['higher_low'] = df['low'] > df['low'].shift(1)
        df['lower_high'] = df['high'] < df['high'].shift(1)
        df['lower_low'] = df['low'] < df['low'].shift(1)
        
        # Trend detection (simple)
        df['uptrend'] = df['higher_high'] & df['higher_low']
        df['downtrend'] = df['lower_high'] & df['lower_low']
        
        # Flag pattern helpers
        df = self._compute_flag_features(df)
        
        return df
    
    def _compute_flag_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute features useful for flag pattern detection."""
        
        # Recent max gain (for flag pole detection)
        window = 10
        df['max_gain_5'] = df['close'].rolling(5).apply(
            lambda x: ((x.iloc[-1] - x.iloc[0]) / x.iloc[0]) * 100 if len(x) > 0 else 0
        )
        
        # Pullback from recent high
        df['recent_high_10'] = df['high'].rolling(10).max()
        df['pullback_pct'] = ((df['recent_high_10'] - df['close']) / df['recent_high_10']) * 100
        
        # Volatility contraction (flag consolidation)
        df['range_contraction'] = df['candle_range'].rolling(3).mean() < df['candle_range'].rolling(10).mean()
        
        return df
    
    @staticmethod
    def _count_consecutive(series: pd.Series, value: bool) -> pd.Series:
        """Count consecutive occurrences of a value."""
        groups = (series != value).cumsum()
        return series.groupby(groups).cumsum()
    
    def get_current_features(
        self,
        df: pd.DataFrame,
        timestamp: datetime
    ) -> Optional[Dict[str, float]]:
        """
        Get features for a specific timestamp.
        
        Args:
            df: DataFrame with computed features
            timestamp: Timestamp to get features for
        
        Returns:
            Dictionary of feature name -> value
        """
        if 'timestamp' not in df.columns:
            return None
        
        row = df[df['timestamp'] == timestamp]
        if row.empty:
            return None
        
        return row.iloc[0].to_dict()
    
    def get_features_up_to(
        self,
        df: pd.DataFrame,
        timestamp: datetime,
        lookback: int = 1
    ) -> Optional[pd.DataFrame]:
        """
        Get features up to and including a timestamp.
        
        Used for strategies that need historical context.
        
        Args:
            df: DataFrame with computed features
            timestamp: Current timestamp
            lookback: Number of rows to return
        
        Returns:
            DataFrame with features
        """
        if 'timestamp' not in df.columns:
            return None
        
        mask = df['timestamp'] <= timestamp
        filtered = df[mask]
        
        if filtered.empty:
            return None
        
        if lookback > 0 and len(filtered) > lookback:
            filtered = filtered.iloc[-lookback:]
        
        return filtered.reset_index(drop=True)
    
    def compute_features_incremental(
        self,
        existing_df: pd.DataFrame,
        new_candle: pd.Series
    ) -> pd.DataFrame:
        """
        Incrementally update features with new candle.
        
        More efficient than recomputing all features.
        
        Args:
            existing_df: DataFrame with existing features
            new_candle: New candle to add
        
        Returns:
            Updated DataFrame
        """
        # Append new candle
        df = pd.concat([
            existing_df,
            pd.DataFrame([new_candle])
        ], ignore_index=True)
        
        # Recompute features (could be optimized for rolling calculations)
        # For now, recompute last N rows
        return self.compute_all_features(df, use_cache=False)
    
    def clear_cache(self) -> None:
        """Clear feature cache."""
        self._feature_cache.clear()
        logger.info("Feature cache cleared")
    
    def get_feature_list(self) -> List[str]:
        """Get list of all computed features."""
        return [
            # Moving averages
            'ema_9', 'ema_20', 'ema_50', 'sma_20',
            'ema_20_above_50', 'ema_cross_up', 'ema_cross_down',
            
            # VWAP
            'vwap', 'price_above_vwap', 'vwap_distance_pct',
            
            # Momentum
            'rsi', 'rsi_oversold', 'rsi_overbought',
            'roc_1', 'roc_5', 'roc_10',
            
            # Volatility
            'atr', 'atr_pct',
            'bb_upper', 'bb_middle', 'bb_lower', 'bb_width', 'bb_position',
            
            # Volume
            'volume_sma_20', 'volume_sma_10',
            'volume_ratio', 'volume_ratio_10', 'volume_surge',
            'volume_increasing', 'volume_pct_change',
            
            # Price
            'pct_change', 'intraday_return',
            'candle_body', 'candle_body_pct', 'candle_range', 'candle_range_pct',
            'is_green', 'breaks_prev_high', 'breaks_prev_low',
            'high_5', 'low_5', 'high_10', 'low_10',
            
            # Pattern
            'green_streak', 'red_streak',
            'higher_high', 'higher_low', 'uptrend', 'downtrend',
            'max_gain_5', 'pullback_pct', 'range_contraction',
        ]
