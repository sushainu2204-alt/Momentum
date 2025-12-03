"""
Unit Tests for backend/core/indicators/technical.py

Tests TechnicalIndicators and MarketIndicators calculations.
"""

import pytest
import pandas as pd
import numpy as np

from backend.core.indicators import TechnicalIndicators, MarketIndicators


@pytest.mark.unit
class TestCalculateEMA:
    """Tests for EMA calculation."""
    
    def test_ema_returns_series(self, ohlcv_factory):
        """Test EMA returns pandas Series."""
        df = ohlcv_factory(num_candles=20)
        
        ema = TechnicalIndicators.calculate_ema(df, period=9)
        
        assert isinstance(ema, pd.Series)
        assert len(ema) == len(df)
    
    def test_ema_period_9(self, ohlcv_factory):
        """Test EMA calculation with period 9."""
        df = ohlcv_factory(num_candles=20)
        
        ema = TechnicalIndicators.calculate_ema(df, period=9)
        
        # EMA should exist for all rows (unlike SMA)
        assert not ema.isna().all()
    
    def test_ema_period_20(self, ohlcv_factory):
        """Test EMA calculation with period 20."""
        df = ohlcv_factory(num_candles=30)
        
        ema = TechnicalIndicators.calculate_ema(df, period=20)
        
        assert not ema.isna().all()
    
    def test_ema_custom_column(self, ohlcv_factory):
        """Test EMA on non-close column."""
        df = ohlcv_factory(num_candles=20)
        
        ema_open = TechnicalIndicators.calculate_ema(df, column='open', period=9)
        ema_close = TechnicalIndicators.calculate_ema(df, column='close', period=9)
        
        # EMAs should be different for different columns
        assert not ema_open.equals(ema_close)


@pytest.mark.unit
class TestCalculateSMA:
    """Tests for SMA calculation."""
    
    def test_sma_returns_series(self, ohlcv_factory):
        """Test SMA returns pandas Series."""
        df = ohlcv_factory(num_candles=30)
        
        sma = TechnicalIndicators.calculate_sma(df, period=20)
        
        assert isinstance(sma, pd.Series)
    
    def test_sma_has_nan_initially(self, ohlcv_factory):
        """Test SMA has NaN for first (period-1) values."""
        df = ohlcv_factory(num_candles=30)
        
        sma = TechnicalIndicators.calculate_sma(df, period=20)
        
        # First 19 values should be NaN
        assert sma.iloc[:19].isna().all()
        # After that should have values
        assert not sma.iloc[19:].isna().any()
    
    def test_sma_is_average(self, ohlcv_factory):
        """Test SMA is actual average of last N values."""
        df = ohlcv_factory(num_candles=10)
        
        sma = TechnicalIndicators.calculate_sma(df, period=5)
        
        # Manual calculation for last row
        expected = df['close'].iloc[-5:].mean()
        actual = sma.iloc[-1]
        
        assert actual == pytest.approx(expected, rel=0.001)


@pytest.mark.unit
class TestCalculateRSI:
    """Tests for RSI calculation."""
    
    def test_rsi_returns_series(self, ohlcv_factory):
        """Test RSI returns pandas Series."""
        df = ohlcv_factory(num_candles=30)
        
        rsi = TechnicalIndicators.calculate_rsi(df, period=14)
        
        assert isinstance(rsi, pd.Series)
    
    def test_rsi_range_0_100(self, ohlcv_factory):
        """Test RSI values are between 0 and 100."""
        df = ohlcv_factory(num_candles=50)
        
        rsi = TechnicalIndicators.calculate_rsi(df, period=14)
        
        # Drop NaN values and check range
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()
    
    def test_rsi_trending_up(self):
        """Test RSI is high when price trending up."""
        dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
        # Strictly trending up prices
        df = pd.DataFrame({
            'close': range(100, 130)
        }, index=dates)
        
        rsi = TechnicalIndicators.calculate_rsi(df, period=14)
        
        # RSI should be high (near 100) for uptrend
        assert rsi.iloc[-1] > 70
    
    def test_rsi_trending_down(self):
        """Test RSI is low when price trending down."""
        dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
        # Strictly trending down prices
        df = pd.DataFrame({
            'close': range(130, 100, -1)
        }, index=dates)
        
        rsi = TechnicalIndicators.calculate_rsi(df, period=14)
        
        # RSI should be low (near 0) for downtrend
        assert rsi.iloc[-1] < 30


