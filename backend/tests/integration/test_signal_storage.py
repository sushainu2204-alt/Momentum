"""
Integration Tests for Signal Storage Service

Tests the SignalStorage service with both file and database backends:
1. File-based storage operations
2. Database storage operations
3. Signal retrieval
4. Order execution tracking
"""

import pytest
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.core.services.storage.signal_storage import SignalStorage
from backend.core.models import Signal, SignalType
from backend.config import PathsConfig


@pytest.fixture
def temp_storage_dir():
    """Create temporary directory for file storage tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def file_storage(temp_storage_dir):
    """Create file-based SignalStorage."""
    paths = PathsConfig(
        signals_dir=f"{temp_storage_dir}/signals",
        orders_dir=f"{temp_storage_dir}/orders",
        logs_dir=f"{temp_storage_dir}/logs"
    )
    return SignalStorage(storage_type="file", paths_config=paths)


@pytest.fixture
def db_storage(mock_db):
    """Create database-backed SignalStorage."""
    return SignalStorage(storage_type="database", database=mock_db)


@pytest.fixture
def sample_signal():
    """Create sample signal for testing."""
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
class TestFileBasedStorage:
    """Tests for file-based signal storage."""
    
    @pytest.mark.asyncio
    async def test_save_signal_creates_directory(self, file_storage, sample_signal, temp_storage_dir):
        """Test that saving creates date directory structure."""
        await file_storage.save_signal(sample_signal, "vwap_breakout")
        
        date_str = sample_signal.timestamp.strftime("%Y-%m-%d")
        expected_dir = Path(temp_storage_dir) / "signals" / date_str
        
        assert expected_dir.exists()
    
    @pytest.mark.asyncio
    async def test_save_signal_creates_json_file(self, file_storage, sample_signal, temp_storage_dir):
        """Test that saving creates JSON file with strategy name."""
        await file_storage.save_signal(sample_signal, "vwap_breakout")
        
        date_str = sample_signal.timestamp.strftime("%Y-%m-%d")
        expected_file = Path(temp_storage_dir) / "signals" / date_str / "vwap_breakout_signals.json"
        
        assert expected_file.exists()
    
    @pytest.mark.asyncio
    async def test_save_multiple_signals_same_strategy(
        self, file_storage, sample_signal, temp_storage_dir
    ):
        """Test saving multiple signals appends to same file."""
        await file_storage.save_signal(sample_signal, "vwap_breakout")
        await file_storage.save_signal(sample_signal, "vwap_breakout")
        await file_storage.save_signal(sample_signal, "vwap_breakout")
        
        date_str = sample_signal.timestamp.strftime("%Y-%m-%d")
        filepath = Path(temp_storage_dir) / "signals" / date_str / "vwap_breakout_signals.json"
        
        import json
        with open(filepath) as f:
            signals = json.load(f)
        
        assert len(signals) == 3
    
    @pytest.mark.asyncio
    async def test_save_signals_different_strategies(
        self, file_storage, sample_signal, temp_storage_dir
    ):
        """Test saving signals creates separate files per strategy."""
        await file_storage.save_signal(sample_signal, "vwap_breakout")
        await file_storage.save_signal(sample_signal, "bullish_flag")
        
        date_str = sample_signal.timestamp.strftime("%Y-%m-%d")
        signal_dir = Path(temp_storage_dir) / "signals" / date_str
        
        assert (signal_dir / "vwap_breakout_signals.json").exists()
        assert (signal_dir / "bullish_flag_signals.json").exists()
    
    def test_get_signals_returns_list(self, file_storage):
        """Test get_signals returns list (may be empty)."""
        signals = file_storage._get_from_file(datetime.now(), None)
        
        assert isinstance(signals, list)
    
    def test_get_signals_nonexistent_date(self, file_storage):
        """Test get_signals for date with no signals."""
        from datetime import datetime, timedelta
        future_date = datetime.now() + timedelta(days=30)
        
        signals = file_storage._get_from_file(future_date, None)
        
        assert signals == []
    
    @pytest.mark.asyncio
    async def test_signal_data_structure(self, file_storage, sample_signal, temp_storage_dir):
        """Test that saved signal contains all required fields."""
        metadata = {"volume_ratio": 2.1}
        await file_storage.save_signal(sample_signal, "vwap_breakout", metadata)
        
        date_str = sample_signal.timestamp.strftime("%Y-%m-%d")
        filepath = Path(temp_storage_dir) / "signals" / date_str / "vwap_breakout_signals.json"
        
        import json
        with open(filepath) as f:
            signals = json.load(f)
        
        signal_data = signals[0]
        assert "timestamp" in signal_data
        assert "symbol" in signal_data
        assert "signal_type" in signal_data
        assert "price" in signal_data
        assert "stop_loss" in signal_data
        assert "target" in signal_data
        assert "quantity" in signal_data
        assert "reason" in signal_data
        assert "metadata" in signal_data
        assert signal_data["metadata"]["volume_ratio"] == 2.1


@pytest.mark.integration
@pytest.mark.asyncio
class TestDatabaseStorage:
    """Tests for database-backed signal storage."""
    
    async def test_save_signal_calls_repository(self, db_storage, sample_signal, mock_db):
        """Test that saving calls database repository."""
        await db_storage.save_signal(sample_signal, "vwap_breakout")
        
        assert len(mock_db.tables["signals"]) == 1
    
    async def test_save_signal_with_metadata(self, db_storage, sample_signal, mock_db):
        """Test saving with metadata."""
        metadata = {"gain_pct": 2.5, "vwap": 2430.50}
        await db_storage.save_signal(sample_signal, "vwap_breakout", metadata)
        
        stored = mock_db.tables["signals"][0]
        assert "metadata" in stored
    
    async def test_get_signals_from_database(self, db_storage, sample_signal):
        """Test retrieving signals from database."""
        await db_storage.save_signal(sample_signal, "vwap_breakout")
        
        signals = await db_storage.get_signals(datetime.now())
        
        assert isinstance(signals, list)


@pytest.mark.integration
@pytest.mark.asyncio
class TestOrderStorage:
    """Tests for executed order storage."""
    
    async def test_save_executed_order_creates_file(
        self, file_storage, sample_signal, temp_storage_dir
    ):
        """Test saving executed order creates file in orders directory."""
        execution_result = {
            "status": "executed",
            "reason": "Order filled",
            "metadata": {"broker_id": "12345"}
        }
        
        await file_storage.save_executed_order(
            signal=sample_signal,
            strategy_name="vwap_breakout",
            order_id="ORDER_123",
            quantity=10,
            execution_result=execution_result
        )
        
        date_str = sample_signal.timestamp.strftime("%Y-%m-%d")
        expected_file = Path(temp_storage_dir) / "orders" / date_str / "vwap_breakout_orders.json"
        
        assert expected_file.exists()
    
    async def test_order_data_structure(
        self, file_storage, sample_signal, temp_storage_dir
    ):
        """Test that order contains all required fields."""
        execution_result = {
            "status": "executed",
            "reason": "Order filled"
        }
        
        await file_storage.save_executed_order(
            signal=sample_signal,
            strategy_name="vwap_breakout",
            order_id="ORDER_123",
            quantity=10,
            execution_result=execution_result
        )
        
        date_str = sample_signal.timestamp.strftime("%Y-%m-%d")
        filepath = Path(temp_storage_dir) / "orders" / date_str / "vwap_breakout_orders.json"
        
        import json
        with open(filepath) as f:
            orders = json.load(f)
        
        order = orders[0]
        assert order["order_id"] == "ORDER_123"
        assert order["quantity"] == 10
        assert order["execution_status"] == "executed"
        assert order["symbol"] == "RELIANCE"


@pytest.mark.integration
class TestStorageInitialization:
    """Tests for storage initialization."""
    
    def test_file_storage_creates_directories(self, temp_storage_dir):
        """Test file storage creates necessary directories."""
        paths = PathsConfig(
            signals_dir=f"{temp_storage_dir}/signals",
            orders_dir=f"{temp_storage_dir}/orders",
            logs_dir=f"{temp_storage_dir}/logs"
        )
        
        storage = SignalStorage(storage_type="file", paths_config=paths)
        
        assert Path(paths.signals_dir).exists()
        assert Path(paths.orders_dir).exists()
    
    def test_database_storage_requires_database(self):
        """Test database storage raises error without database."""
        with pytest.raises(ValueError) as exc_info:
            SignalStorage(storage_type="database", database=None)
        
        assert "Database instance required" in str(exc_info.value)
    
    def test_database_storage_creates_repository(self, mock_db):
        """Test database storage creates repository."""
        storage = SignalStorage(storage_type="database", database=mock_db)
        
        assert storage.repository is not None
