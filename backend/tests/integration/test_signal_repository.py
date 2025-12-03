"""
Integration Tests for Signal Repository

Tests the SignalRepository with MockDatabase to verify:
1. Signal saving and retrieval
2. Query filtering by date, symbol, strategy
3. Daily summary generation
4. Error handling
"""

import pytest
from datetime import datetime, timedelta

from backend.infrastructure.database.signal_repository import SignalRepository
from backend.core.models import Signal, SignalType


@pytest.fixture
def signal_repository(mock_db):
    """Create SignalRepository with mock database."""
    return SignalRepository(mock_db)


@pytest.fixture
def sample_signal():
    """Create a sample signal for testing."""
    return Signal(
        symbol="RELIANCE",
        instrument_token=738561,
        signal_type=SignalType.BUY,
        price=2450.0,
        stop_loss=2420.0,
        target=2510.0,
        quantity=10,
        reason="VWAP breakout with volume surge",
        timestamp=datetime.now()
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestSignalRepositorySave:
    """Tests for saving signals to database."""
    
    async def test_save_signal_returns_id(self, signal_repository, sample_signal):
        """Test that saving a signal returns a valid ID."""
        signal_id = await signal_repository.save_signal(
            signal=sample_signal,
            strategy_name="vwap_breakout"
        )
        
        assert signal_id is not None
        assert signal_id == 1  # First insert should be ID 1
    
    async def test_save_signal_with_metadata(self, signal_repository, sample_signal):
        """Test saving signal with additional metadata."""
        metadata = {
            "gain_pct": 2.5,
            "volume_ratio": 2.1,
            "vwap": 2430.50,
            "ema_20": 2425.30
        }
        
        signal_id = await signal_repository.save_signal(
            signal=sample_signal,
            strategy_name="vwap_breakout",
            metadata=metadata
        )
        
        assert signal_id is not None
    
    async def test_save_multiple_signals_increments_id(self, signal_repository, sample_signal):
        """Test that multiple saves return incrementing IDs."""
        id1 = await signal_repository.save_signal(sample_signal, "vwap_breakout")
        id2 = await signal_repository.save_signal(sample_signal, "vwap_breakout")
        id3 = await signal_repository.save_signal(sample_signal, "bullish_flag")
        
        assert id1 == 1
        assert id2 == 2
        assert id3 == 3
    
    async def test_save_signal_stores_all_fields(self, signal_repository, sample_signal, mock_db):
        """Test that all signal fields are stored in database."""
        await signal_repository.save_signal(sample_signal, "vwap_breakout")
        
        # Check the data was stored
        stored = mock_db.tables["signals"][0]
        
        assert stored["symbol"] == "RELIANCE"
        assert stored["strategy"] == "vwap_breakout"
        assert stored["price"] == 2450.0
        assert stored["stop_loss"] == 2420.0
        assert stored["target"] == 2510.0
        assert stored["quantity"] == 10


@pytest.mark.integration
@pytest.mark.asyncio
class TestSignalRepositoryRetrieve:
    """Tests for retrieving signals from database."""
    
    async def test_get_signals_by_date(self, signal_repository, sample_signal, mock_db):
        """Test retrieving signals for a specific date."""
        # Save some signals
        await signal_repository.save_signal(sample_signal, "vwap_breakout")
        await signal_repository.save_signal(sample_signal, "bullish_flag")
        
        # Retrieve signals
        signals = await signal_repository.get_signals_by_date(datetime.now())
        
        assert isinstance(signals, list)
    
    async def test_get_signals_by_date_with_strategy_filter(
        self, signal_repository, sample_signal, mock_db
    ):
        """Test retrieving signals filtered by strategy."""
        await signal_repository.save_signal(sample_signal, "vwap_breakout")
        await signal_repository.save_signal(sample_signal, "bullish_flag")
        
        signals = await signal_repository.get_signals_by_date(
            datetime.now(),
            strategy_name="vwap_breakout"
        )
        
        assert isinstance(signals, list)
    
    async def test_get_signals_by_symbol(self, signal_repository, sample_signal):
        """Test retrieving signals for a specific symbol."""
        await signal_repository.save_signal(sample_signal, "vwap_breakout")
        
        signals = await signal_repository.get_signals_by_symbol("RELIANCE")
        
        assert isinstance(signals, list)
    
    async def test_get_signals_by_symbol_with_date_range(self, signal_repository, sample_signal):
        """Test retrieving signals for symbol within date range."""
        await signal_repository.save_signal(sample_signal, "vwap_breakout")
        
        start_date = datetime.now() - timedelta(days=1)
        end_date = datetime.now() + timedelta(days=1)
        
        signals = await signal_repository.get_signals_by_symbol(
            "RELIANCE",
            start_date=start_date,
            end_date=end_date
        )
        
        assert isinstance(signals, list)
    
    async def test_get_signals_by_strategy(self, signal_repository, sample_signal):
        """Test retrieving signals for a specific strategy."""
        await signal_repository.save_signal(sample_signal, "vwap_breakout")
        await signal_repository.save_signal(sample_signal, "vwap_breakout")
        
        signals = await signal_repository.get_signals_by_strategy("vwap_breakout")
        
        assert isinstance(signals, list)
    
    async def test_get_signals_by_strategy_with_limit(self, signal_repository, sample_signal):
        """Test retrieving limited signals for strategy."""
        # Save multiple signals
        for _ in range(5):
            await signal_repository.save_signal(sample_signal, "vwap_breakout")
        
        signals = await signal_repository.get_signals_by_strategy(
            "vwap_breakout",
            limit=3
        )
        
        assert isinstance(signals, list)


@pytest.mark.integration
@pytest.mark.asyncio
class TestSignalRepositorySummary:
    """Tests for daily summary generation."""
    
    async def test_get_daily_summary_structure(self, signal_repository, sample_signal):
        """Test daily summary returns correct structure."""
        await signal_repository.save_signal(sample_signal, "vwap_breakout")
        
        summary = await signal_repository.get_daily_summary(datetime.now())
        
        assert "date" in summary
        assert "total_signals" in summary
        assert "strategies" in summary
    
    async def test_get_daily_summary_empty_date(self, signal_repository):
        """Test daily summary for date with no signals."""
        future_date = datetime.now() + timedelta(days=30)
        
        summary = await signal_repository.get_daily_summary(future_date)
        
        assert summary["total_signals"] == 0
        assert summary["strategies"] == {}


@pytest.mark.integration
@pytest.mark.asyncio
class TestSignalRepositoryEdgeCases:
    """Tests for edge cases and error handling."""
    
    async def test_save_signal_with_none_stop_loss(self, signal_repository):
        """Test saving signal without stop loss."""
        signal = Signal(
            symbol="RELIANCE",
            instrument_token=738561,
            signal_type=SignalType.BUY,
            price=2450.0,
            stop_loss=None,
            target=2510.0,
            quantity=10,
            reason="Test signal",
            timestamp=datetime.now()
        )
        
        signal_id = await signal_repository.save_signal(signal, "test_strategy")
        assert signal_id is not None
    
    async def test_save_signal_with_none_target(self, signal_repository):
        """Test saving signal without target."""
        signal = Signal(
            symbol="RELIANCE",
            instrument_token=738561,
            signal_type=SignalType.SELL,
            price=2450.0,
            stop_loss=2480.0,
            target=None,
            quantity=10,
            reason="Exit signal",
            timestamp=datetime.now()
        )
        
        signal_id = await signal_repository.save_signal(signal, "test_strategy")
        assert signal_id is not None
    
    async def test_get_signals_nonexistent_symbol(self, signal_repository):
        """Test retrieving signals for symbol that doesn't exist."""
        signals = await signal_repository.get_signals_by_symbol("NONEXISTENT")
        
        assert signals == []
    
    async def test_get_signals_nonexistent_strategy(self, signal_repository):
        """Test retrieving signals for strategy that doesn't exist."""
        signals = await signal_repository.get_signals_by_strategy("nonexistent_strategy")
        
        assert signals == []
