"""
Unit Tests for Models

Tests Signal, Candidate, Position models.
"""

import pytest
import json
from datetime import datetime, timedelta
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestSignalModel:
    """Test Signal model."""
    
    def test_signal_creation(self):
        """Test basic Signal creation."""
        from backend.models import Signal, SignalType
        
        signal = Signal(
            symbol="RELIANCE",
            instrument_token=738561,
            signal_type=SignalType.BUY,
            price=2450.0,
            stop_loss=2420.0,
            target=2510.0,
            quantity=10,
            timestamp=datetime.now(),
            reason="Test signal"
        )
        
        assert signal.symbol == "RELIANCE"
        assert signal.price == 2450.0
        assert signal.stop_loss == 2420.0
        assert signal.target == 2510.0
        assert signal.quantity == 10
        assert signal.signal_type == SignalType.BUY
    
    def test_signal_to_json(self):
        """Test Signal serialization to JSON."""
        from backend.models import Signal, SignalType
        
        timestamp = datetime(2025, 12, 1, 10, 30, 0)
        signal = Signal(
            symbol="TCS",
            instrument_token=2953217,
            signal_type=SignalType.BUY,
            price=3500.0,
            stop_loss=3450.0,
            target=3580.0,
            quantity=5,
            timestamp=timestamp,
            reason="VWAP breakout",
            metadata={"vwap": 3480.0, "volume_ratio": 1.8}
        )
        
        json_str = signal.to_json()
        data = json.loads(json_str)
        
        assert data["symbol"] == "TCS"
        assert data["price"] == 3500.0
        assert data["signal_type"] == "BUY"
        assert data["timestamp"] == timestamp.isoformat()
        assert data["metadata"]["vwap"] == 3480.0
    
    def test_signal_from_json(self):
        """Test Signal deserialization from JSON."""
        from backend.models import Signal, SignalType
        
        json_str = json.dumps({
            "symbol": "INFY",
            "instrument_token": 408065,
            "signal_type": "SELL",
            "price": 1500.0,
            "stop_loss": 1520.0,
            "target": 1450.0,
            "quantity": 20,
            "timestamp": "2025-12-01T11:00:00",
            "reason": "Target hit",
            "metadata": {}
        })
        
        signal = Signal.from_json(json_str)
        
        assert signal.symbol == "INFY"
        assert signal.signal_type == SignalType.SELL
        assert signal.price == 1500.0
        assert signal.timestamp == datetime(2025, 12, 1, 11, 0, 0)
    
    def test_signal_roundtrip_json(self, sample_signal):
        """Test Signal roundtrip through JSON."""
        original = sample_signal()
        
        json_str = original.to_json()
        restored = type(original).from_json(json_str)
        
        assert restored.symbol == original.symbol
        assert restored.price == original.price
        assert restored.stop_loss == original.stop_loss
        assert restored.target == original.target
        assert restored.quantity == original.quantity
        assert restored.signal_type == original.signal_type
    
    def test_signal_with_metadata(self):
        """Test Signal with rich metadata."""
        from backend.models import Signal, SignalType
        
        signal = Signal(
            symbol="HDFC",
            instrument_token=340481,
            signal_type=SignalType.BUY,
            price=2800.0,
            stop_loss=2760.0,
            target=2880.0,
            quantity=8,
            timestamp=datetime.now(),
            reason="Bullish flag breakout",
            metadata={
                "pattern": "bullish_flag",
                "pole_height_pct": 2.5,
                "pullback_pct": 0.8,
                "volume_multiplier": 1.6,
                "vwap": 2790.0,
                "ema_20": 2785.0
            }
        )
        
        assert signal.metadata["pattern"] == "bullish_flag"
        assert signal.metadata["pole_height_pct"] == 2.5
    
    def test_signal_default_metadata(self):
        """Test Signal has empty dict as default metadata."""
        from backend.models import Signal, SignalType
        
        signal = Signal(
            symbol="TEST",
            instrument_token=12345,
            signal_type=SignalType.BUY,
            price=100.0,
            timestamp=datetime.now()
        )
        
        assert signal.metadata == {}
    
    def test_signal_minimal_creation(self):
        """Test Signal with only required fields."""
        from backend.models import Signal, SignalType
        
        signal = Signal(
            symbol="TEST",
            instrument_token=12345,
            signal_type=SignalType.BUY,
            price=100.0,
            timestamp=datetime.now()
        )
        
        assert signal.symbol == "TEST"
        assert signal.instrument_token == 12345
        assert signal.price == 100.0
        assert signal.stop_loss is None
        assert signal.target is None
        assert signal.quantity is None


class TestCandidateModel:
    """Test Candidate model."""
    
    def test_candidate_creation(self, sample_candidate):
        """Test basic Candidate creation."""
        candidate = sample_candidate()
        
        assert candidate.symbol == "RELIANCE"
        assert candidate.current_price == 2450.0
        assert candidate.gain_pct == 2.5
        assert candidate.volume == 500000
        assert candidate.avg_volume == 300000
    
    def test_candidate_with_optional_fields(self):
        """Test Candidate with optional OHLC fields."""
        from backend.models import Candidate
        
        candidate = Candidate(
            symbol="TCS",
            instrument_token=2953217,
            current_price=3500.0,
            gain_pct=1.8,
            volume=400000,
            avg_volume=350000,
            timestamp=datetime.now(),
            open_price=3450.0,
            high_price=3520.0,
            low_price=3440.0
        )
        
        assert candidate.open_price == 3450.0
        assert candidate.high_price == 3520.0
        assert candidate.low_price == 3440.0
    
    def test_candidate_volume_ratio(self, sample_candidate):
        """Test volume ratio calculation."""
        candidate = sample_candidate(volume=600000)
        
        volume_ratio = candidate.volume / candidate.avg_volume
        
        assert volume_ratio == 2.0
    
    def test_candidate_required_fields(self):
        """Test Candidate with required fields only."""
        from backend.models import Candidate
        
        candidate = Candidate(
            symbol="TEST",
            instrument_token=12345,
            current_price=100.0,
            gain_pct=1.5,
            volume=100000,
            avg_volume=80000,
            timestamp=datetime.now()
        )
        
        assert candidate.symbol == "TEST"
        assert candidate.instrument_token == 12345
        assert candidate.open_price is None
        assert candidate.high_price is None
        assert candidate.low_price is None


