"""
Unit Tests for backend/core/strategies/base.py

Tests BaseStrategy abstract class behavior.
"""

import pytest
from datetime import datetime, time
from dataclasses import dataclass
from typing import Any, Optional
import pandas as pd

from backend.core.strategies.base import BaseStrategy
from backend.config import BaseStrategyConfig


@dataclass
class MockStrategyConfig(BaseStrategyConfig):
    """Mock configuration for testing."""
    name: str = "mock_strategy"
    description: str = "Mock strategy for testing"
    position_size_pct: float = 0.02
    market_open_time: time = time(9, 15)
    no_entry_after: time = time(14, 30)
    exit_time: time = time(15, 20)
    
    def validate(self) -> bool:
        """Validate mock config."""
        return True


class ConcreteStrategy(BaseStrategy):
    """Concrete implementation for testing BaseStrategy."""
    
    def __init__(self, config: BaseStrategyConfig, filter_result: bool = True):
        super().__init__(config)
        self._filter_result = filter_result
        self._enter_result = None
    
    def apply_filters(self, candidate: Any, stock_df: pd.DataFrame) -> bool:
        return self._filter_result
    
    def should_enter(
        self, candidate: Any, stock_df: pd.DataFrame, current_time: datetime
    ) -> Optional[Any]:
        return self._enter_result
    
    @property
    def min_data_points(self) -> int:
        return 20


@pytest.mark.unit
class TestBaseStrategyInitialization:
    """Tests for BaseStrategy initialization."""
    
    def test_strategy_init_with_config(self):
        """Test strategy initialization with configuration."""
        config = MockStrategyConfig(name="test_strategy")
        strategy = ConcreteStrategy(config)
        
        assert strategy.config == config
        assert strategy.name == "test_strategy"
    
    def test_strategy_inherits_config_values(self):
        """Test strategy inherits all config values."""
        config = MockStrategyConfig(
            name="my_strategy",
            description="Test description",
            position_size_pct=0.05
        )
        strategy = ConcreteStrategy(config)
        
        assert strategy.description == "Test description"
        assert strategy.config.position_size_pct == 0.05


@pytest.mark.unit
class TestBaseStrategyPositionSizing:
    """Tests for position size calculation."""
    
    def test_calculate_position_size_default(self):
        """Test default position size calculation."""
        config = MockStrategyConfig(position_size_pct=0.02)  # 2%
        strategy = ConcreteStrategy(config)
        
        quantity = strategy.calculate_position_size(
            capital=100000,
            price=2000
        )
        
        # 2% of 100000 = 2000, at price 2000 = 1 share
        assert quantity == 1
    
    def test_calculate_position_size_multiple_shares(self):
        """Test position size with multiple shares."""
        config = MockStrategyConfig(position_size_pct=0.10)  # 10%
        strategy = ConcreteStrategy(config)
        
        quantity = strategy.calculate_position_size(
            capital=100000,
            price=500
        )
        
        # 10% of 100000 = 10000, at price 500 = 20 shares
        assert quantity == 20
    
    def test_calculate_position_size_minimum_one(self):
        """Test position size is at least 1."""
        config = MockStrategyConfig(position_size_pct=0.001)  # 0.1%
        strategy = ConcreteStrategy(config)
        
        quantity = strategy.calculate_position_size(
            capital=10000,
            price=50000  # Very expensive stock
        )
        
        # Should return minimum of 1
        assert quantity == 1


@pytest.mark.unit
class TestBaseStrategyEntryTimeCheck:
    """Tests for entry time validation."""
    
    @pytest.fixture
    def strategy(self):
        """Create strategy with standard trading hours."""
        config = MockStrategyConfig(
            market_open_time=time(9, 15),
            no_entry_after=time(14, 30),
        )
        return ConcreteStrategy(config)
    
    def test_entry_allowed_during_trading_hours(self, strategy):
        """Test entry allowed during trading hours."""
        trading_time = datetime(2024, 1, 15, 10, 30)
        
        assert strategy._is_entry_allowed(trading_time) is True
    
    def test_entry_allowed_at_market_open(self, strategy):
        """Test entry allowed at market open."""
        market_open = datetime(2024, 1, 15, 9, 15)
        
        assert strategy._is_entry_allowed(market_open) is True
    
    def test_entry_allowed_at_cutoff(self, strategy):
        """Test entry allowed at cutoff time."""
        cutoff_time = datetime(2024, 1, 15, 14, 30)
        
        assert strategy._is_entry_allowed(cutoff_time) is True
    
    def test_entry_not_allowed_before_market_open(self, strategy):
        """Test entry not allowed before market open."""
        pre_market = datetime(2024, 1, 15, 9, 0)
        
        assert strategy._is_entry_allowed(pre_market) is False
    
    def test_entry_not_allowed_after_cutoff(self, strategy):
        """Test entry not allowed after cutoff time."""
        after_cutoff = datetime(2024, 1, 15, 14, 31)
        
        assert strategy._is_entry_allowed(after_cutoff) is False


@pytest.mark.unit
class TestBaseStrategyHelperMethods:
    """Tests for BaseStrategy helper methods."""
    
    def test_calculate_indicators_default(self, ohlcv_factory):
        """Test default calculate_indicators returns DataFrame unchanged."""
        config = MockStrategyConfig()
        strategy = ConcreteStrategy(config)
        df = ohlcv_factory(num_candles=10)
        
        result = strategy.calculate_indicators(df)
        
        pd.testing.assert_frame_equal(result, df)
    
    def test_should_exit_default_returns_none(self):
        """Test default should_exit returns None."""
        config = MockStrategyConfig()
        strategy = ConcreteStrategy(config)
        
        result = strategy.should_exit(
            position=None,
            current_price=100.0,
            current_time=datetime.now()
        )
        
        assert result is None
    
    def test_generate_signal_legacy_returns_none(self):
        """Test legacy generate_signal returns None by default."""
        config = MockStrategyConfig()
        strategy = ConcreteStrategy(config)
        
        result = strategy.generate_signal(
            current_indicators=(100, 50),
            previous_indicators=(99, 49)
        )
        
        assert result is None
    
    def test_min_data_points_property(self):
        """Test min_data_points returns correct value."""
        config = MockStrategyConfig()
        strategy = ConcreteStrategy(config)
        
        assert strategy.min_data_points == 20


@pytest.mark.unit
class TestBaseStrategyFiltering:
    """Tests for strategy filter behavior."""
    
    def test_apply_filters_returns_true(self, ohlcv_factory, candidate_factory):
        """Test apply_filters can return True."""
        config = MockStrategyConfig()
        strategy = ConcreteStrategy(config, filter_result=True)
        
        result = strategy.apply_filters(
            candidate=candidate_factory(),
            stock_df=ohlcv_factory()
        )
        
        assert result is True
    
    def test_apply_filters_returns_false(self, ohlcv_factory, candidate_factory):
        """Test apply_filters can return False."""
        config = MockStrategyConfig()
        strategy = ConcreteStrategy(config, filter_result=False)
        
        result = strategy.apply_filters(
            candidate=candidate_factory(),
            stock_df=ohlcv_factory()
        )
        
        assert result is False
