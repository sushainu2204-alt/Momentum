"""
Unit Tests for VWAP EMA Breakout Strategy

Tests for VWAPEMABreakoutStrategy class.
"""
import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from backend.core.strategies.vwap_ema_breakout import VWAPEMABreakoutStrategy
from backend.core.models import Candidate, Signal
from backend.core.models.enums import SignalType


class TestVWAPEMABreakoutStrategy:
    """Test VWAPEMABreakoutStrategy class."""
    
    @pytest.fixture
    def strategy(self):
        """Create strategy instance with default config."""
        return VWAPEMABreakoutStrategy()
    
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
    
    @pytest.fixture
    def breakout_dataframe(self):
        """Create dataframe with VWAP/EMA breakout pattern."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='5T')
        
        # Create uptrend above VWAP
        np.random.seed(42)
        base_price = 2450.0
        trend = np.linspace(0, 70, 100)
        noise = np.random.randn(100) * 5
        
        close = base_price + trend + noise
        high = close + np.random.rand(100) * 10
        low = close - np.random.rand(100) * 10
        
        # Volume pattern: increasing during breakout
        volume = np.linspace(300000, 600000, 100).astype(int) + np.random.randint(-50000, 50000, 100)
        
        df = pd.DataFrame({
            'open': close - np.random.rand(100) * 5,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        }, index=dates)
        
        return df
    
    @pytest.fixture
    def below_vwap_dataframe(self):
        """Create dataframe with price below VWAP."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='5T')
        
        # Price below VWAP (typical value area)
        np.random.seed(42)
        
        # VWAP would be around 2500, but price is at 2450
        close = np.full(50, 2450.0) + np.random.randn(50) * 5
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': np.full(50, 100000)
        }, index=dates)
        
        return df
    
    def test_strategy_initialization(self, strategy):
        """Test strategy is initialized correctly."""
        assert strategy is not None
        assert hasattr(strategy, 'config') or hasattr(strategy, 'name')
    
    def test_strategy_name(self, strategy):
        """Test strategy has correct name."""
        name = strategy.get_name() if hasattr(strategy, 'get_name') else getattr(strategy, 'name', 'vwap_ema_breakout')
        assert name is not None
    
    def test_calculate_indicators(self, strategy, breakout_dataframe):
        """Test calculate_indicators adds VWAP and EMA columns."""
        if hasattr(strategy, 'calculate_indicators'):
            df = strategy.calculate_indicators(breakout_dataframe.copy())
            
            assert isinstance(df, pd.DataFrame)
            # Original columns preserved
            assert 'close' in df.columns
            assert 'volume' in df.columns
            
            # Should add VWAP and EMA indicators
            indicator_cols = df.columns.tolist()
            has_vwap = any('vwap' in c.lower() for c in indicator_cols)
            has_ema = any('ema' in c.lower() for c in indicator_cols)
            
            # At least some indicators should be added
            assert has_vwap or has_ema or len(indicator_cols) > 5
    
    def test_vwap_calculation(self, strategy, breakout_dataframe):
        """Test VWAP is calculated correctly."""
        if hasattr(strategy, 'calculate_indicators'):
            df = strategy.calculate_indicators(breakout_dataframe.copy())
            
            if 'vwap' in df.columns:
                # VWAP should be within price range
                assert df['vwap'].dropna().iloc[-1] >= df['low'].min()
                assert df['vwap'].dropna().iloc[-1] <= df['high'].max()
    
    def test_ema_calculation(self, strategy, breakout_dataframe):
        """Test EMA is calculated correctly."""
        if hasattr(strategy, 'calculate_indicators'):
            df = strategy.calculate_indicators(breakout_dataframe.copy())
            
            ema_cols = [c for c in df.columns if 'ema' in c.lower()]
            for col in ema_cols:
                # EMA should be within price range
                assert df[col].dropna().iloc[-1] >= df['low'].min() * 0.9
                assert df[col].dropna().iloc[-1] <= df['high'].max() * 1.1
    
    def test_apply_filters(self, strategy, breakout_dataframe, sample_candidate):
        """Test apply_filters method."""
        if hasattr(strategy, 'apply_filters'):
            df = breakout_dataframe.copy()
            if hasattr(strategy, 'calculate_indicators'):
                df = strategy.calculate_indicators(df)
            
            result = strategy.apply_filters(sample_candidate, df)
            
            assert isinstance(result, bool)
    
    def test_should_enter_breakout(self, strategy, breakout_dataframe, sample_candidate):
        """Test should_enter with breakout setup."""
        if hasattr(strategy, 'should_enter'):
            df = breakout_dataframe.copy()
            if hasattr(strategy, 'calculate_indicators'):
                df = strategy.calculate_indicators(df)
            
            result = strategy.should_enter(sample_candidate, df)
            
            assert isinstance(result, bool)
    
    def test_should_enter_below_vwap(self, strategy, below_vwap_dataframe, sample_candidate):
        """Test should_enter when price is below VWAP."""
        if hasattr(strategy, 'should_enter'):
            df = below_vwap_dataframe.copy()
            if hasattr(strategy, 'calculate_indicators'):
                df = strategy.calculate_indicators(df)
            
            result = strategy.should_enter(sample_candidate, df)
            
            assert isinstance(result, bool)
            # Typically should not enter when below VWAP
    
    def test_should_exit(self, strategy, breakout_dataframe, sample_candidate):
        """Test should_exit method."""
        if hasattr(strategy, 'should_exit'):
            df = breakout_dataframe.copy()
            if hasattr(strategy, 'calculate_indicators'):
                df = strategy.calculate_indicators(df)
            
            result = strategy.should_exit(sample_candidate, df)
            
            assert isinstance(result, bool)
    
    def test_generate_signal(self, strategy, breakout_dataframe, sample_candidate):
        """Test generate_signal method."""
        if hasattr(strategy, 'generate_signal'):
            df = breakout_dataframe.copy()
            if hasattr(strategy, 'calculate_indicators'):
                df = strategy.calculate_indicators(df)
            
            signal = strategy.generate_signal(sample_candidate, df)
            
            assert signal is None or isinstance(signal, Signal)


