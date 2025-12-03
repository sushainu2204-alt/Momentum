"""
Unit Tests for Signal Executor Service

Tests signal execution with all guardrails.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, time

from backend.core.services.trading.signal_executor import (
    SignalExecutor, ExecutionResult, ExecutionStatus
)
from backend.core.models import Signal, SignalType


class TestExecutionResult:
    """Test ExecutionResult dataclass."""
    
    def test_executed_result(self):
        """Test executed result."""
        result = ExecutionResult(
            status=ExecutionStatus.EXECUTED,
            decision="EXECUTE",
            reason="Order placed successfully",
            order_id="ORD123",
            quantity=100
        )
        
        assert result.status == ExecutionStatus.EXECUTED
        assert result.order_id == "ORD123"
        assert result.quantity == 100
    
    def test_ignored_result(self):
        """Test ignored result."""
        result = ExecutionResult(
            status=ExecutionStatus.IGNORED,
            decision="IGNORE",
            reason="Already have position"
        )
        
        assert result.status == ExecutionStatus.IGNORED
        assert result.order_id is None
    
    def test_failed_result(self):
        """Test failed result."""
        result = ExecutionResult(
            status=ExecutionStatus.FAILED,
            decision="FAILED",
            reason="Execution error",
            error="API Error"
        )
        
        assert result.status == ExecutionStatus.FAILED
        assert result.error == "API Error"


class TestSignalExecutor:
    """Test SignalExecutor service."""
    
    @pytest.fixture
    def mock_database(self):
        """Create mock database."""
        db = Mock()
        db.fetch_one = AsyncMock(return_value=None)
        db.insert = AsyncMock(return_value=1)
        return db
    
    @pytest.fixture
    def mock_order_manager(self):
        """Create mock order manager."""
        om = Mock()
        om.has_pending_order = AsyncMock(return_value=False)
        om.place_order = AsyncMock(return_value=Mock(entry_order_id="ORD123"))
        return om
    
    @pytest.fixture
    def mock_position_manager(self):
        """Create mock position manager."""
        pm = Mock()
        pm.has_position = AsyncMock(return_value=False)
        pm.get_position = AsyncMock(return_value=None)
        return pm
    
    @pytest.fixture
    def mock_capital_manager(self):
        """Create mock capital manager."""
        cm = Mock()
        cm.check_position_limit = AsyncMock(return_value=True)
        cm.calculate_position_size = AsyncMock(return_value=100)
        cm.can_allocate = AsyncMock(return_value=True)
        cm.check_risk_limit = AsyncMock(return_value=True)
        return cm
    
    @pytest.fixture
    def signal_executor(self, mock_database, mock_order_manager, mock_position_manager, mock_capital_manager):
        """Create signal executor with mocked dependencies."""
        return SignalExecutor(
            database=mock_database,
            order_manager=mock_order_manager,
            position_manager=mock_position_manager,
            capital_manager=mock_capital_manager
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


class TestExecuteSignal(TestSignalExecutor):
    """Test execute_signal method."""
    
    @pytest.mark.asyncio
    async def test_executes_valid_signal(self, signal_executor, sample_signal):
        """Test executing a valid signal."""
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 30)  # 10:30 AM
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=True):
                    result = await signal_executor.execute_signal(
                        signal=sample_signal,
                        strategy_name="vwap_breakout"
                    )
        
        assert result.status == ExecutionStatus.EXECUTED
        assert result.order_id == "ORD123"
    
    @pytest.mark.asyncio
    async def test_ignores_when_market_closed(self, signal_executor, sample_signal):
        """Test ignores signal when market is closed."""
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 8, 0)  # 8 AM - before market
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=False):
                result = await signal_executor.execute_signal(
                    signal=sample_signal,
                    strategy_name="vwap_breakout"
                )
        
        assert result.status == ExecutionStatus.IGNORED
        assert "Market closed" in result.reason
    
    @pytest.mark.asyncio
    async def test_ignores_outside_trading_window(self, signal_executor, sample_signal):
        """Test ignores signal outside trading window."""
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 9, 20)  # 9:20 AM - in skip window
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=False):
                    result = await signal_executor.execute_signal(
                        signal=sample_signal,
                        strategy_name="vwap_breakout"
                    )
        
        assert result.status == ExecutionStatus.IGNORED
        assert "trading window" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_ignores_when_position_exists(self, signal_executor, sample_signal, mock_position_manager):
        """Test ignores signal when position already exists."""
        mock_position_manager.has_position.return_value = True
        
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 30)
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=True):
                    result = await signal_executor.execute_signal(
                        signal=sample_signal,
                        strategy_name="vwap_breakout"
                    )
        
        assert result.status == ExecutionStatus.IGNORED
        assert "position" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_ignores_when_pending_order_exists(self, signal_executor, sample_signal, mock_order_manager):
        """Test ignores signal when pending order exists."""
        mock_order_manager.has_pending_order.return_value = True
        
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 30)
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=True):
                    result = await signal_executor.execute_signal(
                        signal=sample_signal,
                        strategy_name="vwap_breakout"
                    )
        
        assert result.status == ExecutionStatus.IGNORED
        assert "pending" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_ignores_in_cooldown(self, signal_executor, sample_signal, mock_database):
        """Test ignores signal when in cooldown."""
        mock_database.fetch_one.return_value = {'id': 1, 'symbol': 'RELIANCE'}  # Cooldown exists
        
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 30)
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=True):
                    result = await signal_executor.execute_signal(
                        signal=sample_signal,
                        strategy_name="vwap_breakout"
                    )
        
        assert result.status == ExecutionStatus.IGNORED
        assert "cooldown" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_ignores_when_max_positions_reached(self, signal_executor, sample_signal, mock_capital_manager):
        """Test ignores signal when max positions reached."""
        mock_capital_manager.check_position_limit.return_value = False
        
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 30)
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=True):
                    result = await signal_executor.execute_signal(
                        signal=sample_signal,
                        strategy_name="vwap_breakout"
                    )
        
        assert result.status == ExecutionStatus.IGNORED
        assert "position" in result.reason.lower() or "limit" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_ignores_when_insufficient_capital(self, signal_executor, sample_signal, mock_capital_manager):
        """Test ignores signal when insufficient capital."""
        mock_capital_manager.can_allocate.return_value = False
        
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 30)
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=True):
                    result = await signal_executor.execute_signal(
                        signal=sample_signal,
                        strategy_name="vwap_breakout"
                    )
        
        assert result.status == ExecutionStatus.IGNORED
        assert "capital" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_ignores_when_risk_limit_exceeded(self, signal_executor, sample_signal, mock_capital_manager):
        """Test ignores signal when risk limit exceeded."""
        mock_capital_manager.check_risk_limit.return_value = False
        
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 30)
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=True):
                    result = await signal_executor.execute_signal(
                        signal=sample_signal,
                        strategy_name="vwap_breakout"
                    )
        
        assert result.status == ExecutionStatus.IGNORED
        assert "risk" in result.reason.lower()
    
    @pytest.mark.asyncio
    async def test_handles_order_failure(self, signal_executor, sample_signal, mock_order_manager):
        """Test handles order placement failure."""
        mock_order_manager.place_order.return_value = None
        
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 30)
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=True):
                    result = await signal_executor.execute_signal(
                        signal=sample_signal,
                        strategy_name="vwap_breakout"
                    )
        
        assert result.status == ExecutionStatus.FAILED


class TestDryRunMode(TestSignalExecutor):
    """Test dry run mode."""
    
    @pytest.fixture
    def dry_run_executor(self, mock_database, mock_order_manager, mock_position_manager, mock_capital_manager):
        """Create signal executor in dry run mode."""
        return SignalExecutor(
            database=mock_database,
            order_manager=mock_order_manager,
            position_manager=mock_position_manager,
            capital_manager=mock_capital_manager,
            dry_run=True
        )
    
    @pytest.mark.asyncio
    async def test_dry_run_does_not_place_order(self, dry_run_executor, sample_signal, mock_order_manager):
        """Test dry run mode doesn't place actual orders."""
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 30)
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=True):
                    result = await dry_run_executor.execute_signal(
                        signal=sample_signal,
                        strategy_name="vwap_breakout"
                    )
        
        assert result.status == ExecutionStatus.EXECUTED
        assert "DRY RUN" in result.reason
        mock_order_manager.place_order.assert_not_called()


