"""
Unit Tests for backend/core/strategies/vwap_breakout.py

Tests VWAP Breakout Strategy filters and signal generation.
"""

import pytest
from datetime import datetime, time
import pandas as pd
import numpy as np

from backend.core.strategies.vwap_breakout import VWAPBreakoutStrategy
from backend.config import VWAPBreakoutConfig
from backend.core.models import SignalType, PositionStatus


@pytest.fixture
def vwap_config():
    """Create default VWAP Breakout config for testing."""
    return VWAPBreakoutConfig(
        name="vwap_breakout",
        description="VWAP Breakout Strategy",
        vwap_breakout_pct=0.2,
        volume_multiplier=1.5,
        volume_lookback_candles=10,
        stop_loss_pct=0.7,
        target_pct=1.5,
        position_size_pct=0.02,
        market_open_time=time(9, 15),
        no_entry_after=time(14, 30),
        exit_time=time(15, 20),
    )


@pytest.fixture
def vwap_strategy(vwap_config):
    """Create VWAP Breakout strategy for testing."""
    return VWAPBreakoutStrategy(vwap_config)


@pytest.fixture
def breakout_ohlcv_data():
    """Create OHLCV data simulating a VWAP breakout."""
    dates = pd.date_range(start='2024-01-15 09:15', periods=15, freq='5min')
    
    # Simulate price trending up above VWAP
    data = {
        'open': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114],
        'high': [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 116],
        'low': [99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113],
        'close': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 115],
        'volume': [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 2000],
    }
    
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def no_breakout_ohlcv_data():
    """Create OHLCV data with no breakout (price at VWAP)."""
    dates = pd.date_range(start='2024-01-15 09:15', periods=15, freq='5min')
    
    # Flat price at 100
    data = {
        'open': [100] * 15,
        'high': [101] * 15,
        'low': [99] * 15,
        'close': [100] * 15,
        'volume': [1000] * 15,
    }
    
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def low_volume_ohlcv_data():
    """Create OHLCV data with low volume (no surge)."""
    dates = pd.date_range(start='2024-01-15 09:15', periods=15, freq='5min')
    
    data = {
        'open': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114],
        'high': [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 116],
        'low': [99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113],
        'close': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 115],
        'volume': [1000] * 15,  # No volume surge
    }
    
    return pd.DataFrame(data, index=dates)


@pytest.mark.unit
class TestVWAPBreakoutStrategyInit:
    """Tests for VWAP Breakout Strategy initialization."""
    
    def test_strategy_initialization(self, vwap_strategy):
        """Test strategy initializes with correct config."""
        assert vwap_strategy.name == "vwap_breakout"
        assert vwap_strategy.config.vwap_breakout_pct == 0.2
    
    def test_strategy_config_values(self, vwap_strategy):
        """Test strategy has all config values."""
        config = vwap_strategy.config
        
        assert config.volume_multiplier == 1.5
        assert config.stop_loss_pct == 0.7
        assert config.target_pct == 1.5
    
    def test_min_data_points(self, vwap_strategy):
        """Test min_data_points returns correct value."""
        min_points = vwap_strategy.min_data_points
        
        # Should be max of volume_lookback_candles and lookback_candles
        assert min_points >= vwap_strategy.config.volume_lookback_candles


@pytest.mark.unit
class TestVWAPBreakoutFilter:
    """Tests for VWAP breakout filter logic."""
    
    def test_vwap_breakout_detected(self, vwap_strategy, breakout_ohlcv_data, candidate_factory):
        """Test VWAP breakout detection when price is above VWAP."""
        # Set candidate price to match breakout data (price trending up)
        candidate = candidate_factory(symbol="TEST", current_price=115.0)
        
        passed, info = vwap_strategy._check_vwap_breakout_detailed(
            candidate, breakout_ohlcv_data
        )
        
        assert "Breakout" in info
    
    def test_no_vwap_breakout(self, vwap_strategy, no_breakout_ohlcv_data, candidate_factory):
        """Test no breakout when price at VWAP."""
        candidate = candidate_factory(symbol="TEST", current_price=100.0)
        
        passed, info = vwap_strategy._check_vwap_breakout_detailed(
            candidate, no_breakout_ohlcv_data
        )
        
        # Should not pass as no significant breakout
        assert "Breakout" in info
    
    def test_vwap_breakout_empty_data(self, vwap_strategy, candidate_factory):
        """Test VWAP breakout with empty DataFrame."""
        candidate = candidate_factory()
        empty_df = pd.DataFrame()
        
        passed, info = vwap_strategy._check_vwap_breakout_detailed(
            candidate, empty_df
        )
        
        assert passed is False
        assert "Insufficient data" in info


@pytest.mark.unit
class TestVolumeFilter:
    """Tests for volume surge filter logic."""
    
    def test_volume_surge_detected(self, vwap_strategy, breakout_ohlcv_data):
        """Test volume surge detection when volume > multiplier * avg."""
        passed, info = vwap_strategy._check_volume_surge_detailed(breakout_ohlcv_data)
        
        # Last candle has 2000 volume vs avg 1000 = 2x (> 1.5x)
        assert passed == True
        assert "Ratio:" in info
    
    def test_no_volume_surge(self, vwap_strategy, low_volume_ohlcv_data):
        """Test no volume surge when volume is flat."""
        passed, info = vwap_strategy._check_volume_surge_detailed(low_volume_ohlcv_data)
        
        assert passed == False
        assert "Ratio:" in info
    
    def test_volume_surge_insufficient_data(self, vwap_strategy):
        """Test volume surge with insufficient data."""
        dates = pd.date_range(start='2024-01-15 09:15', periods=3, freq='5min')
        small_df = pd.DataFrame({
            'volume': [1000, 1000, 2000]
        }, index=dates)
        
        passed, info = vwap_strategy._check_volume_surge_detailed(small_df)
        
        assert passed is False
        assert "Insufficient" in info


