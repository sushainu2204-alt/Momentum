"""
Unit Tests for backend/core/models/enums.py

Tests SignalType, PositionStatus, OrderStatus, and OrderType enums.
"""

import pytest

from backend.core.models import (
    SignalType,
    PositionStatus,
    OrderStatus,
    OrderType,
)


@pytest.mark.unit
class TestSignalType:
    """Tests for SignalType enum."""
    
    def test_signal_type_buy_value(self):
        """Test BUY signal type value."""
        assert SignalType.BUY.value == "BUY"
    
    def test_signal_type_sell_value(self):
        """Test SELL signal type value."""
        assert SignalType.SELL.value == "SELL"
    
    def test_signal_type_is_string_enum(self):
        """Test SignalType is string compatible."""
        assert isinstance(SignalType.BUY, str)
        assert SignalType.BUY == "BUY"
    
    def test_signal_type_from_string(self):
        """Test creating SignalType from string."""
        signal = SignalType("BUY")
        assert signal == SignalType.BUY
    
    def test_signal_type_invalid_raises_error(self):
        """Test invalid signal type raises ValueError."""
        with pytest.raises(ValueError):
            SignalType("INVALID")
    
    def test_signal_type_all_values(self):
        """Test all SignalType values exist."""
        values = [e.value for e in SignalType]
        assert "BUY" in values
        assert "SELL" in values
        assert len(values) == 2


@pytest.mark.unit
class TestPositionStatus:
    """Tests for PositionStatus enum."""
    
    def test_position_status_open(self):
        """Test OPEN status value."""
        assert PositionStatus.OPEN.value == "OPEN"
    
    def test_position_status_target_hit(self):
        """Test TARGET_HIT status value."""
        assert PositionStatus.TARGET_HIT.value == "TARGET_HIT"
    
    def test_position_status_sl_hit(self):
        """Test SL_HIT status value."""
        assert PositionStatus.SL_HIT.value == "SL_HIT"
    
    def test_position_status_time_exit(self):
        """Test TIME_EXIT status value."""
        assert PositionStatus.TIME_EXIT.value == "TIME_EXIT"
    
    def test_position_status_manual_exit(self):
        """Test MANUAL_EXIT status value."""
        assert PositionStatus.MANUAL_EXIT.value == "MANUAL_EXIT"
    
    def test_position_status_is_string_enum(self):
        """Test PositionStatus is string compatible."""
        assert isinstance(PositionStatus.OPEN, str)
        assert PositionStatus.OPEN == "OPEN"
    
    def test_position_status_all_values(self):
        """Test all PositionStatus values exist."""
        values = [e.value for e in PositionStatus]
        expected = ["OPEN", "TARGET_HIT", "SL_HIT", "TIME_EXIT", "MANUAL_EXIT"]
        assert set(values) == set(expected)
        assert len(values) == 5


@pytest.mark.unit
class TestOrderStatus:
    """Tests for OrderStatus enum."""
    
    def test_order_status_pending(self):
        """Test PENDING status value."""
        assert OrderStatus.PENDING.value == "PENDING"
    
    def test_order_status_open(self):
        """Test OPEN status value."""
        assert OrderStatus.OPEN.value == "OPEN"
    
    def test_order_status_complete(self):
        """Test COMPLETE status value."""
        assert OrderStatus.COMPLETE.value == "COMPLETE"
    
    def test_order_status_cancelled(self):
        """Test CANCELLED status value."""
        assert OrderStatus.CANCELLED.value == "CANCELLED"
    
    def test_order_status_rejected(self):
        """Test REJECTED status value."""
        assert OrderStatus.REJECTED.value == "REJECTED"
    
    def test_order_status_is_string_enum(self):
        """Test OrderStatus is string compatible."""
        assert isinstance(OrderStatus.COMPLETE, str)
        assert OrderStatus.COMPLETE == "COMPLETE"
    
    def test_order_status_all_values(self):
        """Test all OrderStatus values exist."""
        values = [e.value for e in OrderStatus]
        expected = ["PENDING", "OPEN", "COMPLETE", "CANCELLED", "REJECTED"]
        assert set(values) == set(expected)
        assert len(values) == 5


@pytest.mark.unit
class TestOrderType:
    """Tests for OrderType enum."""
    
    def test_order_type_market(self):
        """Test MARKET order type value."""
        assert OrderType.MARKET.value == "MARKET"
    
    def test_order_type_limit(self):
        """Test LIMIT order type value."""
        assert OrderType.LIMIT.value == "LIMIT"
    
    def test_order_type_sl(self):
        """Test SL order type value."""
        assert OrderType.SL.value == "SL"
    
    def test_order_type_sl_m(self):
        """Test SL-M order type value."""
        assert OrderType.SL_M.value == "SL-M"
    
    def test_order_type_is_string_enum(self):
        """Test OrderType is string compatible."""
        assert isinstance(OrderType.MARKET, str)
        assert OrderType.MARKET == "MARKET"
    
    def test_order_type_all_values(self):
        """Test all OrderType values exist."""
        values = [e.value for e in OrderType]
        expected = ["MARKET", "LIMIT", "SL", "SL-M"]
        assert set(values) == set(expected)
        assert len(values) == 4
    
    def test_order_type_from_string_with_hyphen(self):
        """Test creating OrderType from hyphenated string."""
        order_type = OrderType("SL-M")
        assert order_type == OrderType.SL_M


@pytest.mark.unit
class TestEnumComparisons:
    """Tests for enum comparisons and usage patterns."""
    
    def test_signal_type_equality_with_string(self):
        """Test SignalType can be compared with strings."""
        assert SignalType.BUY == "BUY"
        assert SignalType.SELL == "SELL"
    
    def test_position_status_in_check(self):
        """Test PositionStatus in membership checks."""
        closed_statuses = [
            PositionStatus.TARGET_HIT,
            PositionStatus.SL_HIT,
            PositionStatus.TIME_EXIT,
            PositionStatus.MANUAL_EXIT,
        ]
        
        assert PositionStatus.OPEN not in closed_statuses
        assert PositionStatus.TARGET_HIT in closed_statuses
    
    def test_order_status_transition_logic(self):
        """Test OrderStatus can be used in state machine logic."""
        completed_states = [OrderStatus.COMPLETE, OrderStatus.CANCELLED, OrderStatus.REJECTED]
        active_states = [OrderStatus.PENDING, OrderStatus.OPEN]
        
        assert OrderStatus.PENDING in active_states
        assert OrderStatus.COMPLETE in completed_states
    
    def test_enums_are_hashable(self):
        """Test enums can be used as dict keys."""
        status_counts = {
            PositionStatus.OPEN: 5,
            PositionStatus.TARGET_HIT: 3,
            PositionStatus.SL_HIT: 2,
        }
        
        assert status_counts[PositionStatus.OPEN] == 5
