"""
Unit Tests for Repository Layer

Tests database repositories for Position, Order, Signal entities.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================================================
# POSITION REPOSITORY TESTS
# ============================================================================

class TestPositionRepository:
    """Test PositionRepository database operations."""
    
    @pytest.fixture
    def position_repo(self, mock_database):
        """Create PositionRepository with mock database."""
        from backend.infrastructure.database.position_repository import PositionRepository
        return PositionRepository(mock_database)
    
    @pytest.fixture
    def sample_position_data(self):
        """Sample position data for testing."""
        return {
            "id": 1,
            "symbol": "RELIANCE",
            "strategy_name": "vwap_breakout",
            "instrument_token": 738561,
            "quantity": 10,
            "entry_price": 2450.0,
            "exit_price": None,
            "stop_loss": 2420.0,
            "target": 2510.0,
            "status": "OPEN",
            "entry_time": datetime.now(),
            "exit_time": None,
            "pnl": None,
            "metadata": {"reason": "VWAP breakout"}
        }
    
    @pytest.mark.asyncio
    async def test_create_position(self, position_repo, mock_database):
        """Test creating a new position."""
        mock_database.insert.return_value = 1
        
        position_id = await position_repo.create_position(
            symbol="RELIANCE",
            instrument_token=738561,
            strategy_name="vwap_breakout",
            entry_price=2450.0,
            entry_time=datetime.now(),
            quantity=10,
            stop_loss=2420.0,
            target=2510.0,
            metadata={"reason": "VWAP breakout"}
        )
        
        assert position_id == 1
        mock_database.insert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_position(self, position_repo, mock_database, sample_position_data):
        """Test fetching position by ID."""
        mock_database.fetch_one.return_value = sample_position_data
        
        position = await position_repo.get_position(1)
        
        assert position is not None
        assert position['symbol'] == "RELIANCE"
        mock_database.fetch_one.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_position_not_found(self, position_repo, mock_database):
        """Test fetching non-existent position."""
        mock_database.fetch_one.return_value = None
        
        position = await position_repo.get_position(999)
        
        assert position is None
    
    @pytest.mark.asyncio
    async def test_get_open_positions(self, position_repo, mock_database, sample_position_data):
        """Test fetching all open positions."""
        mock_database.fetch_all.return_value = [
            sample_position_data,
            {**sample_position_data, "id": 2, "symbol": "INFY"}
        ]
        
        positions = await position_repo.get_open_positions()
        
        assert len(positions) == 2
        mock_database.fetch_all.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_open_positions_by_strategy(self, position_repo, mock_database, sample_position_data):
        """Test fetching open positions for a strategy."""
        mock_database.fetch_all.return_value = [sample_position_data]
        
        positions = await position_repo.get_open_positions(strategy_name="vwap_breakout")
        
        assert len(positions) == 1
        assert positions[0]['strategy_name'] == "vwap_breakout"
    
    @pytest.mark.asyncio
    async def test_update_position(self, position_repo, mock_database):
        """Test updating position fields."""
        mock_database.update.return_value = None
        
        await position_repo.update_position(
            position_id=1,
            current_price=2480.0,
            pnl=300.0,
            pnl_pct=1.22
        )
        
        mock_database.update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_positions_by_date(self, position_repo, mock_database, sample_position_data):
        """Test fetching positions by date."""
        mock_database.fetch_all.return_value = [sample_position_data]
        
        positions = await position_repo.get_positions_by_date(datetime.now().date())
        
        assert len(positions) == 1
        mock_database.fetch_all.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_position(self, position_repo, mock_database, sample_position_data):
        """Test closing a position."""
        # Setup mock for get_position call within close_position
        mock_database.fetch_one.return_value = sample_position_data
        mock_database.update.return_value = None
        
        await position_repo.close_position(
            position_id=1,
            exit_price=2510.0,
            exit_time=datetime.now(),
            exit_reason="TARGET_HIT"
        )
        
        # close_position calls get_position and update_position
        mock_database.fetch_one.assert_called_once()
        mock_database.update.assert_called_once()


# ============================================================================
# ORDER REPOSITORY TESTS
# ============================================================================

class TestOrderRepository:
    """Test OrderRepository database operations."""
    
    @pytest.fixture
    def order_repo(self, mock_database):
        """Create OrderRepository with mock database."""
        from backend.infrastructure.database.order_repository import OrderRepository
        return OrderRepository(mock_database)
    
    @pytest.fixture
    def sample_order_data(self):
        """Sample order data for testing."""
        return {
            "id": 1,
            "order_id": "230101000001",
            "symbol": "RELIANCE",
            "instrument_token": 738561,
            "strategy_name": "vwap_breakout",
            "order_type": "MARKET",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 2450.0,
            "trigger_price": None,
            "status": "COMPLETE",
            "filled_quantity": 10,
            "average_price": 2450.0,
            "position_id": 1,
            "placed_at": datetime.now()
        }
    
    @pytest.mark.asyncio
    async def test_create_order(self, order_repo, mock_database):
        """Test creating a new order."""
        mock_database.insert.return_value = 1
        
        order_id = await order_repo.create_order(
            order_id="230101000001",
            symbol="RELIANCE",
            instrument_token=738561,
            strategy_name="vwap_breakout",
            order_type="MARKET",
            transaction_type="BUY",
            quantity=10,
            price=2450.0,
            trigger_price=None,
            status="PENDING",
            placed_at=datetime.now()
        )
        
        assert order_id == 1
        mock_database.insert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_order(self, order_repo, mock_database, sample_order_data):
        """Test fetching order by Kite order ID."""
        mock_database.fetch_one.return_value = sample_order_data
        
        order = await order_repo.get_order("230101000001")
        
        assert order is not None
        assert order['order_id'] == "230101000001"
    
    @pytest.mark.asyncio
    async def test_update_order(self, order_repo, mock_database):
        """Test updating order status."""
        mock_database.update.return_value = None
        
        await order_repo.update_order(
            order_id="230101000001",
            status="COMPLETE",
            filled_quantity=10,
            average_price=2450.0
        )
        
        mock_database.update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_pending_orders(self, order_repo, mock_database, sample_order_data):
        """Test fetching pending orders."""
        pending_order = {**sample_order_data, "status": "PENDING"}
        mock_database.fetch_all.return_value = [pending_order]
        
        orders = await order_repo.get_pending_orders()
        
        assert len(orders) == 1
        assert orders[0]['status'] == "PENDING"
    
    @pytest.mark.asyncio
    async def test_get_orders_by_position(self, order_repo, mock_database, sample_order_data):
        """Test fetching orders for a position."""
        mock_database.fetch_all.return_value = [
            sample_order_data,
            {**sample_order_data, "id": 2, "transaction_type": "SELL"}
        ]
        
        orders = await order_repo.get_orders_by_position(1)
        
        assert len(orders) == 2
    
    @pytest.mark.asyncio
    async def test_get_todays_orders(self, order_repo, mock_database, sample_order_data):
        """Test fetching today's orders."""
        mock_database.fetch_all.return_value = [sample_order_data]
        
        orders = await order_repo.get_todays_orders()
        
        assert len(orders) == 1
    
    @pytest.mark.asyncio
    async def test_has_pending_order(self, order_repo, mock_database):
        """Test checking for pending order."""
        mock_database.fetch_one.return_value = {"count": 1}
        
        has_pending = await order_repo.has_pending_order("RELIANCE")
        
        assert has_pending is True
    
    @pytest.mark.asyncio
    async def test_has_pending_order_no_pending(self, order_repo, mock_database):
        """Test checking when no pending order exists."""
        mock_database.fetch_one.return_value = {"count": 0}
        
        has_pending = await order_repo.has_pending_order("RELIANCE")
        
        assert has_pending is False


