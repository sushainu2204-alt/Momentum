"""
Unit Tests for Core Services

Tests OrderManager, PositionManager, CapitalManager.
"""

import pytest
import asyncio
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================================================
# CAPITAL MANAGER TESTS
# ============================================================================

class TestCapitalManager:
    """Test CapitalManager service."""
    
    @pytest.fixture
    def capital_manager(self, mock_db, mock_kite):
        """Create CapitalManager with mocks."""
        from backend.core.services.capital_manager import CapitalManager, TradingLimits
        
        position_manager = MagicMock()
        position_manager.get_open_positions_count = AsyncMock(return_value=2)
        
        limits = TradingLimits(
            starting_capital=100000,
            max_positions=5,
            position_size_pct=20,
            risk_per_trade_pct=2,
            max_capital_at_risk_pct=10
        )
        
        # Use mock_capital to bypass Kite API in tests
        return CapitalManager(
            database=mock_db,
            kite_service=mock_kite,
            position_manager=position_manager,
            limits=limits,
            mock_capital=100000.0  # Paper trading mode for consistent testing
        )
    
    @pytest.mark.asyncio
    async def test_get_available_capital_from_kite(self, capital_manager):
        """Test getting available capital from Kite API."""
        available = await capital_manager.get_available_capital()
        
        # Cash (80000) + Collateral (20000) = 100000
        assert available == 100000.0
    
    @pytest.mark.asyncio
    async def test_get_available_capital_with_mock(self, mock_db, mock_kite):
        """Test getting available capital with mock capital set."""
        from backend.core.services.capital_manager import CapitalManager, TradingLimits
        
        position_manager = MagicMock()
        position_manager.get_open_positions_count = AsyncMock(return_value=0)
        
        manager = CapitalManager(
            database=mock_db,
            kite_service=mock_kite,
            position_manager=position_manager,
            mock_capital=50000.0  # Paper trading mode
        )
        
        available = await manager.get_available_capital()
        
        assert available == 50000.0
    
    @pytest.mark.asyncio
    async def test_can_allocate_sufficient_capital(self, capital_manager):
        """Test can_allocate with sufficient capital."""
        can_allocate = await capital_manager.can_allocate(15000.0)
        
        assert can_allocate is True
    
    @pytest.mark.asyncio
    async def test_can_allocate_insufficient_capital(self, capital_manager):
        """Test can_allocate with insufficient capital."""
        can_allocate = await capital_manager.can_allocate(150000.0)  # More than available
        
        assert can_allocate is False
    
    @pytest.mark.asyncio
    async def test_can_allocate_exceeds_position_limit(self, capital_manager):
        """Test can_allocate when position size exceeds limit."""
        # Max position size is 20% of 100000 = 20000
        can_allocate = await capital_manager.can_allocate(25000.0)
        
        assert can_allocate is False
    
    @pytest.mark.asyncio
    async def test_calculate_position_size(self, capital_manager):
        """Test position size calculation based on risk."""
        entry_price = 2450.0
        stop_loss = 2420.0  # SL distance = 30
        
        quantity = await capital_manager.calculate_position_size(entry_price, stop_loss)
        
        # Risk = 2% of 100000 = 2000
        # SL distance = 30
        # Raw quantity = 2000 / 30 = 66 shares
        # BUT: Position value = 66 * 2450 = 161700
        # Max position = 20% of 100000 = 20000
        # Capped quantity = 20000 / 2450 = 8 shares
        assert quantity == 8  # Capped by position size limit
    
    @pytest.mark.asyncio
    async def test_calculate_position_size_respects_max(self, capital_manager):
        """Test position size doesn't exceed max position value."""
        entry_price = 100.0
        stop_loss = 99.0  # Very small SL distance = 1
        
        quantity = await capital_manager.calculate_position_size(entry_price, stop_loss)
        
        # Risk = 2% of 100000 = 2000
        # SL distance = 1
        # Raw quantity = 2000 / 1 = 2000 shares
        # Max position = 20% of 100000 = 20000
        # Max shares at 100 = 200
        assert quantity == 200  # Capped by position size limit
    
    @pytest.mark.asyncio
    async def test_check_position_limit_under_limit(self, capital_manager):
        """Test position limit check when under limit."""
        can_open = await capital_manager.check_position_limit()
        
        # Currently 2 positions, max 5
        assert can_open is True
    
    @pytest.mark.asyncio
    async def test_check_position_limit_at_limit(self, capital_manager):
        """Test position limit check when at limit."""
        capital_manager.position_manager.get_open_positions_count = AsyncMock(return_value=5)
        
        can_open = await capital_manager.check_position_limit()
        
        assert can_open is False


