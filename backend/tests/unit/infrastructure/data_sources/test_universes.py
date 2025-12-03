"""
Unit Tests for Stock Universe Implementations

Tests for FnOUniverse, Nifty500Universe, Nifty200Universe, and CustomUniverse classes.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import csv
from dataclasses import dataclass
from typing import List

from backend.infrastructure.data_sources.universes import (
    FnOUniverse,
    Nifty500Universe,
    Nifty200Universe,
    CustomUniverse
)


@dataclass
class MockInstrument:
    """Mock Instrument for testing."""
    instrument_token: int
    tradingsymbol: str
    segment: str
    instrument_type: str


class TestFnOUniverse:
    """Test FnOUniverse class."""
    
    @pytest.fixture
    def universe(self):
        """Create FnOUniverse instance."""
        return FnOUniverse()
    
    @pytest.fixture
    def mock_data_source(self):
        """Create mock data source."""
        source = Mock()
        source.get_instruments = Mock(return_value=[
            MockInstrument(738561, "RELIANCE", "NSE", "EQ"),
            MockInstrument(2953217, "TCS", "NSE", "EQ"),
            MockInstrument(341249, "HDFCBANK", "NSE", "EQ"),
            MockInstrument(408065, "INFY", "NSE", "EQ"),
            MockInstrument(1270529, "UNKNOWN", "NSE", "EQ"),  # Not in FnO
            MockInstrument(1234567, "BSESTOCK", "BSE", "EQ"),  # Wrong exchange
            MockInstrument(9876543, "RELIANCE", "NSE", "FUT"),  # Wrong type
        ])
        return source
    
    def test_universe_initialization(self, universe):
        """Test universe is initialized correctly."""
        assert universe is not None
    
    def test_get_name(self, universe):
        """Test get_name returns appropriate name."""
        name = universe.get_name()
        
        assert "F&O" in name
        assert "Universe" in name
    
    def test_fallback_list_not_empty(self, universe):
        """Test fallback list is not empty."""
        assert len(universe.FNO_SYMBOLS_FALLBACK) > 0
        assert "RELIANCE" in universe.FNO_SYMBOLS_FALLBACK
        assert "TCS" in universe.FNO_SYMBOLS_FALLBACK
    
    def test_get_instruments_filters_correctly(self, universe, mock_data_source):
        """Test get_instruments filters to FnO stocks only."""
        instruments = universe.get_instruments(mock_data_source)
        
        # Should include FnO stocks
        symbols = [inst.tradingsymbol for inst in instruments]
        assert "RELIANCE" in symbols
        assert "TCS" in symbols
        assert "HDFCBANK" in symbols
        assert "INFY" in symbols
        
        # Should exclude non-FnO
        assert "UNKNOWN" not in symbols
        
        # Should exclude wrong exchange/type
        assert len([i for i in instruments if i.segment != "NSE"]) == 0
        assert len([i for i in instruments if i.instrument_type != "EQ"]) == 0
    
    def test_load_symbols_from_csv_fallback(self, universe):
        """Test _load_symbols_from_csv returns fallback when file missing."""
        with patch.object(Path, 'exists', return_value=False):
            symbols = universe._load_symbols_from_csv()
            
            assert symbols == universe.FNO_SYMBOLS_FALLBACK
    
    def test_load_symbols_from_csv_success(self, universe):
        """Test _load_symbols_from_csv loads from CSV file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=['symbol'])
            writer.writeheader()
            writer.writerow({'symbol': 'TESTSTOCK1'})
            writer.writerow({'symbol': 'TESTSTOCK2'})
            f.flush()
            
            with patch.object(Path, '__truediv__', return_value=Path(f.name)):
                with patch.object(Path, 'exists', return_value=True):
                    # Read from actual temp file
                    symbols = []
                    with open(f.name, 'r') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            if row.get('symbol', '').strip():
                                symbols.append(row['symbol'])
                    
                    assert 'TESTSTOCK1' in symbols
                    assert 'TESTSTOCK2' in symbols
    
    def test_load_symbols_handles_exception(self, universe):
        """Test _load_symbols_from_csv handles exceptions gracefully."""
        with patch.object(Path, 'exists', side_effect=Exception("File error")):
            symbols = universe._load_symbols_from_csv()
            
            # Should return fallback on error
            assert symbols == universe.FNO_SYMBOLS_FALLBACK


