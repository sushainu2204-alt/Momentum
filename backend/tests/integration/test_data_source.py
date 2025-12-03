"""
Integration Tests for MockDataSource

Tests the MockDataSource implementation to verify:
1. Quote retrieval
2. Historical data generation
3. Instrument search
4. Data customization for testing
"""

import pytest
from datetime import datetime, timedelta
import pandas as pd

from backend.infrastructure.data_sources.base import Quote, Instrument


@pytest.mark.integration
class TestMockDataSourceQuotes:
    """Tests for quote retrieval."""
    
    def test_get_quote_default_instrument(self, mock_data_source):
        """Test getting quote for default instrument."""
        quote = mock_data_source.get_quote(738561)  # RELIANCE
        
        assert quote is not None
        assert quote.instrument_token == 738561
        assert quote.symbol == "RELIANCE"
        assert quote.last_price > 0
    
    def test_get_quote_returns_quote_object(self, mock_data_source):
        """Test that get_quote returns Quote dataclass."""
        quote = mock_data_source.get_quote(738561)
        
        assert isinstance(quote, Quote)
        assert hasattr(quote, 'last_price')
        assert hasattr(quote, 'volume')
        assert hasattr(quote, 'change_pct')
    
    def test_get_quotes_multiple(self, mock_data_source):
        """Test getting quotes for multiple instruments."""
        tokens = [738561, 340481, 2953217]  # RELIANCE, INFY, TCS
        quotes = mock_data_source.get_quotes(tokens)
        
        assert len(quotes) == 3
        assert all(token in quotes for token in tokens)
    
    def test_get_quote_unknown_instrument(self, mock_data_source):
        """Test getting quote for unknown instrument token."""
        quote = mock_data_source.get_quote(999999)
        
        assert quote is not None
        assert quote.instrument_token == 999999
        assert "UNKNOWN" in quote.symbol
    
    def test_set_custom_quote(self, mock_data_source):
        """Test setting custom quote for testing."""
        custom_quote = Quote(
            instrument_token=738561,
            symbol="RELIANCE",
            last_price=2500.0,
            volume=1000000,
            change_pct=5.0,
            timestamp=datetime.now(),
            open_price=2380.0,
            high_price=2510.0,
            low_price=2370.0,
            close_price=2380.0
        )
        
        mock_data_source.set_quote(738561, custom_quote)
        quote = mock_data_source.get_quote(738561)
        
        assert quote.last_price == 2500.0
        assert quote.change_pct == 5.0


@pytest.mark.integration
class TestMockDataSourceHistoricalData:
    """Tests for historical data retrieval."""
    
    def test_get_historical_data_returns_dataframe(self, mock_data_source):
        """Test that historical data returns DataFrame."""
        from_date = datetime.now() - timedelta(days=1)
        to_date = datetime.now()
        
        df = mock_data_source.get_historical_data(
            instrument_token=738561,
            from_date=from_date,
            to_date=to_date,
            interval="5minute"
        )
        
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
    
    def test_historical_data_has_ohlcv_columns(self, mock_data_source):
        """Test that historical data has required columns."""
        df = mock_data_source.get_historical_data(
            instrument_token=738561,
            from_date=datetime.now() - timedelta(days=1),
            to_date=datetime.now(),
            interval="5minute"
        )
        
        required_cols = ["open", "high", "low", "close", "volume"]
        for col in required_cols:
            assert col in df.columns
    
    def test_historical_data_ohlc_consistency(self, mock_data_source):
        """Test OHLC data is consistent."""
        df = mock_data_source.get_historical_data(
            instrument_token=738561,
            from_date=datetime.now() - timedelta(days=1),
            to_date=datetime.now(),
            interval="5minute"
        )
        
        assert (df["high"] >= df["low"]).all()
        assert (df["high"] >= df["open"]).all()
        assert (df["high"] >= df["close"]).all()
    
    def test_set_custom_historical_data(self, mock_data_source, ohlcv_factory):
        """Test setting custom historical data for testing."""
        custom_df = ohlcv_factory(num_candles=30, trend="up")
        mock_data_source.set_historical_data(738561, custom_df)
        
        df = mock_data_source.get_historical_data(
            instrument_token=738561,
            from_date=datetime.now() - timedelta(days=1),
            to_date=datetime.now(),
            interval="5minute"
        )
        
        assert len(df) == 30