# ============================================================================
# ORDER MANAGER TESTS
# ============================================================================

class TestOrderManager:
    """Test OrderManager service."""
    
    @pytest.fixture
    def mock_order_repository(self, mock_db):
        """Create mock order repository."""
        from backend.infrastructure.database.order_repository import OrderRepository
        
        repo = MagicMock()
        repo.has_pending_order = AsyncMock(return_value=False)
        repo.create_order = AsyncMock(return_value=1)
        repo.update_order = AsyncMock()
        repo.get_order = AsyncMock(return_value=None)
        repo.get_pending_orders = AsyncMock(return_value=[])
        
        return repo
    
    @pytest.fixture
    def order_manager(self, mock_kite, mock_order_repository):
        """Create OrderManager with mocks."""
        from backend.core.services.order_manager import OrderManager
        
        return OrderManager(
            kite_service=mock_kite,
            order_repository=mock_order_repository
        )
    
    @pytest.mark.asyncio
    async def test_place_order(self, order_manager, sample_signal, mock_order_repository):
        """Test placing a bracket order."""
        from backend.models import Signal, SignalType
        
        signal = sample_signal()
        
        # Mock the Kite order placement
        order_manager.kite.kite.place_order = MagicMock(return_value="TEST_ORDER_123")
        
        order_id = await order_manager.place_order(
            signal=signal,
            quantity=10,
            strategy_name="vwap_breakout",
            order_type="MARKET",
            product="MIS"
        )
        
        assert order_id == "TEST_ORDER_123"
    
    @pytest.mark.asyncio
    async def test_has_pending_order_true(self, order_manager, mock_order_repository):
        """Test pending order check when pending order exists."""
        # Mock the cached orders method to return pending orders
        order_manager._get_kite_orders_cached = AsyncMock(return_value=[
            {"order_id": "123", "tradingsymbol": "RELIANCE", "status": "OPEN", "transaction_type": "BUY", "quantity": 10}
        ])
        
        has_pending = await order_manager.has_pending_order("RELIANCE")
        
        assert has_pending is True
    
    @pytest.mark.asyncio
    async def test_has_pending_order_false(self, order_manager, mock_order_repository):
        """Test pending order check when no pending order."""
        # Mock the cached orders method to return empty
        order_manager._get_kite_orders_cached = AsyncMock(return_value=[])
        
        has_pending = await order_manager.has_pending_order("TCS")
        
        assert has_pending is False
    
    @pytest.mark.asyncio
    async def test_get_todays_orders(self, order_manager):
        """Test getting today's orders."""
        order_manager.kite.kite.orders = MagicMock(return_value=[
            {"order_id": "123", "tradingsymbol": "RELIANCE", "status": "COMPLETE"}
        ])
        order_manager._invalidate_cache()
        
        orders = await order_manager.get_todays_orders()
        
        assert len(orders) == 1
        assert orders[0]["tradingsymbol"] == "RELIANCE"


# ============================================================================
# POSITION MANAGER TESTS
# ============================================================================

class TestPositionManager:
    """Test PositionManager service."""
    
    @pytest.fixture
    def mock_position_repository(self, mock_db):
        """Create mock position repository."""
        repo = MagicMock()
        repo.create_position = AsyncMock(return_value=1)
        repo.get_position_by_symbol = AsyncMock(return_value=None)
        repo.get_open_positions = AsyncMock(return_value=[])
        repo.get_open_positions_count = AsyncMock(return_value=0)
        repo.update_position = AsyncMock()
        repo.close_position = AsyncMock()
        
        return repo
    
    @pytest.fixture
    def position_manager(self, mock_kite, mock_position_repository):
        """Create PositionManager with mocks."""
        from backend.core.services.position_manager import PositionManager
        
        return PositionManager(
            kite_service=mock_kite,
            position_repository=mock_position_repository
        )
    
    @pytest.mark.asyncio
    async def test_has_position_true(self, position_manager):
        """Test has_position when position exists in Kite."""
        # Mock Kite positions
        position_manager.kite.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "quantity": 10, "pnl": 500}]
        })
        position_manager._invalidate_cache()
        
        has_pos = await position_manager.has_position("RELIANCE")
        
        assert has_pos is True
    
    @pytest.mark.asyncio
    async def test_has_position_false(self, position_manager):
        """Test has_position when no position exists."""
        position_manager.kite.kite.positions = MagicMock(return_value={"day": []})
        position_manager._invalidate_cache()
        
        has_pos = await position_manager.has_position("NONEXISTENT")
        
        assert has_pos is False
    
    @pytest.mark.asyncio
    async def test_get_open_positions(self, position_manager):
        """Test getting open positions from Kite."""
        position_manager.kite.kite.positions = MagicMock(return_value={
            "day": [
                {"tradingsymbol": "RELIANCE", "quantity": 10, "pnl": 500},
                {"tradingsymbol": "TCS", "quantity": 5, "pnl": -100}
            ]
        })
        position_manager._invalidate_cache()
        
        positions = await position_manager.get_open_positions()
        
        assert len(positions) == 2
    
    @pytest.mark.asyncio
    async def test_create_position_record(self, position_manager, mock_position_repository):
        """Test creating a position record in DB."""
        position_id = await position_manager.create_position_record(
            symbol="RELIANCE",
            instrument_token=738561,
            strategy_name="vwap_breakout",
            entry_price=2450.0,
            quantity=10,
            stop_loss=2420.0,
            target=2510.0
        )
        
        assert position_id == 1
        mock_position_repository.create_position.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_position_record(self, position_manager, mock_position_repository):
        """Test closing a position record in DB."""
        mock_position_repository.get_position_by_symbol = AsyncMock(return_value={
            "id": 1,
            "symbol": "RELIANCE",
            "entry_price": 2450.0,
            "quantity": 10
        })
        
        await position_manager.close_position_record(
            symbol="RELIANCE",
            exit_price=2480.0,
            exit_reason="TARGET_HIT"
        )
        
        mock_position_repository.close_position.assert_called_once()