class TestPositionModel:
    """Test Position model."""
    
    def test_position_creation(self, sample_position):
        """Test basic Position creation."""
        from backend.models import PositionStatus
        
        position = sample_position()
        
        assert position.symbol == "RELIANCE"
        assert position.entry_price == 2450.0
        assert position.quantity == 10
        assert position.stop_loss == 2420.0
        assert position.target == 2510.0
        assert position.status == PositionStatus.OPEN
    
    def test_position_update_pnl_profit(self, sample_position):
        """Test P&L calculation with profit."""
        position = sample_position(entry_price=2450.0, quantity=10)
        
        position.update_pnl(2480.0)  # Price went up
        
        assert position.current_price == 2480.0
        assert position.pnl == 300.0  # (2480 - 2450) * 10
        assert abs(position.pnl_pct - 1.224) < 0.01  # ~1.22%
    
    def test_position_update_pnl_loss(self, sample_position):
        """Test P&L calculation with loss."""
        position = sample_position(entry_price=2450.0, quantity=10)
        
        position.update_pnl(2430.0)  # Price went down
        
        assert position.current_price == 2430.0
        assert position.pnl == -200.0  # (2430 - 2450) * 10
        assert abs(position.pnl_pct - (-0.816)) < 0.01  # ~-0.82%
    
    def test_position_check_exit_sl_hit(self, sample_position):
        """Test exit check when stop loss is hit."""
        position = sample_position(stop_loss=2420.0)
        exit_time = datetime.now() + timedelta(hours=6)
        
        reason = position.check_exit(2418.0, datetime.now(), exit_time)
        
        assert reason == "SL_HIT"
    
    def test_position_check_exit_target_hit(self, sample_position):
        """Test exit check when target is hit."""
        position = sample_position(target=2510.0)
        exit_time = datetime.now() + timedelta(hours=6)
        
        reason = position.check_exit(2515.0, datetime.now(), exit_time)
        
        assert reason == "TARGET_HIT"
    
    def test_position_check_exit_time_exit(self, sample_position):
        """Test exit check when time limit is reached."""
        position = sample_position()
        exit_time = datetime.now() - timedelta(minutes=1)  # Exit time has passed
        
        reason = position.check_exit(2460.0, datetime.now(), exit_time)
        
        assert reason == "TIME_EXIT"
    
    def test_position_check_exit_no_exit(self, sample_position):
        """Test no exit when conditions not met."""
        position = sample_position(stop_loss=2420.0, target=2510.0)
        exit_time = datetime.now() + timedelta(hours=6)
        
        reason = position.check_exit(2460.0, datetime.now(), exit_time)  # Price in range
        
        assert reason is None
    
    def test_position_close(self, sample_position):
        """Test closing a position."""
        from backend.models import PositionStatus
        
        position = sample_position()
        close_time = datetime.now()
        
        position.close(2515.0, close_time, "TARGET_HIT")
        
        assert position.exit_price == 2515.0
        assert position.exit_time == close_time
        assert position.exit_reason == "TARGET_HIT"
        assert position.status == PositionStatus.TARGET_HIT
        assert position.pnl == (2515.0 - 2450.0) * 10  # 650
    
    def test_position_required_fields(self):
        """Test Position with required fields only."""
        from backend.models import Position
        
        position = Position(
            symbol="TEST",
            instrument_token=12345,
            entry_price=100.0,
            quantity=10,
            stop_loss=98.0,
            target=105.0,
            entry_time=datetime.now()
        )
        
        assert position.symbol == "TEST"
        assert position.instrument_token == 12345
        assert position.current_price == 0.0
        assert position.pnl == 0.0
        assert position.exit_price is None


class TestSignalTypeEnum:
    """Test SignalType enum."""
    
    def test_signal_type_values(self):
        """Test SignalType enum values."""
        from backend.models import SignalType
        
        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"
    
    def test_signal_type_from_string(self):
        """Test creating SignalType from string."""
        from backend.models import SignalType
        
        buy = SignalType("BUY")
        sell = SignalType("SELL")
        
        assert buy == SignalType.BUY
        assert sell == SignalType.SELL


class TestPositionStatusEnum:
    """Test PositionStatus enum."""
    
    def test_position_status_values(self):
        """Test PositionStatus enum values."""
        from backend.models import PositionStatus
        
        assert PositionStatus.OPEN.value == "OPEN"
        assert PositionStatus.TARGET_HIT.value == "TARGET_HIT"
        assert PositionStatus.SL_HIT.value == "SL_HIT"
        assert PositionStatus.TIME_EXIT.value == "TIME_EXIT"
        assert PositionStatus.MANUAL_EXIT.value == "MANUAL_EXIT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