@pytest.mark.unit
class TestCalculateVWAP:
    """Tests for VWAP calculation."""
    
    def test_vwap_returns_series(self, ohlcv_factory):
        """Test VWAP returns pandas Series."""
        df = ohlcv_factory(num_candles=20)
        
        vwap = TechnicalIndicators.calculate_vwap(df)
        
        assert isinstance(vwap, pd.Series)
        assert len(vwap) == len(df)
    
    def test_vwap_no_nan(self, ohlcv_factory):
        """Test VWAP has no NaN values."""
        df = ohlcv_factory(num_candles=20)
        
        vwap = TechnicalIndicators.calculate_vwap(df)
        
        assert not vwap.isna().any()
    
    def test_vwap_is_volume_weighted(self):
        """Test VWAP weights by volume correctly."""
        dates = pd.date_range(start='2024-01-15 09:15', periods=3, freq='5min')
        df = pd.DataFrame({
            'high': [100, 100, 100],
            'low': [100, 100, 100],
            'close': [100, 100, 100],
            'volume': [1000, 1000, 1000]
        }, index=dates)
        
        vwap = TechnicalIndicators.calculate_vwap(df)
        
        # With uniform price and volume, VWAP = typical price = 100
        assert vwap.iloc[-1] == pytest.approx(100.0, rel=0.001)
    
    def test_vwap_higher_volume_more_weight(self):
        """Test VWAP gives more weight to higher volume candles."""
        dates = pd.date_range(start='2024-01-15 09:15', periods=2, freq='5min')
        df = pd.DataFrame({
            'high': [100, 200],
            'low': [100, 200],
            'close': [100, 200],
            'volume': [1, 9]  # 9x more volume on second candle
        }, index=dates)
        
        vwap = TechnicalIndicators.calculate_vwap(df)
        
        # VWAP should be closer to 200 (higher volume)
        # Expected: (100*1 + 200*9) / (1+9) = 1900/10 = 190
        assert vwap.iloc[-1] == pytest.approx(190.0, rel=0.001)


@pytest.mark.unit
class TestCalculateVolumeSurge:
    """Tests for volume surge detection."""
    
    def test_volume_surge_returns_boolean_series(self, ohlcv_factory):
        """Test volume surge returns boolean Series."""
        df = ohlcv_factory(num_candles=20)
        
        surge = TechnicalIndicators.calculate_volume_surge(df, lookback=10)
        
        assert isinstance(surge, pd.Series)
        assert surge.dtype == bool
    
    def test_volume_surge_detected(self):
        """Test volume surge detection when volume is high."""
        dates = pd.date_range(start='2024-01-15 09:15', periods=15, freq='5min')
        volumes = [1000] * 14 + [3000]  # Last candle 3x average
        df = pd.DataFrame({'volume': volumes}, index=dates)
        
        surge = TechnicalIndicators.calculate_volume_surge(df, lookback=10, multiplier=2.0)
        
        assert surge.iloc[-1] is True or surge.iloc[-1] == True
    
    def test_no_volume_surge(self):
        """Test no surge when volume is normal."""
        dates = pd.date_range(start='2024-01-15 09:15', periods=15, freq='5min')
        df = pd.DataFrame({'volume': [1000] * 15}, index=dates)
        
        surge = TechnicalIndicators.calculate_volume_surge(df, lookback=10, multiplier=2.0)
        
        assert surge.iloc[-1] is False or surge.iloc[-1] == False


@pytest.mark.unit
class TestCalculateATR:
    """Tests for ATR calculation."""
    
    def test_atr_returns_series(self, ohlcv_factory):
        """Test ATR returns pandas Series."""
        df = ohlcv_factory(num_candles=30)
        
        atr = TechnicalIndicators.calculate_atr(df, period=14)
        
        assert isinstance(atr, pd.Series)
    
    def test_atr_positive_values(self, ohlcv_factory):
        """Test ATR values are positive."""
        df = ohlcv_factory(num_candles=30)
        
        atr = TechnicalIndicators.calculate_atr(df, period=14)
        
        # Valid ATR values should be positive
        valid_atr = atr.dropna()
        assert (valid_atr >= 0).all()
    
    def test_atr_higher_volatility(self):
        """Test ATR is higher for more volatile data."""
        dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
        
        # Low volatility
        low_vol_df = pd.DataFrame({
            'high': [100, 101, 100, 101] * 7 + [100, 101],
            'low': [99, 100, 99, 100] * 7 + [99, 100],
            'close': [100, 100, 100, 100] * 7 + [100, 100]
        }, index=dates)
        
        # High volatility
        high_vol_df = pd.DataFrame({
            'high': [105, 110, 105, 110] * 7 + [105, 110],
            'low': [95, 90, 95, 90] * 7 + [95, 90],
            'close': [100, 100, 100, 100] * 7 + [100, 100]
        }, index=dates)
        
        low_atr = TechnicalIndicators.calculate_atr(low_vol_df, period=14)
        high_atr = TechnicalIndicators.calculate_atr(high_vol_df, period=14)
        
        # High volatility should have higher ATR
        assert high_atr.iloc[-1] > low_atr.iloc[-1]