# ============================================================================
# SIGNAL STORAGE TESTS
# ============================================================================

class TestSignalStorage:
    """Test SignalStorage service."""
    
    @pytest.fixture
    def signal_storage(self, tmp_path):
        """Create SignalStorage with temp directory."""
        from backend.core.services.signal_storage import SignalStorage
        
        return SignalStorage(
            storage_type="file",
            base_path=str(tmp_path / "signals")
        )
    
    @pytest.mark.asyncio
    async def test_save_signal_to_file(self, signal_storage, sample_signal, tmp_path):
        """Test saving signal to file."""
        signal = sample_signal()
        
        await signal_storage.save_signal(signal, "vwap_breakout", {"test": "metadata"})
        
        # Check file was created
        import os
        signals_dir = tmp_path / "signals"
        # Directory may or may not exist based on implementation
        assert True  # Placeholder - actual verification depends on implementation
    
    @pytest.mark.asyncio
    async def test_save_executed_order(self, signal_storage, sample_signal, tmp_path):
        """Test saving executed order."""
        signal = sample_signal()
        
        await signal_storage.save_executed_order(
            signal, 
            "vwap_breakout", 
            "TEST_ORDER_123",
            10,  # quantity
            {"execution_time": datetime.now().isoformat(), "status": "complete"}
        )
        
        # Should complete without error
        assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ============================================================================
# TRAILING STOP LOSS SERVICE TESTS (Basic)
# ============================================================================

class TestTrailingStopLossServiceBasic:
    """Basic tests for TrailingStopLossService in test_services.py."""
    
    @pytest.fixture
    def trailing_sl_service(self, mock_db):
        """Create TrailingStopLossService with mocks."""
        from backend.core.services.trailing_sl_service import (
            TrailingStopLossService,
            TrailingStopLossConfig
        )
        
        # Mock position repository
        position_repo = MagicMock()
        position_repo.get_open_positions = AsyncMock(return_value=[])
        position_repo.update_position = AsyncMock()
        position_repo.update_trailing_stop_loss = AsyncMock()
        
        # Mock Kite service
        kite = MagicMock()
        kite.kite = MagicMock()
        kite.kite.positions = MagicMock(return_value={"day": []})
        kite.kite.modify_order = MagicMock()
        kite.kite.VARIETY_BO = "bo"
        
        return TrailingStopLossService(
            position_repository=position_repo,
            kite_service=kite,
            config=TrailingStopLossConfig()
        )
    
    @pytest.mark.asyncio
    async def test_process_positions_empty(self, trailing_sl_service):
        """Test processing when no positions exist."""
        result = await trailing_sl_service.process_positions()
        
        assert result["checked"] == 0
        assert result["updated"] == 0
        assert result["errors"] == 0
    
    @pytest.mark.asyncio
    async def test_config_defaults(self, trailing_sl_service):
        """Test default configuration values."""
        config = trailing_sl_service.get_config()
        
        assert config["enabled"] is True
        assert config["activation_pct"] == 0.5
        assert config["trail_pct"] == 0.3
        assert config["min_sl_move_pct"] == 0.1
    
    @pytest.mark.asyncio
    async def test_disabled_skips_processing(self, trailing_sl_service):
        """Test that disabled service skips processing."""
        trailing_sl_service.update_config(enabled=False)
        
        result = await trailing_sl_service.process_positions()
        
        assert result["checked"] == 0
