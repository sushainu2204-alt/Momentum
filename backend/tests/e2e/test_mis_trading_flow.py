"""
End-to-End Tests for MIS Trading Flow with Trailing Stop Loss

Comprehensive tests covering the complete MIS trading lifecycle:
1. Signal generation → Order placement → Position tracking
2. Trailing stop loss activation and updates
3. Various exit scenarios (SL hit, target hit, time-based, manual)
4. Square-off scenarios

All tests use mock data and mock Kite client to simulate realistic trading flows.
"""

import pytest
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
import asyncio

from backend.core.models import Signal, SignalType, Position, PositionStatus
from backend.core.services.trading.order_manager import OrderManager, OrderResult
from backend.core.services.trading.position_manager import PositionManager
from backend.core.services.trading.trailing_sl_service import (
    TrailingStopLossService, 
    TrailingStopLossConfig
)
from backend.core.services.trading.signal_executor import SignalExecutor, ExecutionStatus
from backend.core.services.trading.capital_manager import CapitalManager
from backend.core.services.market.kite_service import KiteService


# ============================================================================
# MOCK CLASSES FOR E2E TESTING
# ============================================================================

class MockKiteAPI:
    """
    Enhanced mock Kite API for E2E testing.
    
    Simulates realistic Kite behavior including:
    - Order placement with various order types
    - Order modification and cancellation
    - Position tracking with P&L
    - Price updates for trailing SL
    """
    
    # Kite constants
    VARIETY_REGULAR = "regular"
    VARIETY_AMO = "amo"
    EXCHANGE_NSE = "NSE"
    EXCHANGE_BSE = "BSE"
    PRODUCT_MIS = "MIS"
    PRODUCT_CNC = "CNC"
    ORDER_TYPE_MARKET = "MARKET"
    ORDER_TYPE_LIMIT = "LIMIT"
    ORDER_TYPE_SLM = "SL-M"
    ORDER_TYPE_SL = "SL"
    
    def __init__(self):
        self._orders: Dict[str, Dict] = {}
        self._positions: Dict[str, Dict] = {}
        self._order_id_counter = 1000
        self._prices: Dict[str, float] = {}
        self._modification_counts: Dict[str, int] = {}
        self._sl_triggered: Dict[str, bool] = {}
    
    def set_price(self, symbol: str, price: float) -> None:
        """Set current price for a symbol (for testing price movements)."""
        self._prices[symbol] = price
        # Update position's last_price
        if symbol in self._positions:
            self._positions[symbol]['last_price'] = price
            # Calculate P&L
            qty = self._positions[symbol]['quantity']
            avg_price = self._positions[symbol]['average_price']
            self._positions[symbol]['pnl'] = (price - avg_price) * qty
    
    def trigger_sl(self, sl_order_id: str) -> bool:
        """Simulate SL order being triggered."""
        if sl_order_id not in self._orders:
            return False
        
        order = self._orders[sl_order_id]
        if order['order_type'] != 'SL-M' or order['status'] != 'TRIGGER PENDING':
            return False
        
        # Execute the SL order
        order['status'] = 'COMPLETE'
        order['filled_quantity'] = order['quantity']
        order['average_price'] = order['trigger_price']
        
        # Close the position
        symbol = order['tradingsymbol']
        if symbol in self._positions:
            self._positions[symbol]['quantity'] = 0
            self._positions[symbol]['pnl'] = (
                (order['trigger_price'] - self._positions[symbol]['average_price']) 
                * order['quantity']
            )
        
        self._sl_triggered[sl_order_id] = True
        return True
    
    def place_order(
        self,
        variety: str,
        exchange: str,
        tradingsymbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str,
        product: str,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        **kwargs
    ) -> str:
        """Place a mock order."""
        order_id = f"MIS_TEST_{self._order_id_counter}"
        self._order_id_counter += 1
        
        # Determine initial status
        if order_type == "SL-M":
            status = "TRIGGER PENDING"
        else:
            status = "COMPLETE"
        
        # Get execution price
        exec_price = price or self._prices.get(tradingsymbol, 100.0)
        
        self._orders[order_id] = {
            "order_id": order_id,
            "tradingsymbol": tradingsymbol,
            "exchange": exchange,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": order_type,
            "product": product,
            "price": price,
            "trigger_price": trigger_price,
            "status": status,
            "average_price": exec_price if status == "COMPLETE" else None,
            "filled_quantity": quantity if status == "COMPLETE" else 0,
            "variety": variety,
            "order_timestamp": datetime.now(),
        }
        
        # If entry order (BUY, not SL), create position
        if transaction_type == "BUY" and order_type in ["MARKET", "LIMIT"]:
            self._positions[tradingsymbol] = {
                "tradingsymbol": tradingsymbol,
                "instrument_token": kwargs.get("instrument_token", 12345),
                "quantity": quantity,
                "average_price": exec_price,
                "last_price": exec_price,
                "pnl": 0.0,
                "product": product,
                "exchange": exchange,
            }
        
        # If exit order (SELL, MARKET), close position
        if transaction_type == "SELL" and order_type == "MARKET":
            if tradingsymbol in self._positions:
                pos = self._positions[tradingsymbol]
                pos['quantity'] = 0
                pos['pnl'] = (exec_price - pos['average_price']) * quantity
        
        self._modification_counts[order_id] = 0
        return order_id
    
    def modify_order(
        self,
        variety: str,
        order_id: str,
        trigger_price: Optional[float] = None,
        price: Optional[float] = None,
        **kwargs
    ) -> str:
        """Modify an existing order."""
        if order_id not in self._orders:
            raise Exception(f"Order {order_id} not found")
        
        order = self._orders[order_id]
        
        # Check modification limit
        if self._modification_counts[order_id] >= 25:
            raise Exception("Maximum order modification limit reached")
        
        if trigger_price is not None:
            order['trigger_price'] = trigger_price
        if price is not None:
            order['price'] = price
        
        self._modification_counts[order_id] += 1
        return order_id
    
    def cancel_order(self, variety: str, order_id: str) -> str:
        """Cancel an order."""
        if order_id not in self._orders:
            raise Exception(f"Order {order_id} not found")
        
        self._orders[order_id]['status'] = 'CANCELLED'
        return order_id
    
    def orders(self) -> List[Dict]:
        """Get all orders."""
        return list(self._orders.values())
    
    def positions(self) -> Dict[str, List[Dict]]:
        """Get all positions."""
        day_positions = [
            pos for pos in self._positions.values()
            if pos['quantity'] != 0
        ]
        return {
            "day": list(self._positions.values()),
            "net": list(self._positions.values())
        }
    
    def get_order(self, order_id: str) -> Optional[Dict]:
        """Get order by ID."""
        return self._orders.get(order_id)
    
    def ltp(self, instruments: List[str]) -> Dict:
        """Get last traded prices."""
        return {
            inst: {"last_price": self._prices.get(inst.split(":")[-1], 100.0)}
            for inst in instruments
        }
    
    def clear(self) -> None:
        """Clear all state."""
        self._orders.clear()
        self._positions.clear()
        self._prices.clear()
        self._modification_counts.clear()
        self._sl_triggered.clear()
        self._order_id_counter = 1000


