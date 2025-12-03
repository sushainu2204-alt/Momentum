"""
Unit Tests for Top Losers Scanner

Tests for TopLosersConfig and TopLosersScanner classes.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pandas as pd
from datetime import datetime
from dataclasses import dataclass

from backend.core.scanners.top_losers import TopLosersScanner, TopLosersConfig
from backend.core.scanners.base import ScanResult
from backend.core.models.candidate import Candidate


class TestTopLosersConfig:
    """Test TopLosersConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = TopLosersConfig()
        
        assert config.name == "top_losers"
        assert config.description == "Scans NSE for top losing stocks"
        assert config.min_loss_pct == -20.0
        assert config.max_loss_pct == -2.0
        assert config.min_price == 50.0
        assert config.max_price == 10000.0
        assert config.max_results == 30
        assert "FOSec" in config.categories
        assert "NIFTY" in config.categories
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = TopLosersConfig(
            name="custom_losers",
            description="Custom description",
            categories=["NIFTY50"],
            min_loss_pct=-15.0,
            max_loss_pct=-3.0,
            min_price=100.0,
            max_price=5000.0,
            max_results=20
        )
        
        assert config.name == "custom_losers"
        assert config.description == "Custom description"
        assert config.categories == ["NIFTY50"]
        assert config.min_loss_pct == -15.0
        assert config.max_loss_pct == -3.0
        assert config.min_price == 100.0
        assert config.max_price == 5000.0
        assert config.max_results == 20


