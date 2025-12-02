"""
Unit Tests for Trailing Stop Loss Service

Tests the TrailingStopLossService and TrailingStopLossConfig.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.core.services.trailing_sl_service import (
    TrailingStopLossService,
    TrailingStopLossConfig
)


# ============================================================================
# CONFIG TESTS
# ============================================================================

class TestTrailingStopLossConfig:
    """Test TrailingStopLossConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = TrailingStopLossConfig()
        
        assert config.enabled is True
        assert config.activation_pct == 0.5
        assert config.trail_pct == 0.3
        assert config.min_sl_move_pct == 0.1
    
    def test_custom_config(self):
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


# ============================================================================
# SERVICE TESTS
# ============================================================================

class TestTrailingStopLossService:
    """Test TrailingStopLossService."""
    
    @pytest.fixture
    def mock_position_repository(self):
        """Create mock position repository."""
        repo = MagicMock()
        repo.get_open_positions = AsyncMock(return_value=[])
        repo.update_position = AsyncMock()
        repo.update_trailing_stop_loss = AsyncMock()
        return repo
    
    @pytest.fixture
    def mock_kite_service(self):
        """Create mock Kite service."""
        kite = MagicMock()
        kite.kite = MagicMock()
        kite.kite.positions = MagicMock(return_value={"day": []})
        kite.kite.modify_order = MagicMock()
        kite.kite.VARIETY_BO = "bo"
        return kite
    
    @pytest.fixture
    def trailing_sl_service(self, mock_position_repository, mock_kite_service):
        """Create TrailingStopLossService with mocks."""
        return TrailingStopLossService(
            position_repository=mock_position_repository,
            kite_service=mock_kite_service
        )
    
    @pytest.fixture
    def sample_open_position(self):
        """Create a sample open position."""
        return {
            "id": 1,
            "symbol": "RELIANCE",
            "instrument_token": 738561,
            "entry_price": 100.0,
            "stop_loss": 98.0,  # 2% SL
            "target": 106.0,
            "quantity": 10,
            "current_price": 100.0,
            "highest_price": None,
            "original_stop_loss": None,
            "sl_order_id": "SL_ORDER_123",
            "status": "OPEN"
        }
    
    # ----------------------------------------------------------------
    # BASIC FUNCTIONALITY TESTS
    # ----------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_process_positions_disabled(self, trailing_sl_service):
        """Test that processing is skipped when disabled."""
        trailing_sl_service.config.enabled = False
        
        result = await trailing_sl_service.process_positions()
        
        assert result == {"checked": 0, "updated": 0, "errors": 0}
    
    @pytest.mark.asyncio
    async def test_process_positions_no_positions(self, trailing_sl_service, mock_position_repository):
        """Test processing when no positions exist."""
        mock_position_repository.get_open_positions = AsyncMock(return_value=[])
        
        result = await trailing_sl_service.process_positions()
        
        assert result["checked"] == 0
        assert result["updated"] == 0
        assert result["errors"] == 0
    
    @pytest.mark.asyncio
    async def test_process_positions_not_in_profit(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test that SL is not trailed when position is not in profit."""
        # Position at entry price - no profit
        sample_open_position["current_price"] = 100.0
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        # Kite shows same price
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 100.0}]
        })
        
        result = await trailing_sl_service.process_positions()
        
        assert result["checked"] == 1
        assert result["updated"] == 0
        mock_position_repository.update_trailing_stop_loss.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_process_positions_profit_below_activation(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test that SL is not trailed when profit is below activation threshold."""
        # Price up 0.3% - below 0.5% activation
        sample_open_position["current_price"] = 100.3
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 100.3}]
        })
        
        result = await trailing_sl_service.process_positions()
        
        assert result["checked"] == 1
        assert result["updated"] == 0
        mock_position_repository.update_trailing_stop_loss.assert_not_called()
    
    # ----------------------------------------------------------------
    # TRAILING ACTIVATION TESTS
    # ----------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_process_positions_activates_trailing(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test that SL is trailed when profit exceeds activation threshold."""
        # Price up 1% - above 0.5% activation
        sample_open_position["current_price"] = 101.0
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 101.0}]
        })
        
        result = await trailing_sl_service.process_positions()
        
        assert result["checked"] == 1
        assert result["updated"] == 1
        
        # Verify update_trailing_stop_loss was called with correct values
        # New SL = 101 * (1 - 0.3/100) = 100.697 ≈ 100.70
        call_args = mock_position_repository.update_trailing_stop_loss.call_args
        assert call_args[1]["position_id"] == 1
        assert round(call_args[1]["new_stop_loss"], 2) == 100.70
        assert call_args[1]["highest_price"] == 101.0
        assert call_args[1]["original_stop_loss"] == 98.0  # Original SL stored
    
    @pytest.mark.asyncio
    async def test_process_positions_modifies_kite_order(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test that Kite SL order is modified when trailing."""
        sample_open_position["current_price"] = 101.0
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 101.0}]
        })
        
        await trailing_sl_service.process_positions()
        
        # Verify Kite order modification
        mock_kite_service.kite.modify_order.assert_called_once()
        call_args = mock_kite_service.kite.modify_order.call_args
        assert call_args[1]["variety"] == "bo"
        assert call_args[1]["order_id"] == "SL_ORDER_123"
        assert round(call_args[1]["trigger_price"], 2) == 100.70
    
    @pytest.mark.asyncio
    async def test_process_positions_no_sl_order_id(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test handling when no SL order ID is stored."""
        sample_open_position["current_price"] = 101.0
        sample_open_position["sl_order_id"] = None  # No SL order ID
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 101.0}]
        })
        
        result = await trailing_sl_service.process_positions()
        
        # Should still update DB
        assert result["updated"] == 1
        mock_position_repository.update_trailing_stop_loss.assert_called_once()
        
        # But should NOT call Kite modify
        mock_kite_service.kite.modify_order.assert_not_called()
    
    # ----------------------------------------------------------------
    # SL MOVEMENT TESTS
    # ----------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_sl_never_moves_down(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test that SL never moves down even if price drops."""
        # Position was at profit, SL was trailed
        sample_open_position["stop_loss"] = 100.70  # Already trailed SL
        sample_open_position["highest_price"] = 101.0
        sample_open_position["original_stop_loss"] = 98.0
        sample_open_position["current_price"] = 100.5  # Price dropped but still above SL
        
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 100.5}]
        })
        
        result = await trailing_sl_service.process_positions()
        
        # Should not update because new SL would be lower
        # New SL = 101 * 0.997 = 100.70 (same, since highest_price hasn't increased)
        assert result["checked"] == 1
        assert result["updated"] == 0
        mock_position_repository.update_trailing_stop_loss.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_sl_moves_up_with_price(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test that SL moves up as price increases."""
        # Initial trail already happened
        sample_open_position["stop_loss"] = 100.70
        sample_open_position["highest_price"] = 101.0
        sample_open_position["original_stop_loss"] = 98.0
        sample_open_position["current_price"] = 102.0  # Price increased further
        
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 102.0}]
        })
        
        result = await trailing_sl_service.process_positions()
        
        # New SL = 102 * (1 - 0.3/100) = 101.694 ≈ 101.69
        assert result["updated"] == 1
        call_args = mock_position_repository.update_trailing_stop_loss.call_args
        assert round(call_args[1]["new_stop_loss"], 2) == 101.69
        assert call_args[1]["highest_price"] == 102.0
    
    @pytest.mark.asyncio
    async def test_min_sl_move_threshold(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test that SL doesn't update if move is below minimum threshold."""
        # Configure higher min move threshold
        trailing_sl_service.config.min_sl_move_pct = 0.5  # 0.5% min move
        
        # Position with current SL very close to what new SL would be
        sample_open_position["stop_loss"] = 100.65
        sample_open_position["highest_price"] = 101.0
        sample_open_position["current_price"] = 101.1  # Tiny increase
        
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 101.1}]
        })
        
        result = await trailing_sl_service.process_positions()
        
        # New SL = 101.1 * 0.997 = 100.80
        # Move = (100.80 - 100.65) / 100 = 0.15% < 0.5% threshold
        assert result["checked"] == 1
        assert result["updated"] == 0
    
    # ----------------------------------------------------------------
    # HIGHEST PRICE TRACKING TESTS
    # ----------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_highest_price_updated(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test that highest price is updated when price increases."""
        sample_open_position["highest_price"] = 100.0
        sample_open_position["current_price"] = 100.2  # Below activation
        
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 100.2}]
        })
        
        await trailing_sl_service.process_positions()
        
        # Even though not trailing yet, highest_price should be updated
        mock_position_repository.update_position.assert_called()
        call_args = mock_position_repository.update_position.call_args
        assert call_args[1]["highest_price"] == 100.2
    
    @pytest.mark.asyncio
    async def test_highest_price_initialized_from_entry(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test that highest price is initialized from entry price when None."""
        sample_open_position["highest_price"] = None
        sample_open_position["current_price"] = 99.5  # Below entry
        
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 99.5}]
        })
        
        await trailing_sl_service.process_positions()
        
        # Highest price should remain at entry (100) since current (99.5) is lower
        # No update should happen because 99.5 < 100
        mock_position_repository.update_position.assert_not_called()
    
    # ----------------------------------------------------------------
    # MULTIPLE POSITIONS TESTS
    # ----------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_multiple_positions(
        self, trailing_sl_service, mock_position_repository, mock_kite_service
    ):
        """Test processing multiple positions."""
        positions = [
            {
                "id": 1, "symbol": "RELIANCE", "instrument_token": 738561,
                "entry_price": 100.0, "stop_loss": 98.0, "current_price": 101.0,
                "highest_price": None, "original_stop_loss": None, "sl_order_id": "SL_1"
            },
            {
                "id": 2, "symbol": "TCS", "instrument_token": 2953217,
                "entry_price": 200.0, "stop_loss": 196.0, "current_price": 200.5,
                "highest_price": None, "original_stop_loss": None, "sl_order_id": "SL_2"
            },  # Only 0.25% profit - below activation
            {
                "id": 3, "symbol": "INFY", "instrument_token": 408065,
                "entry_price": 150.0, "stop_loss": 147.0, "current_price": 152.0,
                "highest_price": None, "original_stop_loss": None, "sl_order_id": "SL_3"
            }  # 1.33% profit - above activation
        ]
        
        mock_position_repository.get_open_positions = AsyncMock(return_value=positions)
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [
                {"tradingsymbol": "RELIANCE", "last_price": 101.0},
                {"tradingsymbol": "TCS", "last_price": 200.5},
                {"tradingsymbol": "INFY", "last_price": 152.0}
            ]
        })
        
        result = await trailing_sl_service.process_positions()
        
        assert result["checked"] == 3
        assert result["updated"] == 2  # RELIANCE and INFY
        assert result["errors"] == 0
    
    # ----------------------------------------------------------------
    # ERROR HANDLING TESTS
    # ----------------------------------------------------------------
    
    @pytest.mark.asyncio
    async def test_kite_modify_order_error(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test handling when Kite order modification fails."""
        sample_open_position["current_price"] = 101.0
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 101.0}]
        })
        
        # Kite modify fails
        mock_kite_service.kite.modify_order = MagicMock(side_effect=Exception("API Error"))
        
        result = await trailing_sl_service.process_positions()
        
        # DB update should still happen (order modification is non-blocking)
        assert result["updated"] == 1
        mock_position_repository.update_trailing_stop_loss.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_position_processing_error(
        self, trailing_sl_service, mock_position_repository, mock_kite_service
    ):
        """Test handling when processing a position fails."""
        positions = [
            {
                "id": 1, "symbol": "RELIANCE", "entry_price": 100.0, "stop_loss": 98.0,
                "current_price": 101.0, "highest_price": None, "sl_order_id": "SL_1"
            },
            {
                "id": 2, "symbol": "ERROR_STOCK", "entry_price": None,  # This will cause error
                "stop_loss": 98.0, "current_price": 101.0, "sl_order_id": "SL_2"
            }
        ]
        
        mock_position_repository.get_open_positions = AsyncMock(return_value=positions)
        
        mock_kite_service.kite.positions = MagicMock(return_value={
            "day": [
                {"tradingsymbol": "RELIANCE", "last_price": 101.0},
                {"tradingsymbol": "ERROR_STOCK", "last_price": 101.0}
            ]
        })
        
        result = await trailing_sl_service.process_positions()
        
        # First position should succeed, second should error
        assert result["checked"] == 2
        assert result["updated"] == 1
        assert result["errors"] == 1
    
    @pytest.mark.asyncio
    async def test_kite_positions_fetch_error(
        self, trailing_sl_service, mock_position_repository, mock_kite_service, sample_open_position
    ):
        """Test handling when fetching Kite positions fails."""
        sample_open_position["current_price"] = 101.0
        mock_position_repository.get_open_positions = AsyncMock(return_value=[sample_open_position])
        
        # Kite positions fetch fails
        mock_kite_service.kite.positions = MagicMock(side_effect=Exception("Network Error"))
        
        result = await trailing_sl_service.process_positions()
        
        # Should still work using DB price
        assert result["checked"] == 1
        assert result["updated"] == 1
    
    # ----------------------------------------------------------------
    # CONFIGURATION TESTS
    # ----------------------------------------------------------------
    
    def test_update_config(self, trailing_sl_service):
        """Test updating service configuration."""
        trailing_sl_service.update_config(
            enabled=False,
            activation_pct=1.0,
            trail_pct=0.5
        )
        
        assert trailing_sl_service.config.enabled is False
        assert trailing_sl_service.config.activation_pct == 1.0
        assert trailing_sl_service.config.trail_pct == 0.5
        assert trailing_sl_service.config.min_sl_move_pct == 0.1  # Unchanged
    
    def test_get_config(self, trailing_sl_service):
        """Test getting service configuration."""
        config = trailing_sl_service.get_config()
        
        assert "enabled" in config
        assert "activation_pct" in config
        assert "trail_pct" in config
        assert "min_sl_move_pct" in config
        
        assert config["enabled"] is True
        assert config["activation_pct"] == 0.5
        assert config["trail_pct"] == 0.3
        assert config["min_sl_move_pct"] == 0.1
    
    def test_partial_config_update(self, trailing_sl_service):
        """Test partial configuration update."""
        trailing_sl_service.update_config(activation_pct=2.0)
        
        config = trailing_sl_service.get_config()
        assert config["activation_pct"] == 2.0
        assert config["trail_pct"] == 0.3  # Unchanged
        assert config["enabled"] is True  # Unchanged


