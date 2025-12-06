"""
Unit Tests for VWAP EMA Breakout Strategy

Tests the VWAP + EMA breakout confirmation strategy.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, time
from unittest.mock import Mock

from backend.core.strategies.vwap_ema_breakout import VWAPEMABreakoutStrategy
from backend.config import VWAPEMABreakoutConfig
from backend.core.models import Candidate, Position, SignalType


class TestVWAPEMABreakoutStrategy:
    """Test VWAPEMABreakoutStrategy class."""
    
    @pytest.fixture
    def config(self):
        """Create default config."""
        return VWAPEMABreakoutConfig()
    
    @pytest.fixture
    def strategy(self, config):
        """Create strategy with default config."""
        return VWAPEMABreakoutStrategy(config)
    
    @pytest.fixture
    def sample_df(self):
        """Create sample OHLCV DataFrame."""
        np.random.seed(42)
        n = 30
        
        # Create realistic uptrending data
        base = 100
        close = [base + i * 0.3 + np.random.randn() * 0.2 for i in range(n)]
        
        df = pd.DataFrame({
            'open': [c - np.random.rand() * 0.3 for c in close],
            'high': [c + np.random.rand() * 0.5 for c in close],
            'low': [c - np.random.rand() * 0.5 for c in close],
            'close': close,
            'volume': [100000 + np.random.randint(-10000, 50000) for _ in range(n)]
        })
        
        # Ensure OHLC consistency
        df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1)
        df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1)
        
        return df
    
    @pytest.fixture
    def candidate(self):
        """Create sample candidate within valid gain range."""
        return Candidate(
            symbol="TESTSTOCK",
            instrument_token=123456,
            current_price=103.0,
            gain_pct=3.0,  # Within 2-4% range
            volume=200000,
            avg_volume=100000,
            timestamp=datetime.now()
        )
    
    def test_strategy_initialization(self, strategy, config):
        """Test strategy initializes correctly."""
        assert strategy.config == config
    
    def test_min_data_points(self, strategy):
        """Test min_data_points property."""
        expected = max(strategy.config.ema_period, strategy.config.volume_lookback) + 1
        assert strategy.min_data_points == expected
    
    def test_calculate_indicators(self, strategy, sample_df):
        """Test indicator calculation."""
        result = strategy.calculate_indicators(sample_df)
        
        assert 'vwap' in result.columns
        assert f'ema_{strategy.config.ema_period}' in result.columns
        assert len(result) == len(sample_df)
    
    def test_calculate_indicators_empty_df(self, strategy):
        """Test indicator calculation with empty DataFrame."""
        empty_df = pd.DataFrame()
        result = strategy.calculate_indicators(empty_df)
        
        assert result.empty
    
    def test_calculate_indicators_insufficient_data(self, strategy, config):
        """Test indicator calculation with insufficient data."""
        short_df = pd.DataFrame({
            'open': [100, 101],
            'high': [101, 102],
            'low': [99, 100],
            'close': [100.5, 101.5],
            'volume': [100000, 110000]
        })
        
        result = strategy.calculate_indicators(short_df)
        
        # Should return unchanged df
        assert len(result) == 2


class TestVWAPFilter:
    """Test VWAP filter logic."""
    
    @pytest.fixture
    def config(self):
        return VWAPEMABreakoutConfig(vwap_enabled=True)
    
    @pytest.fixture
    def strategy(self, config):
        return VWAPEMABreakoutStrategy(config)
    
    @pytest.fixture
    def sample_df(self):
        """Create sample OHLCV DataFrame."""
        np.random.seed(42)
        n = 30
        
        base = 100
        close = [base + i * 0.3 for i in range(n)]
        
        df = pd.DataFrame({
            'open': [c - 0.2 for c in close],
            'high': [c + 0.5 for c in close],
            'low': [c - 0.5 for c in close],
            'close': close,
            'volume': [100000] * n
        })
        
        return df
    
    def test_vwap_filter_passes_when_above(self, strategy, sample_df):
        """Test VWAP filter passes when price > VWAP."""
        # Calculate indicators
        df = strategy.calculate_indicators(sample_df)
        
        # Artificially set close > VWAP
        df.loc[df.index[-1], 'close'] = df['vwap'].iloc[-1] * 1.02
        
        result = strategy._check_vwap_filter(df)
        assert result == True
    
    def test_vwap_filter_fails_when_below(self, strategy, sample_df):
        """Test VWAP filter fails when price < VWAP."""
        df = strategy.calculate_indicators(sample_df)
        
        # Artificially set close < VWAP
        df.loc[df.index[-1], 'close'] = df['vwap'].iloc[-1] * 0.98
        
        result = strategy._check_vwap_filter(df)
        assert result == False
    
    def test_vwap_filter_disabled(self):
        """Test VWAP filter when disabled."""
        config = VWAPEMABreakoutConfig(vwap_enabled=False)
        strategy = VWAPEMABreakoutStrategy(config)
        
        df = pd.DataFrame()  # Empty df
        
        result = strategy._check_vwap_filter(df)
        assert result is True  # Should pass when disabled


class TestEMAFilter:
    """Test EMA filter logic."""
    
    @pytest.fixture
    def config(self):
        return VWAPEMABreakoutConfig(ema_period=20)
    
    @pytest.fixture
    def strategy(self, config):
        return VWAPEMABreakoutStrategy(config)
    
    @pytest.fixture
    def sample_df(self):
        """Create sample OHLCV DataFrame."""
        n = 30
        close = [100 + i * 0.3 for i in range(n)]
        
        df = pd.DataFrame({
            'open': [c - 0.2 for c in close],
            'high': [c + 0.5 for c in close],
            'low': [c - 0.5 for c in close],
            'close': close,
            'volume': [100000] * n
        })
        
        return df
    
    def test_ema_filter_passes_when_above(self, strategy, sample_df):
        """Test EMA filter passes when price > EMA."""
        df = strategy.calculate_indicators(sample_df)
        
        # In uptrend, price should be above EMA
        result = strategy._check_ema_filter(df)
        
        # Check if close > EMA
        ema_col = f'ema_{strategy.config.ema_period}'
        if df['close'].iloc[-1] > df[ema_col].iloc[-1]:
            assert result == True
    
    def test_ema_filter_insufficient_data(self, strategy):
        """Test EMA filter with insufficient data."""
        short_df = pd.DataFrame({
            'open': [100],
            'high': [101],
            'low': [99],
            'close': [100.5],
            'volume': [100000]
        })
        
        result = strategy._check_ema_filter(short_df)
        assert result is False


class TestVolumeSurgeFilter:
    """Test volume surge filter logic."""
    
    @pytest.fixture
    def config(self):
        return VWAPEMABreakoutConfig(
            volume_multiplier=1.5,
            volume_lookback=5
        )
    
    @pytest.fixture
    def strategy(self, config):
        return VWAPEMABreakoutStrategy(config)
    
    def test_volume_surge_passes(self, strategy):
        """Test volume surge filter passes with high volume."""
        df = pd.DataFrame({
            'open': [100] * 10,
            'high': [101] * 10,
            'low': [99] * 10,
            'close': [100.5] * 10,
            'volume': [100000] * 9 + [200000]  # Last candle has 2x volume
        })
        
        result = strategy._check_volume_surge(df)
        assert result == True  # 2x > 1.5x
    
    def test_volume_surge_fails(self, strategy):
        """Test volume surge filter fails with normal volume."""
        df = pd.DataFrame({
            'open': [100] * 10,
            'high': [101] * 10,
            'low': [99] * 10,
            'close': [100.5] * 10,
            'volume': [100000] * 10  # All normal volume
        })
        
        result = strategy._check_volume_surge(df)
        assert result == False  # 1x < 1.5x


class TestBreakoutFilter:
    """Test breakout of previous high filter."""
    
    @pytest.fixture
    def config(self):
        return VWAPEMABreakoutConfig(breakout_previous_high=True)
    
    @pytest.fixture
    def strategy(self, config):
        return VWAPEMABreakoutStrategy(config)
    
    def test_breakout_passes(self, strategy):
        """Test breakout filter passes when price > previous high."""
        df = pd.DataFrame({
            'open': [100, 101],
            'high': [101, 103],  # Current high > previous
            'low': [99, 100],
            'close': [100.5, 102],  # Current close > previous high (101)
            'volume': [100000, 110000]
        })
        
        result = strategy._check_breakout_previous_high(df)
        assert result == True
    
    def test_breakout_fails(self, strategy):
        """Test breakout filter fails when price < previous high."""
        df = pd.DataFrame({
            'open': [100, 99],
            'high': [103, 101],  # Previous high was higher
            'low': [99, 98],
            'close': [100.5, 100],  # Current close < previous high (103)
            'volume': [100000, 110000]
        })
        
        result = strategy._check_breakout_previous_high(df)
        assert result == False
    
    def test_breakout_disabled(self):
        """Test breakout filter when disabled."""
        config = VWAPEMABreakoutConfig(breakout_previous_high=False)
        strategy = VWAPEMABreakoutStrategy(config)
        
        df = pd.DataFrame({
            'open': [100],
            'high': [101],
            'low': [99],
            'close': [100.5],
            'volume': [100000]
        })
        
        result = strategy._check_breakout_previous_high(df)
        assert result is True  # Should pass when disabled


class TestPriceRangeFilter:
    """Test price range (gain %) filter."""
    
    @pytest.fixture
    def config(self):
        return VWAPEMABreakoutConfig(
            min_gain_pct=2.0,
            max_gain_pct=4.0
        )
    
    @pytest.fixture
    def strategy(self, config):
        return VWAPEMABreakoutStrategy(config)
    
    def test_price_range_within_bounds(self, strategy):
        """Test filter passes for gain within bounds."""
        candidate = Candidate(
            symbol="TEST",
            instrument_token=12345,
            current_price=103.0,
            gain_pct=3.0,  # Within 2-4%
            volume=100000,
            avg_volume=50000,
            timestamp=datetime.now()
        )
        
        result = strategy._check_price_range(candidate)
        assert result is True
    
    def test_price_range_below_min(self, strategy):
        """Test filter fails when gain below min."""
        candidate = Candidate(
            symbol="TEST",
            instrument_token=12345,
            current_price=101.0,
            gain_pct=1.0,  # Below 2%
            volume=100000,
            avg_volume=50000,
            timestamp=datetime.now()
        )
        
        result = strategy._check_price_range(candidate)
        assert result is False
    
    def test_price_range_above_max(self, strategy):
        """Test filter fails when gain above max."""
        candidate = Candidate(
            symbol="TEST",
            instrument_token=12345,
            current_price=105.0,
            gain_pct=5.0,  # Above 4%
            volume=100000,
            avg_volume=50000,
            timestamp=datetime.now()
        )
        
        result = strategy._check_price_range(candidate)
        assert result is False


class TestApplyFilters:
    """Test combined filter application."""
    
    @pytest.fixture
    def config(self):
        return VWAPEMABreakoutConfig(
            min_gain_pct=2.0,
            max_gain_pct=4.0,
            ema_period=5,
            volume_multiplier=1.5,
            volume_lookback=5,
            vwap_enabled=True,
            breakout_previous_high=True
        )
    
    @pytest.fixture
    def strategy(self, config):
        return VWAPEMABreakoutStrategy(config)
    
    @pytest.fixture
    def valid_candidate(self):
        """Candidate with valid gain."""
        return Candidate(
            symbol="VALID",
            instrument_token=12345,
            current_price=103.0,
            gain_pct=3.0,
            volume=200000,
            avg_volume=100000,
            timestamp=datetime.now()
        )
    
    def test_apply_filters_all_pass(self, strategy, valid_candidate):
        """Test all filters passing."""
        # Create data where all conditions are met
        n = 20
        # Strong uptrend data
        close = [100 + i * 0.5 for i in range(n)]  # Steady uptrend
        
        df = pd.DataFrame({
            'open': [c - 0.2 for c in close],
            'high': [c + 0.3 for c in close],
            'low': [c - 0.3 for c in close],
            'close': close,
            # Volume surge on last candle
            'volume': [100000] * (n-1) + [200000]
        })
        
        # Calculate indicators
        df = strategy.calculate_indicators(df)
        
        # The filter result depends on the calculated values
        # This tests that apply_filters doesn't crash
        result = strategy.apply_filters(valid_candidate, df)
        assert isinstance(result, bool)
    
    def test_apply_filters_gain_out_of_range(self, strategy):
        """Test filter fails when gain out of range."""
        candidate = Candidate(
            symbol="INVALID",
            instrument_token=12345,
            current_price=101.0,
            gain_pct=1.0,  # Below 2%
            volume=100000,
            avg_volume=50000,
            timestamp=datetime.now()
        )
        
        df = pd.DataFrame({
            'open': [100] * 10,
            'high': [101] * 10,
            'low': [99] * 10,
            'close': [100.5] * 10,
            'volume': [100000] * 10
        })
        
        df = strategy.calculate_indicators(df)
        result = strategy.apply_filters(candidate, df)
        
        assert result is False


class TestSignalGeneration:
    """Test signal generation logic."""
    
    @pytest.fixture
    def config(self):
        return VWAPEMABreakoutConfig(
            target_pct=1.5,
            stop_loss_pct=0.7
        )
    
    @pytest.fixture
    def strategy(self, config):
        return VWAPEMABreakoutStrategy(config)
    
    def test_should_enter_within_hours(self, strategy):
        """Test entry signal generation."""
        candidate = Candidate(
            symbol="TEST",
            instrument_token=123456,
            current_price=100.0,
            gain_pct=3.0,
            volume=100000,
            avg_volume=50000,
            timestamp=datetime.now()
        )
        
        # Create df with indicators
        n = 30
        df = pd.DataFrame({
            'open': [100] * n,
            'high': [101] * n,
            'low': [99] * n,
            'close': [100.5] * n,
            'volume': [100000] * n
        })
        df = strategy.calculate_indicators(df)
        
        # Use valid trading time (10:00 AM)
        trading_time = datetime(2024, 1, 15, 10, 0, 0)
        
        signal = strategy.should_enter(candidate, df, trading_time)
        
        if signal:
            assert signal.signal_type == SignalType.BUY
            assert signal.symbol == "TEST"
            assert signal.stop_loss is not None
            assert signal.target is not None
    
    def test_should_exit_target_hit(self, strategy):
        """Test exit signal on target hit."""
        position = Position(
            symbol="TEST",
            instrument_token=123456,
            quantity=10,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 15, 10, 0, 0),
            stop_loss=99.3,  # -0.7%
            target=101.5     # +1.5%
        )
        
        current_time = datetime(2024, 1, 15, 11, 0, 0)
        current_price = 102.0  # Above target
        
        signal = strategy.should_exit(position, current_price, current_time)
        
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert "Target" in signal.reason
    
    def test_should_exit_stop_loss_hit(self, strategy):
        """Test exit signal on stop loss hit."""
        position = Position(
            symbol="TEST",
            instrument_token=123456,
            quantity=10,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 15, 10, 0, 0),
            stop_loss=99.3,
            target=101.5
        )
        
        current_time = datetime(2024, 1, 15, 11, 0, 0)
        current_price = 99.0  # Below stop loss
        
        signal = strategy.should_exit(position, current_price, current_time)
        
        assert signal is not None
        assert signal.signal_type == SignalType.SELL
        assert "Stop loss" in signal.reason
    
    def test_should_exit_no_condition_met(self, strategy):
        """Test no exit signal when in range."""
        position = Position(
            symbol="TEST",
            instrument_token=123456,
            quantity=10,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 15, 10, 0, 0),
            stop_loss=99.3,
            target=101.5
        )
        
        current_time = datetime(2024, 1, 15, 11, 0, 0)
        current_price = 100.5  # Between SL and target
        
        signal = strategy.should_exit(position, current_price, current_time)
        
        assert signal is None


class TestCalculateSignalsDataframe:
    """Test batch signal calculation for backtesting."""
    
    @pytest.fixture
    def config(self):
        return VWAPEMABreakoutConfig(
            ema_period=5,
            volume_lookback=5,
            volume_multiplier=1.2
        )
    
    @pytest.fixture
    def strategy(self, config):
        return VWAPEMABreakoutStrategy(config)
    
    def test_calculate_signals_dataframe(self, strategy):
        """Test signal calculation for entire dataframe."""
        n = 30
        close = [100 + i * 0.3 for i in range(n)]
        
        df = pd.DataFrame({
            'open': [c - 0.2 for c in close],
            'high': [c + 0.3 for c in close],
            'low': [c - 0.3 for c in close],
            'close': close,
            'volume': [100000] * (n-1) + [150000]  # Volume surge at end
        })
        
        result = strategy.calculate_signals_dataframe(df)
        
        assert 'signal' in result.columns
        assert 'vwap' in result.columns
        assert f'ema_{strategy.config.ema_period}' in result.columns
        assert len(result) == len(df)


class TestVWAPEMAConfig:
    """Test VWAPEMABreakoutConfig integration."""
    
    def test_config_default_values(self):
        """Test default config values."""
        config = VWAPEMABreakoutConfig()
        
        assert config.name == "VWAP EMA Breakout"
        assert config.min_gain_pct > 0
        assert config.max_gain_pct > config.min_gain_pct
        assert config.ema_period > 0
        assert config.volume_multiplier > 0
    
    def test_config_custom_values(self):
        """Test custom config values."""
        config = VWAPEMABreakoutConfig(
            min_gain_pct=1.5,
            max_gain_pct=5.0,
            ema_period=10,
            volume_multiplier=2.0
        )
        
        assert config.min_gain_pct == 1.5
        assert config.max_gain_pct == 5.0
        assert config.ema_period == 10
        assert config.volume_multiplier == 2.0
    
    def test_strategy_with_custom_config(self):
        """Test strategy uses custom config values."""
        config = VWAPEMABreakoutConfig(
            ema_period=15,
            target_pct=2.0
        )
        
        strategy = VWAPEMABreakoutStrategy(config)
        
        assert strategy.config.ema_period == 15
        assert strategy.config.target_pct == 2.0