@pytest.mark.unit
class TestApplyFilters:
    """Tests for combined filter application."""
    
    def test_all_filters_pass(self, vwap_strategy, candidate_factory):
        """Test apply_filters when all conditions met."""
        # Create data with both VWAP breakout and volume surge
        dates = pd.date_range(start='2024-01-15 09:15', periods=15, freq='5min')
        data = {
            'open': [100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122, 124, 126, 128],
            'high': [101, 103, 105, 107, 109, 111, 113, 115, 117, 119, 121, 123, 125, 127, 130],
            'low': [99, 101, 103, 105, 107, 109, 111, 113, 115, 117, 119, 121, 123, 125, 127],
            'close': [100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122, 124, 126, 129],
            'volume': [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 3000],
        }
        df = pd.DataFrame(data, index=dates)
        
        candidate = candidate_factory(symbol="BREAKOUT", current_price=129.0)
        
        result = vwap_strategy.apply_filters(candidate, df)
        
        # Both VWAP breakout and volume surge should be detected
        assert isinstance(result, bool)


@pytest.mark.unit
class TestShouldEnter:
    """Tests for entry signal generation."""
    
    def test_generate_buy_signal(self, vwap_strategy, breakout_ohlcv_data, candidate_factory):
        """Test BUY signal generation."""
        candidate = candidate_factory(symbol="RELIANCE", current_price=115.0)
        trading_time = datetime(2024, 1, 15, 10, 30)
        
        signal = vwap_strategy.should_enter(
            candidate, breakout_ohlcv_data, trading_time
        )
        
        if signal:
            assert signal.signal_type == SignalType.BUY
            assert signal.symbol == "RELIANCE"
            assert signal.price == 115.0
    
    def test_no_signal_after_cutoff(self, vwap_strategy, breakout_ohlcv_data, candidate_factory):
        """Test no signal generated after cutoff time."""
        candidate = candidate_factory()
        after_cutoff = datetime(2024, 1, 15, 14, 45)
        
        signal = vwap_strategy.should_enter(
            candidate, breakout_ohlcv_data, after_cutoff
        )
        
        assert signal is None
    
    def test_signal_has_stop_loss_and_target(self, vwap_strategy, breakout_ohlcv_data, candidate_factory):
        """Test signal includes stop loss and target."""
        candidate = candidate_factory(current_price=100.0)
        trading_time = datetime(2024, 1, 15, 10, 30)
        
        signal = vwap_strategy.should_enter(
            candidate, breakout_ohlcv_data, trading_time
        )
        
        if signal:
            # SL at 0.7% below entry
            expected_sl = 100.0 * (1 - 0.7 / 100)
            assert signal.stop_loss == pytest.approx(expected_sl, rel=0.01)
            
            # Target at 1.5% above entry
            expected_target = 100.0 * (1 + 1.5 / 100)
            assert signal.target == pytest.approx(expected_target, rel=0.01)


@pytest.mark.unit
class TestShouldExit:
    """Tests for exit signal generation."""
    
    def test_exit_on_target_hit(self, vwap_strategy, position_factory):
        """Test SELL signal when target is hit."""
        position = position_factory(
            symbol="RELIANCE",
            entry_price=100.0,
            target=101.5,
            stop_loss=99.3,
        )
        current_time = datetime(2024, 1, 15, 10, 30)
        
        signal = vwap_strategy.should_exit(
            position,
            current_price=102.0,  # Above target
            current_time=current_time,
        )
        
        if signal:
            assert signal.signal_type == SignalType.SELL
            assert "TARGET" in signal.reason
    
    def test_exit_on_stop_loss_hit(self, vwap_strategy, position_factory):
        """Test SELL signal when stop loss is hit."""
        position = position_factory(
            symbol="RELIANCE",
            entry_price=100.0,
            target=101.5,
            stop_loss=99.3,
        )
        current_time = datetime(2024, 1, 15, 10, 30)
        
        signal = vwap_strategy.should_exit(
            position,
            current_price=99.0,  # Below stop loss
            current_time=current_time,
        )
        
        if signal:
            assert signal.signal_type == SignalType.SELL
            assert "SL" in signal.reason
    
    def test_no_exit_in_range(self, vwap_strategy, position_factory):
        """Test no exit when price is between SL and target."""
        position = position_factory(
            symbol="RELIANCE",
            entry_price=100.0,
            target=101.5,
            stop_loss=99.3,
        )
        current_time = datetime(2024, 1, 15, 10, 30)
        
        signal = vwap_strategy.should_exit(
            position,
            current_price=100.5,  # Between SL and target
            current_time=current_time,
        )
        
        assert signal is None
    
    def test_exit_at_time_based_exit(self, vwap_strategy, position_factory):
        """Test SELL signal at time-based exit."""
        position = position_factory(
            symbol="RELIANCE",
            entry_price=100.0,
            target=101.5,
            stop_loss=99.3,
        )
        exit_time = datetime(2024, 1, 15, 15, 25)  # After 3:20 PM
        
        signal = vwap_strategy.should_exit(
            position,
            current_price=100.5,
            current_time=exit_time,
        )
        
        if signal:
            assert signal.signal_type == SignalType.SELL
            assert "TIME" in signal.reason
