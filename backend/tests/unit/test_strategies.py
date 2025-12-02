"""
Unit Tests for Trading Strategies

Tests VWAPBreakout, VWAPEMABreakout, BullishFlag, EMACrossover strategies.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from unittest.mock import MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def is_bool_like(value) -> bool:
    """Check if value is a boolean-like type (Python bool or numpy.bool_)."""
    return isinstance(value, (bool, np.bool_))


# ============================================================================
# VWAP BREAKOUT STRATEGY TESTS
# ============================================================================

class TestVWAPBreakoutStrategy:
    """Test VWAP Breakout strategy."""
    
    @pytest.fixture
    def vwap_strategy(self):
        """Create VWAP Breakout strategy."""
        from backend.core.strategies.vwap_breakout import VWAPBreakoutStrategy
        from backend.core.config import VWAPBreakoutConfig
        
        config = VWAPBreakoutConfig(
            volume_multiplier=1.5,
            vwap_breakout_pct=0.2,
            stop_loss_pct=0.7,
            target_pct=1.5,
            position_size_pct=0.10
        )
        
        return VWAPBreakoutStrategy(config)
    
    @pytest.fixture
    def breakout_data(self, sample_ohlcv_data):
        """Create data with VWAP breakout pattern."""
        df = sample_ohlcv_data(num_candles=50, base_price=100, trend="up")
        
        # Ensure last candle is above VWAP
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
        
        df.loc[df.index[-1], 'close'] = vwap.iloc[-1] * 1.005  # 0.5% above VWAP
        df.loc[df.index[-1], 'high'] = df.loc[df.index[-1], 'close'] + 0.5
        
        # Add volume spike
        df.loc[df.index[-1], 'volume'] = int(df['volume'].mean() * 2)
        
        return df
    
    def test_check_vwap_breakout_detailed(self, vwap_strategy, breakout_data, sample_candidate):
        """Test VWAP breakout detection when price above VWAP."""
        # Set current price to be above VWAP
        typical_price = (breakout_data['high'] + breakout_data['low'] + breakout_data['close']) / 3
        vwap = (typical_price * breakout_data['volume']).cumsum() / breakout_data['volume'].cumsum()
        above_vwap_price = vwap.iloc[-1] * 1.01  # 1% above VWAP
        
        candidate = sample_candidate(current_price=above_vwap_price)
        
        is_breakout, info = vwap_strategy._check_vwap_breakout_detailed(candidate, breakout_data)
        
        assert is_bool_like(is_breakout)
        assert isinstance(info, str)
        assert "Price" in info
        assert "VWAP" in info
    
    def test_check_volume_surge_detailed(self, vwap_strategy, breakout_data):
        """Test volume surge detection with detailed info."""
        is_surge, info = vwap_strategy._check_volume_surge_detailed(breakout_data)
        
        assert is_bool_like(is_surge)
        assert isinstance(info, str)
        assert "Ratio" in info or "Average" in info or "Avg" in info
    
    def test_check_volume_surge_true(self, vwap_strategy, breakout_data):
        """Test volume surge detection."""
        is_surge = vwap_strategy._check_volume_surge(breakout_data)
        
        assert bool(is_surge) is True
    
    def test_apply_filters(self, vwap_strategy, breakout_data, sample_candidate):
        """Test all filters combined."""
        # Set current price above VWAP
        typical_price = (breakout_data['high'] + breakout_data['low'] + breakout_data['close']) / 3
        vwap = (typical_price * breakout_data['volume']).cumsum() / breakout_data['volume'].cumsum()
        above_vwap_price = vwap.iloc[-1] * 1.01
        
        candidate = sample_candidate(
            current_price=above_vwap_price,
            volume=int(breakout_data['volume'].iloc[-1])
        )
        
        all_pass = vwap_strategy.apply_filters(candidate, breakout_data)
        
        assert is_bool_like(all_pass)
    
    def test_should_enter_during_market_hours(self, vwap_strategy, breakout_data, sample_candidate):
        """Test entry signal generation during market hours."""
        typical_price = (breakout_data['high'] + breakout_data['low'] + breakout_data['close']) / 3
        vwap = (typical_price * breakout_data['volume']).cumsum() / breakout_data['volume'].cumsum()
        above_vwap_price = vwap.iloc[-1] * 1.01
        
        candidate = sample_candidate(
            current_price=above_vwap_price,
            volume=int(breakout_data['volume'].iloc[-1])
        )
        
        # Test during market hours
        market_time = datetime.now().replace(hour=10, minute=30)
        
        signal = vwap_strategy.should_enter(candidate, breakout_data, market_time)
        
        # May or may not generate signal depending on filters
        # Just verify no exception is raised
        assert signal is None or signal.symbol == candidate.symbol
    
    def test_should_enter_outside_market_hours(self, vwap_strategy, breakout_data, sample_candidate):
        """Test no entry outside market hours."""
        candidate = sample_candidate()
        
        # Test after no_entry_after time (14:30)
        late_time = datetime.now().replace(hour=15, minute=0)
        
        signal = vwap_strategy.should_enter(candidate, breakout_data, late_time)
        
        assert signal is None
    
    def test_calculate_position_size(self, vwap_strategy):
        """Test position sizing."""
        capital = 100000
        price = 2450.0
        
        quantity = vwap_strategy.calculate_position_size(capital, price)
        
        # Position size = 10% of 100000 / 2450 = ~4
        assert quantity > 0
        assert quantity * price <= capital * 0.2  # Max 20% of capital
    
    def test_should_exit_target_hit(self, vwap_strategy, sample_position):
        """Test exit when target is hit."""
        position = sample_position(
            entry_price=2450.0,
            stop_loss=2420.0,
            target=2510.0
        )
        
        # Price above target
        exit_signal = vwap_strategy.should_exit(position, 2520.0, datetime.now().replace(hour=10))
        
        assert exit_signal is not None
        assert "TARGET_HIT" in exit_signal.reason
    
    def test_should_exit_sl_hit(self, vwap_strategy, sample_position):
        """Test exit when stop loss is hit."""
        position = sample_position(
            entry_price=2450.0,
            stop_loss=2420.0,
            target=2510.0
        )
        
        # Price below stop loss
        exit_signal = vwap_strategy.should_exit(position, 2410.0, datetime.now().replace(hour=10))
        
        assert exit_signal is not None
        assert "SL_HIT" in exit_signal.reason
    
    def test_should_exit_time_exit(self, vwap_strategy, sample_position):
        """Test exit at auto-exit time (3:20 PM)."""
        position = sample_position()
        
        # Create exit time that's after the strategy's exit_time config
        exit_time = datetime.now().replace(hour=15, minute=25)
        
        exit_signal = vwap_strategy.should_exit(position, position.entry_price, exit_time)
        
        if exit_signal:
            assert "TIME_EXIT" in exit_signal.reason
    
    def test_min_data_points(self, vwap_strategy):
        """Test minimum data points required."""
        min_points = vwap_strategy.min_data_points
        
        assert min_points >= 20  # At least volume_lookback_candles


# ============================================================================
# VWAP EMA BREAKOUT STRATEGY TESTS
# ============================================================================

class TestVWAPEMABreakoutStrategy:
    """Test VWAP EMA Breakout strategy."""
    
    @pytest.fixture
    def vwap_ema_strategy(self):
        """Create VWAP EMA Breakout strategy."""
        from backend.core.strategies.vwap_ema_breakout import VWAPEMABreakoutStrategy
        from backend.core.config import VWAPEMABreakoutConfig
        
        config = VWAPEMABreakoutConfig(
            min_gain_pct=2.0,
            max_gain_pct=4.0,
            ema_period=20,
            vwap_enabled=True,
            volume_multiplier=1.5,
            volume_lookback=20,
            breakout_previous_high=True,
            stop_loss_pct=0.7,
            target_pct=1.5,
            position_size_pct=0.10
        )
        
        return VWAPEMABreakoutStrategy(config)
    
    def test_check_price_range_in_range(self, vwap_ema_strategy, sample_candidate):
        """Test price range filter with valid gain."""
        candidate = sample_candidate(gain_pct=3.0)  # Within 2-4%
        
        is_valid = vwap_ema_strategy._check_price_range(candidate)
        
        assert bool(is_valid) is True
    
    def test_check_price_range_too_low(self, vwap_ema_strategy, sample_candidate):
        """Test price range filter with gain too low."""
        candidate = sample_candidate(gain_pct=1.5)  # Below 2%
        
        is_valid = vwap_ema_strategy._check_price_range(candidate)
        
        assert bool(is_valid) is False
    
    def test_check_price_range_too_high(self, vwap_ema_strategy, sample_candidate):
        """Test price range filter with gain too high."""
        candidate = sample_candidate(gain_pct=5.0)  # Above 4%
        
        is_valid = vwap_ema_strategy._check_price_range(candidate)
        
        assert bool(is_valid) is False
    
    def test_calculate_indicators_includes_ema_and_vwap(self, vwap_ema_strategy, sample_ohlcv_data):
        """Test indicator calculation includes EMA and VWAP."""
        df = sample_ohlcv_data(num_candles=50)
        
        df_with_indicators = vwap_ema_strategy.calculate_indicators(df)
        
        assert 'ema_20' in df_with_indicators.columns
        assert 'vwap' in df_with_indicators.columns
    
    def test_check_vwap_filter(self, vwap_ema_strategy, sample_ohlcv_data):
        """Test VWAP filter."""
        df = sample_ohlcv_data(num_candles=50, trend="up")
        df_with_indicators = vwap_ema_strategy.calculate_indicators(df)
        
        is_above_vwap = vwap_ema_strategy._check_vwap_filter(df_with_indicators)
        
        assert is_bool_like(is_above_vwap)
    
    def test_check_ema_filter(self, vwap_ema_strategy, sample_ohlcv_data):
        """Test EMA filter."""
        df = sample_ohlcv_data(num_candles=50, trend="up")
        df_with_indicators = vwap_ema_strategy.calculate_indicators(df)
        
        is_above_ema = vwap_ema_strategy._check_ema_filter(df_with_indicators)
        
        assert is_bool_like(is_above_ema)
    
    def test_check_volume_surge(self, vwap_ema_strategy, sample_ohlcv_data):
        """Test volume surge check."""
        df = sample_ohlcv_data(num_candles=50)
        # Add volume spike
        df.loc[df.index[-1], 'volume'] = int(df['volume'].mean() * 2)
        
        is_surge = vwap_ema_strategy._check_volume_surge(df)
        
        assert is_bool_like(is_surge)
    
    def test_check_breakout_previous_high(self, vwap_ema_strategy, sample_ohlcv_data):
        """Test previous high breakout detection."""
        df = sample_ohlcv_data(num_candles=50, trend="up")
        
        # Ensure last candle breaks previous high
        df.loc[df.index[-1], 'close'] = df['high'].iloc[-2] + 0.5
        df.loc[df.index[-1], 'high'] = df.loc[df.index[-1], 'close'] + 0.2
        
        is_breakout = vwap_ema_strategy._check_breakout_previous_high(df)
        
        assert bool(is_breakout) is True
    
    def test_calculate_signals_dataframe(self, vwap_ema_strategy, sample_ohlcv_data):
        """Test signal calculation for entire dataframe."""
        df = sample_ohlcv_data(num_candles=50)
        
        df_with_signals = vwap_ema_strategy.calculate_signals_dataframe(df)
        
        assert 'signal' in df_with_signals.columns
        assert 'vwap' in df_with_signals.columns
        assert 'ema_20' in df_with_signals.columns
    
    def test_min_data_points(self, vwap_ema_strategy):
        """Test minimum data points."""
        min_points = vwap_ema_strategy.min_data_points
        
        assert min_points >= 21  # At least ema_period + 1


# ============================================================================
# BULLISH FLAG STRATEGY TESTS
# ============================================================================

class TestBullishFlagStrategy:
    """Test Bullish Flag strategy."""
    
    @pytest.fixture
    def bullish_flag_strategy(self):
        """Create Bullish Flag strategy."""
        from backend.core.strategies.bullish_flag import BullishFlagStrategy
        from backend.core.config import BullishFlagConfig
        
        config = BullishFlagConfig(
            min_initial_move_pct=2.0,
            pullback_pct_min=0.3,
            pullback_pct_max=1.5,
            pullback_candles_min=2,
            pullback_candles_max=5,
            breakout_threshold_pct=0.1,
            volume_multiplier=1.3,
            stop_loss_pct=0.8,
            target_pct=1.8,
            position_size_pct=0.10
        )
        
        return BullishFlagStrategy(config)
    
    @pytest.fixture
    def flag_pattern_data(self):
        """Create data with bullish flag pattern."""
        np.random.seed(42)
        dates = pd.date_range(end=datetime.now(), periods=20, freq='5min')
        
        # Sideways before pole
        prices1 = [100, 100.2, 100.1, 100.3, 100.2]
        # Strong upward move (flag pole)
        prices2 = [100.5, 101.2, 101.8, 102.5]
        # Pullback (flag consolidation)
        prices3 = [102.2, 102.0, 101.9, 101.8]
        # Sideways consolidation
        prices4 = [101.9, 101.8, 101.9]
        # Breakout
        prices5 = [102.2, 102.6, 102.9, 103.2]
        
        all_prices = prices1 + prices2 + prices3 + prices4 + prices5
        
        df = pd.DataFrame({
            'date': dates,
            'open': all_prices,
            'high': [p + np.random.rand() * 0.3 for p in all_prices],
            'low': [p - np.random.rand() * 0.3 for p in all_prices],
            'close': all_prices,
            'volume': np.random.randint(100000, 300000, 20)
        })
        
        # Volume spike on breakout
        df.loc[df.index[-1], 'volume'] = int(df['volume'].mean() * 1.5)
        
        return df
    
    def test_detect_flag_pattern(self, bullish_flag_strategy, flag_pattern_data):
        """Test flag pattern detection."""
        pattern_found, flag_high, flag_low = bullish_flag_strategy.detect_flag_pattern(flag_pattern_data)
        
        assert is_bool_like(pattern_found)
        if pattern_found:
            assert flag_high is not None
            assert flag_low is not None
            assert flag_high > flag_low
    
    def test_detect_flag_pattern_no_pattern(self, bullish_flag_strategy, sample_ohlcv_data):
        """Test pattern detection with random data (no pattern)."""
        df = sample_ohlcv_data(num_candles=20, trend="sideways")
        
        pattern_found, flag_high, flag_low = bullish_flag_strategy.detect_flag_pattern(df)
        
        assert is_bool_like(pattern_found)
    
    def test_apply_filters(self, bullish_flag_strategy, flag_pattern_data, sample_candidate):
        """Test all bullish flag filters."""
        candidate = sample_candidate(
            current_price=flag_pattern_data['close'].iloc[-1],
            gain_pct=3.2
        )
        
        all_pass = bullish_flag_strategy.apply_filters(candidate, flag_pattern_data)
        
        assert is_bool_like(all_pass)
    
    def test_should_enter(self, bullish_flag_strategy, flag_pattern_data, sample_candidate):
        """Test entry signal generation for bullish flag."""
        candidate = sample_candidate(
            current_price=flag_pattern_data['close'].iloc[-1],
            volume=int(flag_pattern_data['volume'].iloc[-1])
        )
        
        market_time = datetime.now().replace(hour=10, minute=30)
        
        # First apply filters to set _flag_high
        bullish_flag_strategy.apply_filters(candidate, flag_pattern_data)
        
        signal = bullish_flag_strategy.should_enter(candidate, flag_pattern_data, market_time)
        
        # Just verify no exception
        assert signal is None or signal.symbol == candidate.symbol
    
    def test_calculate_position_size(self, bullish_flag_strategy):
        """Test position sizing."""
        capital = 100000
        price = 2450.0
        
        quantity = bullish_flag_strategy.calculate_position_size(capital, price)
        
        assert quantity > 0
    
    def test_min_data_points(self, bullish_flag_strategy):
        """Test minimum data points."""
        min_points = bullish_flag_strategy.min_data_points
        
        assert min_points >= 15  # At least pullback_candles_max + 10


# ============================================================================
# EMA CROSSOVER STRATEGY TESTS
# ============================================================================

class TestEMACrossoverStrategy:
    """Test EMA Crossover strategy."""
    
    @pytest.fixture
    def ema_strategy(self):
        """Create EMA Crossover strategy."""
        from backend.core.strategies.ema_crossover import EMACrossoverStrategy
        
        # Constructor takes fast_period and slow_period
        return EMACrossoverStrategy(fast_period=9, slow_period=21)
    
    def test_calculate_indicators(self, ema_strategy, sample_ohlcv_data):
        """Test EMA indicator calculation."""
        df = sample_ohlcv_data(num_candles=50)
        
        fast_ema, slow_ema = ema_strategy.calculate_indicators(df['close'])
        
        assert fast_ema is not None
        assert slow_ema is not None
    
    def test_calculate_indicators_insufficient_data(self, ema_strategy, sample_ohlcv_data):
        """Test indicator calculation with insufficient data."""
        df = sample_ohlcv_data(num_candles=10)  # Less than slow_period
        
        fast_ema, slow_ema = ema_strategy.calculate_indicators(df['close'])
        
        # Should return None, None for insufficient data
        assert fast_ema is None
        assert slow_ema is None
    
    def test_generate_signal_bullish_crossover(self, ema_strategy):
        """Test bullish crossover signal."""
        # Current: fast EMA above slow EMA
        # Previous: fast EMA below slow EMA
        current = (105.0, 100.0)  # fast > slow
        previous = (98.0, 100.0)  # fast < slow
        
        signal = ema_strategy.generate_signal(current, previous)
        
        assert signal == "BUY"
    
    def test_generate_signal_bearish_crossover(self, ema_strategy):
        """Test bearish crossover signal."""
        # Current: fast EMA below slow EMA
        # Previous: fast EMA above slow EMA
        current = (98.0, 100.0)  # fast < slow
        previous = (102.0, 100.0)  # fast > slow
        
        signal = ema_strategy.generate_signal(current, previous)
        
        assert signal == "SELL"
    
    def test_generate_signal_no_crossover(self, ema_strategy):
        """Test no signal when no crossover."""
        current = (105.0, 100.0)  # fast > slow
        previous = (104.0, 100.0)  # fast > slow
        
        signal = ema_strategy.generate_signal(current, previous)
        
        assert signal is None
    
    def test_generate_signal_with_none_values(self, ema_strategy):
        """Test signal generation with None values."""
        current = (None, 100.0)
        previous = (98.0, 100.0)
        
        signal = ema_strategy.generate_signal(current, previous)
        
        assert signal is None
    
    def test_min_data_points(self, ema_strategy):
        """Test minimum data points requirement."""
        min_points = ema_strategy.min_data_points
        
        # Should be at least the slow EMA period + 2
        assert min_points >= 23
    
    def test_calculate_signals_dataframe(self, ema_strategy, sample_ohlcv_data):
        """Test signal calculation for entire dataframe."""
        df = sample_ohlcv_data(num_candles=50)
        
        result = ema_strategy.calculate_signals_dataframe(df)
        
        assert 'ema_fast' in result.columns
        assert 'ema_slow' in result.columns
        assert 'signal' in result.columns
        assert 'position' in result.columns
    
    def test_get_indicator_series(self, ema_strategy, sample_ohlcv_data):
        """Test getting full indicator series."""
        df = sample_ohlcv_data(num_candles=50)
        
        fast_series, slow_series = ema_strategy.get_indicator_series(df['close'])
        
        assert len(fast_series) == len(df)
        assert len(slow_series) == len(df)


# ============================================================================
# STRATEGY CONFIG TESTS
# ============================================================================

class TestStrategyConfig:
    """Test strategy configuration."""
    
    def test_vwap_breakout_config_defaults(self):
        """Test VWAP Breakout config defaults."""
        from backend.core.config import VWAPBreakoutConfig
        
        config = VWAPBreakoutConfig()
        
        assert config.volume_multiplier > 0
        assert config.vwap_breakout_pct > 0
        assert config.stop_loss_pct > 0
        assert config.target_pct > 0
    
    def test_vwap_ema_config_custom(self):
        """Test VWAP EMA config with custom values."""
        from backend.core.config import VWAPEMABreakoutConfig
        
        config = VWAPEMABreakoutConfig(
            min_gain_pct=1.5,
            max_gain_pct=5.0,
            ema_period=15,
            stop_loss_pct=1.0,
            target_pct=2.0
        )
        
        assert config.min_gain_pct == 1.5
        assert config.max_gain_pct == 5.0
        assert config.ema_period == 15
    
    def test_bullish_flag_config_risk_reward(self):
        """Test Bullish Flag config risk/reward ratio."""
        from backend.core.config import BullishFlagConfig
        
        config = BullishFlagConfig(
            stop_loss_pct=0.8,
            target_pct=1.6
        )
        
        risk_reward = config.target_pct / config.stop_loss_pct
        
        assert risk_reward == 2.0
    
    def test_ema_crossover_config(self):
        """Test EMA Crossover config."""
        from backend.core.config import EMACrossoverConfig
        
        config = EMACrossoverConfig(
            fast_period=5,
            slow_period=15
        )
        
        assert config.fast_period == 5
        assert config.slow_period == 15
        assert config.validate() is True
    
    def test_ema_crossover_config_invalid(self):
        """Test EMA Crossover config validation."""
        from backend.core.config import EMACrossoverConfig
        
        config = EMACrossoverConfig(
            fast_period=21,
            slow_period=9  # Invalid: fast > slow
        )
        
        with pytest.raises(ValueError):
            config.validate()
    
    def test_strategy_config_factory(self):
        """Test StrategyConfigFactory."""
        from backend.core.config import StrategyConfigFactory
        
        # Create different strategy configs
        vwap_config = StrategyConfigFactory.create('vwap_breakout')
        ema_config = StrategyConfigFactory.create('ema_crossover')
        
        assert vwap_config is not None
        assert ema_config is not None
    
    def test_strategy_config_factory_unknown(self):
        """Test StrategyConfigFactory with unknown strategy."""
        from backend.core.config import StrategyConfigFactory
        
        with pytest.raises(ValueError):
            StrategyConfigFactory.create('unknown_strategy')
    
    def test_strategy_config_factory_list(self):
        """Test listing available strategies."""
        from backend.core.config import StrategyConfigFactory
        
        strategies = StrategyConfigFactory.list_strategies()
        
        assert 'vwap_breakout' in strategies
        assert 'ema_crossover' in strategies
        assert 'bullish_flag' in strategies


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