class TestTimeChecks(TestSignalExecutor):
    """Test time-related methods."""
    
    def test_is_market_open_during_hours(self, signal_executor):
        """Test market open check during trading hours."""
        trading_time = datetime(2024, 1, 15, 10, 30)  # Monday 10:30 AM
        
        result = signal_executor._is_market_open(trading_time)
        
        assert result is True
    
    def test_is_market_open_before_hours(self, signal_executor):
        """Test market open check before trading hours."""
        before_market = datetime(2024, 1, 15, 8, 0)  # 8 AM
        
        result = signal_executor._is_market_open(before_market)
        
        assert result is False
    
    def test_is_market_open_on_weekend(self, signal_executor):
        """Test market open check on weekend."""
        weekend = datetime(2024, 1, 13, 10, 30)  # Saturday
        
        result = signal_executor._is_market_open(weekend)
        
        assert result is False
    
    def test_should_exit_all_positions(self, signal_executor):
        """Test exit time check."""
        exit_time = datetime(2024, 1, 15, 15, 20)  # 3:20 PM
        
        result = signal_executor.should_exit_all_positions(exit_time)
        
        assert result is True
    
    def test_should_not_exit_before_time(self, signal_executor):
        """Test not exiting before exit time."""
        before_exit = datetime(2024, 1, 15, 14, 0)  # 2 PM
        
        result = signal_executor.should_exit_all_positions(before_exit)
        
        assert result is False


class TestCooldownManagement(TestSignalExecutor):
    """Test cooldown management."""
    
    @pytest.mark.asyncio
    async def test_check_cooldown_returns_true_when_in_cooldown(self, signal_executor, mock_database):
        """Test cooldown check returns True when in cooldown."""
        mock_database.fetch_one.return_value = {'id': 1}  # Cooldown exists
        
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 30)
            
            result = await signal_executor._check_cooldown("RELIANCE", "vwap_breakout")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_cooldown_returns_false_when_not_in_cooldown(self, signal_executor, mock_database):
        """Test cooldown check returns False when not in cooldown."""
        mock_database.fetch_one.return_value = None  # No cooldown
        
        result = await signal_executor._check_cooldown("RELIANCE", "vwap_breakout")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_add_cooldown(self, signal_executor, mock_database):
        """Test adding cooldown."""
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime(2024, 1, 15, 10, 30)
            
            await signal_executor._add_cooldown("RELIANCE", "vwap_breakout")
        
        mock_database.insert.assert_called()


class TestExecutionStats(TestSignalExecutor):
    """Test execution statistics."""
    
    @pytest.mark.asyncio
    async def test_get_execution_stats(self, signal_executor, mock_database):
        """Test getting execution statistics."""
        mock_database.fetch_one.return_value = {
            'total_signals': 10,
            'executed': 5,
            'ignored': 4,
            'failed': 1
        }
        
        result = await signal_executor.get_execution_stats()
        
        assert result['total_signals'] == 10
        assert result['executed'] == 5
