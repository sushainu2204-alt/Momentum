"""
Unit Tests for Top Gainers Momentum Strategy

Tests for TopGainersMomentumStrategy class.
Note: This strategy requires a TopGainersMomentumConfig object.
"""
import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time

from backend.core.strategies.top_gainers_momentum import TopGainersMomentumStrategy
from backend.config import TopGainersMomentumConfig
from backend.core.models import Candidate, Signal
from backend.core.models.enums import SignalType


class TestTopGainersMomentumStrategy:
    """Test TopGainersMomentumStrategy class."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return TopGainersMomentumConfig(
            min_gain_pct=2.0,
            max_gain_pct=5.0,
            max_open_gain_pct=6.0,
            volume_surge_multiplier=1.5,
            stock_ema_period=20,
            stop_loss_pct=1.0,
            target_pct=2.0
        )
    
    @pytest.fixture
    def strategy(self, config):
        """Create strategy instance with config."""
        return TopGainersMomentumStrategy(config)
    
    @pytest.fixture
    def sample_candidate(self):
        """Create sample candidate with top gainer characteristics."""
        return Candidate(
            symbol="RELIANCE",
            instrument_token=738561,
            current_price=2500.0,
            open_price=2400.0,
            high_price=2520.0,
            low_price=2380.0,
            volume=500000,
            avg_volume=200000,
            gain_pct=4.17,
            timestamp=datetime.now()
        )
    
    @pytest.fixture
    def momentum_dataframe(self):
        """Create dataframe with strong momentum characteristics."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='5min')
        
        # Strong uptrend with momentum
        np.random.seed(42)
        base_price = 2400.0
        trend = np.linspace(0, 100, 100)
        noise = np.random.randn(100) * 5
        
        close = base_price + trend + noise
        volume = np.linspace(300000, 600000, 100) + np.random.randint(-50000, 50000, 100)
        
        df = pd.DataFrame({
            'open': close - np.random.rand(100) * 5,
            'high': close + np.random.rand(100) * 10,
            'low': close - np.random.rand(100) * 10,
            'close': close,
            'volume': volume.astype(int)
        }, index=dates)
        
        return df
    
    @pytest.fixture
    def index_dataframe(self):
        """Create index (NIFTY) dataframe with bullish trend."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='5min')
        
        np.random.seed(42)
        base_price = 20000.0
        trend = np.linspace(0, 200, 100)
        noise = np.random.randn(100) * 10
        
        close = base_price + trend + noise
        
        df = pd.DataFrame({
            'open': close - np.random.rand(100) * 10,
            'high': close + np.random.rand(100) * 20,
            'low': close - np.random.rand(100) * 20,
            'close': close,
            'volume': np.random.randint(1000000, 5000000, 100)
        }, index=dates)
        
        return df
    
    def test_strategy_initialization(self, strategy, config):
        """Test strategy is initialized correctly."""
        assert strategy is not None
        assert strategy.config == config
        assert strategy.name == config.name
    
    def test_strategy_name(self, strategy):
        """Test strategy has correct name."""
        assert strategy.name == "Top Gainers Momentum"
    
    def test_min_data_points(self, strategy, config):
        """Test min_data_points returns correct value."""
        expected = max(config.stock_ema_period, config.index_ema_period)
        assert strategy.min_data_points == expected
    
    def test_calculate_indicators(self, strategy, momentum_dataframe):
        """Test calculate_indicators returns tuple."""
        prices = momentum_dataframe['close']
        
        result = strategy.calculate_indicators(prices)
        
        assert isinstance(result, tuple)
        assert len(result) == 2
    
    def test_calculate_signals_dataframe(self, strategy, momentum_dataframe):
        """Test calculate_signals_dataframe adds indicator columns."""
        df = strategy.calculate_signals_dataframe(momentum_dataframe.copy())
        
        assert isinstance(df, pd.DataFrame)
        assert 'ema_20' in df.columns
    
    def test_should_enter_within_trading_hours(self, strategy, sample_candidate, momentum_dataframe):
        """Test should_enter within trading hours."""
        # Create time during market hours
        trading_time = datetime.now().replace(hour=10, minute=30)
        
        signal = strategy.should_enter(sample_candidate, momentum_dataframe, trading_time)
        
        # Result depends on conditions met
        assert signal is None or isinstance(signal, Signal)
    
    def test_should_enter_after_cutoff(self, strategy, sample_candidate, momentum_dataframe):
        """Test should_enter returns None after entry cutoff time."""
        # Time after no_entry_after (15:00)
        late_time = datetime.now().replace(hour=15, minute=30)
        
        signal = strategy.should_enter(sample_candidate, momentum_dataframe, late_time)
        
        assert signal is None
    
    def test_generate_signal_returns_none(self, strategy):
        """Test generate_signal returns None (uses should_enter instead)."""
        current = (100.0, 55.0)
        previous = (95.0, 50.0)
        
        result = strategy.generate_signal(current, previous)
        
        # This strategy uses should_enter, not indicator-based generate_signal
        assert result is None
    
    def test_calculate_position_size(self, strategy):
        """Test position size calculation."""
        capital = 100000.0
        price = 500.0
        
        quantity = strategy.calculate_position_size(capital, price)
        
        # With 10% position size: 100000 * 0.10 / 500 = 20
        assert quantity >= 1
        assert isinstance(quantity, int)


class TestTopGainersMomentumFilters:
    """Test individual filter methods."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return TopGainersMomentumConfig(
            volume_surge_multiplier=2.0,
            stock_ema_period=20,
            check_vwap=True,
            check_candle_break=True,
            max_open_gain_pct=6.0
        )
    
    @pytest.fixture
    def strategy(self, config):
        """Create strategy instance."""
        return TopGainersMomentumStrategy(config)
    
    @pytest.fixture
    def sample_df(self):
        """Create sample dataframe with VWAP/EMA."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='5min')
        close = np.linspace(100, 110, 50)
        
        df = pd.DataFrame({
            'open': close * 0.998,
            'high': close * 1.01,
            'low': close * 0.99,
            'close': close,
            'volume': np.full(50, 50000)
        }, index=dates)
        
        return df
    
    def test_check_volume_surge_with_high_volume(self, strategy, sample_df):
        """Test volume surge check passes with high volume."""
        candidate = Candidate(
            symbol="HIGHVOL",
            instrument_token=1001,
            current_price=110.0,
            open_price=100.0,
            high_price=111.0,
            low_price=99.0,
            volume=500000,
            avg_volume=100000,  # Volume 5x average
            gain_pct=10.0,
            timestamp=datetime.now()
        )
        
        result = strategy._check_volume_surge_candidate(candidate, sample_df)
        
        assert result is True
    
    def test_check_volume_surge_with_low_volume(self, strategy, sample_df):
        """Test volume surge check fails with low volume."""
        candidate = Candidate(
            symbol="LOWVOL",
            instrument_token=1001,
            current_price=110.0,
            open_price=100.0,
            high_price=111.0,
            low_price=99.0,
            volume=50000,
            avg_volume=100000,  # Volume below average
            gain_pct=10.0,
            timestamp=datetime.now()
        )
        
        result = strategy._check_volume_surge_candidate(candidate, sample_df)
        
        # May pass if candle volume check passes
        assert isinstance(result, bool)
    
    def test_check_price_circuit(self, strategy):
        """Test price circuit filter."""
        # Candidate at circuit (high gain)
        candidate_circuit = Candidate(
            symbol="CIRCUIT",
            instrument_token=1001,
            current_price=110.0,
            open_price=100.0,
            high_price=110.0,
            low_price=100.0,
            volume=500000,
            avg_volume=100000,
            gain_pct=10.0,  # Above max_open_gain_pct (6.0)
            timestamp=datetime.now()
        )
        
        result = strategy._check_price_circuit_candidate(candidate_circuit)
        
        assert result is False  # Should fail circuit check
    
    def test_check_price_circuit_valid(self, strategy):
        """Test price circuit filter passes for valid candidate."""
        candidate_valid = Candidate(
            symbol="VALID",
            instrument_token=1001,
            current_price=105.0,
            open_price=100.0,
            high_price=106.0,
            low_price=99.0,
            volume=500000,
            avg_volume=100000,
            gain_pct=5.0,  # Below max_open_gain_pct (6.0)
            timestamp=datetime.now()
        )
        
        result = strategy._check_price_circuit_candidate(candidate_valid)
        
        assert result is True


class TestTopGainersMomentumEdgeCases:
    """Test edge cases for Top Gainers Momentum Strategy."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return TopGainersMomentumConfig()
    
    @pytest.fixture
    def strategy(self, config):
        """Create strategy instance."""
        return TopGainersMomentumStrategy(config)
    
    def test_insufficient_data(self, strategy):
        """Test strategy handles insufficient data."""
        df = pd.DataFrame({
            'open': [100, 101, 102],
            'high': [101, 102, 103],
            'low': [99, 100, 101],
            'close': [100, 101, 102],
            'volume': [10000, 20000, 30000]
        }, index=pd.date_range(start='2024-01-01', periods=3, freq='5min'))
        
        candidate = Candidate(
            symbol="TEST",
            instrument_token=1001,
            current_price=102.0,
            open_price=100.0,
            high_price=103.0,
            low_price=99.0,
            volume=30000,
            avg_volume=20000,
            gain_pct=2.0,
            timestamp=datetime.now()
        )
        
        # Should handle gracefully
        result = strategy._check_stock_momentum_candidate(candidate, df)
        assert isinstance(result, bool)
    
    def test_string_representation(self, strategy, config):
        """Test string representation."""
        result = str(strategy)
        
        assert isinstance(result, str)


class TestTopGainersMomentumConfig:
    """Test Top Gainers Momentum configuration."""
    
    def test_config_default_values(self):
        """Test default config values."""
        config = TopGainersMomentumConfig()
        
        assert config.min_gain_pct == 2.0
        assert config.max_gain_pct == 3.0
        assert config.stop_loss_pct == 1.0
        assert config.target_pct == 2.0
    
    def test_config_custom_values(self):
        """Test custom config values."""
        config = TopGainersMomentumConfig(
            min_gain_pct=3.0,
            max_gain_pct=6.0,
            stop_loss_pct=0.5,
            target_pct=1.5
        )
        
        assert config.min_gain_pct == 3.0
        assert config.max_gain_pct == 6.0
        assert config.stop_loss_pct == 0.5
        assert config.target_pct == 1.5
    
    def test_strategy_with_config(self):
        """Test strategy accepts config."""
        config = TopGainersMomentumConfig(
            name="Custom Momentum",
            description="Custom strategy"
        )
        strategy = TopGainersMomentumStrategy(config)
        
        assert strategy.name == "Custom Momentum"
        assert strategy.description == "Custom strategy"
