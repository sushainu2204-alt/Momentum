"""
Unit Tests for Trailing Stop Loss Service

Tests trailing stop loss calculation and updates.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from backend.core.services.trading.trailing_sl_service import (
    TrailingStopLossService, TrailingStopLossConfig
)


class TestTrailingStopLossConfig:
    """Test TrailingStopLossConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = TrailingStopLossConfig()
        
        assert config.enabled is True
        assert config.activation_pct == 0.5
        assert config.trail_pct == 0.3
        assert config.min_sl_move_pct == 0.1
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = TrailingStopLossConfig(
            enabled=False,
            activation_pct=1.0,
            trail_pct=0.5,
            min_sl_move_pct=0.2
        )
        
        assert config.enabled is False
        assert config.activation_pct == 1.0
        assert config.trail_pct == 0.5
        assert config.min_sl_move_pct == 0.2


class TestTrailingStopLossService:
    """Test TrailingStopLossService."""
    
    @pytest.fixture
    def mock_position_repository(self):
        """Create mock position repository."""
        repo = Mock()
        repo.get_open_positions = AsyncMock(return_value=[])
        repo.update_position = AsyncMock(return_value=True)
        repo.update_trailing_stop_loss = AsyncMock(return_value=True)
        return repo
    
    @pytest.fixture
    def mock_order_repository(self):
        """Create mock order repository."""
        repo = Mock()
        repo.get_modification_count = AsyncMock(return_value=0)
        repo.increment_modification_count = AsyncMock(return_value=1)
        return repo
    
    @pytest.fixture
    def mock_kite_service(self):
        """Create mock Kite service."""
        kite = Mock()
        kite.kite = Mock()
        kite.kite.VARIETY_REGULAR = "regular"
        kite.kite.positions = Mock(return_value={'day': []})
        kite.kite.modify_order = Mock()
        return kite
    
    @pytest.fixture
    def mock_order_manager(self):
        """Create mock order manager."""
        om = Mock()
        om.modify_sl_order = AsyncMock(return_value=(True, None))
        return om
    
    @pytest.fixture
    def trailing_service(self, mock_position_repository, mock_kite_service, mock_order_repository, mock_order_manager):
        """Create trailing stop loss service with mocked dependencies."""
        return TrailingStopLossService(
            position_repository=mock_position_repository,
            kite_service=mock_kite_service,
            order_repository=mock_order_repository,
            order_manager=mock_order_manager,
            config=TrailingStopLossConfig()
        )


class TestProcessPositions(TestTrailingStopLossService):
    """Test process_positions method."""
    
    @pytest.mark.asyncio
    async def test_returns_empty_stats_when_disabled(self, trailing_service):
        """Test returns empty stats when service is disabled."""
        trailing_service.config.enabled = False
        
        result = await trailing_service.process_positions()
        
        assert result == {"checked": 0, "updated": 0, "errors": 0}
    
    @pytest.mark.asyncio
    async def test_returns_empty_stats_with_no_positions(self, trailing_service, mock_position_repository):
        """Test returns empty stats when no open positions."""
        mock_position_repository.get_open_positions.return_value = []
        
        result = await trailing_service.process_positions()
        
        assert result["checked"] == 0
        assert result["updated"] == 0
    
    @pytest.mark.asyncio
    async def test_processes_positions_and_updates_sl(self, trailing_service, mock_position_repository, mock_kite_service):
        """Test processes positions and updates trailing SL."""
        # Position with 1% profit (above 0.5% activation)
        mock_position_repository.get_open_positions.return_value = [{
            'id': 1,
            'symbol': 'RELIANCE',
            'entry_price': 100.0,
            'stop_loss': 98.0,
            'current_price': 101.5,
            'highest_price': 101.0,
            'sl_order_id': 'SL123'
        }]
        
        mock_kite_service.kite.positions.return_value = {
            'day': [{'tradingsymbol': 'RELIANCE', 'last_price': 101.5}]
        }
        
        result = await trailing_service.process_positions()
        
        assert result["checked"] == 1
        assert result["updated"] == 1
    
    @pytest.mark.asyncio
    async def test_handles_errors_gracefully(self, trailing_service, mock_position_repository):
        """Test handles errors gracefully."""
        mock_position_repository.get_open_positions.side_effect = Exception("DB Error")
        
        result = await trailing_service.process_positions()
        
        assert result["checked"] == 0
        assert result["errors"] == 0  # Error in getting positions doesn't increment error count


class TestProcessSinglePosition(TestTrailingStopLossService):
    """Test _process_single_position method."""
    
    @pytest.mark.asyncio
    async def test_no_trail_when_below_activation(self, trailing_service, mock_position_repository):
        """Test no trailing when profit below activation threshold."""
        position = {
            'id': 1,
            'symbol': 'RELIANCE',
            'entry_price': 100.0,
            'stop_loss': 98.0,
            'current_price': 100.3,  # Only 0.3% profit < 0.5% activation
            'highest_price': 100.3
        }
        
        result = await trailing_service._process_single_position(position, {'RELIANCE': 100.3})
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_no_trail_when_new_sl_lower(self, trailing_service, mock_position_repository):
        """Test no trailing when new SL would be lower than current."""
        # With highest_price=101.0 and trail_pct=0.3%, new_sl = 101 * 0.997 = 100.697
        # Set current SL higher than calculated new SL to test this condition
        position = {
            'id': 1,
            'symbol': 'RELIANCE',
            'entry_price': 100.0,
            'stop_loss': 100.8,  # Higher than new_sl (100.697)
            'current_price': 101.0,
            'highest_price': 101.0
        }
        
        result = await trailing_service._process_single_position(position, {'RELIANCE': 101.0})
        
        # Should return False because new SL (100.697) <= current SL (100.8)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_updates_highest_price(self, trailing_service, mock_position_repository):
        """Test updates highest price when current price is higher."""
        position = {
            'id': 1,
            'symbol': 'RELIANCE',
            'entry_price': 100.0,
            'stop_loss': 98.0,
            'current_price': 99.0,
            'highest_price': 100.0  # Old high
        }
        
        # New current price is higher
        kite_price_map = {'RELIANCE': 101.0}
        
        await trailing_service._process_single_position(position, kite_price_map)
        
        # Should update position with new highest price
        mock_position_repository.update_position.assert_called()


