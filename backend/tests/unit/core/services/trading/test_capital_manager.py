"""
Unit Tests for Capital Manager Service

Tests capital allocation, position sizing, and risk management.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import date, datetime
from dataclasses import dataclass

from backend.core.services.trading.capital_manager import CapitalManager, TradingLimits


class TestTradingLimits:
    """Test TradingLimits dataclass."""
    
    def test_default_values(self):
        """Test default trading limits."""
        limits = TradingLimits()
        
        assert limits.starting_capital == 100000
        assert limits.max_positions == 5
        assert limits.position_size_pct == 20
        assert limits.risk_per_trade_pct == 2
        assert limits.max_capital_at_risk_pct == 10
    
    def test_custom_values(self):
        """Test custom trading limits."""
        limits = TradingLimits(
            starting_capital=500000,
            max_positions=10,
            position_size_pct=10,
            risk_per_trade_pct=1,
            max_capital_at_risk_pct=5
        )
        
        assert limits.starting_capital == 500000
        assert limits.max_positions == 10
        assert limits.position_size_pct == 10
        assert limits.risk_per_trade_pct == 1
        assert limits.max_capital_at_risk_pct == 5


class TestCapitalManager:
    """Test CapitalManager service."""
    
    @pytest.fixture
    def mock_database(self):
        """Create mock database."""
        db = Mock()
        db.fetch_one = AsyncMock(return_value=None)
        db.insert = AsyncMock(return_value=1)
        db.update = AsyncMock(return_value=True)
        return db
    
    @pytest.fixture
    def mock_kite_service(self):
        """Create mock Kite service."""
        kite = Mock()
        kite.margins = Mock(return_value={
            'equity': {
                'net': 100000,
                'available': {
                    'cash': 80000,
                    'collateral': 10000
                },
                'utilised': {
                    'debits': 10000,
                    'opening_balance': 100000,
                    'm2m_realised': 500,
                    'm2m_unrealised': 200
                }
            }
        })
        return kite
    
    @pytest.fixture
    def mock_position_manager(self):
        """Create mock position manager."""
        pm = Mock()
        pm.get_open_positions_count = AsyncMock(return_value=2)
        return pm
    
    @pytest.fixture
    def capital_manager(self, mock_database, mock_kite_service, mock_position_manager):
        """Create capital manager with mocked dependencies."""
        return CapitalManager(
            database=mock_database,
            kite_service=mock_kite_service,
            position_manager=mock_position_manager,
            limits=TradingLimits()
        )
    
    @pytest.fixture
    def paper_trading_manager(self, mock_database, mock_kite_service, mock_position_manager):
        """Create capital manager with mock capital for paper trading."""
        return CapitalManager(
            database=mock_database,
            kite_service=mock_kite_service,
            position_manager=mock_position_manager,
            limits=TradingLimits(),
            mock_capital=200000  # Paper trading mode
        )


class TestGetAvailableCapital(TestCapitalManager):
    """Test get_available_capital method."""
    
    @pytest.mark.asyncio
    async def test_returns_available_capital_from_kite(self, capital_manager):
        """Test getting available capital from Kite API."""
        result = await capital_manager.get_available_capital()
        
        # cash (80000) + collateral (10000) = 90000
        assert result == 90000
    
    @pytest.mark.asyncio
    async def test_returns_mock_capital_in_paper_trading(self, paper_trading_manager):
        """Test returns mock capital in paper trading mode."""
        result = await paper_trading_manager.get_available_capital()
        
        assert result == 200000
    
    @pytest.mark.asyncio
    async def test_fallback_to_db_when_kite_fails(self, capital_manager, mock_database):
        """Test fallback to database when Kite fails."""
        # Make Kite fail
        capital_manager.kite.margins.side_effect = Exception("API Error")
        
        # Setup DB fallback
        mock_database.fetch_one.return_value = {
            'available_capital': 75000,
            'current_capital': 100000
        }
        
        result = await capital_manager.get_available_capital()
        
        assert result == 75000
    
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_data_available(self, capital_manager, mock_database):
        """Test returns 0 when no data available."""
        # Make Kite fail
        capital_manager.kite.margins.side_effect = Exception("API Error")
        
        # No DB data
        mock_database.fetch_one.return_value = None
        
        result = await capital_manager.get_available_capital()
        
        assert result == 0.0


class TestGetCurrentCapital(TestCapitalManager):
    """Test get_current_capital method."""
    
    @pytest.mark.asyncio
    async def test_returns_net_capital_from_kite(self, capital_manager):
        """Test getting current capital from Kite API."""
        result = await capital_manager.get_current_capital()
        
        # net = 100000
        assert result == 100000
    
    @pytest.mark.asyncio
    async def test_returns_mock_capital_in_paper_trading(self, paper_trading_manager):
        """Test returns mock capital in paper trading mode."""
        result = await paper_trading_manager.get_current_capital()
        
        assert result == 200000
    
    @pytest.mark.asyncio
    async def test_fallback_to_db_when_kite_fails(self, capital_manager, mock_database):
        """Test fallback to database when Kite fails."""
        capital_manager.kite.margins.side_effect = Exception("API Error")
        
        mock_database.fetch_one.return_value = {
            'available_capital': 75000,
            'current_capital': 95000
        }
        
        result = await capital_manager.get_current_capital()
        
        assert result == 95000


class TestGetUtilizedMargin(TestCapitalManager):
    """Test get_utilized_margin method."""
    
    @pytest.mark.asyncio
    async def test_returns_utilized_margin(self, capital_manager):
        """Test getting utilized margin from Kite."""
        result = await capital_manager.get_utilized_margin()
        
        # debits = 10000
        assert result == 10000
    
    @pytest.mark.asyncio
    async def test_returns_zero_on_error(self, capital_manager):
        """Test returns 0 on error."""
        capital_manager.kite.margins.side_effect = Exception("API Error")
        
        result = await capital_manager.get_utilized_margin()
        
        assert result == 0.0


class TestCanAllocate(TestCapitalManager):
    """Test can_allocate method."""
    
    @pytest.mark.asyncio
    async def test_returns_true_when_capital_available(self, capital_manager):
        """Test returns True when enough capital available."""
        # Available = 90000, requesting 15000
        result = await capital_manager.can_allocate(15000)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_returns_false_when_insufficient_capital(self, capital_manager):
        """Test returns False when insufficient capital."""
        # Available = 90000, requesting 100000
        result = await capital_manager.can_allocate(100000)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_returns_false_when_position_too_large(self, capital_manager):
        """Test returns False when position exceeds size limit."""
        # Current capital = 100000, max 20% = 20000
        # Request 25000 (within available 90000 but exceeds 20%)
        result = await capital_manager.can_allocate(25000)
        
        assert result is False


class TestCalculatePositionSize(TestCapitalManager):
    """Test calculate_position_size method."""
    
    @pytest.mark.asyncio
    async def test_calculates_position_size_based_on_risk(self, capital_manager):
        """Test position size calculation based on risk."""
        # Current capital = 100000
        # Risk 2% = 2000
        # SL distance = 100 - 95 = 5
        # Quantity by risk = 2000 / 5 = 400
        # BUT: Position value = 400 * 100 = 40000 > max 20% (20000)
        # So quantity is capped: 20000 / 100 = 200
        
        result = await capital_manager.calculate_position_size(
            entry_price=100,
            stop_loss=95
        )
        
        # Position size limited by max position size (20% of capital)
        assert result == 200
    
    @pytest.mark.asyncio
    async def test_respects_position_size_limit(self, capital_manager):
        """Test position size respects max position size limit."""
        # Current capital = 100000
        # Max 20% = 20000
        # With entry_price=10, max quantity = 2000
        # But risk calculation might give more
        
        result = await capital_manager.calculate_position_size(
            entry_price=10,
            stop_loss=9.5  # Only 0.5 SL distance
        )
        
        # Risk 2% = 2000
        # Quantity by risk = 2000 / 0.5 = 4000
        # But max position = 20000 / 10 = 2000
        assert result == 2000
    
    @pytest.mark.asyncio
    async def test_handles_zero_sl_distance(self, capital_manager):
        """Test handles zero SL distance gracefully."""
        # When SL equals entry, should use 1% default
        result = await capital_manager.calculate_position_size(
            entry_price=100,
            stop_loss=100  # Same as entry
        )
        
        # Should use 1% of entry = 1 as SL distance
        assert result >= 1
    
    @pytest.mark.asyncio
    async def test_custom_risk_percentage(self, capital_manager):
        """Test with custom risk percentage."""
        # Current capital = 100000
        # Risk 1% = 1000
        # SL distance = 100 - 95 = 5
        # Quantity = 1000 / 5 = 200
        
        result = await capital_manager.calculate_position_size(
            entry_price=100,
            stop_loss=95,
            risk_pct=1
        )
        
        assert result == 200


class TestCheckPositionLimit(TestCapitalManager):
    """Test check_position_limit method."""
    
    @pytest.mark.asyncio
    async def test_returns_true_when_below_limit(self, capital_manager, mock_position_manager):
        """Test returns True when below max positions."""
        # Current positions = 2, max = 5
        result = await capital_manager.check_position_limit()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_returns_false_when_at_limit(self, capital_manager, mock_position_manager):
        """Test returns False when at max positions."""
        mock_position_manager.get_open_positions_count.return_value = 5
        
        result = await capital_manager.check_position_limit()
        
        assert result is False


class TestGetTotalRisk(TestCapitalManager):
    """Test get_total_risk method."""
    
    @pytest.mark.asyncio
    async def test_calculates_total_risk_from_positions(self, capital_manager, mock_database):
        """Test calculates total risk from open positions."""
        # Mock PositionRepository with open positions (dynamic import in get_total_risk)
        with patch('backend.infrastructure.database.position_repository.PositionRepository') as MockRepo:
            mock_repo = Mock()
            mock_repo.get_open_positions = AsyncMock(return_value=[
                {'entry_price': 100, 'stop_loss': 95, 'quantity': 100},  # Risk = 500
                {'entry_price': 200, 'stop_loss': 190, 'quantity': 50}   # Risk = 500
            ])
            MockRepo.return_value = mock_repo
            
            result = await capital_manager.get_total_risk()
            
            assert result == 1000


class TestCheckRiskLimit(TestCapitalManager):
    """Test check_risk_limit method."""
    
    @pytest.mark.asyncio
    async def test_returns_true_when_within_limit(self, capital_manager):
        """Test returns True when within risk limit."""
        # Mock get_total_risk to return 5000
        with patch.object(capital_manager, 'get_total_risk', new_callable=AsyncMock) as mock_risk:
            mock_risk.return_value = 5000
            
            # Current capital = 100000, max 10% = 10000
            # Total risk = 5000 + 2000 = 7000 < 10000
            result = await capital_manager.check_risk_limit(2000)
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_returns_false_when_exceeds_limit(self, capital_manager):
        """Test returns False when exceeds risk limit."""
        with patch.object(capital_manager, 'get_total_risk', new_callable=AsyncMock) as mock_risk:
            mock_risk.return_value = 8000
            
            # Total risk = 8000 + 3000 = 11000 > 10000
            result = await capital_manager.check_risk_limit(3000)
            
            assert result is False


class TestMarginsCache(TestCapitalManager):
    """Test margins caching behavior."""
    
    @pytest.mark.asyncio
    async def test_cache_is_used_within_ttl(self, capital_manager):
        """Test cached margins used within TTL."""
        # First call populates cache
        await capital_manager.get_available_capital()
        
        # Second call should use cache
        await capital_manager.get_available_capital()
        
        # margins() should only be called once
        assert capital_manager.kite.margins.call_count == 1
    
    def test_invalidate_cache(self, capital_manager):
        """Test cache invalidation."""
        capital_manager._margins_cache = {'test': 'data'}
        capital_manager._cache_timestamp = datetime.now()
        
        capital_manager._invalidate_cache()
        
        assert capital_manager._margins_cache is None
        assert capital_manager._cache_timestamp is None


class TestSyncMarginsToDb(TestCapitalManager):
    """Test sync_margins_to_db method."""
    
    @pytest.mark.asyncio
    async def test_syncs_margins_to_db(self, capital_manager, mock_database):
        """Test syncing margins data to database."""
        # No existing record
        mock_database.fetch_one.return_value = None
        
        await capital_manager.sync_margins_to_db()
        
        # Should insert new record
        mock_database.insert.assert_called_once()
        call_args = mock_database.insert.call_args
        assert call_args[0][0] == "capital_state"
    
    @pytest.mark.asyncio
    async def test_updates_existing_record(self, capital_manager, mock_database):
        """Test updating existing capital state record."""
        # Existing record
        mock_database.fetch_one.return_value = {'id': 1, 'date': date.today()}
        
        await capital_manager.sync_margins_to_db()
        
        # Should update existing record
        mock_database.update.assert_called_once()


class TestInitializeDailyCapital(TestCapitalManager):
    """Test initialize_daily_capital method."""
    
    @pytest.mark.asyncio
    async def test_initializes_capital_for_new_day(self, capital_manager, mock_database):
        """Test initializing capital for a new trading day."""
        # No existing record
        mock_database.fetch_one.return_value = None
        
        await capital_manager.initialize_daily_capital()
        
        # Should insert new record
        mock_database.insert.assert_called_once()
        call_args = mock_database.insert.call_args
        assert 'starting_capital' in call_args[0][1]
    
    @pytest.mark.asyncio
    async def test_skips_if_already_initialized(self, capital_manager, mock_database):
        """Test skips initialization if already done."""
        # Existing record
        mock_database.fetch_one.return_value = {'id': 1}
        
        await capital_manager.initialize_daily_capital()
        
        # Should not insert
        mock_database.insert.assert_not_called()


class TestGetCapitalSummary(TestCapitalManager):
    """Test get_capital_summary method."""
    
    @pytest.mark.asyncio
    async def test_returns_comprehensive_summary(self, capital_manager):
        """Test returns comprehensive capital summary."""
        result = await capital_manager.get_capital_summary()
        
        assert result['source'] == 'kite'
        assert result['starting_capital'] == 100000
        assert result['current_capital'] == 100000
        assert result['available_capital'] == 90000
        assert 'total_pnl' in result
        assert 'timestamp' in result
    
    @pytest.mark.asyncio
    async def test_fallback_to_db_summary(self, capital_manager, mock_database):
        """Test fallback to database for summary."""
        # Make Kite fail
        capital_manager.kite.margins.side_effect = Exception("API Error")
        
        # Setup DB fallback
        mock_database.fetch_one.return_value = {
            'starting_capital': 100000,
            'current_capital': 95000,
            'available_capital': 75000,
            'capital_in_positions': 20000,
            'total_pnl': -5000,
            'realized_pnl': -3000,
            'unrealized_pnl': -2000,
            'open_positions_count': 2,
            'max_positions_allowed': 5,
            'total_risk': 4000,
            'max_risk_allowed': 10000,
            'updated_at': datetime.now()
        }
        
        result = await capital_manager.get_capital_summary()
        
        assert result['source'] == 'database'
        assert result['current_capital'] == 95000
    
    @pytest.mark.asyncio
    async def test_returns_error_when_no_data(self, capital_manager, mock_database):
        """Test returns error when no data available."""
        capital_manager.kite.margins.side_effect = Exception("API Error")
        mock_database.fetch_one.return_value = None
        
        result = await capital_manager.get_capital_summary()
        
        assert result['source'] == 'unavailable'
        assert 'error' in result