@pytest.mark.integration
class TestMockDataSourceInstruments:
    """Tests for instrument management."""
    
    def test_get_instruments_returns_list(self, mock_data_source):
        """Test getting all instruments."""
        instruments = mock_data_source.get_instruments()
        
        assert isinstance(instruments, list)
        assert len(instruments) > 0
    
    def test_get_instruments_by_exchange(self, mock_data_source):
        """Test filtering instruments by exchange."""
        nse_instruments = mock_data_source.get_instruments(exchange="NSE")
        
        assert all(i.exchange == "NSE" for i in nse_instruments)
    
    def test_instrument_structure(self, mock_data_source):
        """Test instrument has all required fields."""
        instruments = mock_data_source.get_instruments()
        instrument = instruments[0]
        
        assert isinstance(instrument, Instrument)
        assert instrument.instrument_token > 0
        assert instrument.tradingsymbol
        assert instrument.name
        assert instrument.exchange
    
    def test_default_instruments_include_major_stocks(self, mock_data_source):
        """Test default instruments include major stocks."""
        instruments = mock_data_source.get_instruments()
        symbols = [i.tradingsymbol for i in instruments]
        
        assert "RELIANCE" in symbols
        assert "INFY" in symbols
        assert "TCS" in symbols
    
    def test_add_custom_instrument(self, mock_data_source):
        """Test adding custom instrument."""
        new_instrument = Instrument(
            instrument_token=12345,
            exchange_token=999,
            tradingsymbol="TESTSTOCK",
            name="Test Stock Limited",
            exchange="NSE",
            segment="NSE",
            instrument_type="EQ",
            lot_size=1
        )
        
        mock_data_source.add_instrument(new_instrument)
        instruments = mock_data_source.get_instruments()
        
        assert any(i.tradingsymbol == "TESTSTOCK" for i in instruments)


@pytest.mark.integration
class TestMockDataSourceSearch:
    """Tests for instrument search."""
    
    def test_search_by_symbol(self, mock_data_source):
        """Test searching instruments by symbol."""
        results = mock_data_source.search_instruments("RELI")
        
        assert len(results) > 0
        assert any("RELI" in i.tradingsymbol for i in results)
    
    def test_search_by_name(self, mock_data_source):
        """Test searching instruments by company name."""
        results = mock_data_source.search_instruments("Infosys")
        
        assert len(results) > 0
        assert any("INFY" in i.tradingsymbol for i in results)
    
    def test_search_case_insensitive(self, mock_data_source):
        """Test search is case insensitive."""
        results_upper = mock_data_source.search_instruments("RELIANCE")
        results_lower = mock_data_source.search_instruments("reliance")
        
        assert len(results_upper) == len(results_lower)
    
    def test_search_no_results(self, mock_data_source):
        """Test search with no matching results."""
        results = mock_data_source.search_instruments("ZZZZNOTFOUND")
        
        assert results == []


@pytest.mark.integration
class TestMockDataSourceIntegrationScenarios:
    """Integration scenarios combining multiple operations."""
    
    def test_get_quote_and_historical_for_instrument(self, mock_data_source):
        """Test getting both quote and historical data for instrument."""
        # Get instruments
        instruments = mock_data_source.get_instruments()
        reliance = next(i for i in instruments if i.tradingsymbol == "RELIANCE")
        
        # Get current quote
        quote = mock_data_source.get_quote(reliance.instrument_token)
        
        # Get historical data
        df = mock_data_source.get_historical_data(
            instrument_token=reliance.instrument_token,
            from_date=datetime.now() - timedelta(days=1),
            to_date=datetime.now(),
            interval="5minute"
        )
        
        assert quote.symbol == "RELIANCE"
        assert len(df) > 0
    
    def test_simulate_top_gainers_scenario(self, mock_data_source):
        """Test simulating top gainers screening scenario."""
        # Set up custom quotes with different gains
        for i, (token, symbol, gain) in enumerate([
            (738561, "RELIANCE", 3.5),
            (340481, "INFY", 2.1),
            (2953217, "TCS", 1.8),
            (779521, "SBIN", 4.2),
            (408065, "ICICIBANK", 0.5)
        ]):
            mock_data_source.set_quote(token, Quote(
                instrument_token=token,
                symbol=symbol,
                last_price=100 + i,
                volume=500000,
                change_pct=gain,
                timestamp=datetime.now()
            ))
        
        # Get all quotes
        tokens = [738561, 340481, 2953217, 779521, 408065]
        quotes = mock_data_source.get_quotes(tokens)
        
        # Find top gainers
        top_gainers = sorted(
            quotes.values(),
            key=lambda q: q.change_pct,
            reverse=True
        )[:3]
        
        assert top_gainers[0].symbol == "SBIN"
        assert top_gainers[1].symbol == "RELIANCE"
        assert top_gainers[2].symbol == "INFY"