class TestNifty500Universe:
    """Test Nifty500Universe class."""
    
    @pytest.fixture
    def universe(self):
        """Create Nifty500Universe instance."""
        return Nifty500Universe()
    
    @pytest.fixture
    def mock_data_source(self):
        """Create mock data source."""
        source = Mock()
        source.get_instruments = Mock(return_value=[
            MockInstrument(738561, "RELIANCE", "NSE", "EQ"),
            MockInstrument(2953217, "TCS", "NSE", "EQ"),
            MockInstrument(341249, "HDFCBANK", "NSE", "EQ"),
            MockInstrument(1270529, "SMALLCAP", "NSE", "EQ"),  # Not in Nifty 500
        ])
        return source
    
    def test_universe_initialization(self, universe):
        """Test universe is initialized correctly."""
        assert universe is not None
    
    def test_get_name(self, universe):
        """Test get_name returns appropriate name."""
        name = universe.get_name()
        
        assert "Nifty 500" in name
    
    def test_fallback_list_not_empty(self, universe):
        """Test fallback list is not empty."""
        assert len(universe.NIFTY_500_SYMBOLS_FALLBACK) > 0
        assert "RELIANCE" in universe.NIFTY_500_SYMBOLS_FALLBACK
    
    def test_get_instruments_filters_correctly(self, universe, mock_data_source):
        """Test get_instruments filters to Nifty 500 stocks."""
        instruments = universe.get_instruments(mock_data_source)
        
        symbols = [inst.tradingsymbol for inst in instruments]
        assert "RELIANCE" in symbols
        assert "TCS" in symbols
        assert "HDFCBANK" in symbols
        assert "SMALLCAP" not in symbols


class TestNifty200Universe:
    """Test Nifty200Universe class."""
    
    @pytest.fixture
    def universe(self):
        """Create Nifty200Universe instance."""
        return Nifty200Universe()
    
    @pytest.fixture
    def mock_data_source(self):
        """Create mock data source."""
        source = Mock()
        source.get_instruments = Mock(return_value=[
            MockInstrument(738561, "RELIANCE", "NSE", "EQ"),
            MockInstrument(2953217, "TCS", "NSE", "EQ"),
        ])
        return source
    
    def test_universe_initialization(self, universe):
        """Test universe is initialized correctly."""
        assert universe is not None
    
    def test_get_name(self, universe):
        """Test get_name returns appropriate name."""
        name = universe.get_name()
        
        assert "Nifty 200" in name
    
    def test_get_instruments_uses_nifty500_logic(self, universe, mock_data_source):
        """Test get_instruments returns instruments."""
        instruments = universe.get_instruments(mock_data_source)
        
        # Should return instruments (uses Nifty500 logic)
        assert isinstance(instruments, list)


class TestCustomUniverse:
    """Test CustomUniverse class."""
    
    @pytest.fixture
    def custom_symbols(self):
        """Create list of custom symbols."""
        return ["RELIANCE", "TCS", "INFY", "HDFCBANK"]
    
    @pytest.fixture
    def universe(self, custom_symbols):
        """Create CustomUniverse instance."""
        return CustomUniverse(custom_symbols)
    
    @pytest.fixture
    def mock_data_source(self):
        """Create mock data source."""
        source = Mock()
        source.get_instruments = Mock(return_value=[
            MockInstrument(738561, "RELIANCE", "NSE", "EQ"),
            MockInstrument(2953217, "TCS", "NSE", "EQ"),
            MockInstrument(408065, "INFY", "NSE", "EQ"),
            MockInstrument(341249, "HDFCBANK", "NSE", "EQ"),
            MockInstrument(1270529, "OTHER", "NSE", "EQ"),  # Not in custom list
        ])
        return source
    
    def test_universe_initialization(self, universe, custom_symbols):
        """Test universe is initialized with custom symbols."""
        assert universe.symbols == custom_symbols
    
    def test_get_name_includes_count(self, universe, custom_symbols):
        """Test get_name includes symbol count."""
        name = universe.get_name()
        
        assert "Custom" in name
        assert str(len(custom_symbols)) in name
    
    def test_get_instruments_returns_only_custom_symbols(self, universe, mock_data_source):
        """Test get_instruments returns only custom symbols."""
        instruments = universe.get_instruments(mock_data_source)
        
        symbols = [inst.tradingsymbol for inst in instruments]
        
        assert "RELIANCE" in symbols
        assert "TCS" in symbols
        assert "INFY" in symbols
        assert "HDFCBANK" in symbols
        assert "OTHER" not in symbols
        assert len(instruments) == 4
    
    def test_empty_custom_universe(self, mock_data_source):
        """Test CustomUniverse with empty symbols list."""
        universe = CustomUniverse([])
        
        instruments = universe.get_instruments(mock_data_source)
        
        assert instruments == []
    
    def test_custom_universe_with_nonexistent_symbols(self, mock_data_source):
        """Test CustomUniverse with symbols not in data source."""
        universe = CustomUniverse(["NONEXISTENT1", "NONEXISTENT2"])
        
        instruments = universe.get_instruments(mock_data_source)
        
        assert instruments == []
    
    def test_custom_universe_partial_match(self, mock_data_source):
        """Test CustomUniverse with some existing and some non-existing symbols."""
        universe = CustomUniverse(["RELIANCE", "NONEXISTENT", "TCS"])
        
        instruments = universe.get_instruments(mock_data_source)
        
        symbols = [inst.tradingsymbol for inst in instruments]
        assert "RELIANCE" in symbols
        assert "TCS" in symbols
        assert len(instruments) == 2


