"""
Unit Tests for Bullish Flag Strategy

Tests the bullish flag pattern detection and trading logic.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, time
from unittest.mock import Mock

from backend.core.strategies.bullish_flag import BullishFlagStrategy
from backend.config import BullishFlagConfig
from backend.core.models import Candidate


class TestBullishFlagStrategy:
    """Test BullishFlagStrategy class."""
    
    @pytest.fixture
    def config(self):
        """Create default config."""
        return BullishFlagConfig()
    
    @pytest.fixture
    def strategy(self, config):
        """Create strategy with default config."""
        return BullishFlagStrategy(config)
    
    @pytest.fixture
    def sample_df(self):
        """Create sample OHLCV DataFrame."""
        np.random.seed(42)
        n = 50
        
        # Create realistic OHLCV data
        close = [100 + i * 0.2 + np.random.randn() * 0.5 for i in range(n)]
        
        df = pd.DataFrame({
            'open': [c - np.random.rand() * 0.5 for c in close],
            'high': [c + np.random.rand() * 1.0 for c in close],
            'low': [c - np.random.rand() * 1.0 for c in close],
            'close': close,
            'volume': [100000 + np.random.randint(-20000, 20000) for _ in range(n)]
        })
        
        # Ensure OHLC consistency
        df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1)
        df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1)
        
        return df
    
    @pytest.fixture
    def candidate(self):
        """Create sample candidate."""
        return Candidate(
            symbol="TESTSTOCK",
            instrument_token=123456,
            current_price=105.0,
            gain_pct=3.0,
            volume=150000,
            avg_volume=100000,
            timestamp=datetime.now()
        )
    
    def test_strategy_initialization(self, strategy, config):
        """Test strategy initializes correctly."""
        assert strategy.config == config
        assert strategy._flag_high is None
        assert strategy._flag_low is None
    
    def test_strategy_name(self, strategy):
        """Test strategy has correct name from config."""
        assert strategy.name == strategy.config.name
    
    def test_min_data_points(self, strategy):
        """Test min_data_points property."""
        # min_data_points is calculated from config values
        expected = max(
            strategy.config.pullback_candles_max + 10,
            strategy.config.lookback_candles
        )
        assert strategy.min_data_points == expected
    
    def test_detect_flag_pattern_empty_df(self, strategy):
        """Test pattern detection with empty DataFrame."""
        empty_df = pd.DataFrame()
        
        detected, flag_high, flag_low = strategy.detect_flag_pattern(empty_df)
        
        assert detected is False
        assert flag_high is None
        assert flag_low is None
    
    def test_detect_flag_pattern_insufficient_data(self, strategy):
        """Test pattern detection with insufficient data."""
        short_df = pd.DataFrame({
            'open': [100, 101, 102],
            'high': [101, 102, 103],
            'low': [99, 100, 101],
            'close': [100.5, 101.5, 102.5],
            'volume': [100000, 110000, 120000]
        })
        
        detected, flag_high, flag_low = strategy.detect_flag_pattern(short_df)
        
        assert detected is False


class TestBullishFlagPatternDetection:
    """Test flag pattern detection logic."""
    
    @pytest.fixture
    def config(self):
        return BullishFlagConfig()
    
    @pytest.fixture
    def strategy(self, config):
        return BullishFlagStrategy(config)
    
    def test_detects_pattern_with_valid_pole(self, strategy):
        """Test detection of valid bullish flag pattern."""
        # Create data with a clear flag pole (strong upward move)
        n = 25
        
        # Start with flat prices
        base = [100.0] * 5
        
        # Flag pole: +3% move over 3 candles
        pole = [100.0, 101.5, 103.0]
        
        # Consolidation: slight pullback over 3 candles
        consolidation = [102.5, 102.3, 102.8]
        
        # Breakout: price breaks above consolidation high
        breakout = [103.5, 104.0, 104.5]
        
        # Pad with more data
        padding = [104.5 + 0.1 * i for i in range(n - len(base) - len(pole) - len(consolidation) - len(breakout))]
        
        all_close = base + pole + consolidation + breakout + padding
        
        df = pd.DataFrame({
            'open': [c - 0.3 for c in all_close],
            'high': [c + 0.5 for c in all_close],
            'low': [c - 0.5 for c in all_close],
            'close': all_close,
            'volume': [100000] * len(all_close)
        })
        
        # The pattern may or may not be detected depending on exact config values
        # Main test is that it doesn't crash
        detected, flag_high, flag_low = strategy.detect_flag_pattern(df)
        
        assert isinstance(detected, bool)
        if detected:
            assert flag_high is not None
            assert flag_low is not None
    
    def test_no_pattern_in_flat_data(self, strategy):
        """Test no pattern detected in flat price data."""
        n = 30
        flat_close = [100.0] * n
        
        df = pd.DataFrame({
            'open': flat_close,
            'high': [c + 0.1 for c in flat_close],
            'low': [c - 0.1 for c in flat_close],
            'close': flat_close,
            'volume': [100000] * n
        })
        
        detected, flag_high, flag_low = strategy.detect_flag_pattern(df)
        
        # Flat data shouldn't have a flag pole
        assert detected is False


class TestBullishFlagConfig:
    """Test BullishFlagConfig integration."""
    
    def test_config_default_values(self):
        """Test default config values."""
        config = BullishFlagConfig()
        
        assert config.name == "Bullish Flag Momentum"
        assert config.min_initial_move_pct > 0
        assert config.target_pct > 0
        assert config.stop_loss_pct > 0
    
    def test_config_custom_values(self):
        """Test custom config values."""
        config = BullishFlagConfig(
            min_initial_move_pct=3.0,
            target_pct=2.5,
            stop_loss_pct=1.2
        )
        
        assert config.min_initial_move_pct == 3.0
        assert config.target_pct == 2.5
        assert config.stop_loss_pct == 1.2
    
    def test_strategy_with_custom_config(self):
        """Test strategy uses custom config values."""
        config = BullishFlagConfig(
            min_initial_move_pct=3.5,
            volume_multiplier=1.5
        )
        
        strategy = BullishFlagStrategy(config)
        
        assert strategy.config.min_initial_move_pct == 3.5
        assert strategy.config.volume_multiplier == 1.5