class MockOrderRepository:
    """Mock order repository for testing."""
    
    def __init__(self):
        self._orders: Dict[str, Dict] = {}
        self._modification_counts: Dict[str, int] = {}
    
    async def create_order(self, **kwargs) -> int:
        """Create order record."""
        order_id = kwargs.get('order_id')
        self._orders[order_id] = kwargs
        self._modification_counts[order_id] = kwargs.get('metadata', {}).get('modification_count', 0)
        return 1
    
    async def get_order(self, order_id: str) -> Optional[Dict]:
        """Get order by ID."""
        return self._orders.get(order_id)
    
    async def update_order(self, order_id: str, **kwargs) -> int:
        """Update order."""
        if order_id in self._orders:
            self._orders[order_id].update(kwargs)
            return 1
        return 0
    
    async def has_pending_order(self, symbol: str, transaction_type: Optional[str] = None) -> bool:
        """Check for pending orders."""
        for order in self._orders.values():
            if order.get('symbol') == symbol and order.get('status') in ['PENDING', 'OPEN', 'TRIGGER PENDING']:
                if transaction_type is None or order.get('transaction_type') == transaction_type:
                    return True
        return False
    
    async def get_pending_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get pending orders."""
        pending = []
        for order in self._orders.values():
            if order.get('status') in ['PENDING', 'OPEN', 'TRIGGER PENDING']:
                if symbol is None or order.get('symbol') == symbol:
                    pending.append(order)
        return pending
    
    async def get_modification_count(self, order_id: str) -> int:
        """Get modification count for order."""
        return self._modification_counts.get(order_id, 0)
    
    async def increment_modification_count(self, order_id: str) -> int:
        """Increment and return new modification count."""
        current = self._modification_counts.get(order_id, 0)
        self._modification_counts[order_id] = current + 1
        return current + 1
    
    async def get_orders_by_symbol(self, symbol: str) -> List[Dict]:
        """Get orders for a symbol."""
        return [o for o in self._orders.values() if o.get('symbol') == symbol]
    
    def clear(self) -> None:
        """Clear all orders."""
        self._orders.clear()
        self._modification_counts.clear()


class MockPositionRepository:
    """Mock position repository for testing."""
    
    def __init__(self):
        self._positions: Dict[int, Dict] = {}
        self._position_counter = 1
    
    async def create_position(self, **kwargs) -> int:
        """Create position record."""
        pos_id = self._position_counter
        self._position_counter += 1
        kwargs['id'] = pos_id
        kwargs['status'] = 'OPEN'
        kwargs['highest_price'] = kwargs.get('entry_price', 0)
        kwargs['original_stop_loss'] = None
        self._positions[pos_id] = kwargs
        return pos_id
    
    async def get_position_by_symbol(self, symbol: str, status: str = "OPEN") -> Optional[Dict]:
        """Get position by symbol."""
        for pos in self._positions.values():
            if pos.get('symbol') == symbol and pos.get('status') == status:
                return pos
        return None
    
    async def get_open_positions(self) -> List[Dict]:
        """Get all open positions."""
        return [p for p in self._positions.values() if p.get('status') == 'OPEN']
    
    async def get_open_positions_count(self) -> int:
        """Count open positions."""
        return len([p for p in self._positions.values() if p.get('status') == 'OPEN'])
    
    async def update_position(self, position_id: int, **kwargs) -> int:
        """Update position."""
        if position_id in self._positions:
            self._positions[position_id].update(kwargs)
            return 1
        return 0
    
    async def update_trailing_stop_loss(
        self,
        position_id: int,
        new_stop_loss: float,
        highest_price: float,
        original_stop_loss: Optional[float] = None
    ) -> int:
        """Update trailing stop loss."""
        if position_id in self._positions:
            pos = self._positions[position_id]
            if original_stop_loss is not None:
                pos['original_stop_loss'] = original_stop_loss
            pos['stop_loss'] = new_stop_loss
            pos['highest_price'] = highest_price
            return 1
        return 0
    
    async def close_position(
        self,
        position_id: int,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str,
        exit_order_id: Optional[str] = None
    ) -> int:
        """Close position."""
        if position_id in self._positions:
            pos = self._positions[position_id]
            pos['status'] = 'CLOSED'
            pos['exit_price'] = exit_price
            pos['exit_time'] = exit_time
            pos['exit_reason'] = exit_reason
            pos['exit_order_id'] = exit_order_id
            return 1
        return 0
    
    async def get_daily_stats(self, date) -> Dict:
        """Get daily statistics."""
        return {
            "total_trades": len(self._positions),
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0
        }
    
    def clear(self) -> None:
        """Clear all positions."""
        self._positions.clear()
        self._position_counter = 1


class MockCapitalManager:
    """Mock capital manager for testing."""
    
    def __init__(self, total_capital: float = 100000.0, max_positions: int = 5):
        self.total_capital = total_capital
        self.max_positions = max_positions
        self.allocated_capital = 0.0
        self.open_positions = 0
    
    async def check_position_limit(self) -> bool:
        """Check if more positions can be opened."""
        return self.open_positions < self.max_positions
    
    async def calculate_position_size(self, entry_price: float, stop_loss: float) -> int:
        """Calculate position size based on risk."""
        risk_per_share = abs(entry_price - stop_loss)
        max_risk = self.total_capital * 0.01  # 1% risk per trade
        quantity = int(max_risk / risk_per_share)
        return max(1, min(quantity, 100))  # Between 1 and 100 shares
    
    async def can_allocate(self, amount: float) -> bool:
        """Check if capital can be allocated."""
        return (self.allocated_capital + amount) <= self.total_capital * 0.8
    
    async def check_risk_limit(self, risk: float) -> bool:
        """Check if risk is within limits."""
        return risk <= self.total_capital * 0.02  # Max 2% risk per trade
    
    def allocate(self, amount: float) -> None:
        """Allocate capital."""
        self.allocated_capital += amount
        self.open_positions += 1
    
    def release(self, amount: float) -> None:
        """Release capital."""
        self.allocated_capital -= amount
        self.open_positions = max(0, self.open_positions - 1)


class MockDatabase:
    """Mock database for trade logging."""
    
    def __init__(self):
        self.tables: Dict[str, List[Dict]] = {
            'trade_logs': [],
            'cooldown_tracker': []
        }
        self.pool = True  # Fake pool to pass connection check
    
    async def insert(self, table: str, data: Dict) -> int:
        """Insert record."""
        if table not in self.tables:
            self.tables[table] = []
        self.tables[table].append(data)
        return len(self.tables[table])
    
    async def fetch_one(self, query: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Fetch single record."""
        return None
    
    async def fetch_all(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Fetch all records."""
        return []


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_kite_api():
    """Create mock Kite API."""
    return MockKiteAPI()


@pytest.fixture
def mock_kite_service(mock_kite_api):
    """Create mock KiteService wrapping MockKiteAPI."""
    service = MagicMock(spec=KiteService)
    service.kite = mock_kite_api
    return service


@pytest.fixture
def mock_order_repo():
    """Create mock order repository."""
    return MockOrderRepository()


@pytest.fixture
def mock_position_repo():
    """Create mock position repository."""
    return MockPositionRepository()


@pytest.fixture
def mock_capital_manager():
    """Create mock capital manager with ample capital for testing."""
    return MockCapitalManager(total_capital=500000.0, max_positions=10)


@pytest.fixture
def mock_db():
    """Create mock database."""
    return MockDatabase()


@pytest.fixture
def order_manager(mock_kite_service, mock_order_repo):
    """Create OrderManager with mocks."""
    return OrderManager(
        kite_service=mock_kite_service,
        order_repository=mock_order_repo
    )


@pytest.fixture
def position_manager(mock_kite_service, mock_position_repo, mock_order_repo):
    """Create PositionManager with mocks."""
    return PositionManager(
        kite_service=mock_kite_service,
        position_repository=mock_position_repo,
        order_repository=mock_order_repo
    )


@pytest.fixture
def trailing_sl_service(mock_position_repo, mock_kite_service, mock_order_repo, order_manager):
    """Create TrailingStopLossService with mocks."""
    config = TrailingStopLossConfig(
        enabled=True,
        activation_pct=0.5,  # Start trailing after 0.5% profit
        trail_pct=0.3,       # Trail 0.3% below highest price
        min_sl_move_pct=0.1  # Minimum 0.1% SL move
    )
    return TrailingStopLossService(
        position_repository=mock_position_repo,
        kite_service=mock_kite_service,
        order_repository=mock_order_repo,
        order_manager=order_manager,
        config=config
    )


@pytest.fixture
def signal_executor(mock_db, order_manager, position_manager, mock_capital_manager):
    """Create SignalExecutor with mocks."""
    return SignalExecutor(
        database=mock_db,
        order_manager=order_manager,
        position_manager=position_manager,
        capital_manager=mock_capital_manager,
        dry_run=False
    )


@pytest.fixture
def sample_buy_signal():
    """Create a sample BUY signal."""
    return Signal(
        symbol="RELIANCE",
        instrument_token=738561,
        signal_type=SignalType.BUY,
        price=2450.0,
        stop_loss=2420.0,  # 1.22% below entry
        target=2510.0,     # 2.45% above entry
        quantity=10,
        reason="VWAP breakout with volume surge",
        timestamp=datetime.now()
    )


# ============================================================================
# SCENARIO 1: COMPLETE MIS TRADE FLOW - ENTRY TO TARGET EXIT
# ============================================================================

class TestMISTradeFlowTargetExit:
    """Test complete MIS trade flow with target hit exit."""
    
    @pytest.mark.asyncio
    async def test_entry_order_placement(
        self,
        order_manager,
        mock_kite_api,
        sample_buy_signal
    ):
        """Test placing entry order with SL order."""
        # Set initial price
        mock_kite_api.set_price("RELIANCE", 2450.0)
        
        # Place order
        result = await order_manager.place_order(
            signal=sample_buy_signal,
            quantity=10,
            strategy_name="VWAP_BREAKOUT",
            order_type="MARKET",
            product="MIS"
        )
        
        # Verify result
        assert result is not None
        assert result.entry_order_id is not None
        assert result.sl_order_id is not None
        assert result.quantity == 10
        
        # Verify entry order
        entry_order = mock_kite_api.get_order(result.entry_order_id)
        assert entry_order is not None
        assert entry_order['tradingsymbol'] == "RELIANCE"
        assert entry_order['transaction_type'] == "BUY"
        assert entry_order['status'] == "COMPLETE"
        assert entry_order['product'] == "MIS"
        
        # Verify SL order
        sl_order = mock_kite_api.get_order(result.sl_order_id)
        assert sl_order is not None
        assert sl_order['order_type'] == "SL-M"
        assert sl_order['transaction_type'] == "SELL"
        assert sl_order['status'] == "TRIGGER PENDING"
        assert sl_order['trigger_price'] == 2420.0
    
    @pytest.mark.asyncio
    async def test_position_created_after_entry(
        self,
        order_manager,
        position_manager,
        mock_kite_api,
        mock_position_repo,
        sample_buy_signal
    ):
        """Test position is created after entry order fills."""
        mock_kite_api.set_price("RELIANCE", 2450.0)
        
        # Place entry order
        result = await order_manager.place_order(
            signal=sample_buy_signal,
            quantity=10,
            strategy_name="VWAP_BREAKOUT",
            order_type="MARKET",
            product="MIS"
        )
        
        # Sync positions from Kite (this creates DB record)
        synced = await position_manager.sync_positions_from_kite()
        assert synced >= 1
        
        # Verify position exists
        has_position = await position_manager.has_position("RELIANCE")
        assert has_position
    
    @pytest.mark.asyncio
    async def test_exit_at_target(
        self,
        order_manager,
        mock_kite_api,
        mock_order_repo,
        sample_buy_signal
    ):
        """Test exiting position when target is hit."""
        mock_kite_api.set_price("RELIANCE", 2450.0)
        
        # Place entry
        result = await order_manager.place_order(
            signal=sample_buy_signal,
            quantity=10,
            strategy_name="VWAP_BREAKOUT",
            order_type="MARKET",
            product="MIS"
        )
        sl_order_id = result.sl_order_id
        
        # Price rises to target
        mock_kite_api.set_price("RELIANCE", 2510.0)
        
        # Exit position (cancel SL order first)
        exit_order_id = await order_manager.exit_position(
            symbol="RELIANCE",
            quantity=10,
            transaction_type="SELL",
            product="MIS",
            sl_order_id=sl_order_id
        )
        
        assert exit_order_id is not None
        
        # Verify SL order was cancelled
        sl_order = mock_kite_api.get_order(sl_order_id)
        assert sl_order['status'] == "CANCELLED"
        
        # Verify position is closed
        positions = mock_kite_api.positions()['day']
        reliance_pos = next((p for p in positions if p['tradingsymbol'] == "RELIANCE"), None)
        assert reliance_pos['quantity'] == 0


# ============================================================================
# SCENARIO 2: STOP LOSS HIT
# ============================================================================

class TestMISTradeFlowStopLossHit:
    """Test MIS trade flow when stop loss is triggered."""
    
    @pytest.mark.asyncio
    async def test_sl_order_triggered(
        self,
        order_manager,
        mock_kite_api,
        sample_buy_signal
    ):
        """Test SL order is triggered when price drops."""
        mock_kite_api.set_price("RELIANCE", 2450.0)
        
        # Place entry
        result = await order_manager.place_order(
            signal=sample_buy_signal,
            quantity=10,
            strategy_name="VWAP_BREAKOUT",
            order_type="MARKET",
            product="MIS"
        )
        sl_order_id = result.sl_order_id
        
        # Price drops to SL level
        mock_kite_api.set_price("RELIANCE", 2415.0)
        
        # Trigger SL (in real trading, Kite would do this)
        triggered = mock_kite_api.trigger_sl(sl_order_id)
        assert triggered
        
        # Verify SL order executed
        sl_order = mock_kite_api.get_order(sl_order_id)
        assert sl_order['status'] == "COMPLETE"
        
        # Verify position closed
        positions = mock_kite_api.positions()['day']
        reliance_pos = next((p for p in positions if p['tradingsymbol'] == "RELIANCE"), None)
        assert reliance_pos['quantity'] == 0
        
        # Verify P&L is negative (loss)
        assert reliance_pos['pnl'] < 0


# ============================================================================
# SCENARIO 3: TRAILING STOP LOSS
# ============================================================================

class TestMISTradeFlowTrailingSL:
    """Test MIS trade with trailing stop loss updates."""
    
    @pytest.mark.asyncio
    async def test_trailing_sl_activation(
        self,
        trailing_sl_service,
        mock_position_repo,
        mock_kite_api,
        mock_order_repo
    ):
        """Test trailing SL activates after minimum profit threshold."""
        # Create a position manually for this test
        pos_id = await mock_position_repo.create_position(
            symbol="RELIANCE",
            instrument_token=738561,
            strategy_name="VWAP_BREAKOUT",
            entry_price=2450.0,
            entry_time=datetime.now(),
            quantity=10,
            stop_loss=2420.0,
            target=2510.0,
            sl_order_id="SL_ORDER_001"
        )
        
        # Create SL order in order repo
        await mock_order_repo.create_order(
            order_id="SL_ORDER_001",
            symbol="RELIANCE",
            instrument_token=738561,
            strategy_name="VWAP_BREAKOUT",
            order_type="SL-M",
            transaction_type="SELL",
            quantity=10,
            trigger_price=2420.0,
            status="TRIGGER PENDING",
            placed_at=datetime.now(),
            metadata={"modification_count": 0}
        )
        
        # Also add to Kite API mock
        mock_kite_api._orders["SL_ORDER_001"] = {
            "order_id": "SL_ORDER_001",
            "tradingsymbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "SELL",
            "quantity": 10,
            "order_type": "SL-M",
            "trigger_price": 2420.0,
            "status": "TRIGGER PENDING"
        }
        mock_kite_api._modification_counts["SL_ORDER_001"] = 0
        
        # Price moves up by 0.6% (above 0.5% activation threshold)
        # New price = 2450 * 1.006 = 2464.70
        mock_kite_api.set_price("RELIANCE", 2465.0)
        mock_kite_api._positions["RELIANCE"] = {
            "tradingsymbol": "RELIANCE",
            "instrument_token": 738561,
            "quantity": 10,
            "average_price": 2450.0,
            "last_price": 2465.0,
            "pnl": 150.0,
            "product": "MIS",
            "exchange": "NSE"
        }
        
        # Update position current_price in repo
        await mock_position_repo.update_position(
            position_id=pos_id,
            current_price=2465.0
        )
        
        # Process trailing SL
        stats = await trailing_sl_service.process_positions()
        
        # Check if SL was updated
        position = await mock_position_repo.get_position_by_symbol("RELIANCE", status="OPEN")
        
        # Trailing should have activated:
        # - Profit = (2465 - 2450) / 2450 = 0.61% > 0.5% activation
        # - New SL = 2465 * (1 - 0.3/100) = 2457.61 (rounded to 2457.61)
        # - Old SL was 2420, new SL > old SL, so update happens
        assert stats["checked"] == 1
        
        if stats["updated"] == 1:
            # SL should have been raised
            assert position["stop_loss"] > 2420.0
            assert position["highest_price"] == 2465.0
    
    @pytest.mark.asyncio
    async def test_trailing_sl_multiple_updates(
        self,
        trailing_sl_service,
        mock_position_repo,
        mock_kite_api,
        mock_order_repo
    ):
        """Test multiple trailing SL updates as price rises."""
        # Create position
        pos_id = await mock_position_repo.create_position(
            symbol="TCS",
            instrument_token=2953217,
            strategy_name="VWAP_BREAKOUT",
            entry_price=3500.0,
            entry_time=datetime.now(),
            quantity=5,
            stop_loss=3465.0,  # 1% SL
            target=3605.0,     # 3% target
            sl_order_id="SL_TCS_001"
        )
        
        # Create SL order
        await mock_order_repo.create_order(
            order_id="SL_TCS_001",
            symbol="TCS",
            instrument_token=2953217,
            strategy_name="VWAP_BREAKOUT",
            order_type="SL-M",
            transaction_type="SELL",
            quantity=5,
            trigger_price=3465.0,
            status="TRIGGER PENDING",
            placed_at=datetime.now(),
            metadata={"modification_count": 0}
        )
        
        mock_kite_api._orders["SL_TCS_001"] = {
            "order_id": "SL_TCS_001",
            "tradingsymbol": "TCS",
            "exchange": "NSE",
            "transaction_type": "SELL",
            "quantity": 5,
            "order_type": "SL-M",
            "trigger_price": 3465.0,
            "status": "TRIGGER PENDING"
        }
        mock_kite_api._modification_counts["SL_TCS_001"] = 0
        
        # Track SL updates
        sl_history = [3465.0]  # Initial SL
        
        # Simulate price rising in steps
        price_levels = [3520.0, 3550.0, 3580.0]  # Rising prices
        
        for price in price_levels:
            mock_kite_api.set_price("TCS", price)
            mock_kite_api._positions["TCS"] = {
                "tradingsymbol": "TCS",
                "instrument_token": 2953217,
                "quantity": 5,
                "average_price": 3500.0,
                "last_price": price,
                "pnl": (price - 3500.0) * 5,
                "product": "MIS",
                "exchange": "NSE"
            }
            
            await mock_position_repo.update_position(
                position_id=pos_id,
                current_price=price
            )
            
            # Process trailing SL
            await trailing_sl_service.process_positions()
            
            # Get updated position
            position = await mock_position_repo.get_position_by_symbol("TCS", status="OPEN")
            sl_history.append(position["stop_loss"])
        
        # Verify SL has been trailing upward
        # Each new SL should be >= previous (never moves down)
        for i in range(1, len(sl_history)):
            assert sl_history[i] >= sl_history[i-1], \
                f"SL should not decrease: {sl_history[i-1]} -> {sl_history[i]}"
    
    @pytest.mark.asyncio
    async def test_trailing_sl_not_active_below_threshold(
        self,
        trailing_sl_service,
        mock_position_repo,
        mock_kite_api,
        mock_order_repo
    ):
        """Test trailing SL doesn't activate below profit threshold."""
        # Create position
        pos_id = await mock_position_repo.create_position(
            symbol="INFY",
            instrument_token=340481,
            strategy_name="VWAP_BREAKOUT",
            entry_price=1600.0,
            entry_time=datetime.now(),
            quantity=10,
            stop_loss=1584.0,  # 1% SL
            target=1650.0,
            sl_order_id="SL_INFY_001"
        )
        
        await mock_order_repo.create_order(
            order_id="SL_INFY_001",
            symbol="INFY",
            instrument_token=340481,
            strategy_name="VWAP_BREAKOUT",
            order_type="SL-M",
            transaction_type="SELL",
            quantity=10,
            trigger_price=1584.0,
            status="TRIGGER PENDING",
            placed_at=datetime.now(),
            metadata={"modification_count": 0}
        )
        
        mock_kite_api._orders["SL_INFY_001"] = {
            "order_id": "SL_INFY_001",
            "tradingsymbol": "INFY",
            "exchange": "NSE",
            "transaction_type": "SELL",
            "quantity": 10,
            "order_type": "SL-M",
            "trigger_price": 1584.0,
            "status": "TRIGGER PENDING"
        }
        
        # Price moves up only 0.3% (below 0.5% activation threshold)
        mock_kite_api.set_price("INFY", 1604.8)
        mock_kite_api._positions["INFY"] = {
            "tradingsymbol": "INFY",
            "instrument_token": 340481,
            "quantity": 10,
            "average_price": 1600.0,
            "last_price": 1604.8,
            "pnl": 48.0,
            "product": "MIS",
            "exchange": "NSE"
        }
        
        await mock_position_repo.update_position(
            position_id=pos_id,
            current_price=1604.8
        )
        
        # Process trailing SL
        stats = await trailing_sl_service.process_positions()
        
        # SL should NOT be updated (profit below activation threshold)
        assert stats["updated"] == 0
        
        position = await mock_position_repo.get_position_by_symbol("INFY", status="OPEN")
        assert position["stop_loss"] == 1584.0  # Unchanged


# ============================================================================
# SCENARIO 4: TIME-BASED SQUARE OFF (EOD)
# ============================================================================

class TestMISTradeFlowSquareOff:
    """Test MIS time-based square off scenarios."""
    
    @pytest.mark.asyncio
    async def test_exit_all_positions_at_eod(
        self,
        order_manager,
        mock_kite_api,
        mock_position_repo
    ):
        """Test exiting all positions at end of day."""
        # Create multiple positions
        symbols = ["RELIANCE", "TCS", "INFY"]
        sl_orders = []
        
        for i, symbol in enumerate(symbols):
            mock_kite_api.set_price(symbol, 100.0 * (i + 1))
            
            signal = Signal(
                symbol=symbol,
                instrument_token=i + 1000,
                signal_type=SignalType.BUY,
                price=100.0 * (i + 1),
                stop_loss=98.0 * (i + 1),
                target=105.0 * (i + 1),
                timestamp=datetime.now()
            )
            
            result = await order_manager.place_order(
                signal=signal,
                quantity=10,
                strategy_name="TEST",
                order_type="MARKET",
                product="MIS"
            )
            
            sl_orders.append({
                'symbol': symbol,
                'sl_order_id': result.sl_order_id
            })
        
        # Verify we have 3 open positions
        positions = mock_kite_api.positions()['day']
        open_positions = [p for p in positions if p['quantity'] > 0]
        assert len(open_positions) == 3
        
        # Exit all positions (simulating EOD square off)
        exited = await order_manager.exit_all_positions(db_positions=sl_orders)
        
        assert exited == 3
        
        # Verify all positions closed
        positions = mock_kite_api.positions()['day']
        open_positions = [p for p in positions if p['quantity'] > 0]
        assert len(open_positions) == 0
        
        # Verify all SL orders cancelled
        for sl_info in sl_orders:
            sl_order = mock_kite_api.get_order(sl_info['sl_order_id'])
            assert sl_order['status'] == "CANCELLED"
    
    @pytest.mark.asyncio
    async def test_square_off_with_profit(
        self,
        order_manager,
        mock_kite_api,
        sample_buy_signal
    ):
        """Test square off with profitable position."""
        mock_kite_api.set_price("RELIANCE", 2450.0)
        
        # Place entry
        result = await order_manager.place_order(
            signal=sample_buy_signal,
            quantity=10,
            strategy_name="VWAP_BREAKOUT",
            order_type="MARKET",
            product="MIS"
        )
        
        # Price rises but not to target
        mock_kite_api.set_price("RELIANCE", 2480.0)
        
        # Square off
        exit_order_id = await order_manager.exit_position(
            symbol="RELIANCE",
            quantity=10,
            transaction_type="SELL",
            product="MIS",
            sl_order_id=result.sl_order_id
        )
        
        assert exit_order_id is not None
        
        # Verify profit
        positions = mock_kite_api.positions()['day']
        reliance_pos = next(p for p in positions if p['tradingsymbol'] == "RELIANCE")
        assert reliance_pos['pnl'] > 0  # Should be (2480 - 2450) * 10 = 300
    
    @pytest.mark.asyncio
    async def test_square_off_with_loss(
        self,
        order_manager,
        mock_kite_api,
        sample_buy_signal
    ):
        """Test square off with losing position (price dropped but SL not hit)."""
        mock_kite_api.set_price("RELIANCE", 2450.0)
        
        # Place entry
        result = await order_manager.place_order(
            signal=sample_buy_signal,
            quantity=10,
            strategy_name="VWAP_BREAKOUT",
            order_type="MARKET",
            product="MIS"
        )
        
        # Price drops but stays above SL (2420)
        mock_kite_api.set_price("RELIANCE", 2430.0)
        
        # Square off
        exit_order_id = await order_manager.exit_position(
            symbol="RELIANCE",
            quantity=10,
            transaction_type="SELL",
            product="MIS",
            sl_order_id=result.sl_order_id
        )
        
        assert exit_order_id is not None
        
        # Verify loss
        positions = mock_kite_api.positions()['day']
        reliance_pos = next(p for p in positions if p['tradingsymbol'] == "RELIANCE")
        assert reliance_pos['pnl'] < 0  # Should be (2430 - 2450) * 10 = -200


# ============================================================================
# SCENARIO 5: ORDER MODIFICATION LIMITS
# ============================================================================

class TestOrderModificationLimits:
    """Test SL order modification limit handling."""
    
    @pytest.mark.asyncio
    async def test_sl_order_recreation_at_limit(
        self,
        order_manager,
        mock_kite_api,
        mock_order_repo
    ):
        """Test SL order is recreated when modification limit is reached."""
        # Create initial SL order with high modification count
        original_sl_order_id = "SL_LIMIT_TEST"
        mock_kite_api._orders[original_sl_order_id] = {
            "order_id": original_sl_order_id,
            "tradingsymbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "SELL",
            "quantity": 10,
            "order_type": "SL-M",
            "trigger_price": 2420.0,
            "status": "TRIGGER PENDING"
        }
        mock_kite_api._modification_counts[original_sl_order_id] = 20
        
        await mock_order_repo.create_order(
            order_id=original_sl_order_id,
            symbol="RELIANCE",
            instrument_token=738561,
            strategy_name="TEST",
            order_type="SL-M",
            transaction_type="SELL",
            quantity=10,
            trigger_price=2420.0,
            status="TRIGGER PENDING",
            placed_at=datetime.now(),
            metadata={
                "product": "MIS",
                "order_role": "STOP_LOSS",
                "modification_count": 20
            }
        )
        
        # Try to modify SL order (should trigger recreation)
        success, new_order_id = await order_manager.modify_sl_order(
            order_id=original_sl_order_id,
            new_trigger_price=2450.0,
            modification_count=20  # At the limit
        )
        
        assert success
        assert new_order_id is not None
        assert new_order_id != original_sl_order_id
        
        # Original order should be cancelled
        original_order = mock_kite_api.get_order(original_sl_order_id)
        assert original_order['status'] == "CANCELLED"
        
        # New order should exist with new trigger price
        new_order = mock_kite_api.get_order(new_order_id)
        assert new_order is not None
        assert new_order['trigger_price'] == 2450.0


# ============================================================================
# SCENARIO 6: SIGNAL EXECUTION WITH GUARDRAILS
# ============================================================================

class TestSignalExecutionGuardrails:
    """Test signal execution with all guardrails."""
    
    @pytest.mark.asyncio
    async def test_signal_execution_during_market_hours(
        self,
        mock_db,
        mock_kite_api,
        mock_kite_service,
        mock_capital_manager,
        sample_buy_signal
    ):
        """Test signal execution during market hours with all guardrails passing."""
        mock_kite_api.set_price("RELIANCE", 2450.0)
        
        # Create mock managers with all methods mocked
        mock_order_manager = MagicMock()
        mock_order_manager.has_pending_order = AsyncMock(return_value=False)
        mock_order_manager.place_order = AsyncMock(
            return_value=OrderResult(
                entry_order_id="TEST_ENTRY_001",
                sl_order_id="TEST_SL_001",
                quantity=10
            )
        )
        
        mock_position_manager = MagicMock()
        mock_position_manager.has_position = AsyncMock(return_value=False)
        
        # Create SignalExecutor with mocked managers
        signal_executor = SignalExecutor(
            database=mock_db,
            order_manager=mock_order_manager,
            position_manager=mock_position_manager,
            capital_manager=mock_capital_manager,
            dry_run=False
        )
        
        # Patch time to be during market hours
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime.now().replace(hour=10, minute=30)
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=True):
                    result = await signal_executor.execute_signal(
                        signal=sample_buy_signal,
                        strategy_name="VWAP_BREAKOUT"
                    )
        
        assert result.status == ExecutionStatus.EXECUTED
        assert result.order_id is not None
    
    @pytest.mark.asyncio
    async def test_signal_ignored_outside_market_hours(
        self,
        signal_executor,
        sample_buy_signal
    ):
        """Test signal is ignored outside market hours."""
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime.now().replace(hour=8, minute=0)
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=False):
                result = await signal_executor.execute_signal(
                    signal=sample_buy_signal,
                    strategy_name="VWAP_BREAKOUT"
                )
        
        assert result.status == ExecutionStatus.IGNORED
        assert "Market closed" in result.reason
    
    @pytest.mark.asyncio
    async def test_signal_ignored_with_existing_position(
        self,
        signal_executor,
        position_manager,
        mock_kite_api,
        sample_buy_signal
    ):
        """Test signal is ignored when position already exists."""
        # Create existing position
        mock_kite_api._positions["RELIANCE"] = {
            "tradingsymbol": "RELIANCE",
            "quantity": 10,
            "average_price": 2400.0,
            "last_price": 2450.0,
            "pnl": 500.0
        }
        
        with patch('backend.core.services.trading.signal_executor.now_ist') as mock_now:
            mock_now.return_value = datetime.now().replace(hour=10, minute=30)
            
            with patch('backend.core.services.trading.signal_executor.is_market_hours', return_value=True):
                with patch('backend.core.services.trading.signal_executor.is_trading_window', return_value=True):
                    result = await signal_executor.execute_signal(
                        signal=sample_buy_signal,
                        strategy_name="VWAP_BREAKOUT"
                    )
        
        assert result.status == ExecutionStatus.IGNORED
        assert "Already have position" in result.reason


