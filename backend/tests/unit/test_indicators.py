"""
Unit Tests for Technical Indicators

Tests EMA, SMA, RSI, VWAP, ATR, Bollinger Bands, and volume surge.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.core.indicators.technical import TechnicalIndicators


# ============================================================================
# EMA TESTS
# ============================================================================

class TestCalculateEMA:
    """Test Exponential Moving Average calculations."""
    
    def test_calculate_ema_basic(self, sample_ohlcv_data):
        """Test basic EMA calculation."""
        df = sample_ohlcv_data(num_candles=50)
        
        ema = TechnicalIndicators.calculate_ema(df, column='close', period=20)
        
        assert len(ema) == len(df)
        # EMA should be populated for all values (ewm doesn't need warmup like rolling)
        assert not ema.isnull().all()
    
    def test_calculate_ema_short_period(self, sample_ohlcv_data):
        """Test short period EMA (more responsive)."""
        df = sample_ohlcv_data(num_candles=50)
        
        ema_5 = TechnicalIndicators.calculate_ema(df, column='close', period=5)
        ema_20 = TechnicalIndicators.calculate_ema(df, column='close', period=20)
        
        # Short EMA should track price more closely
        recent_variance_5 = (ema_5.iloc[-10:] - df['close'].iloc[-10:]).std()
        recent_variance_20 = (ema_20.iloc[-10:] - df['close'].iloc[-10:]).std()
        
        assert recent_variance_5 < recent_variance_20
    
    def test_calculate_ema_uptrend(self):
        """Test EMA in uptrend."""
        df = pd.DataFrame({
            'close': [100, 102, 104, 106, 108, 110, 112, 114, 116, 118]
        })
        
        ema = TechnicalIndicators.calculate_ema(df, column='close', period=5)
        
        # In uptrend, EMA should be increasing
        assert ema.iloc[-1] > ema.iloc[-3]
    
    def test_calculate_ema_downtrend(self):
        """Test EMA in downtrend."""
        df = pd.DataFrame({
            'close': [120, 118, 116, 114, 112, 110, 108, 106, 104, 102]
        })
        
        ema = TechnicalIndicators.calculate_ema(df, column='close', period=5)
        
        # In downtrend, EMA should be decreasing
        assert ema.iloc[-1] < ema.iloc[-3]


# ============================================================================
# SMA TESTS
# ============================================================================

class TestCalculateSMA:
    """Test Simple Moving Average calculations."""
    
    def test_calculate_sma_basic(self, sample_ohlcv_data):
        """Test basic SMA calculation."""
        df = sample_ohlcv_data(num_candles=50)
        
        sma = TechnicalIndicators.calculate_sma(df, column='close', period=20)
        
        assert len(sma) == len(df)
        # Verify SMA is actually the mean of window
        expected_sma_at_20 = df['close'].iloc[0:20].mean()
        assert abs(sma.iloc[19] - expected_sma_at_20) < 0.01
    
    def test_calculate_sma_vs_ema_lag(self, sample_ohlcv_data):
        """Test SMA and EMA behave differently - EMA is more responsive."""
        df = sample_ohlcv_data(num_candles=50, trend="up")
        
        sma = TechnicalIndicators.calculate_sma(df, column='close', period=20)
        ema = TechnicalIndicators.calculate_ema(df, column='close', period=20)
        
        # Both should produce valid series
        assert not sma.isna().all()
        assert not ema.isna().all()
        
        # EMA responds faster to price changes (different from SMA)
        # They should not be identical
        assert not (sma == ema).all()


# ============================================================================
# RSI TESTS
# ============================================================================

class TestCalculateRSI:
    """Test Relative Strength Index calculations."""
    
    def test_calculate_rsi_basic(self, sample_ohlcv_data):
        """Test basic RSI calculation."""
        df = sample_ohlcv_data(num_candles=50)
        
        rsi = TechnicalIndicators.calculate_rsi(df, column='close', period=14)
        
        assert len(rsi) == len(df)
        # RSI should be between 0 and 100
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()
    
    def test_calculate_rsi_overbought(self):
        """Test RSI overbought detection."""
        # Strong uptrend
        df = pd.DataFrame({
            'close': [100 + i * 2 for i in range(30)]
        })
        
        rsi = TechnicalIndicators.calculate_rsi(df, column='close', period=14)
        
        # Strong uptrend should have high RSI
        assert rsi.iloc[-1] > 70
    
    def test_calculate_rsi_oversold(self):
        """Test RSI oversold detection."""
        # Strong downtrend
        df = pd.DataFrame({
            'close': [100 - i * 2 for i in range(30)]
        })
        
        rsi = TechnicalIndicators.calculate_rsi(df, column='close', period=14)
        
        # Strong downtrend should have low RSI
        assert rsi.iloc[-1] < 30
    
    def test_calculate_rsi_neutral(self, sample_ohlcv_data):
        """Test RSI in sideways market."""
        # Sideways/neutral data
        np.random.seed(42)
        df = pd.DataFrame({
            'close': [100 + np.random.randn() for _ in range(30)]
        })
        
        rsi = TechnicalIndicators.calculate_rsi(df, column='close', period=14)
        
        # Sideways market should have RSI near 50
        assert 30 < rsi.iloc[-1] < 70


# ============================================================================
# VWAP TESTS
# ============================================================================

class TestCalculateVWAP:
    """Test Volume Weighted Average Price calculations."""
    
    def test_calculate_vwap_basic(self, sample_ohlcv_data):
        """Test basic VWAP calculation."""
        df = sample_ohlcv_data(num_candles=50)
        
        vwap = TechnicalIndicators.calculate_vwap(df)
        
        assert len(vwap) == len(df)
        assert not vwap.isnull().any()
    
    def test_calculate_vwap_between_high_low(self, sample_ohlcv_data):
        """Test VWAP is between cumulative high/low."""
        df = sample_ohlcv_data(num_candles=50)
        
        vwap = TechnicalIndicators.calculate_vwap(df)
        
        # VWAP should be reasonable - around the typical price range
        avg_price = (df['high'] + df['low']) / 2
        assert abs(vwap.iloc[-1] - avg_price.mean()) < avg_price.std() * 3
    
    def test_calculate_vwap_with_volume_spike(self, sample_ohlcv_data):
        """Test VWAP pulls toward candle with volume spike."""
        df = sample_ohlcv_data(num_candles=50)
        
        # Add massive volume at last candle
        df_copy = df.copy()
        df_copy.loc[df_copy.index[-1], 'volume'] = df_copy['volume'].sum() * 10
        
        vwap_before = TechnicalIndicators.calculate_vwap(df.iloc[:-1]).iloc[-1]
        vwap_after = TechnicalIndicators.calculate_vwap(df_copy).iloc[-1]
        
        # VWAP should move toward the high-volume candle's typical price
        typical_price_last = (df_copy.iloc[-1]['high'] + df_copy.iloc[-1]['low'] + df_copy.iloc[-1]['close']) / 3
        
        # VWAP should be closer to the high-volume candle's price
        if typical_price_last > vwap_before:
            assert vwap_after > vwap_before
        elif typical_price_last < vwap_before:
            assert vwap_after < vwap_before


# ============================================================================
# ATR TESTS
# ============================================================================

class TestCalculateATR:
    """Test Average True Range calculations."""
    
    def test_calculate_atr_basic(self, sample_ohlcv_data):
        """Test basic ATR calculation."""
        df = sample_ohlcv_data(num_candles=50)
        
        atr = TechnicalIndicators.calculate_atr(df, period=14)
        
        assert len(atr) == len(df)
        # ATR should always be positive
        valid_atr = atr.dropna()
        assert (valid_atr > 0).all()
    
    def test_calculate_atr_high_volatility(self):
        """Test ATR is high in volatile market."""
        np.random.seed(42)
        dates = pd.date_range(end=datetime.now(), periods=30, freq='5min')
        
        # High volatility data
        prices = []
        for i in range(30):
            if i % 2 == 0:
                prices.append(100 + np.random.rand() * 5)
            else:
                prices.append(100 - np.random.rand() * 5)
        
        df = pd.DataFrame({
            'date': dates,
            'open': prices,
            'high': [p + 2 for p in prices],
            'low': [p - 2 for p in prices],
            'close': prices,
            'volume': [100000] * 30
        })
        
        atr = TechnicalIndicators.calculate_atr(df, period=14)
        
        # ATR should be significant
        assert atr.iloc[-1] > 1.0
    
    def test_calculate_atr_low_volatility(self):
        """Test ATR is low in calm market."""
        dates = pd.date_range(end=datetime.now(), periods=30, freq='5min')
        
        # Low volatility data - almost flat
        df = pd.DataFrame({
            'date': dates,
            'open': [100 + i * 0.01 for i in range(30)],
            'high': [100.2 + i * 0.01 for i in range(30)],
            'low': [99.9 + i * 0.01 for i in range(30)],
            'close': [100.1 + i * 0.01 for i in range(30)],
            'volume': [100000] * 30
        })
        
        atr = TechnicalIndicators.calculate_atr(df, period=14)
        
        # ATR should be small
        assert atr.iloc[-1] < 1.0


# ============================================================================
# BOLLINGER BANDS TESTS
# ============================================================================

class TestCalculateBollingerBands:
    """Test Bollinger Bands calculations."""
    
    def test_calculate_bollinger_bands_basic(self, sample_ohlcv_data):
        """Test basic Bollinger Bands calculation."""
        df = sample_ohlcv_data(num_candles=50)
        
        upper, middle, lower = TechnicalIndicators.calculate_bollinger_bands(
            df, column='close', period=20, std_dev=2
        )
        
        assert len(upper) == len(df)
        assert len(middle) == len(df)
        assert len(lower) == len(df)
    
    def test_calculate_bollinger_bands_order(self, sample_ohlcv_data):
        """Test upper > middle > lower."""
        df = sample_ohlcv_data(num_candles=50)
        
        upper, middle, lower = TechnicalIndicators.calculate_bollinger_bands(
            df, column='close', period=20, std_dev=2
        )
        
        valid_indices = upper.dropna().index
        
        assert (upper.loc[valid_indices] > middle.loc[valid_indices]).all()
        assert (middle.loc[valid_indices] > lower.loc[valid_indices]).all()


# ============================================================================
# VOLUME SURGE TESTS
# ============================================================================

class TestCalculateVolumeSurge:
    """Test volume surge detection."""
    
    def test_calculate_volume_surge_detection(self, sample_ohlcv_data):
        """Test volume surge detection."""
        df = sample_ohlcv_data(num_candles=50)
        
        # Add volume spike at last candle
        df_copy = df.copy()
        df_copy.loc[df_copy.index[-1], 'volume'] = int(df_copy['volume'].mean() * 2.5)
        
        is_surge = TechnicalIndicators.calculate_volume_surge(
            df_copy, lookback=20, multiplier=1.5
        )
        
        assert is_surge.iloc[-1] == True
    
    def test_calculate_no_volume_surge(self, sample_ohlcv_data):
        """Test no surge detection with normal volume."""
        df = sample_ohlcv_data(num_candles=50)
        
        # Ensure last candle has normal volume
        df_copy = df.copy()
        df_copy.loc[df_copy.index[-1], 'volume'] = int(df_copy['volume'].mean())
        
        is_surge = TechnicalIndicators.calculate_volume_surge(
            df_copy, lookback=20, multiplier=1.5
        )
        
        assert is_surge.iloc[-1] == False


# ============================================================================
# CANDLE BREAK TESTS
# ============================================================================

class TestIsCandleBreak:
    """Test candle breakout detection."""
    
    def test_is_candle_break_basic(self):
        """Test candle break detection."""
        df = pd.DataFrame({
            'high': [100, 101, 102, 103, 105],  # Last candle breaks previous high
            'low': [98, 99, 100, 101, 102],
            'close': [99, 100, 101, 102, 104]
        })
        
        is_break = TechnicalIndicators.is_candle_break(df, lookback=1)
        
        assert is_break.iloc[-1] == True
    
    def test_is_candle_no_break(self):
        """Test no candle break detection."""
        df = pd.DataFrame({
            'high': [100, 101, 102, 103, 102],  # Last candle doesn't break previous high
            'low': [98, 99, 100, 101, 100],
            'close': [99, 100, 101, 102, 101]
        })
        
        is_break = TechnicalIndicators.is_candle_break(df, lookback=1)
        
        assert is_break.iloc[-1] == False


# ============================================================================
# SUPERTREND TESTS
# ============================================================================

class TestCalculateSupertrend:
    """Test Supertrend calculations."""
    
    def test_calculate_supertrend_basic(self, sample_ohlcv_data):
        """Test basic Supertrend calculation."""
        df = sample_ohlcv_data(num_candles=50)
        
        supertrend, direction = TechnicalIndicators.calculate_supertrend(
            df, period=10, multiplier=3.0
        )
        
        assert len(supertrend) == len(df)
        assert len(direction) == len(df)
    
    def test_calculate_supertrend_uptrend(self, sample_ohlcv_data):
        """Test Supertrend in uptrend market."""
        df = sample_ohlcv_data(num_candles=50, trend="up")
        
        supertrend, direction = TechnicalIndicators.calculate_supertrend(
            df, period=10, multiplier=3.0
        )
        
        # In uptrend, direction should be positive (1)
        # Get the last non-null direction value
        valid_direction = direction.dropna()
        if len(valid_direction) > 0:
            assert valid_direction.iloc[-1] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
