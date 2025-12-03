"""
Unit Tests for Order Manager Service

Tests order placement, cancellation, and lifecycle management.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from backend.core.services.trading.order_manager import OrderManager, OrderResult
from backend.core.models import Signal, SignalType


class TestOrderResult:
    """Test OrderResult dataclass."""
    
    def test_default_values(self):
        """Test default values for OrderResult."""
        result = OrderResult()
        
        assert result.entry_order_id is None
        assert result.sl_order_id is None
        assert result.target_order_id is None
        assert result.quantity is None
        assert result.stop_loss is None
        assert result.target is None
        assert result.success is False
        assert result.error is None
    
    def test_successful_order_result(self):
        """Test successful order result."""
        result = OrderResult(
            entry_order_id="ORD123",
            sl_order_id="SL456",
            quantity=100,
            stop_loss=95.0,
            target=110.0,
            success=True
        )
        
        assert result.entry_order_id == "ORD123"
        assert result.sl_order_id == "SL456"
        assert result.quantity == 100
        assert result.success is True


class TestOrderManager:
    """Test OrderManager service."""
    
    @pytest.fixture
    def mock_kite_service(self):
        """Create mock Kite service."""
        kite = Mock()
        kite.kite = Mock()
        
        # Setup constants
        kite.kite.VARIETY_REGULAR = "regular"
        kite.kite.EXCHANGE_NSE = "NSE"
        kite.kite.ORDER_TYPE_MARKET = "MARKET"
        kite.kite.ORDER_TYPE_LIMIT = "LIMIT"
        kite.kite.ORDER_TYPE_SLM = "SL-M"
        kite.kite.PRODUCT_MIS = "MIS"
        kite.kite.PRODUCT_CNC = "CNC"
        
        # Mock methods
        kite.kite.place_order = Mock(return_value="ORD123")
        kite.kite.cancel_order = Mock()
        kite.kite.modify_order = Mock()
        kite.kite.orders = Mock(return_value=[])
        kite.kite.positions = Mock(return_value={"day": []})
        
        return kite
    
    @pytest.fixture
    def mock_order_repository(self):
        """Create mock order repository."""
        repo = Mock()
        repo.create_order = AsyncMock(return_value=1)
        repo.update_order = AsyncMock(return_value=True)
        repo.get_order = AsyncMock(return_value=None)
        repo.has_pending_order = AsyncMock(return_value=False)
        repo.get_pending_orders = AsyncMock(return_value=[])
        repo.get_orders_by_symbol = AsyncMock(return_value=[])
        return repo
    
    @pytest.fixture
    def order_manager(self, mock_kite_service, mock_order_repository):
        """Create order manager with mocked dependencies."""
        return OrderManager(
            kite_service=mock_kite_service,
            order_repository=mock_order_repository
        )
    
    @pytest.fixture
    def sample_signal(self):
        """Create sample trading signal."""
        return Signal(
            symbol="RELIANCE",
            instrument_token=738561,
            signal_type=SignalType.BUY,
            price=2500.0,
            stop_loss=2450.0,
            target=2600.0,
            quantity=10,
            reason="VWAP breakout",
            timestamp=datetime.now()
        )


class TestHasPendingOrder(TestOrderManager):
    """Test has_pending_order method."""
    
    @pytest.mark.asyncio
    async def test_returns_true_when_pending_order_exists(self, order_manager, mock_kite_service):
        """Test returns True when pending order exists in Kite."""
        mock_kite_service.kite.orders.return_value = [
            {
                'order_id': 'ORD123',
                'tradingsymbol': 'RELIANCE',
                'status': 'OPEN',
                'transaction_type': 'BUY',
                'quantity': 100
            }
        ]
        
        result = await order_manager.has_pending_order("RELIANCE")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_returns_false_when_no_pending_order(self, order_manager, mock_kite_service):
        """Test returns False when no pending order exists."""
        mock_kite_service.kite.orders.return_value = [
            {
                'order_id': 'ORD123',
                'tradingsymbol': 'RELIANCE',
                'status': 'COMPLETE',  # Not pending
                'transaction_type': 'BUY',
                'quantity': 100
            }
        ]
        
        result = await order_manager.has_pending_order("RELIANCE")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_filters_by_transaction_type(self, order_manager, mock_kite_service):
        """Test filtering by transaction type."""
        mock_kite_service.kite.orders.return_value = [
            {
                'order_id': 'ORD123',
                'tradingsymbol': 'RELIANCE',
                'status': 'OPEN',
                'transaction_type': 'SELL',
                'quantity': 100
            }
        ]
        
        # Looking for BUY, but only SELL exists
        result = await order_manager.has_pending_order("RELIANCE", "BUY")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_returns_false_on_kite_error_with_empty_cache(self, order_manager, mock_kite_service):
        """Test returns False when Kite fails and cache is empty."""
        # When Kite fails, _get_kite_orders_cached returns empty cache (not exception)
        mock_kite_service.kite.orders.side_effect = Exception("API Error")
        
        result = await order_manager.has_pending_order("RELIANCE")
        
        # Returns False because empty cache has no pending orders
        assert result is False


class TestGetPendingOrders(TestOrderManager):
    """Test get_pending_orders method."""
    
    @pytest.mark.asyncio
    async def test_returns_pending_orders(self, order_manager, mock_kite_service):
        """Test returns all pending orders."""
        mock_kite_service.kite.orders.return_value = [
            {'order_id': 'ORD1', 'tradingsymbol': 'RELIANCE', 'status': 'OPEN'},
            {'order_id': 'ORD2', 'tradingsymbol': 'TCS', 'status': 'TRIGGER PENDING'},
            {'order_id': 'ORD3', 'tradingsymbol': 'INFY', 'status': 'COMPLETE'}
        ]
        
        result = await order_manager.get_pending_orders()
        
        assert len(result) == 2
        assert all(o['status'] in ['OPEN', 'TRIGGER PENDING'] for o in result)
    
    @pytest.mark.asyncio
    async def test_filters_by_symbol(self, order_manager, mock_kite_service):
        """Test filtering pending orders by symbol."""
        mock_kite_service.kite.orders.return_value = [
            {'order_id': 'ORD1', 'tradingsymbol': 'RELIANCE', 'status': 'OPEN'},
            {'order_id': 'ORD2', 'tradingsymbol': 'TCS', 'status': 'OPEN'}
        ]
        
        result = await order_manager.get_pending_orders("RELIANCE")
        
        assert len(result) == 1
        assert result[0]['tradingsymbol'] == 'RELIANCE'


class TestPlaceOrder(TestOrderManager):
    """Test place_order method."""
    
    @pytest.mark.asyncio
    async def test_places_entry_and_sl_orders(self, order_manager, mock_kite_service, sample_signal):
        """Test placing entry order and SL order."""
        # Setup mock returns for entry and SL orders
        mock_kite_service.kite.place_order.side_effect = ["ENTRY_ORD123", "SL_ORD456"]
        
        result = await order_manager.place_order(
            signal=sample_signal,
            quantity=10,
            strategy_name="vwap_breakout"
        )
        
        assert result is not None
        assert result.entry_order_id == "ENTRY_ORD123"
        assert result.sl_order_id == "SL_ORD456"
        assert result.quantity == 10
        assert result.stop_loss == 2450.0
    
    @pytest.mark.asyncio
    async def test_records_orders_to_db(self, order_manager, mock_order_repository, mock_kite_service, sample_signal):
        """Test orders are recorded to database."""
        mock_kite_service.kite.place_order.side_effect = ["ENTRY_ORD123", "SL_ORD456"]
        
        await order_manager.place_order(
            signal=sample_signal,
            quantity=10,
            strategy_name="vwap_breakout"
        )
        
        # Should create 2 orders (entry + SL)
        assert mock_order_repository.create_order.call_count == 2
    
    @pytest.mark.asyncio
    async def test_returns_none_on_entry_failure(self, order_manager, mock_kite_service, sample_signal):
        """Test returns None when entry order fails."""
        mock_kite_service.kite.place_order.return_value = None
        
        result = await order_manager.place_order(
            signal=sample_signal,
            quantity=10,
            strategy_name="vwap_breakout"
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_handles_market_order(self, order_manager, mock_kite_service, sample_signal):
        """Test placing market order."""
        mock_kite_service.kite.place_order.return_value = "ORD123"
        
        await order_manager.place_order(
            signal=sample_signal,
            quantity=10,
            strategy_name="vwap_breakout",
            order_type="MARKET"
        )
        
        # Verify market order type used
        call_args = mock_kite_service.kite.place_order.call_args_list[0]
        assert call_args[1]['order_type'] == mock_kite_service.kite.ORDER_TYPE_MARKET


class TestCancelOrder(TestOrderManager):
    """Test cancel_order method."""
    
    @pytest.mark.asyncio
    async def test_cancels_order_successfully(self, order_manager, mock_kite_service, mock_order_repository):
        """Test successful order cancellation."""
        result = await order_manager.cancel_order("ORD123")
        
        assert result is True
        mock_kite_service.kite.cancel_order.assert_called_once()
        mock_order_repository.update_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_returns_false_on_cancel_failure(self, order_manager, mock_kite_service):
        """Test returns False when cancellation fails."""
        mock_kite_service.kite.cancel_order.side_effect = Exception("Cancel failed")
        
        result = await order_manager.cancel_order("ORD123")
        
        assert result is False


class TestSyncOrdersFromKite(TestOrderManager):
    """Test sync_orders_from_kite method."""
    
    @pytest.mark.asyncio
    async def test_syncs_new_orders(self, order_manager, mock_kite_service, mock_order_repository):
        """Test syncing new orders from Kite."""
        mock_kite_service.kite.orders.return_value = [
            {
                'order_id': 'ORD123',
                'tradingsymbol': 'RELIANCE',
                'instrument_token': 738561,
                'order_type': 'MARKET',
                'transaction_type': 'BUY',
                'quantity': 100,
                'price': None,
                'trigger_price': None,
                'status': 'COMPLETE',
                'order_timestamp': datetime.now()
            }
        ]
        mock_order_repository.get_order.return_value = None  # Not in DB
        
        synced = await order_manager.sync_orders_from_kite()
        
        assert synced == 1
        mock_order_repository.create_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_updates_existing_orders(self, order_manager, mock_kite_service, mock_order_repository):
        """Test updating existing orders with new status."""
        mock_kite_service.kite.orders.return_value = [
            {
                'order_id': 'ORD123',
                'tradingsymbol': 'RELIANCE',
                'status': 'COMPLETE',
                'status_message': None,
                'filled_quantity': 100,
                'average_price': 2500
            }
        ]
        mock_order_repository.get_order.return_value = {
            'order_id': 'ORD123',
            'status': 'OPEN'  # Different status
        }
        
        synced = await order_manager.sync_orders_from_kite()
        
        assert synced == 1
        mock_order_repository.update_order.assert_called_once()


class TestModifySLOrder(TestOrderManager):
    """Test modify_sl_order method."""
    
    @pytest.mark.asyncio
    async def test_modifies_sl_order(self, order_manager, mock_kite_service):
        """Test modifying SL order trigger price."""
        success, new_order_id = await order_manager.modify_sl_order(
            order_id="SL123",
            new_trigger_price=2475.0,
            modification_count=5
        )
        
        assert success is True
        assert new_order_id is None
        mock_kite_service.kite.modify_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_recreates_order_at_modification_limit(self, order_manager, mock_kite_service, mock_order_repository):
        """Test recreates order when modification limit reached."""
        # Setup for order recreation
        mock_order_repository.get_order.return_value = {
            'order_id': 'SL123',
            'symbol': 'RELIANCE',
            'instrument_token': 738561,
            'strategy_name': 'vwap_breakout',
            'transaction_type': 'SELL',
            'quantity': 100,
            'metadata': {'product': 'MIS', 'parent_order_id': 'ENTRY123'}
        }
        mock_kite_service.kite.place_order.return_value = "NEW_SL456"
        
        success, new_order_id = await order_manager.modify_sl_order(
            order_id="SL123",
            new_trigger_price=2475.0,
            modification_count=20  # At limit
        )
        
        assert success is True
        assert new_order_id == "NEW_SL456"


class TestCancelSLOrder(TestOrderManager):
    """Test cancel_sl_order method."""
    
    @pytest.mark.asyncio
    async def test_cancels_pending_sl_order(self, order_manager, mock_kite_service):
        """Test cancelling a pending SL order."""
        mock_kite_service.kite.orders.return_value = [
            {
                'order_id': 'SL123',
                'status': 'TRIGGER PENDING'
            }
        ]
        
        result = await order_manager.cancel_sl_order("SL123")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_returns_true_if_already_cancelled(self, order_manager, mock_kite_service):
        """Test returns True if order already cancelled."""
        mock_kite_service.kite.orders.return_value = [
            {
                'order_id': 'SL123',
                'status': 'CANCELLED'
            }
        ]
        
        result = await order_manager.cancel_sl_order("SL123")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_returns_false_with_no_order_id(self, order_manager):
        """Test returns False when no order ID provided."""
        result = await order_manager.cancel_sl_order(None)
        
        assert result is False


class TestExitPosition(TestOrderManager):
    """Test exit_position method."""
    
    @pytest.mark.asyncio
    async def test_exits_position_with_market_order(self, order_manager, mock_kite_service):
        """Test exiting position with market order."""
        mock_kite_service.kite.place_order.return_value = "EXIT_ORD123"
        mock_kite_service.kite.orders.return_value = []  # No SL order to cancel
        
        result = await order_manager.exit_position(
            symbol="RELIANCE",
            quantity=100,
            transaction_type="SELL"
        )
        
        assert result == "EXIT_ORD123"
    
    @pytest.mark.asyncio
    async def test_cancels_sl_order_on_exit(self, order_manager, mock_kite_service):
        """Test cancels SL order when exiting position."""
        mock_kite_service.kite.place_order.return_value = "EXIT_ORD123"
        mock_kite_service.kite.orders.return_value = [
            {'order_id': 'SL456', 'status': 'TRIGGER PENDING'}
        ]
        
        result = await order_manager.exit_position(
            symbol="RELIANCE",
            quantity=100,
            transaction_type="SELL",
            sl_order_id="SL456"
        )
        
        assert result == "EXIT_ORD123"
        # Verify SL was cancelled
        mock_kite_service.kite.cancel_order.assert_called()


class TestExitAllPositions(TestOrderManager):
    """Test exit_all_positions method."""
    
    @pytest.mark.asyncio
    async def test_exits_all_open_positions(self, order_manager, mock_kite_service):
        """Test exiting all open positions."""
        mock_kite_service.kite.positions.return_value = {
            'day': [
                {'tradingsymbol': 'RELIANCE', 'quantity': 100, 'product': 'MIS'},
                {'tradingsymbol': 'TCS', 'quantity': -50, 'product': 'MIS'}  # Short
            ]
        }
        mock_kite_service.kite.place_order.return_value = "EXIT_ORD"
        mock_kite_service.kite.orders.return_value = []
        
        exited = await order_manager.exit_all_positions()
        
        assert exited == 2
    
    @pytest.mark.asyncio
    async def test_skips_zero_quantity_positions(self, order_manager, mock_kite_service):
        """Test skips positions with zero quantity."""
        mock_kite_service.kite.positions.return_value = {
            'day': [
                {'tradingsymbol': 'RELIANCE', 'quantity': 0, 'product': 'MIS'},  # Already closed
                {'tradingsymbol': 'TCS', 'quantity': 100, 'product': 'MIS'}
            ]
        }
        mock_kite_service.kite.place_order.return_value = "EXIT_ORD"
        mock_kite_service.kite.orders.return_value = []
        
        exited = await order_manager.exit_all_positions()
        
        assert exited == 1


class TestGetOrderStatus(TestOrderManager):
    """Test get_order_status method."""
    
    @pytest.mark.asyncio
    async def test_returns_order_status(self, order_manager, mock_kite_service):
        """Test returns order status from Kite."""
        mock_kite_service.kite.orders.return_value = [
            {'order_id': 'ORD123', 'status': 'COMPLETE', 'tradingsymbol': 'RELIANCE'}
        ]
        
        result = await order_manager.get_order_status("ORD123")
        
        assert result is not None
        assert result['status'] == 'COMPLETE'
    
    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_order(self, order_manager, mock_kite_service):
        """Test returns None for unknown order."""
        mock_kite_service.kite.orders.return_value = []
        
        result = await order_manager.get_order_status("UNKNOWN")
        
        assert result is None


class TestOrderCache(TestOrderManager):
    """Test order caching behavior."""
    
    @pytest.mark.asyncio
    async def test_cache_is_used_within_ttl(self, order_manager, mock_kite_service):
        """Test cached orders used within TTL."""
        mock_kite_service.kite.orders.return_value = [
            {'order_id': 'ORD123', 'status': 'OPEN'}
        ]
        
        # First call populates cache
        await order_manager.get_todays_orders()
        
        # Second call should use cache
        await order_manager.get_todays_orders()
        
        # orders() should only be called once
        assert mock_kite_service.kite.orders.call_count == 1
    
    def test_invalidate_cache(self, order_manager):
        """Test cache invalidation."""
        order_manager._cache_timestamp = datetime.now()
        
        order_manager._invalidate_cache()
        
        assert order_manager._cache_timestamp is None