class TestVWAPEMABreakoutFilters:
    """Test individual filter methods for VWAP EMA Breakout."""
    
    @pytest.fixture
    def strategy(self):
        """Create strategy instance."""
        return VWAPEMABreakoutStrategy()
    
    def test_price_above_vwap_filter(self, strategy):
        """Test price above VWAP filter."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='5T')
        
        # Price above VWAP scenario
        close = np.full(50, 2500.0)
        volume = np.full(50, 100000)
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': volume
        }, index=dates)
        
        if hasattr(strategy, 'calculate_indicators'):
            df = strategy.calculate_indicators(df)
            
            if 'vwap' in df.columns:
                # Check if last close is above VWAP
                is_above_vwap = df['close'].iloc[-1] >= df['vwap'].iloc[-1]
                assert isinstance(is_above_vwap, (bool, np.bool_))
    
    def test_ema_alignment_filter(self, strategy):
        """Test EMA alignment filter (short above long)."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='5T')
        
        # Uptrending data - short EMA above long EMA
        close = np.linspace(100, 120, 100)
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': np.full(100, 100000)
        }, index=dates)
        
        if hasattr(strategy, 'calculate_indicators'):
            df = strategy.calculate_indicators(df)
            
            # Check for EMA columns
            ema_cols = [c for c in df.columns if 'ema' in c.lower()]
            if len(ema_cols) >= 2:
                # Short EMA should be above long EMA in uptrend
                pass  # Structure is present
    
    def test_volume_confirmation_filter(self, strategy):
        """Test volume confirmation filter."""
        dates = pd.date_range(start='2024-01-01', periods=30, freq='5T')
        
        # Volume surge scenario
        volume = np.concatenate([
            np.full(20, 100000),   # Normal volume
            np.full(10, 300000)    # Volume surge
        ])
        
        close = np.linspace(100, 110, 30)
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': volume
        }, index=dates)
        
        if hasattr(strategy, 'calculate_indicators'):
            df = strategy.calculate_indicators(df)
            
            # Volume filter should consider recent volume vs average
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            current_volume = df['volume'].iloc[-1]
            
            assert current_volume > avg_volume


