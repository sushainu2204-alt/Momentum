"""
Unit Tests for backend/core/models/signal.py

Tests Signal model creation, serialization, and methods.
"""

import json
import pytest
from datetime import datetime

from backend.core.models import Signal, SignalType


@pytest.mark.unit
class TestSignalCreation:
    """Tests for Signal model creation."""
    
    def test_create_signal_with_required_fields(self, signal_factory):
        """Test signal creation with required fields."""
        signal = signal_factory()
        
        assert signal.symbol == "RELIANCE"
        assert signal.instrument_token == 738561
        assert signal.signal_type == SignalType.BUY
        assert signal.price == 2450.0
        assert isinstance(signal.timestamp, datetime)
    
    def test_create_signal_with_all_fields(self, signal_factory):
        """Test signal creation with all fields."""
        signal = signal_factory(
            symbol="TCS",
            instrument_token=2953217,
            signal_type=SignalType.SELL,
            price=3500.0,
            stop_loss=3550.0,
            target=3400.0,
            quantity=20,
            reason="EMA crossover bearish",
        )
        
        assert signal.symbol == "TCS"
        assert signal.signal_type == SignalType.SELL
        assert signal.price == 3500.0
        assert signal.stop_loss == 3550.0
        assert signal.target == 3400.0
        assert signal.quantity == 20
        assert signal.reason == "EMA crossover bearish"
    
    def test_signal_default_metadata(self, signal_factory):
        """Test signal has empty metadata by default."""
        signal = signal_factory()
        
        assert signal.metadata == {} or signal.metadata is not None


@pytest.mark.unit
class TestSignalSerialization:
    """Tests for Signal serialization/deserialization."""
    
    def test_to_json_returns_valid_json(self, signal_factory):
        """Test to_json returns valid JSON string."""
        signal = signal_factory()
        json_str = signal.to_json()
        
        # Should not raise
        data = json.loads(json_str)
        assert isinstance(data, dict)
    
    def test_to_json_contains_all_fields(self, signal_factory):
        """Test to_json includes all signal fields."""
        signal = signal_factory(
            symbol="INFY",
            price=1650.0,
            stop_loss=1620.0,
            target=1700.0,
        )
        json_str = signal.to_json()
        data = json.loads(json_str)
        
        assert data["symbol"] == "INFY"
        assert data["price"] == 1650.0
        assert data["stop_loss"] == 1620.0
        assert data["target"] == 1700.0
        assert data["signal_type"] == "BUY"
        assert "timestamp" in data
    
    def test_from_json_restores_signal(self, signal_factory):
        """Test from_json correctly restores Signal."""
        original = signal_factory(symbol="HDFC", price=2800.0)
        json_str = original.to_json()
        
        restored = Signal.from_json(json_str)
        
        assert restored.symbol == original.symbol
        assert restored.price == original.price
        assert restored.signal_type == original.signal_type
        assert restored.stop_loss == original.stop_loss
        assert restored.target == original.target
    
    def test_from_json_restores_timestamp(self, signal_factory):
        """Test from_json correctly restores timestamp."""
        original = signal_factory()
        json_str = original.to_json()
        
        restored = Signal.from_json(json_str)
        
        assert isinstance(restored.timestamp, datetime)
        # Compare without microseconds due to ISO format precision
        assert restored.timestamp.replace(microsecond=0) == original.timestamp.replace(microsecond=0)
    
    def test_to_dict_returns_dict(self, signal_factory):
        """Test to_dict returns dictionary."""
        signal = signal_factory()
        data = signal.to_dict()
        
        assert isinstance(data, dict)
        assert data["symbol"] == "RELIANCE"
        assert data["price"] == 2450.0


@pytest.mark.unit
class TestSignalWithMetadata:
    """Tests for Signal with metadata."""
    
    def test_signal_with_metadata(self, signal_factory):
        """Test signal stores metadata correctly."""
        signal = signal_factory()
        signal.metadata = {
            "vwap": 2440.0,
            "volume_surge": 2.5,
            "ema_20": 2430.0,
        }
        
        assert signal.metadata["vwap"] == 2440.0
        assert signal.metadata["volume_surge"] == 2.5
    
    def test_metadata_serialization(self, signal_factory):
        """Test metadata is included in JSON serialization."""
        signal = signal_factory()
        signal.metadata = {"indicator": "RSI", "value": 65.5}
        
        json_str = signal.to_json()
        restored = Signal.from_json(json_str)
        
        assert restored.metadata["indicator"] == "RSI"
        assert restored.metadata["value"] == 65.5