class TestTopLosersScanner:
    """Test TopLosersScanner class."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return TopLosersConfig(
            categories=["FOSec"],
            min_loss_pct=-15.0,
            max_loss_pct=-2.0,
            min_price=50.0,
            max_price=5000.0,
            max_results=10
        )
    
    @pytest.fixture
    def scanner(self, config):
        """Create scanner instance."""
        return TopLosersScanner(config=config)
    
    @pytest.fixture
    def mock_nse_loser(self):
        """Create a mock NSE loser object."""
        @dataclass
        class MockNSELoser:
            symbol: str
            last_price: float
            open_price: float
            high_price: float
            low_price: float
            volume: int
            pct_change: float
        return MockNSELoser
    
    @pytest.fixture
    def sample_losers_data(self, mock_nse_loser):
        """Create sample losers data matching NSE format."""
        return [
            mock_nse_loser(
                symbol="RELIANCE",
                last_price=2450.0,
                open_price=2500.0,
                high_price=2510.0,
                low_price=2440.0,
                volume=500000,
                pct_change=-3.5
            ),
            mock_nse_loser(
                symbol="TCS",
                last_price=3800.0,
                open_price=3900.0,
                high_price=3920.0,
                low_price=3780.0,
                volume=300000,
                pct_change=-2.5
            ),
            mock_nse_loser(
                symbol="HDFC",
                last_price=1600.0,
                open_price=1680.0,
                high_price=1690.0,
                low_price=1590.0,
                volume=200000,
                pct_change=-5.0
            ),
            mock_nse_loser(
                symbol="INFY",
                last_price=1450.0,
                open_price=1520.0,
                high_price=1530.0,
                low_price=1440.0,
                volume=400000,
                pct_change=-4.5
            ),
        ]
    
    def test_scanner_initialization(self, scanner, config):
        """Test scanner is initialized correctly."""
        assert scanner.config == config
        assert scanner.get_name() == "top_losers"
    
    def test_get_name(self, scanner):
        """Test get_name returns correct name."""
        assert scanner.get_name() == "top_losers"
    
    def test_get_description(self, scanner):
        """Test get_description returns formatted string."""
        desc = scanner.get_description()
        assert "-15.0%" in desc or "-15" in desc
        assert "-2.0%" in desc or "-2" in desc
    
    @pytest.mark.asyncio
    async def test_initialize_creates_nse_source(self, scanner):
        """Test initialize creates NSE data source."""
        assert scanner._nse_source is None
        
        await scanner.initialize()
        
        assert scanner._nse_source is not None
    
    @pytest.mark.asyncio
    async def test_cleanup_closes_nse_source(self, scanner):
        """Test cleanup closes NSE data source."""
        # First initialize
        await scanner.initialize()
        assert scanner._nse_source is not None
        
        # Mock the close method
        scanner._nse_source.close = AsyncMock()
        
        # Cleanup
        await scanner.cleanup()
        
        assert scanner._nse_source is None
    
    @pytest.mark.asyncio
    async def test_scan_returns_scan_result(self, scanner, sample_losers_data):
        """Test scan returns ScanResult object."""
        # Mock the NSE source
        scanner._nse_source = Mock()
        scanner._nse_source.get_top_losers = AsyncMock(return_value=sample_losers_data)
        
        result = await scanner.scan()
        
        assert isinstance(result, ScanResult)
        assert result.scanner_name == "top_losers"
        assert result.scan_time is not None
    
    @pytest.mark.asyncio
    async def test_scan_converts_to_candidates(self, scanner, sample_losers_data):
        """Test scan converts NSE data to Candidates."""
        scanner._nse_source = Mock()
        scanner._nse_source.get_top_losers = AsyncMock(return_value=sample_losers_data)
        
        result = await scanner.scan()
        
        assert len(result.candidates) > 0
        for candidate in result.candidates:
            assert isinstance(candidate, Candidate)
    
    @pytest.mark.asyncio
    async def test_scan_filters_by_loss_range(self, scanner, mock_nse_loser):
        """Test scan filters candidates by loss percentage range."""
        # Config is: min_loss_pct=-15.0, max_loss_pct=-2.0
        losers = [
            mock_nse_loser(
                symbol="SMALL_LOSS", last_price=500.0, open_price=510.0,
                high_price=515.0, low_price=495.0, volume=200000, pct_change=-1.0  # -1.0 > -2.0 (max_loss_pct), filtered out
            ),
            mock_nse_loser(
                symbol="EXTREME_LOSS", last_price=500.0, open_price=600.0,
                high_price=605.0, low_price=490.0, volume=200000, pct_change=-18.0  # -18.0 < -15.0 (min_loss_pct), filtered out
            ),
            mock_nse_loser(
                symbol="VALID_LOSS", last_price=500.0, open_price=530.0,
                high_price=535.0, low_price=495.0, volume=200000, pct_change=-5.0  # Within range: -15.0 <= -5.0 <= -2.0
            ),
        ]
        
        scanner._nse_source = Mock()
        scanner._nse_source.get_top_losers = AsyncMock(return_value=losers)
        
        result = await scanner.scan()
        
        symbols = [c.symbol for c in result.candidates]
        assert "SMALL_LOSS" not in symbols  # -1.0 > -2.0 (max_loss_pct)
        assert "EXTREME_LOSS" not in symbols  # -18.0 < -15.0 (min_loss_pct)
        assert "VALID_LOSS" in symbols
    
    @pytest.mark.asyncio
    async def test_scan_filters_by_price(self, scanner, mock_nse_loser):
        """Test scan filters candidates by price range."""
        losers = [
            mock_nse_loser(
                symbol="TOO_CHEAP", last_price=25.0, open_price=30.0,
                high_price=32.0, low_price=24.0, volume=200000, pct_change=-5.0
            ),
            mock_nse_loser(
                symbol="TOO_EXPENSIVE", last_price=6000.0, open_price=6300.0,
                high_price=6350.0, low_price=5950.0, volume=200000, pct_change=-5.0
            ),
            mock_nse_loser(
                symbol="VALID_PRICE", last_price=500.0, open_price=530.0,
                high_price=535.0, low_price=495.0, volume=200000, pct_change=-5.0
            ),
        ]
        
        scanner._nse_source = Mock()
        scanner._nse_source.get_top_losers = AsyncMock(return_value=losers)
        
        result = await scanner.scan()
        
        symbols = [c.symbol for c in result.candidates]
        assert "TOO_CHEAP" not in symbols
        assert "TOO_EXPENSIVE" not in symbols
        assert "VALID_PRICE" in symbols
    
    @pytest.mark.asyncio
    async def test_scan_respects_max_results(self, scanner, mock_nse_loser):
        """Test scan limits results to max_results."""
        # Create more losers than max_results (10)
        losers = [
            mock_nse_loser(
                symbol=f"STOCK{i}", last_price=500.0, open_price=530.0,
                high_price=535.0, low_price=495.0, volume=200000, pct_change=-5.0
            )
            for i in range(20)
        ]
        
        scanner._nse_source = Mock()
        scanner._nse_source.get_top_losers = AsyncMock(return_value=losers)
        
        result = await scanner.scan()
        
        assert len(result.candidates) <= scanner.config.max_results
    
    @pytest.mark.asyncio
    async def test_scan_sorts_by_loss(self, scanner, mock_nse_loser):
        """Test candidates are sorted by loss (most negative first)."""
        losers = [
            mock_nse_loser(
                symbol="SMALL_LOSS", last_price=500.0, open_price=510.0,
                high_price=515.0, low_price=495.0, volume=200000, pct_change=-2.5
            ),
            mock_nse_loser(
                symbol="BIG_LOSS", last_price=500.0, open_price=560.0,
                high_price=565.0, low_price=490.0, volume=200000, pct_change=-10.0
            ),
            mock_nse_loser(
                symbol="MED_LOSS", last_price=500.0, open_price=530.0,
                high_price=535.0, low_price=495.0, volume=200000, pct_change=-5.0
            ),
        ]
        
        scanner._nse_source = Mock()
        scanner._nse_source.get_top_losers = AsyncMock(return_value=losers)
        
        result = await scanner.scan()
        
        if len(result.candidates) > 1:
            # Most negative should be first
            assert result.candidates[0].gain_pct <= result.candidates[-1].gain_pct
    
    @pytest.mark.asyncio
    async def test_scan_empty_data(self, scanner):
        """Test scan handles empty data."""
        scanner._nse_source = Mock()
        scanner._nse_source.get_top_losers = AsyncMock(return_value=[])
        
        result = await scanner.scan()
        
        assert result.candidates == []
        assert result.total_scanned == 0
    
    @pytest.mark.asyncio
    async def test_scan_handles_category_error(self, scanner):
        """Test scan handles category fetch errors gracefully."""
        scanner._nse_source = Mock()
        scanner._nse_source.get_top_losers = AsyncMock(side_effect=Exception("API Error"))
        
        result = await scanner.scan()
        
        # Should still return a result with errors logged
        assert isinstance(result, ScanResult)
        assert len(result.errors) > 0


class TestTopLosersScannerEdgeCases:
    """Test edge cases for TopLosersScanner."""
    
    def test_config_with_tight_loss_range(self):
        """Test config with tight loss range."""
        config = TopLosersConfig(
            min_loss_pct=-5.0,
            max_loss_pct=-4.0
        )
        scanner = TopLosersScanner(config=config)
        
        assert scanner.config.min_loss_pct == -5.0
        assert scanner.config.max_loss_pct == -4.0
    
    def test_config_with_single_category(self):
        """Test config with single category."""
        config = TopLosersConfig(categories=["FOSec"])
        scanner = TopLosersScanner(config=config)
        
        assert scanner.config.categories == ["FOSec"]
    
    def test_config_equal_price_range(self):
        """Test config with equal min and max price."""
        config = TopLosersConfig(min_price=100.0, max_price=100.0)
        scanner = TopLosersScanner(config=config)
        
        assert scanner.config.min_price == scanner.config.max_price
    
    def test_default_nse_config(self):
        """Test scanner uses default NSE config."""
        scanner = TopLosersScanner()
        
        assert scanner.nse_config is not None