class TestModifySLOrderOnKite(TestTrailingStopLossService):
    """Test _modify_sl_order_on_kite method."""
    
    @pytest.mark.asyncio
    async def test_modifies_sl_order_via_order_manager(self, trailing_service, mock_order_manager):
        """Test modifies SL order via OrderManager."""
        position = {'id': 1, 'symbol': 'RELIANCE'}
        
        result = await trailing_service._modify_sl_order_on_kite(
            sl_order_id="SL123",
            new_trigger_price=99.5,
            position=position,
            position_id=1
        )
        
        mock_order_manager.modify_sl_order.assert_called_once()
        assert result is None  # No new order created
    
    @pytest.mark.asyncio
    async def test_returns_new_order_id_when_recreated(self, trailing_service, mock_order_manager, mock_position_repository):
        """Test returns new order ID when order is recreated."""
        mock_order_manager.modify_sl_order.return_value = (True, "NEW_SL456")
        position = {'id': 1, 'symbol': 'RELIANCE'}
        
        result = await trailing_service._modify_sl_order_on_kite(
            sl_order_id="SL123",
            new_trigger_price=99.5,
            position=position,
            position_id=1
        )
        
        assert result == "NEW_SL456"
        # Should update position with new SL order ID
        mock_position_repository.update_position.assert_called_with(
            position_id=1,
            sl_order_id="NEW_SL456"
        )
    
    @pytest.mark.asyncio
    async def test_handles_modification_error(self, trailing_service, mock_order_manager):
        """Test handles modification error gracefully."""
        mock_order_manager.modify_sl_order.return_value = (False, None)
        position = {'id': 1, 'symbol': 'RELIANCE'}
        
        result = await trailing_service._modify_sl_order_on_kite(
            sl_order_id="SL123",
            new_trigger_price=99.5,
            position=position,
            position_id=1
        )
        
        assert result is None


class TestGetKitePositions(TestTrailingStopLossService):
    """Test _get_kite_positions method."""
    
    def test_returns_day_positions(self, trailing_service, mock_kite_service):
        """Test returns day positions from Kite."""
        mock_kite_service.kite.positions.return_value = {
            'day': [
                {'tradingsymbol': 'RELIANCE', 'last_price': 2500.0},
                {'tradingsymbol': 'TCS', 'last_price': 3500.0}
            ]
        }
        
        result = trailing_service._get_kite_positions()
        
        assert len(result) == 2
    
    def test_returns_empty_on_error(self, trailing_service, mock_kite_service):
        """Test returns empty list on error."""
        mock_kite_service.kite.positions.side_effect = Exception("API Error")
        
        result = trailing_service._get_kite_positions()
        
        assert result == []


class TestConfigurationMethods(TestTrailingStopLossService):
    """Test configuration methods."""
    
    def test_update_config(self, trailing_service):
        """Test updating configuration."""
        trailing_service.update_config(
            enabled=False,
            activation_pct=1.5,
            trail_pct=0.5
        )
        
        assert trailing_service.config.enabled is False
        assert trailing_service.config.activation_pct == 1.5
        assert trailing_service.config.trail_pct == 0.5
    
    def test_get_config(self, trailing_service):
        """Test getting configuration."""
        result = trailing_service.get_config()
        
        assert 'enabled' in result
        assert 'activation_pct' in result
        assert 'trail_pct' in result
        assert 'min_sl_move_pct' in result


class TestTrailingSLCalculations(TestTrailingStopLossService):
    """Test trailing SL calculation scenarios."""
    
    @pytest.mark.asyncio
    async def test_trail_calculation_example(self, trailing_service, mock_position_repository, mock_kite_service):
        """Test trail calculation with example values."""
        # Entry: ₹100, Initial SL: ₹98 (2% SL)
        # Config: activation_pct=0.5%, trail_pct=0.3%
        # Price at ₹101 (+1%): Profit > activation, trailing starts
        # New SL = 101 * (1 - 0.3/100) = ₹100.697
        
        trailing_service.config = TrailingStopLossConfig(
            enabled=True,
            activation_pct=0.5,
            trail_pct=0.3,
            min_sl_move_pct=0.1
        )
        
        position = {
            'id': 1,
            'symbol': 'RELIANCE',
            'entry_price': 100.0,
            'stop_loss': 98.0,  # Initial 2% SL
            'current_price': 101.0,
            'highest_price': 101.0,
            'sl_order_id': 'SL123'
        }
        
        mock_position_repository.get_open_positions.return_value = [position]
        mock_kite_service.kite.positions.return_value = {
            'day': [{'tradingsymbol': 'RELIANCE', 'last_price': 101.0}]
        }
        
        result = await trailing_service.process_positions()
        
        # Should update SL from 98 to ~100.697
        assert result["updated"] == 1
        
        # Verify update_trailing_stop_loss was called with correct values
        mock_position_repository.update_trailing_stop_loss.assert_called_once()
        call_args = mock_position_repository.update_trailing_stop_loss.call_args
        new_sl = call_args[1]['new_stop_loss']
        
        # New SL should be approximately 100.70 (101 * 0.997 rounded to 2 decimals)
        assert abs(new_sl - 100.70) < 0.01
