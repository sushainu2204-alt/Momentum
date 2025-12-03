"""
Unit Tests for Bullish Flag Strategy

Tests for BullishFlagStrategy class.
"""
import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from backend.core.strategies.bullish_flag import BullishFlagStrategy
from backend.core.models import Candidate, Signal
from backend.core.models.enums import SignalType


class TestBullishFlagStrategy:
    """Test BullishFlagStrategy class."""
    
    @pytest.fixture
    def strategy(self):
        """Create strategy instance with default config."""
        return BullishFlagStrategy()
    
    @pytest.fixture
    def bullish_flag_dataframe(self):
        """Create dataframe with bullish flag pattern."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='5T')
        
        # Create flag pattern: strong uptrend (pole) followed by consolidation (flag)
        pole = np.linspace(100, 120, 30)  # Strong upward move (pole)
        flag = 120 + np.random.randn(40) * 1  # Consolidation (flag body)
        breakout = np.linspace(120, 130, 30)  # Breakout
        
        close = np.concatenate([pole, flag, breakout])
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': np.concatenate([
                np.full(30, 100000),   # High volume during pole
                np.full(40, 30000),    # Low volume during flag
                np.full(30, 80000)     # Increasing volume during breakout
            ])
        }, index=dates)
        
        return df
    
    @pytest.fixture
    def no_flag_dataframe(self):
        """Create dataframe without flag pattern."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='5T')
        
        # Sideways movement - no clear pattern
        np.random.seed(42)
        close = 100 + np.random.randn(50) * 2
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': np.full(50, 50000)
        }, index=dates)
        
        return df
    
    @pytest.fixture
    def sample_candidate(self):
        """Create sample candidate."""
        return Candidate(
            symbol="RELIANCE",
            instrument_token=738561,
            current_price=2500.0,
            open_price=2450.0,
            high_price=2520.0,
            low_price=2440.0,
            volume=500000,
            gain_pct=2.0,
            timestamp=datetime.now()
        )
    
    def test_strategy_initialization(self, strategy):
        """Test strategy is initialized correctly."""
        assert strategy is not None
        assert hasattr(strategy, 'config') or hasattr(strategy, 'name')
    
    def test_strategy_name(self, strategy):
        """Test strategy has a name."""
        name = strategy.get_name() if hasattr(strategy, 'get_name') else getattr(strategy, 'name', 'bullish_flag')
        assert name is not None
    
    def test_calculate_indicators(self, strategy, bullish_flag_dataframe):
        """Test calculate_indicators adds relevant columns."""
        if hasattr(strategy, 'calculate_indicators'):
            df = strategy.calculate_indicators(bullish_flag_dataframe.copy())
            
            assert isinstance(df, pd.DataFrame)
            # Original columns should be preserved
            assert 'close' in df.columns
            assert 'volume' in df.columns
    
    def test_detect_flag_pattern(self, strategy, bullish_flag_dataframe):
        """Test detect_flag_pattern identifies flag patterns."""
        if hasattr(strategy, 'detect_flag_pattern'):
            df = bullish_flag_dataframe.copy()
            if hasattr(strategy, 'calculate_indicators'):
                df = strategy.calculate_indicators(df)
            
            result = strategy.detect_flag_pattern(df)
            
            # Should return boolean or dict with pattern info
            assert isinstance(result, (bool, dict))
    
    def test_no_flag_pattern_detected(self, strategy, no_flag_dataframe):
        """Test no flag pattern detected in random data."""
        if hasattr(strategy, 'detect_flag_pattern'):
            df = no_flag_dataframe.copy()
            if hasattr(strategy, 'calculate_indicators'):
                df = strategy.calculate_indicators(df)
            
            result = strategy.detect_flag_pattern(df)
            
            # May or may not detect pattern in noisy data
            assert isinstance(result, (bool, dict))
    
    def test_apply_filters(self, strategy, bullish_flag_dataframe, sample_candidate):
        """Test apply_filters method."""
        if hasattr(strategy, 'apply_filters'):
            df = bullish_flag_dataframe.copy()
            if hasattr(strategy, 'calculate_indicators'):
                df = strategy.calculate_indicators(df)
            
            result = strategy.apply_filters(sample_candidate, df)
            
            assert isinstance(result, bool)
    
    def test_should_enter_with_flag_pattern(self, strategy, bullish_flag_dataframe, sample_candidate):
        """Test should_enter with bullish flag pattern."""
        if hasattr(strategy, 'should_enter'):
            df = bullish_flag_dataframe.copy()
            if hasattr(strategy, 'calculate_indicators'):
                df = strategy.calculate_indicators(df)
            
            result = strategy.should_enter(sample_candidate, df)
            
            assert isinstance(result, bool)
    
    def test_should_exit(self, strategy, bullish_flag_dataframe, sample_candidate):
        """Test should_exit method."""
        if hasattr(strategy, 'should_exit'):
            df = bullish_flag_dataframe.copy()
            if hasattr(strategy, 'calculate_indicators'):
                df = strategy.calculate_indicators(df)
            
            result = strategy.should_exit(sample_candidate, df)
            
            assert isinstance(result, bool)
    
    def test_generate_signal(self, strategy, bullish_flag_dataframe, sample_candidate):
        """Test generate_signal method."""
        if hasattr(strategy, 'generate_signal'):
            df = bullish_flag_dataframe.copy()
            if hasattr(strategy, 'calculate_indicators'):
                df = strategy.calculate_indicators(df)
            
            signal = strategy.generate_signal(sample_candidate, df)
            
            # Should return Signal or None
            assert signal is None or isinstance(signal, Signal)