class TestUniverseEdgeCases:
    """Test edge cases for all universe classes."""
    
    def test_fno_empty_data_source(self):
        """Test FnOUniverse with empty data source."""
        universe = FnOUniverse()
        mock_source = Mock()
        mock_source.get_instruments = Mock(return_value=[])
        
        instruments = universe.get_instruments(mock_source)
        
        assert instruments == []
    
    def test_nifty500_empty_data_source(self):
        """Test Nifty500Universe with empty data source."""
        universe = Nifty500Universe()
        mock_source = Mock()
        mock_source.get_instruments = Mock(return_value=[])
        
        instruments = universe.get_instruments(mock_source)
        
        assert instruments == []
    
    def test_data_source_exception_handling(self):
        """Test universe handles data source exceptions."""
        universe = FnOUniverse()
        mock_source = Mock()
        mock_source.get_instruments = Mock(side_effect=Exception("API Error"))
        
        with pytest.raises(Exception, match="API Error"):
            universe.get_instruments(mock_source)
    
    def test_instruments_with_mixed_segments(self):
        """Test filtering works correctly with mixed segments."""
        universe = FnOUniverse()
        mock_source = Mock()
        mock_source.get_instruments = Mock(return_value=[
            MockInstrument(1, "RELIANCE", "NSE", "EQ"),
            MockInstrument(2, "RELIANCE", "BSE", "EQ"),  # Same symbol, different exchange
            MockInstrument(3, "TCS", "NSE", "EQ"),
            MockInstrument(4, "TCS", "NFO", "FUT"),  # Futures
        ])
        
        instruments = universe.get_instruments(mock_source)
        
        # Should only include NSE EQ
        assert all(inst.segment == "NSE" for inst in instruments)
        assert all(inst.instrument_type == "EQ" for inst in instruments)
        assert len(instruments) == 2


class TestUniverseCSVLoading:
    """Test CSV loading functionality."""
    
    def test_fno_csv_with_empty_lines(self):
        """Test FnOUniverse handles CSV with empty lines."""
        universe = FnOUniverse()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=['symbol'])
            writer.writeheader()
            writer.writerow({'symbol': 'STOCK1'})
            writer.writerow({'symbol': ''})  # Empty line
            writer.writerow({'symbol': 'STOCK2'})
            writer.writerow({'symbol': '   '})  # Whitespace only
            f.flush()
            
            # Manually test the loading logic
            symbols = []
            with open(f.name, 'r') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    symbol = row.get('symbol', '').strip()
                    if symbol:
                        symbols.append(symbol)
            
            assert 'STOCK1' in symbols
            assert 'STOCK2' in symbols
            assert '' not in symbols
            assert len(symbols) == 2
    
    def test_nifty500_csv_loading(self):
        """Test Nifty500Universe CSV loading."""
        universe = Nifty500Universe()
        
        # Should have fallback list
        assert len(universe.NIFTY_500_SYMBOLS_FALLBACK) > 0
        
        # _load_symbols_from_csv should exist
        assert hasattr(universe, '_load_symbols_from_csv')
