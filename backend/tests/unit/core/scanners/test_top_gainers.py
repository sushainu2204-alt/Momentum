"""
Unit Tests for Top Gainers Scanner

Tests the top gainers scanner implementation.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from dataclasses import dataclass

from backend.core.scanners.top_gainers import TopGainersScanner, TopGainersConfig
from backend.core.scanners.base import ScanResult
from backend.core.models import Candidate


@dataclass
class MockNSEGainer:
    """Mock NSE top gainer data."""
    symbol: str
    last_price: float
    open_price: float
    high_price: float
    low_price: float
    volume: int
    pct_change: float


class TestTopGainersScanner:
    """Test TopGainersScanner."""
    
    @pytest.fixture
    def scanner(self):
        """Create scanner with default config."""
        return TopGainersScanner()
    
    @pytest.fixture
    def scanner_with_config(self):
        """Create scanner with custom config."""
        config = TopGainersConfig(
            min_gain_pct=3.0,
            max_gain_pct=15.0,
            min_price=100.0,
            max_price=5000.0,
            categories=["FOSec", "NIFTY"]
        )
        return TopGainersScanner(config=config)
    
    def test_init_with_default_config(self, scanner):
        """Test scanner initialization with default config."""
        assert scanner.config is not None
        assert scanner.config.name == "top_gainers"
        assert scanner._nse_source is None
    
    def test_init_with_custom_config(self, scanner_with_config):
        """Test scanner initialization with custom config."""
        assert scanner_with_config.config.min_gain_pct == 3.0
        assert scanner_with_config.config.max_gain_pct == 15.0
    
    def test_get_name(self, scanner):
        """Test get_name returns correct name."""
        assert scanner.get_name() == "top_gainers"
    
    def test_get_description(self, scanner):
        """Test get_description returns meaningful description."""
        description = scanner.get_description()
        
        assert "Top gaining stocks" in description
        assert str(scanner.config.min_gain_pct) in description
        assert str(scanner.config.max_gain_pct) in description
    
    @pytest.mark.asyncio
    async def test_initialize_creates_nse_source(self, scanner):
        """Test initialize creates NSE data source."""
        with patch('backend.core.scanners.top_gainers.NSEDataSource') as MockNSE:
            mock_source = Mock()
            MockNSE.return_value = mock_source
            
            await scanner.initialize()
            
            assert scanner._nse_source == mock_source
    
    @pytest.mark.asyncio
    async def test_initialize_only_creates_once(self, scanner):
        """Test initialize doesn't recreate existing source."""
        mock_source = Mock()
        scanner._nse_source = mock_source
        
        await scanner.initialize()
        
        # Should still be the same instance
        assert scanner._nse_source == mock_source
    
    @pytest.mark.asyncio
    async def test_cleanup_closes_nse_source(self, scanner):
        """Test cleanup closes NSE data source."""
        mock_source = AsyncMock()
        scanner._nse_source = mock_source
        
        await scanner.cleanup()
        
        mock_source.close.assert_called_once()
        assert scanner._nse_source is None
    
    @pytest.mark.asyncio
    async def test_cleanup_handles_no_source(self, scanner):
        """Test cleanup handles no source gracefully."""
        scanner._nse_source = None
        
        # Should not raise
        await scanner.cleanup()
    
    @pytest.mark.asyncio
    async def test_scan_returns_candidates(self, scanner):
        """Test scan returns candidates from NSE."""
        mock_gainers = [
            MockNSEGainer(
                symbol="RELIANCE",
                last_price=2500.0,
                open_price=2400.0,
                high_price=2550.0,
                low_price=2380.0,
                volume=1000000,
                pct_change=4.5
            ),
            MockNSEGainer(
                symbol="TCS",
                last_price=3500.0,
                open_price=3400.0,
                high_price=3550.0,
                low_price=3380.0,
                volume=500000,
                pct_change=3.2
            )
        ]
        
        mock_nse = AsyncMock()
        mock_nse.get_top_gainers.return_value = mock_gainers
        scanner._nse_source = mock_nse
        
        result = await scanner.scan()
        
        assert isinstance(result, ScanResult)
        assert result.scanner_name == "top_gainers"
        assert len(result.candidates) == 2
        assert result.success == True
    
    @pytest.mark.asyncio
    async def test_scan_deduplicates_symbols(self, scanner):
        """Test scan removes duplicate symbols across categories."""
        mock_gainer = MockNSEGainer(
            symbol="RELIANCE",
            last_price=2500.0,
            open_price=2400.0,
            high_price=2550.0,
            low_price=2380.0,
            volume=1000000,
            pct_change=4.5
        )
        
        mock_nse = AsyncMock()
        # Return same symbol for different categories
        mock_nse.get_top_gainers.return_value = [mock_gainer]
        scanner._nse_source = mock_nse
        
        result = await scanner.scan()
        
        # Should only have one RELIANCE even if returned by multiple categories
        symbols = [c.symbol for c in result.candidates]
        assert symbols.count("RELIANCE") == 1
    
    @pytest.mark.asyncio
    async def test_scan_filters_by_gain(self, scanner_with_config):
        """Test scan filters candidates by gain percentage."""
        mock_gainers = [
            MockNSEGainer(
                symbol="HIGH_GAIN",
                last_price=500.0,
                open_price=400.0,
                high_price=520.0,
                low_price=390.0,
                volume=100000,
                pct_change=25.0  # Too high (above 15%)
            ),
            MockNSEGainer(
                symbol="GOOD_GAIN",
                last_price=500.0,
                open_price=475.0,
                high_price=510.0,
                low_price=470.0,
                volume=100000,
                pct_change=5.0  # Good (3-15%)
            ),
            MockNSEGainer(
                symbol="LOW_GAIN",
                last_price=500.0,
                open_price=495.0,
                high_price=505.0,
                low_price=490.0,
                volume=100000,
                pct_change=1.0  # Too low (below 3%)
            )
        ]
        
        mock_nse = AsyncMock()
        mock_nse.get_top_gainers.return_value = mock_gainers
        scanner_with_config._nse_source = mock_nse
        
        result = await scanner_with_config.scan()
        
        symbols = [c.symbol for c in result.candidates]
        assert "GOOD_GAIN" in symbols
        assert "HIGH_GAIN" not in symbols
        assert "LOW_GAIN" not in symbols
    
    @pytest.mark.asyncio
    async def test_scan_filters_by_price(self, scanner_with_config):
        """Test scan filters candidates by price."""
        mock_gainers = [
            MockNSEGainer(
                symbol="CHEAP",
                last_price=50.0,  # Too cheap (below 100)
                open_price=48.0,
                high_price=52.0,
                low_price=47.0,
                volume=100000,
                pct_change=5.0
            ),
            MockNSEGainer(
                symbol="GOOD_PRICE",
                last_price=500.0,  # Good (100-5000)
                open_price=475.0,
                high_price=510.0,
                low_price=470.0,
                volume=100000,
                pct_change=5.0
            ),
            MockNSEGainer(
                symbol="EXPENSIVE",
                last_price=10000.0,  # Too expensive (above 5000)
                open_price=9500.0,
                high_price=10100.0,
                low_price=9400.0,
                volume=100000,
                pct_change=5.0
            )
        ]
        
        mock_nse = AsyncMock()
        mock_nse.get_top_gainers.return_value = mock_gainers
        scanner_with_config._nse_source = mock_nse
        
        result = await scanner_with_config.scan()
        
        symbols = [c.symbol for c in result.candidates]
        assert "GOOD_PRICE" in symbols
        assert "CHEAP" not in symbols
        assert "EXPENSIVE" not in symbols
    
    @pytest.mark.asyncio
    async def test_scan_sorts_by_gain_descending(self, scanner):
        """Test scan sorts candidates by gain percentage descending."""
        mock_gainers = [
            MockNSEGainer(
                symbol="LOW",
                last_price=500.0,
                open_price=475.0,
                high_price=510.0,
                low_price=470.0,
                volume=100000,
                pct_change=3.0
            ),
            MockNSEGainer(
                symbol="HIGH",
                last_price=500.0,
                open_price=450.0,
                high_price=510.0,
                low_price=440.0,
                volume=100000,
                pct_change=10.0
            ),
            MockNSEGainer(
                symbol="MID",
                last_price=500.0,
                open_price=465.0,
                high_price=510.0,
                low_price=460.0,
                volume=100000,
                pct_change=7.0
            )
        ]
        
        mock_nse = AsyncMock()
        mock_nse.get_top_gainers.return_value = mock_gainers
        scanner._nse_source = mock_nse
        
        result = await scanner.scan()
        
        # Should be sorted HIGH > MID > LOW
        assert result.candidates[0].symbol == "HIGH"
        assert result.candidates[1].symbol == "MID"
        assert result.candidates[2].symbol == "LOW"
    
    @pytest.mark.asyncio
    async def test_scan_handles_empty_response(self, scanner):
        """Test scan handles empty response from NSE."""
        mock_nse = AsyncMock()
        mock_nse.get_top_gainers.return_value = []
        scanner._nse_source = mock_nse
        
        result = await scanner.scan()
        
        assert result.success == False
        assert len(result.candidates) == 0
    
    @pytest.mark.asyncio
    async def test_scan_handles_api_error(self, scanner):
        """Test scan handles API errors gracefully."""
        mock_nse = AsyncMock()
        mock_nse.get_top_gainers.side_effect = Exception("API error")
        scanner._nse_source = mock_nse
        
        result = await scanner.scan()
        
        assert result.success == False
        assert len(result.errors) > 0
    
    @pytest.mark.asyncio
    async def test_scan_records_category_stats(self, scanner):
        """Test scan records category statistics."""
        mock_gainer = MockNSEGainer(
            symbol="TEST",
            last_price=500.0,
            open_price=475.0,
            high_price=510.0,
            low_price=470.0,
            volume=100000,
            pct_change=5.0
        )
        
        mock_nse = AsyncMock()
        mock_nse.get_top_gainers.return_value = [mock_gainer]
        scanner._nse_source = mock_nse
        
        result = await scanner.scan()
        
        # Should have stats for each category scanned
        assert len(result.category_stats) > 0
    
    @pytest.mark.asyncio
    async def test_scan_records_duration(self, scanner):
        """Test scan records duration."""
        mock_nse = AsyncMock()
        mock_nse.get_top_gainers.return_value = []
        scanner._nse_source = mock_nse
        
        result = await scanner.scan()
        
        assert result.duration_ms > 0
    
    def test_convert_to_candidates(self, scanner):
        """Test _convert_to_candidates converts NSE data correctly."""
        mock_gainers = [
            MockNSEGainer(
                symbol="TEST",
                last_price=500.0,
                open_price=475.0,
                high_price=510.0,
                low_price=470.0,
                volume=100000,
                pct_change=5.0
            )
        ]
        
        candidates = scanner._convert_to_candidates(mock_gainers)
        
        assert len(candidates) == 1
        assert candidates[0].symbol == "TEST"
        assert candidates[0].current_price == 500.0
        assert candidates[0].open_price == 475.0
        assert candidates[0].high_price == 510.0
        assert candidates[0].low_price == 470.0
        assert candidates[0].volume == 100000
        assert candidates[0].gain_pct == 5.0
    
    def test_convert_to_candidates_handles_errors(self, scanner):
        """Test _convert_to_candidates handles conversion errors."""
        # Create invalid object
        class InvalidGainer:
            pass
        
        candidates = scanner._convert_to_candidates([InvalidGainer()])
        
        # Should return empty list, not raise
        assert len(candidates) == 0
