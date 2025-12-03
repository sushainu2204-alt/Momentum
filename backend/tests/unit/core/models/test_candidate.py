"""
Unit Tests for backend/core/models/candidate.py

Tests Candidate model creation and methods.
"""

import pytest
from datetime import datetime

from backend.core.models import Candidate


@pytest.mark.unit
class TestCandidateCreation:
    """Tests for Candidate model creation."""
    
    def test_create_candidate_with_required_fields(self, candidate_factory):
        """Test candidate creation with required fields."""
        candidate = candidate_factory()
        
        assert candidate.symbol == "RELIANCE"
        assert candidate.instrument_token == 738561
        assert candidate.current_price == 2450.0
        assert candidate.gain_pct == 2.5
        assert candidate.volume == 500000
        assert candidate.avg_volume == 300000
        assert isinstance(candidate.timestamp, datetime)
    
    def test_create_candidate_with_custom_values(self, candidate_factory):
        """Test candidate with custom values."""
        candidate = candidate_factory(
            symbol="TCS",
            instrument_token=2953217,
            current_price=3500.0,
            gain_pct=3.8,
            volume=800000,
            avg_volume=400000,
        )
        
        assert candidate.symbol == "TCS"
        assert candidate.current_price == 3500.0
        assert candidate.gain_pct == 3.8
        assert candidate.volume == 800000
    
    def test_candidate_with_ohlc_prices(self, candidate_factory):
        """Test candidate with OHLC prices."""
        candidate = candidate_factory(
            current_price=2450.0,
            open_price=2400.0,
            high_price=2470.0,
            low_price=2390.0,
        )
        
        assert candidate.open_price == 2400.0
        assert candidate.high_price == 2470.0
        assert candidate.low_price == 2390.0


@pytest.mark.unit
class TestCandidateVolumeAnalysis:
    """Tests for Candidate volume-related functionality."""
    
    def test_volume_ratio_calculation(self, candidate_factory):
        """Test volume ratio can be calculated."""
        candidate = candidate_factory(volume=600000, avg_volume=300000)
        
        volume_ratio = candidate.volume / candidate.avg_volume
        
        assert volume_ratio == 2.0
    
    def test_volume_surge_detection(self, candidate_factory):
        """Test detecting volume surge."""
        candidate = candidate_factory(volume=750000, avg_volume=300000)
        
        volume_ratio = candidate.volume / candidate.avg_volume
        is_surge = volume_ratio >= 2.0
        
        assert is_surge is True
    
    def test_no_volume_surge(self, candidate_factory):
        """Test when there's no volume surge."""
        candidate = candidate_factory(volume=400000, avg_volume=300000)
        
        volume_ratio = candidate.volume / candidate.avg_volume
        is_surge = volume_ratio >= 2.0
        
        assert is_surge is False


@pytest.mark.unit
class TestCandidateSerialization:
    """Tests for Candidate serialization."""
    
    def test_to_dict_returns_dict(self, candidate_factory):
        """Test to_dict returns dictionary."""
        candidate = candidate_factory()
        data = candidate.to_dict()
        
        assert isinstance(data, dict)
    
    def test_to_dict_contains_all_fields(self, candidate_factory):
        """Test to_dict includes all fields."""
        candidate = candidate_factory(
            symbol="INFY",
            current_price=1650.0,
            gain_pct=2.8,
        )
        data = candidate.to_dict()
        
        assert data["symbol"] == "INFY"
        assert data["current_price"] == 1650.0
        assert data["gain_pct"] == 2.8
        assert "volume" in data
        assert "avg_volume" in data
        assert "timestamp" in data