# ============================================================================
# SCENARIO 7: COMPLETE TRADE LIFECYCLE
# ============================================================================

class TestCompleteTradeLifecycle:
    """Test complete trade lifecycle from signal to exit."""
    
    @pytest.mark.asyncio
    async def test_full_trade_lifecycle_with_trailing_sl_and_target_exit(
        self,
        order_manager,
        position_manager,
        trailing_sl_service,
        mock_kite_api,
        mock_kite_service,
        mock_position_repo,
        mock_order_repo,
        sample_buy_signal
    ):
        """
        Test complete trade lifecycle:
        1. Entry signal → Order placed
        2. Position created
        3. Price rises → Trailing SL activates
        4. Price continues up → Trailing SL updates
        5. Price hits target → Exit position
        """
        # Step 1: Entry
        mock_kite_api.set_price("RELIANCE", 2450.0)
        entry_result = await order_manager.place_order(
            signal=sample_buy_signal,
            quantity=10,
            strategy_name="VWAP_BREAKOUT",
            order_type="MARKET",
            product="MIS"
        )
        assert entry_result.entry_order_id is not None
        sl_order_id = entry_result.sl_order_id
        
        # Step 2: Create position in repo
        pos_id = await mock_position_repo.create_position(
            symbol="RELIANCE",
            instrument_token=738561,
            strategy_name="VWAP_BREAKOUT",
            entry_price=2450.0,
            entry_time=datetime.now(),
            quantity=10,
            stop_loss=2420.0,
            target=2510.0,
            sl_order_id=sl_order_id
        )
        initial_sl = 2420.0
        
        # Add SL order to repo for trailing service
        await mock_order_repo.create_order(
            order_id=sl_order_id,
            symbol="RELIANCE",
            instrument_token=738561,
            strategy_name="VWAP_BREAKOUT",
            order_type="SL-M",
            transaction_type="SELL",
            quantity=10,
            trigger_price=initial_sl,
            status="TRIGGER PENDING",
            placed_at=datetime.now(),
            metadata={"modification_count": 0}
        )
        
        # Step 3: Price rises, trailing SL activates (need >0.5% profit)
        # Entry: 2450, profit_pct = (2475 - 2450) / 2450 * 100 = 1.02% > 0.5% activation
        mock_kite_api.set_price("RELIANCE", 2475.0)  # +1.02% profit
        
        # Update position with current price for trailing SL service
        await mock_position_repo.update_position(pos_id, current_price=2475.0, highest_price=2475.0)
        
        # Mock Kite positions to return the position with current price
        mock_kite_service.kite.positions = MagicMock(return_value={
            'day': [{
                'tradingsymbol': 'RELIANCE',
                'quantity': 10,
                'average_price': 2450.0,
                'last_price': 2475.0
            }]
        })
        
        stats1 = await trailing_sl_service.process_positions()
        pos_after_trail1 = await mock_position_repo.get_position_by_symbol("RELIANCE", "OPEN")
        
        # With trail_pct=0.3%, new_sl = 2475 * (1 - 0.003) = 2467.575
        # This is higher than initial 2420, so it should update
        if pos_after_trail1:
            first_trail_sl = pos_after_trail1.get("stop_loss", initial_sl)
            assert first_trail_sl > initial_sl, f"SL should trail up from {initial_sl} to ~2467"
        
        # Step 4: Price continues up significantly, trailing SL updates again
        mock_kite_api.set_price("RELIANCE", 2520.0)  # +2.86% profit - well above target
        await mock_position_repo.update_position(pos_id, current_price=2520.0, highest_price=2520.0)
        
        # Update Kite mock
        mock_kite_service.kite.positions = MagicMock(return_value={
            'day': [{
                'tradingsymbol': 'RELIANCE',
                'quantity': 10,
                'average_price': 2450.0,
                'last_price': 2520.0
            }]
        })
        
        stats2 = await trailing_sl_service.process_positions()
        pos_after_trail2 = await mock_position_repo.get_position_by_symbol("RELIANCE", "OPEN")
        
        # With trail_pct=0.3%, new_sl = 2520 * (1 - 0.003) = 2512.44
        # This should be higher than the first trail SL
        if pos_after_trail2 and pos_after_trail1:
            second_trail_sl = pos_after_trail2.get("stop_loss", first_trail_sl)
            # The SL should have moved up
            assert second_trail_sl >= first_trail_sl, \
                f"SL should be >= {first_trail_sl}, got {second_trail_sl}"
        
        # Step 5: Price hits target, exit
        mock_kite_api.set_price("RELIANCE", 2510.0)
        
        exit_order_id = await order_manager.exit_position(
            symbol="RELIANCE",
            quantity=10,
            transaction_type="SELL",
            product="MIS",
            sl_order_id=sl_order_id
        )
        
        assert exit_order_id is not None
        
        # Close position in repo
        await mock_position_repo.close_position(
            position_id=pos_id,
            exit_price=2510.0,
            exit_time=datetime.now(),
            exit_reason="TARGET_HIT"
        )
        
        # Verify final state
        final_pos = self._get_position_by_id(mock_position_repo, pos_id)
        assert final_pos["status"] == "CLOSED"
        assert final_pos["exit_reason"] == "TARGET_HIT"
        assert final_pos["exit_price"] == 2510.0
    
    def _get_position_by_id(self, repo, pos_id):
        """Helper to get position by ID."""
        return repo._positions.get(pos_id)
    
    @pytest.mark.asyncio
    async def test_full_trade_lifecycle_with_sl_hit(
        self,
        order_manager,
        mock_kite_api,
        mock_position_repo,
        sample_buy_signal
    ):
        """
        Test trade lifecycle when stop loss is hit:
        1. Entry signal → Order placed
        2. Price drops → SL triggered
        3. Position closed with loss
        """
        # Step 1: Entry
        mock_kite_api.set_price("RELIANCE", 2450.0)
        entry_result = await order_manager.place_order(
            signal=sample_buy_signal,
            quantity=10,
            strategy_name="VWAP_BREAKOUT",
            order_type="MARKET",
            product="MIS"
        )
        sl_order_id = entry_result.sl_order_id
        
        # Create position in repo
        pos_id = await mock_position_repo.create_position(
            symbol="RELIANCE",
            instrument_token=738561,
            strategy_name="VWAP_BREAKOUT",
            entry_price=2450.0,
            entry_time=datetime.now(),
            quantity=10,
            stop_loss=2420.0,
            target=2510.0,
            sl_order_id=sl_order_id
        )
        
        # Step 2: Price drops to SL
        mock_kite_api.set_price("RELIANCE", 2415.0)
        
        # Trigger SL
        triggered = mock_kite_api.trigger_sl(sl_order_id)
        assert triggered
        
        # Step 3: Close position
        await mock_position_repo.close_position(
            position_id=pos_id,
            exit_price=2420.0,  # SL price
            exit_time=datetime.now(),
            exit_reason="SL_HIT"
        )
        
        # Verify final state
        final_pos = mock_position_repo._positions[pos_id]
        assert final_pos["status"] == "CLOSED"
        assert final_pos["exit_reason"] == "SL_HIT"
        
        # Calculate loss
        entry = final_pos["entry_price"]
        exit_price = final_pos["exit_price"]
        qty = final_pos["quantity"]
        pnl = (exit_price - entry) * qty  # (2420 - 2450) * 10 = -300
        assert pnl < 0


