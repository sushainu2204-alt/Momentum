"""
Integration Tests for MockBroker

Tests the MockBroker implementation to verify:
1. Order placement and management
2. Position tracking
3. Margin calculations
4. Connection handling
"""

import pytest
from datetime import datetime

from backend.infrastructure.brokers.base import OrderStatus, Position as BrokerPosition


@pytest.mark.integration
@pytest.mark.asyncio
class TestMockBrokerOrders:
    """Tests for order operations."""
    
    async def test_place_market_order(self, mock_broker):
        """Test placing a market order."""
        response = await mock_broker.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=10,
            order_type="MARKET"
        )
        
        assert response.order_id.startswith("MOCK_")
        assert response.status == OrderStatus.COMPLETE
        assert response.symbol == "RELIANCE"
        assert response.quantity == 10
        assert response.filled_quantity == 10
    
    async def test_place_limit_order(self, mock_broker):
        """Test placing a limit order."""
        response = await mock_broker.place_order(
            symbol="INFY",
            exchange="NSE",
            transaction_type="BUY",
            quantity=20,
            order_type="LIMIT",
            price=1650.0
        )
        
        assert response.order_id is not None
        assert response.price == 1650.0
        assert response.average_price == 1650.0
    
    async def test_place_stop_loss_order(self, mock_broker):
        """Test placing a stop-loss order."""
        response = await mock_broker.place_order(
            symbol="TCS",
            exchange="NSE",
            transaction_type="SELL",
            quantity=5,
            order_type="SL",
            price=3500.0,
            trigger_price=3510.0
        )
        
        assert response.order_id is not None
        assert response.transaction_type == "SELL"
    
    async def test_order_ids_increment(self, mock_broker):
        """Test that order IDs increment properly."""
        response1 = await mock_broker.place_order(
            symbol="RELIANCE", exchange="NSE",
            transaction_type="BUY", quantity=10
        )
        response2 = await mock_broker.place_order(
            symbol="INFY", exchange="NSE",
            transaction_type="BUY", quantity=5
        )
        
        # Extract numeric part
        id1 = int(response1.order_id.split("_")[1])
        id2 = int(response2.order_id.split("_")[1])
        
        assert id2 == id1 + 1
    
    async def test_order_with_tag(self, mock_broker):
        """Test placing order with custom tag."""
        response = await mock_broker.place_order(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=10,
            tag="vwap_breakout_signal"
        )
        
        order = await mock_broker.get_order(response.order_id)
        assert order.tag == "vwap_breakout_signal"


@pytest.mark.integration
@pytest.mark.asyncio
class TestMockBrokerOrderManagement:
    """Tests for order modification and cancellation."""
    
    async def test_modify_order_quantity(self, mock_broker):
        """Test modifying order quantity."""
        # Place initial order
        response = await mock_broker.place_order(
            symbol="RELIANCE", exchange="NSE",
            transaction_type="BUY", quantity=10
        )
        
        # Modify quantity
        modified = await mock_broker.modify_order(
            response.order_id,
            quantity=15
        )
        
        assert modified.quantity == 15
    
    async def test_modify_order_price(self, mock_broker):
        """Test modifying order price."""
        response = await mock_broker.place_order(
            symbol="RELIANCE", exchange="NSE",
            transaction_type="BUY", quantity=10,
            order_type="LIMIT", price=2450.0
        )
        
        modified = await mock_broker.modify_order(
            response.order_id,
            price=2460.0
        )
        
        assert modified.price == 2460.0
    
    async def test_cancel_order(self, mock_broker):
        """Test cancelling an order."""
        response = await mock_broker.place_order(
            symbol="RELIANCE", exchange="NSE",
            transaction_type="BUY", quantity=10
        )
        
        cancelled = await mock_broker.cancel_order(response.order_id)
        
        assert cancelled is True
        
        order = await mock_broker.get_order(response.order_id)
        assert order.status == OrderStatus.CANCELLED
    
    async def test_cancel_nonexistent_order(self, mock_broker):
        """Test cancelling order that doesn't exist."""
        cancelled = await mock_broker.cancel_order("NONEXISTENT_123")
        
        assert cancelled is False
    
    async def test_get_all_orders(self, mock_broker):
        """Test retrieving all orders."""
        await mock_broker.place_order(
            symbol="RELIANCE", exchange="NSE",
            transaction_type="BUY", quantity=10
        )
        await mock_broker.place_order(
            symbol="INFY", exchange="NSE",
            transaction_type="BUY", quantity=5
        )
        
        orders = await mock_broker.get_orders()
        
        assert len(orders) == 2