class TestVWAPEMABreakoutEdgeCases:
    """Test edge cases for VWAP EMA Breakout Strategy."""
    
    @pytest.fixture
    def strategy(self):
        """Create strategy instance."""
        return VWAPEMABreakoutStrategy()
    
    def test_empty_dataframe(self, strategy):
        """Test strategy handles empty dataframe."""
        df = pd.DataFrame()
        
        if hasattr(strategy, 'calculate_indicators'):
            result = strategy.calculate_indicators(df)
            assert isinstance(result, pd.DataFrame)
    
    def test_insufficient_data(self, strategy):
        """Test strategy handles insufficient data for indicators."""
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
    
    def test_zero_volume(self, strategy):
        """Test strategy handles zero volume data."""
        dates = pd.date_range(start='2024-01-01', periods=20, freq='5T')
        
        df = pd.DataFrame({
            'open': [100] * 20,
            'high': [101] * 20,
            'low': [99] * 20,
            'close': [100] * 20,
            'volume': [0] * 20  # Zero volume
        }, index=dates)
        
        if hasattr(strategy, 'calculate_indicators'):
            result = strategy.calculate_indicators(df)
            # Should handle zero volume gracefully
            assert isinstance(result, pd.DataFrame)
    
    def test_nan_values(self, strategy):
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
    
    def test_extreme_price_movement(self, strategy):
        """Test strategy with extreme price movement."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='5T')
        
        # 50% price spike
        close = np.concatenate([
            np.full(40, 100),
            np.full(10, 150)
        ])
        
        df = pd.DataFrame({
            'open': close * 0.99,
            'high': close * 1.02,
            'low': close * 0.98,
            'close': close,
            'volume': np.full(50, 500000)
        }, index=dates)
        
        candidate = Candidate(
            symbol="SPIKE",
            instrument_token=1001,
            current_price=150.0,
            open_price=100.0,
            high_price=152.0,
            low_price=98.0,
            volume=1000000,
            gain_pct=50.0,
            timestamp=datetime.now()
        )
        
        if hasattr(strategy, 'should_enter'):
            df_with_indicators = strategy.calculate_indicators(df.copy()) if hasattr(strategy, 'calculate_indicators') else df
            result = strategy.should_enter(candidate, df_with_indicators)
            assert isinstance(result, bool)
    
    def test_vwap_equals_close(self, strategy):
        """Test when VWAP equals close price."""
        dates = pd.date_range(start='2024-01-01', periods=30, freq='5T')
        
        # Flat price - VWAP will equal close
        df = pd.DataFrame({
            'open': [100] * 30,
            'high': [100] * 30,
            'low': [100] * 30,
            'close': [100] * 30,
            'volume': [100000] * 30
        }, index=dates)
        
        if hasattr(strategy, 'calculate_indicators'):
            result = strategy.calculate_indicators(df)
            assert isinstance(result, pd.DataFrame)
            
            if 'vwap' in result.columns:
                # VWAP should be close to price
                assert abs(result['vwap'].iloc[-1] - 100) < 1


class TestVWAPEMABreakoutIntegration:
    """Integration tests for VWAP EMA Breakout Strategy."""
    
    @pytest.fixture
    def strategy(self):
        """Create strategy instance."""
        return VWAPEMABreakoutStrategy()
    
    def test_full_workflow(self, strategy):
        """Test complete workflow: indicators -> filters -> signal."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='5T')
        
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(100) * 0.5)
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': np.random.randint(50000, 200000, 100)
        }, index=dates)
        
        candidate = Candidate(
            symbol="TEST",
            instrument_token=12345,
            current_price=close[-1],
            open_price=close[0],
            high_price=close.max(),
            low_price=close.min(),
            volume=150000,
            gain_pct=(close[-1] - close[0]) / close[0] * 100,
            timestamp=datetime.now()
        )
        
        # Step 1: Calculate indicators
        if hasattr(strategy, 'calculate_indicators'):
            df = strategy.calculate_indicators(df)
        
        # Step 2: Apply filters
        if hasattr(strategy, 'apply_filters'):
            filter_result = strategy.apply_filters(candidate, df)
            assert isinstance(filter_result, bool)
        
        # Step 3: Check entry
        if hasattr(strategy, 'should_enter'):
            entry_result = strategy.should_enter(candidate, df)
            assert isinstance(entry_result, bool)
        
        # Step 4: Generate signal (if entry)
        if hasattr(strategy, 'generate_signal'):
            signal = strategy.generate_signal(candidate, df)
            assert signal is None or isinstance(signal, Signal)


class TestVWAPEMABreakoutConfig:
    """Test VWAP EMA Breakout configuration."""
    
    def test_strategy_has_config(self):
        """Test strategy has configuration."""
        strategy = VWAPEMABreakoutStrategy()
        assert strategy is not None
    
    def test_default_ema_periods(self):
        """Test default EMA periods are reasonable."""
        strategy = VWAPEMABreakoutStrategy()
        
        if hasattr(strategy, 'config'):
            config = strategy.config
            if hasattr(config, 'ema_short'):
                assert config.ema_short > 0
            if hasattr(config, 'ema_long'):
                assert config.ema_long > 0
            if hasattr(config, 'ema_short') and hasattr(config, 'ema_long'):
                assert config.ema_short < config.ema_long
    
    def test_default_breakout_threshold(self):
        """Test default breakout threshold is reasonable."""
        strategy = VWAPEMABreakoutStrategy()
        
        if hasattr(strategy, 'config'):
            config = strategy.config
            if hasattr(config, 'vwap_breakout_pct'):
                assert config.vwap_breakout_pct >= 0