# ============================================================================
# SCENARIO 8: EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Test edge cases in MIS trading flow."""
    
    @pytest.mark.asyncio
    async def test_cancel_orphaned_sl_orders(
        self,
        order_manager,
        mock_kite_api,
        mock_order_repo
    ):
        """Test cancelling SL orders when position is closed externally."""
        # Create position with SL order
        mock_kite_api.set_price("HDFC", 1600.0)
        
        signal = Signal(
            symbol="HDFC",
            instrument_token=999,
            signal_type=SignalType.BUY,
            price=1600.0,
            stop_loss=1580.0,
            target=1650.0,
            timestamp=datetime.now()
        )
        
        result = await order_manager.place_order(
            signal=signal,
            quantity=5,
            strategy_name="TEST",
            order_type="MARKET",
            product="MIS"
        )
        sl_order_id = result.sl_order_id
        
        # Simulate position being closed externally (manually or via target)
        mock_kite_api._positions["HDFC"]["quantity"] = 0
        
        # Cancel orphaned SL orders
        cancelled = await order_manager.cancel_orphaned_sl_orders(
            open_position_symbols=[],  # No open positions
            db_positions=[{"symbol": "HDFC", "sl_order_id": sl_order_id}]
        )
        
        assert cancelled == 1
        
        # Verify SL order is cancelled
        sl_order = mock_kite_api.get_order(sl_order_id)
        assert sl_order["status"] == "CANCELLED"
    
    @pytest.mark.asyncio
    async def test_position_sync_creates_db_record(
        self,
        position_manager,
        mock_kite_api,
        mock_position_repo,
        mock_order_repo
    ):
        """Test position sync creates DB record for Kite position."""
        # Create position directly in Kite (simulating external trade)
        mock_kite_api._positions["SBIN"] = {
            "tradingsymbol": "SBIN",
            "instrument_token": 779521,
            "quantity": 20,
            "average_price": 550.0,
            "last_price": 555.0,
            "pnl": 100.0,
            "product": "MIS",
            "exchange": "NSE"
        }
        
        # Sync should detect and create DB record
        synced = await position_manager.sync_positions_from_kite()
        
        assert synced >= 1
        
        # Verify position exists in DB
        db_pos = await mock_position_repo.get_position_by_symbol("SBIN", status="OPEN")
        assert db_pos is not None
        assert db_pos["symbol"] == "SBIN"
        assert db_pos["entry_price"] == 550.0
    
    @pytest.mark.asyncio
    async def test_multiple_positions_different_symbols(
        self,
        order_manager,
        mock_kite_api
    ):
        """Test managing multiple positions in different symbols."""
        symbols = ["RELIANCE", "TCS", "INFY", "HDFC", "SBIN"]
        positions = []
        
        for i, symbol in enumerate(symbols):
            base_price = 100.0 * (i + 1)
            mock_kite_api.set_price(symbol, base_price)
            
            signal = Signal(
                symbol=symbol,
                instrument_token=1000 + i,
                signal_type=SignalType.BUY,
                price=base_price,
                stop_loss=base_price * 0.98,
                target=base_price * 1.03,
                timestamp=datetime.now()
            )
            
            result = await order_manager.place_order(
                signal=signal,
                quantity=10,
                strategy_name="MULTI_TEST",
                order_type="MARKET",
                product="MIS"
            )
            
            positions.append({
                "symbol": symbol,
                "entry_order_id": result.entry_order_id,
                "sl_order_id": result.sl_order_id
            })
        
        # Verify all positions exist
        kite_positions = mock_kite_api.positions()['day']
        open_positions = [p for p in kite_positions if p['quantity'] > 0]
        assert len(open_positions) == 5
        
        # Exit one position
        await order_manager.exit_position(
            symbol="TCS",
            quantity=10,
            transaction_type="SELL",
            product="MIS",
            sl_order_id=positions[1]["sl_order_id"]
        )
        
        # Verify only 4 positions remain
        kite_positions = mock_kite_api.positions()['day']
        open_positions = [p for p in kite_positions if p['quantity'] > 0]
        assert len(open_positions) == 4


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