@pytest.mark.integration
@pytest.mark.asyncio
class TestMockBrokerPositions:
    """Tests for position management."""
    
    async def test_get_empty_positions(self, mock_broker):
        """Test getting positions when none exist."""
        positions = await mock_broker.get_positions()
        
        assert positions == []
    
    async def test_add_and_get_position(self, mock_broker):
        """Test adding and retrieving positions."""
        position = BrokerPosition(
            symbol="RELIANCE",
            exchange="NSE",
            instrument_token=738561,
            quantity=10,
            average_price=2450.0,
            last_price=2470.0,
            pnl=200.0,
            pnl_pct=0.82,
            product="MIS"
        )
        
        mock_broker.add_position(position)
        positions = await mock_broker.get_positions()
        
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
        assert positions[0].pnl == 200.0
    
    async def test_get_specific_position(self, mock_broker):
        """Test getting position for specific symbol."""
        mock_broker.add_position(BrokerPosition(
            symbol="RELIANCE", exchange="NSE", instrument_token=738561,
            quantity=10, average_price=2450.0, last_price=2470.0,
            pnl=200.0, pnl_pct=0.82, product="MIS"
        ))
        mock_broker.add_position(BrokerPosition(
            symbol="INFY", exchange="NSE", instrument_token=340481,
            quantity=5, average_price=1650.0, last_price=1640.0,
            pnl=-50.0, pnl_pct=-0.61, product="MIS"
        ))
        
        position = await mock_broker.get_position("RELIANCE", "NSE")
        
        assert position is not None
        assert position.symbol == "RELIANCE"
    
    async def test_get_nonexistent_position(self, mock_broker):
        """Test getting position that doesn't exist."""
        position = await mock_broker.get_position("NONEXISTENT", "NSE")
        
        assert position is None


@pytest.mark.integration
@pytest.mark.asyncio
class TestMockBrokerMargins:
    """Tests for margin operations."""
    
    async def test_get_margins_default(self, mock_broker):
        """Test getting default margin values."""
        margins = await mock_broker.get_margins()
        
        assert margins.total_balance == 100000.0
        assert margins.available_margin > 0
    
    async def test_margins_update_after_order(self, mock_broker):
        """Test that margins update after placing order."""
        initial_margins = await mock_broker.get_margins()
        initial_available = initial_margins.available_margin
        
        await mock_broker.place_order(
            symbol="RELIANCE", exchange="NSE",
            transaction_type="BUY", quantity=10,
            price=2450.0, product="MIS"
        )
        
        updated_margins = await mock_broker.get_margins()
        
        # MIS uses 20% margin
        expected_used = 10 * 2450.0 * 0.20
        assert updated_margins.used_margin == expected_used
        assert updated_margins.available_margin < initial_available
    
    async def test_set_custom_margin(self, mock_broker):
        """Test setting custom margin values."""
        mock_broker.set_margin(available=50000.0, used=10000.0)
        
        margins = await mock_broker.get_margins()
        
        assert margins.total_balance == 50000.0
        assert margins.used_margin == 10000.0
        assert margins.available_margin == 40000.0


@pytest.mark.integration
class TestMockBrokerConnection:
    """Tests for connection handling."""
    
    @pytest.mark.asyncio
    async def test_default_connected(self, mock_broker):
        """Test broker is connected by default."""
        connected = await mock_broker.is_connected()
        
        assert connected is True
    
    @pytest.mark.asyncio
    async def test_set_disconnected(self, mock_broker):
        """Test setting broker as disconnected."""
        mock_broker.set_connected(False)
        
        connected = await mock_broker.is_connected()
        
        assert connected is False
    
    def test_broker_name(self, mock_broker):
        """Test broker name."""
        assert mock_broker.get_broker_name() == "MockBroker"


@pytest.mark.integration
@pytest.mark.asyncio
class TestMockBrokerCleanup:
    """Tests for cleanup operations."""
    
    async def test_clear_orders(self, mock_broker):
        """Test clearing all orders."""
        await mock_broker.place_order(
            symbol="RELIANCE", exchange="NSE",
            transaction_type="BUY", quantity=10
        )
        await mock_broker.place_order(
            symbol="INFY", exchange="NSE",
            transaction_type="BUY", quantity=5
        )
        
        mock_broker.clear_orders()
        orders = await mock_broker.get_orders()
        
        assert len(orders) == 0
    
    async def test_clear_positions(self, mock_broker):
        """Test clearing all positions."""
        mock_broker.add_position(BrokerPosition(
            symbol="RELIANCE", exchange="NSE", instrument_token=738561,
            quantity=10, average_price=2450.0, last_price=2470.0,
            pnl=200.0, pnl_pct=0.82, product="MIS"
        ))
        
        mock_broker.clear_positions()
        positions = await mock_broker.get_positions()
        
        assert len(positions) == 0