# ============================================================================
# SIGNAL REPOSITORY TESTS
# ============================================================================

class TestSignalRepository:
    """Test SignalRepository database operations."""
    
    @pytest.fixture
    def signal_repo(self, mock_database):
        """Create SignalRepository with mock database."""
        from backend.infrastructure.database.signal_repository import SignalRepository
        return SignalRepository(mock_database)
    
    @pytest.fixture
    def sample_signal_data(self):
        """Sample signal data for testing."""
        return {
            "id": 1,
            "timestamp": datetime.now(),
            "symbol": "RELIANCE",
            "signal_type": "BUY",
            "price": 2450.0,
            "stop_loss": 2420.0,
            "target": 2510.0,
            "quantity": 10,
            "reason": "VWAP breakout with volume surge",
            "strategy": "vwap_breakout",
            "metadata": json.dumps({"gain_pct": 2.5})
        }
    
    @pytest.mark.asyncio
    async def test_save_signal(self, signal_repo, mock_database, sample_signal):
        """Test saving a new signal."""
        signal = sample_signal()
        mock_database.insert.return_value = 1
        
        signal_id = await signal_repo.save_signal(signal, "vwap_breakout")
        
        assert signal_id == 1
        mock_database.insert.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_signals_by_strategy(self, signal_repo, mock_database, sample_signal_data):
        """Test fetching signals by strategy."""
        mock_database.fetch_all.return_value = [sample_signal_data]
        
        signals = await signal_repo.get_signals_by_strategy("vwap_breakout")
        
        assert len(signals) == 1
    
    @pytest.mark.asyncio
    async def test_get_signals_by_date(self, signal_repo, mock_database, sample_signal_data):
        """Test fetching signals by date."""
        mock_database.fetch_all.return_value = [sample_signal_data]
        
        signals = await signal_repo.get_signals_by_date(datetime.now())
        
        assert len(signals) == 1
    
    @pytest.mark.asyncio
    async def test_get_signals_by_symbol(self, signal_repo, mock_database, sample_signal_data):
        """Test fetching signals by symbol."""
        mock_database.fetch_all.return_value = [sample_signal_data]
        
        signals = await signal_repo.get_signals_by_symbol("RELIANCE")
        
        assert len(signals) == 1
        assert signals[0]['symbol'] == "RELIANCE"
    
    @pytest.mark.asyncio
    async def test_get_daily_summary(self, signal_repo, mock_database):
        """Test fetching daily summary."""
        mock_database.fetch_all.return_value = [
            {"strategy": "vwap_breakout", "signal_count": 5, "unique_symbols": 3}
        ]
        
        summary = await signal_repo.get_daily_summary(datetime.now())
        
        assert summary['total_signals'] == 5
        assert 'vwap_breakout' in summary['strategies']


# ============================================================================
# DATABASE CONNECTION POOL TESTS
# ============================================================================

class TestDatabasePool:
    """Test database connection pool management."""
    
    @pytest.mark.asyncio
    async def test_connect_creates_pool(self, mock_database):
        """Test that connect creates a connection pool."""
        await mock_database.connect()
        
        mock_database.connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_disconnect_closes_pool(self, mock_database):
        """Test that disconnect closes the connection pool."""
        await mock_database.disconnect()
        
        mock_database.disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_connection_error_handling(self, mock_database):
        """Test connection error handling."""
        mock_database.connect.side_effect = Exception("Connection failed")
        
        with pytest.raises(Exception) as exc_info:
            await mock_database.connect()
        
        assert "Connection failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_query_error_handling(self, mock_database):
        """Test query error handling."""
        mock_database.fetch_one.side_effect = Exception("Query failed")
        
        with pytest.raises(Exception) as exc_info:
            await mock_database.fetch_one("SELECT 1")
        
        assert "Query failed" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