@pytest.mark.unit
class TestCalculateBollingerBands:
    """Tests for Bollinger Bands calculation."""
    
    def test_bollinger_returns_three_series(self, ohlcv_factory):
        """Test Bollinger Bands returns three Series."""
        df = ohlcv_factory(num_candles=30)
        
        upper, middle, lower = TechnicalIndicators.calculate_bollinger_bands(df)
        
        assert isinstance(upper, pd.Series)
        assert isinstance(middle, pd.Series)
        assert isinstance(lower, pd.Series)
    
    def test_bollinger_band_order(self, ohlcv_factory):
        """Test upper > middle > lower."""
        df = ohlcv_factory(num_candles=30)
        
        upper, middle, lower = TechnicalIndicators.calculate_bollinger_bands(df, period=20)
        
        # For valid values (after period)
        valid_idx = ~upper.isna()
        assert (upper[valid_idx] >= middle[valid_idx]).all()
        assert (middle[valid_idx] >= lower[valid_idx]).all()
    
    def test_bollinger_middle_is_sma(self, ohlcv_factory):
        """Test middle band equals SMA."""
        df = ohlcv_factory(num_candles=30)
        
        upper, middle, lower = TechnicalIndicators.calculate_bollinger_bands(df, period=20)
        sma = TechnicalIndicators.calculate_sma(df, period=20)
        
        pd.testing.assert_series_equal(middle, sma)


@pytest.mark.unit
class TestIsCandleBreak:
    """Tests for candle break detection."""
    
    def test_candle_break_returns_boolean_series(self, ohlcv_factory):
        """Test is_candle_break returns boolean Series."""
        df = ohlcv_factory(num_candles=10)
        
        is_break = TechnicalIndicators.is_candle_break(df)
        
        assert isinstance(is_break, pd.Series)
        assert is_break.dtype == bool
    
    def test_candle_break_detected(self):
        """Test candle break when current high > previous high."""
        dates = pd.date_range(start='2024-01-15 09:15', periods=3, freq='5min')
        df = pd.DataFrame({
            'high': [100, 105, 110]  # Each candle breaks previous
        }, index=dates)
        
        is_break = TechnicalIndicators.is_candle_break(df, lookback=1)
        
        assert is_break.iloc[-1] is True or is_break.iloc[-1] == True
    
    def test_no_candle_break(self):
        """Test no break when current high < previous high."""
        dates = pd.date_range(start='2024-01-15 09:15', periods=3, freq='5min')
        df = pd.DataFrame({
            'high': [110, 105, 100]  # Descending highs
        }, index=dates)
        
        is_break = TechnicalIndicators.is_candle_break(df, lookback=1)
        
        assert is_break.iloc[-1] is False or is_break.iloc[-1] == False


@pytest.mark.unit
class TestCalculateSupertrend:
    """Tests for Supertrend calculation."""
    
    def test_supertrend_returns_two_series(self, ohlcv_factory):
        """Test Supertrend returns two Series."""
        df = ohlcv_factory(num_candles=30)
        
        supertrend, direction = TechnicalIndicators.calculate_supertrend(df)
        
        assert isinstance(supertrend, pd.Series)
        assert isinstance(direction, pd.Series)
    
    def test_supertrend_direction_values(self, ohlcv_factory):
        """Test direction is 1 (bullish) or -1 (bearish)."""
        df = ohlcv_factory(num_candles=30)
        
        supertrend, direction = TechnicalIndicators.calculate_supertrend(df, period=10)
        
        # Valid direction values should be 1 or -1
        valid_direction = direction.dropna()
        assert set(valid_direction.unique()).issubset({1, -1, 0})


@pytest.mark.unit
class TestMarketIndicators:
    """Tests for MarketIndicators class."""
    
    def test_advance_decline_ratio_positive(self):
        """Test advance/decline ratio calculation."""
        ratio = MarketIndicators.calculate_advance_decline_ratio(
            advances=100, declines=50
        )
        
        assert ratio == 2.0
    
    def test_advance_decline_ratio_zero_declines(self):
        """Test advance/decline ratio with zero declines."""
        ratio = MarketIndicators.calculate_advance_decline_ratio(
            advances=100, declines=0
        )
        
        assert ratio == float('inf')
    
    def test_is_market_bullish_true(self):
        """Test market bullish detection when conditions met."""
        dates = pd.date_range(start='2024-01-01', periods=60, freq='D')
        # Strongly trending up
        prices = list(range(100, 160))
        df = pd.DataFrame({'close': prices}, index=dates)
        
        is_bullish = MarketIndicators.is_market_bullish(df, ema_period=50)
        
        assert is_bullish == True
    
    def test_is_market_bullish_insufficient_data(self):
        """Test market bullish returns False with insufficient data."""
        dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
        df = pd.DataFrame({'close': range(100, 130)}, index=dates)
        
        is_bullish = MarketIndicators.is_market_bullish(df, ema_period=50)
        
        assert is_bullish is False