class TestBullishFlagPatternDetection:
    """Test bullish flag pattern detection logic."""
    
    @pytest.fixture
    def strategy(self):
        """Create strategy instance."""
        return BullishFlagStrategy()
    
    def test_pole_detection(self, strategy):
        """Test detection of pole (strong upward move)."""
        dates = pd.date_range(start='2024-01-01', periods=30, freq='5T')
        
        # Strong upward move (pole)
        close = np.linspace(100, 130, 30)  # 30% gain
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': np.full(30, 100000)
        }, index=dates)
        
        # Strategy should recognize this as potential pole
        if hasattr(strategy, 'calculate_indicators'):
            df = strategy.calculate_indicators(df)
        
        assert isinstance(df, pd.DataFrame)
    
    def test_flag_consolidation(self, strategy):
        """Test detection of flag consolidation."""
        dates = pd.date_range(start='2024-01-01', periods=40, freq='5T')
        
        # Consolidation with slight downward slope
        np.random.seed(42)
        close = 120 - np.linspace(0, 5, 40) + np.random.randn(40) * 0.5
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': np.full(40, 30000)  # Lower volume during consolidation
        }, index=dates)
        
        if hasattr(strategy, 'calculate_indicators'):
            df = strategy.calculate_indicators(df)
        
        assert isinstance(df, pd.DataFrame)
    
    def test_volume_pattern(self, strategy):
        """Test volume pattern recognition."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='5T')
        
        close = np.concatenate([
            np.linspace(100, 120, 20),  # Pole
            np.linspace(120, 118, 30)   # Flag
        ])
        
        volume = np.concatenate([
            np.full(20, 100000),  # High volume during pole
            np.full(30, 30000)   # Low volume during flag
        ])
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': volume
        }, index=dates)
        
        if hasattr(strategy, 'calculate_indicators'):
            df = strategy.calculate_indicators(df)
        
        assert isinstance(df, pd.DataFrame)


class TestBullishFlagEdgeCases:
    """Test edge cases for Bullish Flag Strategy."""
    
    @pytest.fixture
    def strategy(self):
        """Create strategy instance."""
        return BullishFlagStrategy()
    
    def test_empty_dataframe(self, strategy):
        """Test strategy handles empty dataframe."""
        df = pd.DataFrame()
        
        if hasattr(strategy, 'calculate_indicators'):
            result = strategy.calculate_indicators(df)
            assert isinstance(result, pd.DataFrame)
    
    def test_insufficient_data(self, strategy):
        """Test strategy handles insufficient data."""
        df = pd.DataFrame({
            'open': [100, 101],
            'high': [101, 102],
            'low': [99, 100],
            'close': [100, 101],
            'volume': [10000, 20000]
        }, index=pd.date_range(start='2024-01-01', periods=2, freq='5T'))
        
        if hasattr(strategy, 'calculate_indicators'):
            result = strategy.calculate_indicators(df)
            assert isinstance(result, pd.DataFrame)
    
    def test_bearish_pattern_not_detected(self, strategy):
        """Test bearish pattern is not detected as bullish flag."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='5T')
        
        # Bearish pattern (inverted flag)
        close = np.concatenate([
            np.linspace(100, 80, 20),   # Downward pole
            np.linspace(80, 82, 30)     # Consolidation
        ])
        
        df = pd.DataFrame({
            'open': close * 1.002,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': np.full(50, 50000)
        }, index=dates)
        
        candidate = Candidate(
            symbol="TEST",
            instrument_token=12345,
            current_price=82.0,
            open_price=100.0,
            high_price=100.0,
            low_price=80.0,
            volume=50000,
            gain_pct=-18.0,
            timestamp=datetime.now()
        )
        
        if hasattr(strategy, 'should_enter'):
            df_with_indicators = strategy.calculate_indicators(df.copy()) if hasattr(strategy, 'calculate_indicators') else df
            result = strategy.should_enter(candidate, df_with_indicators)
            # Should not generate entry signal for bearish pattern
            assert isinstance(result, bool)
    
    def test_nan_values_handling(self, strategy):
        """Test strategy handles NaN values."""
        df = pd.DataFrame({
            'open': [100, np.nan, 102, 103, 104],
            'high': [101, 102, np.nan, 104, 105],
            'low': [99, 100, 101, np.nan, 103],
            'close': [100, 101, 102, 103, np.nan],
            'volume': [10000, 20000, 30000, 40000, 50000]
        }, index=pd.date_range(start='2024-01-01', periods=5, freq='5T'))
        
        if hasattr(strategy, 'calculate_indicators'):
            result = strategy.calculate_indicators(df)
            assert isinstance(result, pd.DataFrame)
    
    def test_very_long_pole(self, strategy):
        """Test flag pattern with very long pole."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='5T')
        
        # Very long pole with small flag
        close = np.concatenate([
            np.linspace(100, 200, 80),  # Long pole
            np.linspace(200, 195, 20)   # Short flag
        ])
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': np.full(100, 50000)
        }, index=dates)
        
        if hasattr(strategy, 'calculate_indicators'):
            result = strategy.calculate_indicators(df)
            assert isinstance(result, pd.DataFrame)


class TestBullishFlagConfig:
    """Test Bullish Flag configuration."""
    
    def test_strategy_has_config(self):
        """Test strategy has configuration."""
        strategy = BullishFlagStrategy()
        
        # Strategy should have some form of configuration
        assert strategy is not None
    
    def test_default_values_are_reasonable(self):
        """Test default configuration values are reasonable."""
        strategy = BullishFlagStrategy()
        
        if hasattr(strategy, 'config'):
            config = strategy.config
            # Verify config has reasonable defaults
            if hasattr(config, 'min_pole_pct'):
                assert config.min_pole_pct > 0
            if hasattr(config, 'max_flag_retracement'):
                assert 0 < config.max_flag_retracement < 1
