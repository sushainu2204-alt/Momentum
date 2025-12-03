"""
Unit Tests for Position Manager Service

Tests position tracking, sync, and exit detection.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, date, time

from backend.core.services.trading.position_manager import PositionManager
from backend.core.models import Position, PositionStatus


class TestPositionManager:
    """Test PositionManager service."""
    
    @pytest.fixture
    def mock_kite_service(self):
        """Create mock Kite service."""
        kite = Mock()
        kite.kite = Mock()
        kite.kite.positions = Mock(return_value={
            'day': [
                {
                    'tradingsymbol': 'RELIANCE',
                    'instrument_token': 738561,
                    'quantity': 100,
                    'average_price': 2500.0,
                    'last_price': 2550.0,
                    'pnl': 5000.0
                }
            ]
        })
        return kite
    
    @pytest.fixture
    def mock_position_repository(self):
        """Create mock position repository."""
        repo = Mock()
        repo.create_position = AsyncMock(return_value=1)
        repo.update_position = AsyncMock(return_value=True)
        repo.close_position = AsyncMock(return_value=True)
        repo.get_position_by_symbol = AsyncMock(return_value=None)
        repo.get_open_positions = AsyncMock(return_value=[])
        repo.get_open_positions_count = AsyncMock(return_value=0)
        repo.get_daily_stats = AsyncMock(return_value={})
        return repo
    
    @pytest.fixture
    def mock_order_repository(self):
        """Create mock order repository."""
        repo = Mock()
        repo.get_orders_by_symbol = AsyncMock(return_value=[])
        return repo
    
    @pytest.fixture
    def position_manager(self, mock_kite_service, mock_position_repository, mock_order_repository):
        """Create position manager with mocked dependencies."""
        return PositionManager(
            kite_service=mock_kite_service,
            position_repository=mock_position_repository,
            order_repository=mock_order_repository,
            exit_time=time(15, 20)
        )


class TestHasPosition(TestPositionManager):
    """Test has_position method."""
    
    @pytest.mark.asyncio
    async def test_returns_true_when_position_exists(self, position_manager, mock_kite_service):
        """Test returns True when position exists in Kite."""
        result = await position_manager.has_position("RELIANCE")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_returns_false_when_no_position(self, position_manager, mock_kite_service):
        """Test returns False when no position exists."""
        result = await position_manager.has_position("TCS")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_returns_false_for_zero_quantity(self, position_manager, mock_kite_service):
        """Test returns False when quantity is zero."""
        mock_kite_service.kite.positions.return_value = {
            'day': [
                {'tradingsymbol': 'RELIANCE', 'quantity': 0}
            ]
        }
        
        result = await position_manager.has_position("RELIANCE")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_returns_false_on_kite_error_with_empty_cache(self, position_manager, mock_kite_service):
        """Test returns False when Kite fails and cache is empty."""
        # When Kite fails, _get_kite_positions_cached returns empty cache (not exception)
        mock_kite_service.kite.positions.side_effect = Exception("API Error")
        
        result = await position_manager.has_position("RELIANCE")
        
        # Returns False because empty cache has no positions
        assert result is False


class TestGetOpenPositions(TestPositionManager):
    """Test get_open_positions method."""
    
    @pytest.mark.asyncio
    async def test_returns_open_positions(self, position_manager):
        """Test returns all open positions from Kite."""
        result = await position_manager.get_open_positions()
        
        assert len(result) == 1
        assert result[0]['tradingsymbol'] == 'RELIANCE'
    
    @pytest.mark.asyncio
    async def test_filters_out_zero_quantity(self, position_manager, mock_kite_service):
        """Test filters out positions with zero quantity."""
        mock_kite_service.kite.positions.return_value = {
            'day': [
                {'tradingsymbol': 'RELIANCE', 'quantity': 100},
                {'tradingsymbol': 'TCS', 'quantity': 0}  # Closed
            ]
        }
        
        result = await position_manager.get_open_positions()
        
        assert len(result) == 1
        assert result[0]['tradingsymbol'] == 'RELIANCE'
    
    @pytest.mark.asyncio
    async def test_returns_empty_on_kite_error_with_empty_cache(self, position_manager, mock_kite_service):
        """Test returns empty list when Kite fails and cache is empty."""
        # When Kite fails, _get_kite_positions_cached returns empty cache
        mock_kite_service.kite.positions.side_effect = Exception("API Error")
        
        result = await position_manager.get_open_positions()
        
        # Returns empty because cache is empty
        assert len(result) == 0


class TestGetOpenPositionsCount(TestPositionManager):
    """Test get_open_positions_count method."""
    
    @pytest.mark.asyncio
    async def test_returns_correct_count(self, position_manager):
        """Test returns correct position count."""
        result = await position_manager.get_open_positions_count()
        
        assert result == 1
    
    @pytest.mark.asyncio
    async def test_returns_zero_on_kite_error_with_empty_cache(self, position_manager, mock_kite_service):
        """Test returns 0 when Kite fails and cache is empty."""
        # When Kite fails, _get_kite_positions_cached returns empty cache
        mock_kite_service.kite.positions.side_effect = Exception("API Error")
        
        result = await position_manager.get_open_positions_count()
        
        # Returns 0 because cache is empty
        assert result == 0


class TestGetPosition(TestPositionManager):
    """Test get_position method."""
    
    @pytest.mark.asyncio
    async def test_returns_position_by_symbol(self, position_manager):
        """Test returns position for specific symbol."""
        result = await position_manager.get_position("RELIANCE")
        
        assert result is not None
        assert result['tradingsymbol'] == 'RELIANCE'
    
    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_symbol(self, position_manager):
        """Test returns None for unknown symbol."""
        result = await position_manager.get_position("UNKNOWN")
        
        assert result is None


class TestClosePositionRecord(TestPositionManager):
    """Test close_position_record method."""
    
    @pytest.mark.asyncio
    async def test_closes_position_in_db(self, position_manager, mock_position_repository):
        """Test closing position record in database."""
        mock_position_repository.get_position_by_symbol.return_value = {
            'id': 1,
            'symbol': 'RELIANCE'
        }
        
        await position_manager.close_position_record(
            symbol="RELIANCE",
            exit_price=2550.0,
            exit_reason="TARGET_HIT",
            exit_order_id="EXIT123"
        )
        
        mock_position_repository.close_position.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handles_no_position_found(self, position_manager, mock_position_repository):
        """Test handles case when no position found."""
        mock_position_repository.get_position_by_symbol.return_value = None
        
        # Should not raise
        await position_manager.close_position_record(
            symbol="UNKNOWN",
            exit_price=100.0,
            exit_reason="MANUAL_EXIT"
        )
        
        # Should not call close_position
        mock_position_repository.close_position.assert_not_called()


class TestSyncPositionsFromKite(TestPositionManager):
    """Test sync_positions_from_kite method."""
    
    @pytest.mark.asyncio
    async def test_creates_new_positions(self, position_manager, mock_kite_service, mock_position_repository, mock_order_repository):
        """Test creates new positions from Kite sync."""
        # Position in Kite but not in DB
        mock_position_repository.get_open_positions.return_value = []
        
        synced = await position_manager.sync_positions_from_kite()
        
        assert synced >= 1
        mock_position_repository.create_position.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_updates_existing_positions(self, position_manager, mock_kite_service, mock_position_repository):
        """Test updates existing positions with P&L."""
        mock_position_repository.get_open_positions.return_value = [
            {
                'id': 1,
                'symbol': 'RELIANCE',
                'entry_price': 2500.0,
                'stop_loss': 2450.0,
                'target': 2600.0,
                'current_price': 2500.0
            }
        ]
        
        synced = await position_manager.sync_positions_from_kite()
        
        assert synced >= 1
        mock_position_repository.update_position.assert_called()
    
    @pytest.mark.asyncio
    async def test_closes_positions_not_in_kite(self, position_manager, mock_kite_service, mock_position_repository):
        """Test closes positions that are no longer in Kite."""
        # Position in DB but not in Kite
        mock_kite_service.kite.positions.return_value = {'day': []}
        mock_position_repository.get_open_positions.return_value = [
            {
                'id': 1,
                'symbol': 'RELIANCE',
                'entry_price': 2500.0,
                'stop_loss': 2450.0,
                'target': 2600.0,
                'current_price': 2550.0
            }
        ]
        
        synced = await position_manager.sync_positions_from_kite()
        
        assert synced >= 1
        mock_position_repository.close_position.assert_called()
    
    @pytest.mark.asyncio
    async def test_links_position_to_entry_order(self, position_manager, mock_kite_service, mock_position_repository, mock_order_repository):
        """Test links new position to entry order for SL order ID."""
        mock_position_repository.get_open_positions.return_value = []
        mock_order_repository.get_orders_by_symbol.return_value = [
            {
                'order_id': 'ENTRY123',
                'transaction_type': 'BUY',
                'status': 'COMPLETE',
                'strategy_name': 'vwap_breakout',
                'placed_at': datetime.now(),
                'metadata': {
                    'order_role': 'ENTRY',
                    'sl_order_id': 'SL456',
                    'stop_loss': 2450.0,
                    'target': 2600.0
                }
            }
        ]
        
        await position_manager.sync_positions_from_kite()
        
        # Verify position created with sl_order_id
        call_args = mock_position_repository.create_position.call_args
        assert call_args[1]['sl_order_id'] == 'SL456'


class TestDetectExitReason(TestPositionManager):
    """Test _detect_exit_reason method."""
    
    def test_detects_sl_hit(self, position_manager):
        """Test detects stop loss hit."""
        result = position_manager._detect_exit_reason(
            exit_price=2450.0,
            entry_price=2500.0,
            stop_loss=2450.0,
            target=2600.0
        )
        
        assert result == "SL_HIT"
    
    def test_detects_target_hit(self, position_manager):
        """Test detects target hit."""
        result = position_manager._detect_exit_reason(
            exit_price=2600.0,
            entry_price=2500.0,
            stop_loss=2450.0,
            target=2600.0
        )
        
        assert result == "TARGET_HIT"
    
    def test_detects_time_exit(self, position_manager):
        """Test detects time-based exit."""
        with patch('backend.core.services.trading.position_manager.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 15, 30)  # After 3:15 PM
            
            result = position_manager._detect_exit_reason(
                exit_price=2525.0,  # Between SL and target
                entry_price=2500.0,
                stop_loss=2450.0,
                target=2600.0
            )
            
            assert result == "TIME_EXIT"
    
    def test_detects_manual_exit(self, position_manager):
        """Test detects manual exit."""
        with patch('backend.core.services.trading.position_manager.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 10, 30)  # Before 3:15 PM
            
            result = position_manager._detect_exit_reason(
                exit_price=2525.0,  # Between SL and target
                entry_price=2500.0,
                stop_loss=2450.0,
                target=2600.0
            )
            
            assert result == "MANUAL_EXIT"


class TestPositionCache(TestPositionManager):
    """Test position caching behavior."""
    
    @pytest.mark.asyncio
    async def test_cache_is_used_within_ttl(self, position_manager, mock_kite_service):
        """Test cached positions used within TTL."""
        # First call populates cache
        await position_manager.get_open_positions()
        
        # Second call should use cache
        await position_manager.get_open_positions()
        
        # positions() should only be called once
        assert mock_kite_service.kite.positions.call_count == 1
    
    def test_invalidate_cache(self, position_manager):
        """Test cache invalidation."""
        position_manager._cache_timestamp = datetime.now()
        
        position_manager._invalidate_cache()
        
        assert position_manager._cache_timestamp is None


class TestGetDailyStats(TestPositionManager):
    """Test get_daily_stats method."""
    
    @pytest.mark.asyncio
    async def test_returns_daily_stats(self, position_manager, mock_position_repository):
        """Test returns daily statistics."""
        mock_position_repository.get_daily_stats.return_value = {
            'total_trades': 5,
            'winning_trades': 3,
            'losing_trades': 2,
            'total_pnl': 5000.0
        }
        
        result = await position_manager.get_daily_stats()
        
        assert result['total_trades'] == 5
        assert result['total_pnl'] == 5000.0


class TestGetTotalPnl(TestPositionManager):
    """Test get_total_pnl method."""
    
    @pytest.mark.asyncio
    async def test_calculates_total_pnl(self, position_manager, mock_kite_service):
        """Test calculates total P&L from positions."""
        mock_kite_service.kite.positions.return_value = {
            'day': [
                {'tradingsymbol': 'RELIANCE', 'quantity': 100, 'pnl': 5000.0},
                {'tradingsymbol': 'TCS', 'quantity': 50, 'pnl': 2500.0}
            ]
        }
        
        result = await position_manager.get_total_pnl()
        
        assert result == 7500.0
    
    @pytest.mark.asyncio
    async def test_returns_zero_on_error(self, position_manager, mock_kite_service):
        """Test returns 0 on error."""
        mock_kite_service.kite.positions.side_effect = Exception("API Error")
        
        result = await position_manager.get_total_pnl()
        
        assert result == 0.0
