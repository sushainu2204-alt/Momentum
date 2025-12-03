"""
Unit Tests for backend/core/models/position.py

Tests Position model creation, P&L calculation, and exit logic.
"""

import pytest
from datetime import datetime, timedelta

from backend.core.models import Position, PositionStatus


@pytest.mark.unit
class TestPositionCreation:
    """Tests for Position model creation."""
    
    def test_create_position_with_required_fields(self, position_factory):
        """Test position creation with required fields."""
        position = position_factory()
        
        assert position.symbol == "RELIANCE"
        assert position.instrument_token == 738561
        assert position.entry_price == 2450.0
        assert position.quantity == 10
        assert position.stop_loss == 2420.0
        assert position.target == 2510.0
        assert position.status == PositionStatus.OPEN
    
    def test_create_position_with_custom_values(self, position_factory):
        """Test position with custom values."""
        position = position_factory(
            symbol="TCS",
            entry_price=3500.0,
            quantity=20,
            stop_loss=3450.0,
            target=3600.0,
        )
        
        assert position.symbol == "TCS"
        assert position.entry_price == 3500.0
        assert position.quantity == 20
    
    def test_position_initial_pnl_is_zero(self, position_factory):
        """Test position starts with zero P&L."""
        position = position_factory()
        
        assert position.pnl == 0.0
        assert position.pnl_pct == 0.0


@pytest.mark.unit
class TestPositionPnLCalculation:
    """Tests for Position P&L calculation."""
    
    def test_update_pnl_with_profit(self, position_factory):
        """Test P&L calculation when in profit."""
        position = position_factory(entry_price=2450.0, quantity=10)
        
        position.update_pnl(current_price=2500.0)
        
        assert position.current_price == 2500.0
        assert position.pnl == 500.0  # (2500 - 2450) * 10
        assert position.pnl_pct == pytest.approx(2.04, rel=0.01)
    
    def test_update_pnl_with_loss(self, position_factory):
        """Test P&L calculation when in loss."""
        position = position_factory(entry_price=2450.0, quantity=10)
        
        position.update_pnl(current_price=2400.0)
        
        assert position.current_price == 2400.0
        assert position.pnl == -500.0  # (2400 - 2450) * 10
        assert position.pnl_pct == pytest.approx(-2.04, rel=0.01)
    
    def test_update_pnl_breakeven(self, position_factory):
        """Test P&L calculation at breakeven."""
        position = position_factory(entry_price=2450.0, quantity=10)
        
        position.update_pnl(current_price=2450.0)
        
        assert position.pnl == 0.0
        assert position.pnl_pct == 0.0
    
    def test_update_pnl_updates_current_price(self, position_factory):
        """Test that update_pnl updates current_price."""
        position = position_factory()
        
        position.update_pnl(current_price=2480.0)
        assert position.current_price == 2480.0
        
        position.update_pnl(current_price=2520.0)
        assert position.current_price == 2520.0


