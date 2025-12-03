"""
Unit Tests for EMA Crossover Strategy

Tests for EMACrossoverStrategy class.
Note: EMACrossoverStrategy has a custom __init__ that takes (fast_period, slow_period)
rather than a config object.
"""
import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from backend.core.strategies.ema_crossover import EMACrossoverStrategy


class TestEMACrossoverStrategy:
    """Test EMACrossoverStrategy class."""
    
    @pytest.fixture
    def strategy(self):
        """Create strategy instance with default parameters."""
        return EMACrossoverStrategy(fast_period=9, slow_period=21)
    
    @pytest.fixture
    def custom_strategy(self):
        """Create strategy with custom EMA periods."""
        return EMACrossoverStrategy(fast_period=5, slow_period=15)
    
    @pytest.fixture
    def sample_prices(self):
        """Create sample price series for testing."""
        np.random.seed(42)
        # Create uptrending data
        base_price = 100.0
        trend = np.linspace(0, 10, 50)
        noise = np.random.randn(50) * 0.3
        return pd.Series(base_price + trend + noise)
    
    @pytest.fixture
    def sample_ohlc_dataframe(self):
        """Create sample OHLC dataframe for testing."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='5T')
        
        np.random.seed(42)
        base_price = 100.0
        trend = np.linspace(0, 10, 100)
        noise = np.random.randn(100) * 0.5
        
        close = base_price + trend + noise
        
        df = pd.DataFrame({
            'open': close - np.random.rand(100) * 0.5,
            'high': close + np.random.rand(100) * 1.0,
            'low': close - np.random.rand(100) * 1.0,
            'close': close,
            'volume': np.random.randint(10000, 100000, 100)
        }, index=dates)
        
        return df
    
    @pytest.fixture
    def crossover_bullish_prices(self):
        """Create price series with bullish EMA crossover."""
        # Downtrend then uptrend to create crossover
        down = np.linspace(100, 90, 25)
        up = np.linspace(90, 110, 25)
        return pd.Series(np.concatenate([down, up]))
    
    @pytest.fixture
    def crossover_bearish_prices(self):
        """Create price series with bearish EMA crossover."""
        # Uptrend then downtrend to create crossover
        up = np.linspace(100, 115, 25)
        down = np.linspace(115, 95, 25)
        return pd.Series(np.concatenate([up, down]))
    
    def test_strategy_initialization_default(self, strategy):
        """Test strategy is initialized with defaults correctly."""
        assert strategy.fast_period == 9
        assert strategy.slow_period == 21
        assert strategy.name == "EMA_CROSSOVER"
    
    def test_strategy_initialization_custom(self, custom_strategy):
        """Test strategy is initialized with custom values."""
        assert custom_strategy.fast_period == 5
        assert custom_strategy.slow_period == 15
    
    def test_min_data_points(self, strategy):
        """Test min_data_points returns correct value."""
        # Should need at least slow_period + 2
        assert strategy.min_data_points == strategy.slow_period + 2
    
    def test_calculate_indicators_returns_tuple(self, strategy, sample_prices):
        """Test calculate_indicators returns (fast_ema, slow_ema) tuple."""
        fast_ema, slow_ema = strategy.calculate_indicators(sample_prices)
        
        assert isinstance(fast_ema, float)
        assert isinstance(slow_ema, float)
    
    def test_calculate_indicators_with_insufficient_data(self, strategy):
        """Test calculate_indicators returns None with insufficient data."""
        short_prices = pd.Series([100, 101, 102])  # Less than slow_period
        
        fast_ema, slow_ema = strategy.calculate_indicators(short_prices)
        
        assert fast_ema is None
        assert slow_ema is None
    
    def test_fast_ema_more_responsive(self, strategy, sample_prices):
        """Test fast EMA responds more quickly to price changes."""
        fast_ema, slow_ema = strategy.calculate_indicators(sample_prices)
        
        # In uptrend, fast EMA should be closer to latest price
        latest_price = sample_prices.iloc[-1]
        fast_distance = abs(fast_ema - latest_price)
        slow_distance = abs(slow_ema - latest_price)
        
        assert fast_distance <= slow_distance
    
    def test_generate_signal_bullish_crossover(self, strategy):
        """Test BUY signal on bullish crossover."""
        # Previous: fast <= slow, Current: fast > slow
        current = (110.0, 105.0)  # fast > slow
        previous = (100.0, 105.0)  # fast <= slow
        
        signal = strategy.generate_signal(current, previous)
        
        assert signal == "BUY"
    
    def test_generate_signal_bearish_crossover(self, strategy):
        """Test SELL signal on bearish crossover."""
        # Previous: fast >= slow, Current: fast < slow
        current = (100.0, 105.0)  # fast < slow
        previous = (110.0, 105.0)  # fast >= slow
        
        signal = strategy.generate_signal(current, previous)
        
        assert signal == "SELL"
    
    def test_generate_signal_no_crossover(self, strategy):
        """Test no signal when no crossover."""
        # Both above
        current = (110.0, 100.0)
        previous = (108.0, 100.0)
        
        signal = strategy.generate_signal(current, previous)
        
        assert signal is None
    
    def test_generate_signal_with_none_values(self, strategy):
        """Test no signal when indicators contain None."""
        current = (None, 100.0)
        previous = (100.0, 100.0)
        
        signal = strategy.generate_signal(current, previous)
        
        assert signal is None
    
    def test_calculate_signals_dataframe(self, strategy, sample_ohlc_dataframe):
        """Test calculate_signals_dataframe adds required columns."""
        df = strategy.calculate_signals_dataframe(sample_ohlc_dataframe.copy())
        
        assert 'ema_fast' in df.columns
        assert 'ema_slow' in df.columns
        assert 'signal' in df.columns
        assert 'position' in df.columns
    
    def test_calculate_signals_dataframe_signal_values(self, strategy, sample_ohlc_dataframe):
        """Test signal column has correct values (-1, 0, 1)."""
        df = strategy.calculate_signals_dataframe(sample_ohlc_dataframe.copy())
        
        # Signal should be 1 (fast > slow), -1 (fast < slow), or 0
        assert set(df['signal'].unique()).issubset({-1, 0, 1})
    
    def test_get_indicator_series(self, strategy, sample_prices):
        """Test get_indicator_series returns full series."""
        fast_series, slow_series = strategy.get_indicator_series(sample_prices)
        
        assert isinstance(fast_series, pd.Series)
        assert isinstance(slow_series, pd.Series)
        assert len(fast_series) == len(sample_prices)
        assert len(slow_series) == len(sample_prices)


class TestEMACrossoverEdgeCases:
    """Test edge cases for EMA Crossover Strategy."""
    
    @pytest.fixture
    def strategy(self):
        """Create strategy instance."""
        return EMACrossoverStrategy()
    
    def test_flat_prices_no_crossover(self, strategy):
        """Test no crossover in flat market."""
        flat_prices = pd.Series([100.0] * 50)
        
        fast_ema, slow_ema = strategy.calculate_indicators(flat_prices)
        
        # EMAs should be equal in flat market
        assert abs(fast_ema - slow_ema) < 0.001
    
    def test_generate_signal_exact_crossover(self, strategy):
        """Test signal when EMAs are exactly equal."""
        current = (100.0, 100.0)  # Equal
        previous = (99.0, 100.0)  # fast < slow
        
        # Fast crossed to equal slow - this is technically a bullish crossover
        signal = strategy.generate_signal(current, previous)
        
        # No crossover since fast == slow is not > slow
        assert signal is None
    
    def test_strategy_with_single_value(self, strategy):
        """Test strategy with single price value."""
        single_price = pd.Series([100.0])
        
        fast_ema, slow_ema = strategy.calculate_indicators(single_price)
        
        assert fast_ema is None
        assert slow_ema is None
    
    def test_strategy_with_nan_in_series(self, strategy):
        """Test strategy handles NaN values gracefully."""
        prices = pd.Series([100.0, np.nan, 102.0, 103.0] + [104.0] * 30)
        
        # Should not crash
        fast_ema, slow_ema = strategy.calculate_indicators(prices)
        
        # May return None or actual values depending on NaN handling


class TestEMACrossoverConfig:
    """Test EMA Crossover configuration."""
    
    def test_default_parameters(self):
        """Test default EMA periods are set correctly."""
        strategy = EMACrossoverStrategy()
        
        assert strategy.fast_period == 9
        assert strategy.slow_period == 21
    
    def test_custom_parameters(self):
        """Test custom EMA periods are accepted."""
        strategy = EMACrossoverStrategy(fast_period=12, slow_period=26)
        
        assert strategy.fast_period == 12
        assert strategy.slow_period == 26
    
    def test_strategy_name(self):
        """Test strategy name is set correctly."""
        strategy = EMACrossoverStrategy()
        
        assert strategy.name == "EMA_CROSSOVER"