# ============================================================================
# INTEGRATION-STYLE TESTS
# ============================================================================

class TestTrailingStopLossScenarios:
    """Test realistic trading scenarios."""
    
    @pytest.fixture
    def service_with_mocks(self):
        """Create service with pre-configured mocks."""
        repo = MagicMock()
        repo.get_open_positions = AsyncMock(return_value=[])
        repo.update_position = AsyncMock()
        repo.update_trailing_stop_loss = AsyncMock()
        
        kite = MagicMock()
        kite.kite = MagicMock()
        kite.kite.positions = MagicMock(return_value={"day": []})
        kite.kite.modify_order = MagicMock()
        kite.kite.VARIETY_BO = "bo"
        
        service = TrailingStopLossService(
            position_repository=repo,
            kite_service=kite
        )
        
        return service, repo, kite
    
    @pytest.mark.asyncio
    async def test_scenario_gradual_price_increase(self, service_with_mocks):
        """Test scenario where price gradually increases over time."""
        service, repo, kite = service_with_mocks
        
        # Simulate position through multiple price updates
        base_position = {
            "id": 1, "symbol": "RELIANCE", "instrument_token": 738561,
            "entry_price": 100.0, "stop_loss": 98.0, "target": 106.0,
            "quantity": 10, "highest_price": None, "original_stop_loss": None,
            "sl_order_id": "SL_123", "status": "OPEN"
        }
        
        # Step 1: Price at 100.3 (0.3% profit) - below activation
        base_position["current_price"] = 100.3
        repo.get_open_positions = AsyncMock(return_value=[base_position.copy()])
        kite.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 100.3}]
        })
        
        result = await service.process_positions()
        assert result["updated"] == 0
        
        # Step 2: Price at 101.0 (1% profit) - activates trailing
        base_position["current_price"] = 101.0
        base_position["highest_price"] = 100.3  # From previous update
        repo.get_open_positions = AsyncMock(return_value=[base_position.copy()])
        kite.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 101.0}]
        })
        
        result = await service.process_positions()
        assert result["updated"] == 1
        
        # Verify SL moved to ~100.70
        call_args = repo.update_trailing_stop_loss.call_args
        assert round(call_args[1]["new_stop_loss"], 2) == 100.70
        
        # Step 3: Price at 103.0 (3% profit) - SL trails higher
        base_position["current_price"] = 103.0
        base_position["stop_loss"] = 100.70
        base_position["highest_price"] = 101.0
        base_position["original_stop_loss"] = 98.0
        repo.get_open_positions = AsyncMock(return_value=[base_position.copy()])
        kite.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 103.0}]
        })
        repo.update_trailing_stop_loss.reset_mock()
        
        result = await service.process_positions()
        assert result["updated"] == 1
        
        # Verify SL moved to ~102.69
        call_args = repo.update_trailing_stop_loss.call_args
        assert round(call_args[1]["new_stop_loss"], 2) == 102.69
    
    @pytest.mark.asyncio
    async def test_scenario_price_pullback(self, service_with_mocks):
        """Test scenario where price pulls back after reaching high."""
        service, repo, kite = service_with_mocks
        
        # Position reached 103 (high), SL trailed to 102.69
        position = {
            "id": 1, "symbol": "RELIANCE", "instrument_token": 738561,
            "entry_price": 100.0, "stop_loss": 102.69, "target": 106.0,
            "quantity": 10, "highest_price": 103.0, "original_stop_loss": 98.0,
            "sl_order_id": "SL_123", "status": "OPEN", "current_price": 103.0
        }
        
        # Price pulls back to 101.5
        position["current_price"] = 101.5
        repo.get_open_positions = AsyncMock(return_value=[position])
        kite.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 101.5}]
        })
        
        result = await service.process_positions()
        
        # SL should NOT move down
        assert result["updated"] == 0
        repo.update_trailing_stop_loss.assert_not_called()
        
        # Verify highest_price is NOT updated (price didn't exceed previous high)
        repo.update_position.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_scenario_target_hit(self, service_with_mocks):
        """Test scenario where price reaches target area."""
        service, repo, kite = service_with_mocks
        
        # Position approaching target
        position = {
            "id": 1, "symbol": "RELIANCE", "instrument_token": 738561,
            "entry_price": 100.0, "stop_loss": 104.0, "target": 106.0,
            "quantity": 10, "highest_price": 104.5, "original_stop_loss": 98.0,
            "sl_order_id": "SL_123", "status": "OPEN", "current_price": 104.5
        }
        
        # Price near target at 105.5
        position["current_price"] = 105.5
        repo.get_open_positions = AsyncMock(return_value=[position])
        kite.kite.positions = MagicMock(return_value={
            "day": [{"tradingsymbol": "RELIANCE", "last_price": 105.5}]
        })
        
        result = await service.process_positions()
        
        # SL should trail to lock in most of the profit
        # New SL = 105.5 * 0.997 = 105.18
        assert result["updated"] == 1
        call_args = repo.update_trailing_stop_loss.call_args
        assert round(call_args[1]["new_stop_loss"], 2) == 105.18


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