@pytest.mark.unit
class TestPositionExitCheck:
    """Tests for Position exit condition checking."""
    
    @pytest.fixture
    def position_with_levels(self, position_factory):
        """Create position with defined SL and target."""
        return position_factory(
            entry_price=2450.0,
            stop_loss=2420.0,
            target=2510.0,
        )
    
    @pytest.fixture
    def exit_datetime(self):
        """Return exit time (3:20 PM)."""
        return datetime.now().replace(hour=15, minute=20, second=0)
    
    @pytest.fixture
    def market_datetime(self):
        """Return market hours time (10:30 AM)."""
        return datetime.now().replace(hour=10, minute=30, second=0)
    
    def test_check_exit_stop_loss_hit(self, position_with_levels, exit_datetime, market_datetime):
        """Test exit when stop loss is hit."""
        reason = position_with_levels.check_exit(
            current_price=2410.0,  # Below stop loss
            current_time=market_datetime,
            exit_time=exit_datetime,
        )
        
        assert reason == "SL_HIT"
    
    def test_check_exit_stop_loss_exact(self, position_with_levels, exit_datetime, market_datetime):
        """Test exit when price equals stop loss."""
        reason = position_with_levels.check_exit(
            current_price=2420.0,  # Exactly at stop loss
            current_time=market_datetime,
            exit_time=exit_datetime,
        )
        
        assert reason == "SL_HIT"
    
    def test_check_exit_target_hit(self, position_with_levels, exit_datetime, market_datetime):
        """Test exit when target is hit."""
        reason = position_with_levels.check_exit(
            current_price=2520.0,  # Above target
            current_time=market_datetime,
            exit_time=exit_datetime,
        )
        
        assert reason == "TARGET_HIT"
    
    def test_check_exit_target_exact(self, position_with_levels, exit_datetime, market_datetime):
        """Test exit when price equals target."""
        reason = position_with_levels.check_exit(
            current_price=2510.0,  # Exactly at target
            current_time=market_datetime,
            exit_time=exit_datetime,
        )
        
        assert reason == "TARGET_HIT"
    
    def test_check_exit_time_based(self, position_with_levels, exit_datetime):
        """Test exit when current time >= exit time."""
        late_time = exit_datetime + timedelta(minutes=5)
        
        reason = position_with_levels.check_exit(
            current_price=2460.0,  # Between SL and target
            current_time=late_time,
            exit_time=exit_datetime,
        )
        
        assert reason == "TIME_EXIT"
    
    def test_check_exit_no_exit_condition(self, position_with_levels, exit_datetime, market_datetime):
        """Test no exit when all conditions are fine."""
        reason = position_with_levels.check_exit(
            current_price=2460.0,  # Between SL and target
            current_time=market_datetime,  # Before exit time
            exit_time=exit_datetime,
        )
        
        assert reason is None


@pytest.mark.unit
class TestPositionClose:
    """Tests for closing a Position."""
    
    def test_close_position_target_hit(self, position_factory):
        """Test closing position at target."""
        position = position_factory(entry_price=2450.0, quantity=10)
        exit_time = datetime.now()
        
        position.close(
            exit_price=2510.0,
            exit_time=exit_time,
            exit_reason="TARGET_HIT",
        )
        
        assert position.exit_price == 2510.0
        assert position.exit_time == exit_time
        assert position.exit_reason == "TARGET_HIT"
        assert position.status == PositionStatus.TARGET_HIT
        assert position.pnl == 600.0  # (2510 - 2450) * 10
    
    def test_close_position_stop_loss(self, position_factory):
        """Test closing position at stop loss."""
        position = position_factory(entry_price=2450.0, quantity=10)
        exit_time = datetime.now()
        
        position.close(
            exit_price=2420.0,
            exit_time=exit_time,
            exit_reason="SL_HIT",
        )
        
        assert position.exit_price == 2420.0
        assert position.status == PositionStatus.SL_HIT
        assert position.pnl == -300.0  # (2420 - 2450) * 10
    
    def test_close_position_time_exit(self, position_factory):
        """Test closing position at time exit."""
        position = position_factory(entry_price=2450.0, quantity=10)
        exit_time = datetime.now()
        
        position.close(
            exit_price=2470.0,
            exit_time=exit_time,
            exit_reason="TIME_EXIT",
        )
        
        assert position.status == PositionStatus.TIME_EXIT
        assert position.pnl == 200.0  # (2470 - 2450) * 10


@pytest.mark.unit
class TestPositionSerialization:
    """Tests for Position serialization."""
    
    def test_to_dict_returns_dict(self, position_factory):
        """Test to_dict returns dictionary."""
        position = position_factory()
        data = position.to_dict()
        
        assert isinstance(data, dict)
    
    def test_to_dict_contains_all_fields(self, position_factory):
        """Test to_dict includes all fields."""
        position = position_factory(symbol="INFY", entry_price=1650.0)
        data = position.to_dict()
        
        assert data["symbol"] == "INFY"
        assert data["entry_price"] == 1650.0
        assert "stop_loss" in data
        assert "target" in data
        assert "quantity" in data
        assert "status" in data
