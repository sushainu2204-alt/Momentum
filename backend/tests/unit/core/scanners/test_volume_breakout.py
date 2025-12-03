"""
Unit Tests for Volume Breakout Scanner

Tests the volume breakout scanner implementation.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from dataclasses import dataclass

import pandas as pd
import numpy as np

from backend.core.scanners.volume_breakout import VolumeBreakoutScanner, VolumeBreakoutConfig
from backend.core.scanners.base import ScanResult


@dataclass
class MockQuote:
    """Mock quote data."""
    symbol: str
    instrument_token: int
    last_price: float
    open_price: float
    high_price: float
    low_price: float
    volume: int
    change_pct: float


@dataclass
class MockInstrument:
    """Mock instrument data."""
    symbol: str
    instrument_token: int


class TestVolumeBreakoutScanner:
    """Test VolumeBreakoutScanner."""
    
    @pytest.fixture
    def scanner(self):
        """Create scanner with default config."""
        return VolumeBreakoutScanner()
    
    @pytest.fixture
    def scanner_with_config(self):
        """Create scanner with custom config."""
        config = VolumeBreakoutConfig(
            volume_multiplier=3.0,
            avg_volume_days=10,
            min_gain_pct=1.0,
            max_gain_pct=10.0,
            min_price=100.0,
            max_price=5000.0
        )
        return VolumeBreakoutScanner(config=config)
    
    @pytest.fixture
    def mock_data_source(self):
        """Create mock data source."""
        source = Mock()
        return source
    
    @pytest.fixture
    def mock_instruments(self):
        """Create mock instruments."""
        return [
            MockInstrument(symbol="TEST1", instrument_token=1001),
            MockInstrument(symbol="TEST2", instrument_token=1002),
            MockInstrument(symbol="TEST3", instrument_token=1003)
        ]
    
    def test_init_with_default_config(self, scanner):
        """Test scanner initialization with default config."""
        assert scanner.config is not None
        assert scanner.config.name == "volume_breakout"
        assert scanner.config.volume_multiplier == 2.0
        assert scanner.data_source is None
        assert scanner.instruments == []
    
    def test_init_with_custom_config(self, scanner_with_config):
        """Test scanner initialization with custom config."""
        assert scanner_with_config.config.volume_multiplier == 3.0
        assert scanner_with_config.config.avg_volume_days == 10
    
    def test_init_with_data_source(self, mock_data_source, mock_instruments):
        """Test scanner initialization with data source."""
        scanner = VolumeBreakoutScanner(
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        assert scanner.data_source == mock_data_source
        assert len(scanner.instruments) == 3
    
    def test_get_name(self, scanner):
        """Test get_name returns correct name."""
        assert scanner.get_name() == "volume_breakout"
    
    def test_get_description(self, scanner):
        """Test get_description returns meaningful description."""
        description = scanner.get_description()
        
        assert "volume" in description.lower()
        assert str(scanner.config.volume_multiplier) in description
    
    @pytest.mark.asyncio
    async def test_scan_without_data_source_returns_error(self, scanner):
        """Test scan without data source returns error."""
        result = await scanner.scan()
        
        assert result.success == False
        assert "No data source" in result.errors[0]
    
    @pytest.mark.asyncio
    async def test_scan_without_instruments_returns_error(self, mock_data_source):
        """Test scan without instruments returns error."""
        scanner = VolumeBreakoutScanner(
            data_source=mock_data_source,
            instruments=[]
        )
        
        result = await scanner.scan()
        
        assert result.success == False
        assert "No instruments" in result.errors[0]
    
    @pytest.mark.asyncio
    async def test_scan_returns_volume_breakouts(
        self,
        mock_data_source,
        mock_instruments
    ):
        """Test scan returns stocks with volume breakout."""
        # Setup mock quotes
        mock_quotes = {
            1001: MockQuote(
                symbol="TEST1",
                instrument_token=1001,
                last_price=500.0,
                open_price=480.0,
                high_price=510.0,
                low_price=475.0,
                volume=500000,  # 5x average (100000)
                change_pct=4.0
            ),
            1002: MockQuote(
                symbol="TEST2",
                instrument_token=1002,
                last_price=300.0,
                open_price=295.0,
                high_price=305.0,
                low_price=290.0,
                volume=50000,  # Only 0.5x average (no breakout)
                change_pct=2.0
            )
        }
        mock_data_source.get_quotes.return_value = mock_quotes
        
        # Setup mock historical data for average volume
        def mock_historical(token, from_date, to_date, interval):
            return pd.DataFrame({
                'volume': [100000] * 20  # Average volume = 100000
            })
        mock_data_source.get_historical_data = mock_historical
        
        scanner = VolumeBreakoutScanner(
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        result = await scanner.scan()
        
        # Only TEST1 should qualify (5x volume, above 2x threshold)
        assert len(result.candidates) == 1
        assert result.candidates[0].symbol == "TEST1"
    
    @pytest.mark.asyncio
    async def test_scan_filters_by_gain_range(
        self,
        mock_data_source,
        mock_instruments
    ):
        """Test scan filters by gain percentage range."""
        config = VolumeBreakoutConfig(
            min_gain_pct=1.0,
            max_gain_pct=10.0
        )
        
        mock_quotes = {
            1001: MockQuote(
                symbol="TOO_LOW",
                instrument_token=1001,
                last_price=500.0,
                open_price=499.0,
                high_price=501.0,
                low_price=498.0,
                volume=500000,
                change_pct=0.2  # Below min
            ),
            1002: MockQuote(
                symbol="GOOD",
                instrument_token=1002,
                last_price=500.0,
                open_price=475.0,
                high_price=510.0,
                low_price=470.0,
                volume=500000,
                change_pct=5.0  # Within range
            ),
            1003: MockQuote(
                symbol="TOO_HIGH",
                instrument_token=1003,
                last_price=500.0,
                open_price=400.0,
                high_price=520.0,
                low_price=390.0,
                volume=500000,
                change_pct=25.0  # Above max
            )
        }
        mock_data_source.get_quotes.return_value = mock_quotes
        
        def mock_historical(token, from_date, to_date, interval):
            return pd.DataFrame({'volume': [100000] * 20})
        mock_data_source.get_historical_data = mock_historical
        
        scanner = VolumeBreakoutScanner(
            config=config,
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        result = await scanner.scan()
        
        symbols = [c.symbol for c in result.candidates]
        assert "GOOD" in symbols
        assert "TOO_LOW" not in symbols
        assert "TOO_HIGH" not in symbols
    
    @pytest.mark.asyncio
    async def test_scan_filters_by_price_range(
        self,
        mock_data_source,
        mock_instruments
    ):
        """Test scan filters by price range."""
        config = VolumeBreakoutConfig(
            min_price=100.0,
            max_price=1000.0
        )
        
        mock_quotes = {
            1001: MockQuote(
                symbol="CHEAP",
                instrument_token=1001,
                last_price=50.0,
                open_price=48.0,
                high_price=52.0,
                low_price=47.0,
                volume=500000,
                change_pct=5.0
            ),
            1002: MockQuote(
                symbol="GOOD",
                instrument_token=1002,
                last_price=500.0,
                open_price=475.0,
                high_price=510.0,
                low_price=470.0,
                volume=500000,
                change_pct=5.0
            ),
            1003: MockQuote(
                symbol="EXPENSIVE",
                instrument_token=1003,
                last_price=5000.0,
                open_price=4750.0,
                high_price=5100.0,
                low_price=4700.0,
                volume=500000,
                change_pct=5.0
            )
        }
        mock_data_source.get_quotes.return_value = mock_quotes
        
        def mock_historical(token, from_date, to_date, interval):
            return pd.DataFrame({'volume': [100000] * 20})
        mock_data_source.get_historical_data = mock_historical
        
        scanner = VolumeBreakoutScanner(
            config=config,
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        result = await scanner.scan()
        
        symbols = [c.symbol for c in result.candidates]
        assert "GOOD" in symbols
        assert "CHEAP" not in symbols
        assert "EXPENSIVE" not in symbols
    
    @pytest.mark.asyncio
    async def test_scan_sorts_by_volume_ratio(
        self,
        mock_data_source,
        mock_instruments
    ):
        """Test scan sorts candidates by volume ratio."""
        mock_quotes = {
            1001: MockQuote(
                symbol="LOW_VOL",
                instrument_token=1001,
                last_price=500.0,
                open_price=475.0,
                high_price=510.0,
                low_price=470.0,
                volume=250000,  # 2.5x
                change_pct=5.0
            ),
            1002: MockQuote(
                symbol="HIGH_VOL",
                instrument_token=1002,
                last_price=500.0,
                open_price=475.0,
                high_price=510.0,
                low_price=470.0,
                volume=500000,  # 5x
                change_pct=5.0
            ),
            1003: MockQuote(
                symbol="MID_VOL",
                instrument_token=1003,
                last_price=500.0,
                open_price=475.0,
                high_price=510.0,
                low_price=470.0,
                volume=350000,  # 3.5x
                change_pct=5.0
            )
        }
        mock_data_source.get_quotes.return_value = mock_quotes
        
        def mock_historical(token, from_date, to_date, interval):
            return pd.DataFrame({'volume': [100000] * 20})
        mock_data_source.get_historical_data = mock_historical
        
        scanner = VolumeBreakoutScanner(
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        result = await scanner.scan()
        
        # Should be sorted by volume ratio descending
        assert result.candidates[0].symbol == "HIGH_VOL"
        assert result.candidates[1].symbol == "MID_VOL"
        assert result.candidates[2].symbol == "LOW_VOL"
    
    @pytest.mark.asyncio
    async def test_scan_limits_results(self, mock_data_source):
        """Test scan limits results to max_results."""
        config = VolumeBreakoutConfig(max_results=2)
        
        # Create many instruments
        instruments = [
            MockInstrument(symbol=f"TEST{i}", instrument_token=1000+i)
            for i in range(10)
        ]
        
        mock_quotes = {
            inst.instrument_token: MockQuote(
                symbol=inst.symbol,
                instrument_token=inst.instrument_token,
                last_price=500.0,
                open_price=475.0,
                high_price=510.0,
                low_price=470.0,
                volume=300000,
                change_pct=5.0
            )
            for inst in instruments
        }
        mock_data_source.get_quotes.return_value = mock_quotes
        
        def mock_historical(token, from_date, to_date, interval):
            return pd.DataFrame({'volume': [100000] * 20})
        mock_data_source.get_historical_data = mock_historical
        
        scanner = VolumeBreakoutScanner(
            config=config,
            data_source=mock_data_source,
            instruments=instruments
        )
        
        result = await scanner.scan()
        
        assert len(result.candidates) == 2
    
    @pytest.mark.asyncio
    async def test_scan_handles_quote_errors(
        self,
        mock_data_source,
        mock_instruments
    ):
        """Test scan handles individual quote errors gracefully."""
        mock_data_source.get_quotes.return_value = {}  # No quotes
        
        scanner = VolumeBreakoutScanner(
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        result = await scanner.scan()
        
        # Should return empty result, not raise
        assert len(result.candidates) == 0
    
    @pytest.mark.asyncio
    async def test_scan_handles_api_exception(
        self,
        mock_data_source,
        mock_instruments
    ):
        """Test scan handles API exceptions gracefully."""
        mock_data_source.get_quotes.side_effect = Exception("API error")
        
        scanner = VolumeBreakoutScanner(
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        result = await scanner.scan()
        
        assert result.success == False
        assert len(result.errors) > 0
    
    @pytest.mark.asyncio
    async def test_get_avg_volume_uses_cache(
        self,
        mock_data_source,
        mock_instruments
    ):
        """Test _get_avg_volume caches results."""
        def mock_historical(token, from_date, to_date, interval):
            return pd.DataFrame({'volume': [100000] * 20})
        mock_data_source.get_historical_data = mock_historical
        
        scanner = VolumeBreakoutScanner(
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        # First call should fetch
        avg1 = await scanner._get_avg_volume(1001)
        # Second call should use cache
        avg2 = await scanner._get_avg_volume(1001)
        
        assert avg1 == avg2
        assert 1001 in scanner._avg_volume_cache
    
    @pytest.mark.asyncio
    async def test_get_avg_volume_handles_errors(
        self,
        mock_data_source,
        mock_instruments
    ):
        """Test _get_avg_volume handles errors gracefully."""
        mock_data_source.get_historical_data = Mock(side_effect=Exception("API error"))
        
        scanner = VolumeBreakoutScanner(
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        avg = await scanner._get_avg_volume(1001)
        
        assert avg == 0.0
    
    @pytest.mark.asyncio
    async def test_get_avg_volume_handles_empty_data(
        self,
        mock_data_source,
        mock_instruments
    ):
        """Test _get_avg_volume handles empty historical data."""
        mock_data_source.get_historical_data = Mock(return_value=pd.DataFrame())
        
        scanner = VolumeBreakoutScanner(
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        avg = await scanner._get_avg_volume(1001)
        
        assert avg == 0.0
    
    def test_clear_cache(self, scanner):
        """Test clear_cache clears the volume cache."""
        scanner._avg_volume_cache = {1001: 100000, 1002: 200000}
        scanner._cache_date = datetime.now().date()
        
        scanner.clear_cache()
        
        assert scanner._avg_volume_cache == {}
        assert scanner._cache_date is None
    
    @pytest.mark.asyncio
    async def test_scan_records_total_scanned(
        self,
        mock_data_source,
        mock_instruments
    ):
        """Test scan records total instruments scanned."""
        mock_data_source.get_quotes.return_value = {}
        
        scanner = VolumeBreakoutScanner(
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        result = await scanner.scan()
        
        assert result.total_scanned == 3
    
    @pytest.mark.asyncio
    async def test_scan_records_duration(
        self,
        mock_data_source,
        mock_instruments
    ):
        """Test scan records duration."""
        mock_data_source.get_quotes.return_value = {}
        
        scanner = VolumeBreakoutScanner(
            data_source=mock_data_source,
            instruments=mock_instruments
        )
        
        result = await scanner.scan()
        
        assert result.duration_ms > 0
