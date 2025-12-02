"""
Pytest Configuration and Shared Fixtures

Provides mocks and fixtures for testing the Momentum trading system.
"""

import pytest
import asyncio
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional
from unittest.mock import MagicMock, AsyncMock
import pandas as pd
import numpy as np

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# EVENT LOOP FIXTURE
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# MOCK KITE SERVICE
# ============================================================================

class MockKiteService:
    """Mock Kite API for testing without real API calls."""
    
    def __init__(self):
        self.orders: Dict[str, Dict] = {}
        self.positions: List[Dict] = []
        self.next_order_id = 1000
        self.margins_data = {
            "equity": {
                "enabled": True,
                "net": 100000.00,
                "available": {
                    "adhoc_margin": 0,
                    "cash": 80000.00,
                    "opening_balance": 100000.00,
                    "live_balance": 100000.00,
                    "collateral": 20000.00,
                    "intraday_payin": 0
                },
                "utilised": {
                    "debits": 20000.00,
                    "exposure": 0,
                    "m2m_realised": 500.00,
                    "m2m_unrealised": 200.00,
                    "option_premium": 0,
                    "payout": 0,
                    "span": 0,
                    "holding_sales": 0,
                    "turnover": 0,
                    "liquid_collateral": 0,
                    "stock_collateral": 0,
                    "opening_balance": 100000.00
                }
            }
        }
        self.instruments_data = [
            {"tradingsymbol": "RELIANCE", "instrument_token": 738561, "exchange": "NSE"},
            {"tradingsymbol": "TCS", "instrument_token": 2953217, "exchange": "NSE"},
            {"tradingsymbol": "INFY", "instrument_token": 408065, "exchange": "NSE"},
            {"tradingsymbol": "HDFC", "instrument_token": 340481, "exchange": "NSE"},
            {"tradingsymbol": "ICICIBANK", "instrument_token": 1270529, "exchange": "NSE"},
        ]
        # Simulate the kite client
        self.kite = MagicMock()
        self.kite.orders.return_value = list(self.orders.values())
        self.kite.positions.return_value = {"net": self.positions, "day": self.positions}
        self.kite.margins.return_value = self.margins_data
        self.kite.instruments.return_value = self.instruments_data
        self.kite.profile.return_value = {"user_name": "Test User", "user_id": "TEST123"}
        self.kite.ltp.return_value = {"NSE:RELIANCE": {"last_price": 2450.50}}
    
    def place_order(
        self,
        tradingsymbol: str,
        exchange: str = "NSE",
        transaction_type: str = "BUY",
        quantity: int = 1,
        order_type: str = "MARKET",
        product: str = "MIS",
        variety: str = "regular",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        stoploss: Optional[float] = None,
        squareoff: Optional[float] = None,
        **kwargs
    ) -> str:
        """Mock order placement."""
        order_id = f"TEST_{self.next_order_id}"
        self.next_order_id += 1
        
        self.orders[order_id] = {
            "order_id": order_id,
            "exchange_order_id": f"EXC_{order_id}",
            "tradingsymbol": tradingsymbol,
            "exchange": exchange,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": order_type,
            "product": product,
            "status": "COMPLETE",
            "status_message": "Order completed",
            "filled_quantity": quantity,
            "pending_quantity": 0,
            "average_price": price if price else 100.0,
            "price": price,
            "trigger_price": trigger_price,
            "placed_by": "TEST_USER",
            "order_timestamp": datetime.now(),
            "exchange_timestamp": datetime.now(),
            "variety": variety,
            "validity": "DAY",
            "stoploss": stoploss,
            "squareoff": squareoff,
        }
        
        return order_id
    
    def margins(self, segment: str = "equity") -> Dict:
        """Get margin data."""
        return self.margins_data
    
    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "5minute",
        continuous: bool = False,
        oi: bool = False
    ) -> List[Dict]:
        """Get historical OHLCV data."""
        # Generate mock historical data
        num_candles = 50
        dates = pd.date_range(end=to_date, periods=num_candles, freq='5min')
        base_price = 100.0
        
        data = []
        for i, date in enumerate(dates):
            price = base_price + i * 0.1
            data.append({
                "date": date,
                "open": price - 0.3,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price,
                "volume": 100000 + i * 1000
            })
        return data
    
    def quote(self, instruments: List[str]) -> Dict:
        """Get live quotes for instruments."""
        result = {}
        for instrument in instruments:
            symbol = instrument.split(":")[1] if ":" in instrument else instrument
            result[instrument] = {
                "last_price": 2450.0,
                "volume": 1000000,
                "ohlc": {
                    "open": 2430.0,
                    "high": 2460.0,
                    "low": 2425.0,
                    "close": 2445.0
                },
                "instrument_token": 738561
            }
        return result
    
    def ltp(self, instruments: List[str]) -> Dict:
        """Get last traded price."""
        result = {}
        for instrument in instruments:
            result[instrument] = {"last_price": 2450.0}
        return result
    
    def orders(self) -> List[Dict]:
        """Get all orders."""
        return list(self.orders.values())
    
    def positions(self) -> Dict[str, List[Dict]]:
        """Get all positions."""
        return {"net": self.positions, "day": self.positions}
    
    def add_position(self, symbol: str, quantity: int, avg_price: float, pnl: float = 0):
        """Add a mock position."""
        self.positions.append({
            "tradingsymbol": symbol,
            "exchange": "NSE",
            "instrument_token": 12345,
            "product": "MIS",
            "quantity": quantity,
            "average_price": avg_price,
            "last_price": avg_price + (pnl / quantity) if quantity else avg_price,
            "pnl": pnl,
            "m2m": pnl,
            "unrealised": pnl,
            "realised": 0,
        })
    
    def update_margins(self, available_cash: float, utilized: float = 0):
        """Update mock margins."""
        self.margins_data["equity"]["available"]["cash"] = available_cash
        self.margins_data["equity"]["utilised"]["debits"] = utilized
        self.margins_data["equity"]["net"] = available_cash + utilized


@pytest.fixture
def mock_kite():
    """Provide a MockKiteService instance."""
    return MockKiteService()


# Alias for backward compatibility
@pytest.fixture
def mock_kite_service(mock_kite):
    """Alias for mock_kite fixture."""
    return mock_kite


# ============================================================================
# MOCK DATABASE
# ============================================================================

class MockDatabase:
    """Mock database for testing without real PostgreSQL."""
    
    def __init__(self):
        self.tables: Dict[str, List[Dict]] = {
            "positions": [],
            "orders": [],
            "capital_state": [],
            "trade_logs": [],
            "cooldown_tracker": [],
            "signals": [],
        }
        self.next_ids: Dict[str, int] = {table: 1 for table in self.tables}
        self._connected = False
    
    async def connect(self):
        """Mock connect."""
        self._connected = True
    
    async def disconnect(self):
        """Mock disconnect."""
        self._connected = False
    
    async def insert(self, table: str, data: Dict) -> int:
        """Insert a record and return ID."""
        record_id = self.next_ids[table]
        self.next_ids[table] += 1
        
        data["id"] = record_id
        data["created_at"] = datetime.now()
        self.tables[table].append(data)
        
        return record_id
    
    async def update(self, table: str, data: Dict, where: Dict) -> int:
        """Update records matching where clause."""
        updated = 0
        for record in self.tables[table]:
            if all(record.get(k) == v for k, v in where.items()):
                record.update(data)
                updated += 1
        return updated
    
    async def fetch_one(self, query: str, params: Dict) -> Optional[Dict]:
        """Fetch single record."""
        # Simple mock: return first matching record based on params
        table_name = self._extract_table_name(query)
        if table_name and table_name in self.tables:
            for record in self.tables[table_name]:
                # Check if any param value matches record
                if self._matches_params(record, params):
                    return record
        return None
    
    async def fetch_all(self, query: str, params: Dict) -> List[Dict]:
        """Fetch all matching records."""
        table_name = self._extract_table_name(query)
        if table_name and table_name in self.tables:
            return [r for r in self.tables[table_name] if self._matches_params(r, params)]
        return []
    
    async def execute(self, query: str, params: Dict) -> int:
        """Execute a query."""
        # Mock execution
        return 1
    
    def _extract_table_name(self, query: str) -> Optional[str]:
        """Extract table name from query."""
        query_lower = query.lower()
        for table in self.tables:
            if table in query_lower:
                return table
        return None
    
    def _matches_params(self, record: Dict, params: Dict) -> bool:
        """Check if record matches params."""
        if not params:
            return True
        for key, value in params.items():
            # Handle $1, $2 style params
            clean_key = key.replace("$", "").replace("1", "").replace("2", "").strip()
            if clean_key and record.get(clean_key) != value:
                return False
        return True
    
    def seed_data(self, table: str, records: List[Dict]):
        """Seed test data."""
        for record in records:
            record_id = self.next_ids[table]
            self.next_ids[table] += 1
            record["id"] = record_id
            self.tables[table].append(record)


@pytest.fixture
def mock_db():
    """Provide a MockDatabase instance."""
    return MockDatabase()


# Alias for backward compatibility with AsyncMock methods
@pytest.fixture
def mock_database():
    """Provide a mock database with AsyncMock methods for repository tests."""
    db = MagicMock()
    db.connect = AsyncMock()
    db.disconnect = AsyncMock()
    db.insert = AsyncMock(return_value=1)
    db.update = AsyncMock(return_value=1)
    db.fetch_one = AsyncMock(return_value=None)
    db.fetch_all = AsyncMock(return_value=[])
    db.execute = AsyncMock(return_value=1)
    return db


# Redis mock fixture
@pytest.fixture
def mock_redis():
    """Provide a mock Redis client."""
    redis = MagicMock()
    redis.publish = AsyncMock()
    redis.subscribe = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    return redis


# ============================================================================
# SAMPLE DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing."""
    def _create(num_candles: int = 100, base_price: float = 100.0, trend: str = "up"):
        np.random.seed(42)  # Reproducible
        
        dates = pd.date_range(end=datetime.now(), periods=num_candles, freq='5min')
        
        # Create price movement based on trend
        if trend == "up":
            prices = base_price + np.cumsum(np.random.randn(num_candles) * 0.5 + 0.1)
        elif trend == "down":
            prices = base_price + np.cumsum(np.random.randn(num_candles) * 0.5 - 0.1)
        else:
            prices = base_price + np.cumsum(np.random.randn(num_candles) * 0.5)
        
        prices = np.maximum(prices, base_price * 0.8)
        
        df = pd.DataFrame({
            'date': dates,
            'open': prices - np.random.rand(num_candles) * 0.5,
            'high': prices + np.random.rand(num_candles) * 1.0,
            'low': prices - np.random.rand(num_candles) * 0.5,
            'close': prices,
            'volume': np.random.randint(100000, 500000, num_candles)
        })
        
        return df
    
    return _create


@pytest.fixture
def sample_signal():
    """Create a sample Signal for testing."""
    from backend.models import Signal, SignalType
    
    def _create(
        symbol: str = "RELIANCE",
        price: float = 2450.0,
        stop_loss: float = 2420.0,
        target: float = 2510.0,
        signal_type: SignalType = SignalType.BUY
    ):
        return Signal(
            symbol=symbol,
            instrument_token=738561,
            signal_type=signal_type,
            price=price,
            stop_loss=stop_loss,
            target=target,
            quantity=10,
            timestamp=datetime.now(),
            reason="Test signal"
        )
    
    return _create


@pytest.fixture
def sample_candidate():
    """Create a sample Candidate for testing."""
    from backend.models import Candidate
    
    def _create(
        symbol: str = "RELIANCE",
        current_price: float = 2450.0,
        gain_pct: float = 2.5,
        volume: int = 500000
    ):
        return Candidate(
            symbol=symbol,
            instrument_token=738561,
            current_price=current_price,
            gain_pct=gain_pct,
            volume=volume,
            avg_volume=300000,
            timestamp=datetime.now(),
            open_price=current_price - 50,
            high_price=current_price + 10,
            low_price=current_price - 60,
        )
    
    return _create


@pytest.fixture
def sample_position():
    """Create a sample Position for testing."""
    from backend.models import Position, PositionStatus
    
    def _create(
        symbol: str = "RELIANCE",
        entry_price: float = 2450.0,
        quantity: int = 10,
        stop_loss: float = 2420.0,
        target: float = 2510.0
    ):
        return Position(
            symbol=symbol,
            instrument_token=738561,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            target=target,
            entry_time=datetime.now(),
            current_price=entry_price,
            status=PositionStatus.OPEN
        )
    
    return _create


# ============================================================================
# MARKET HOURS FIXTURES
# ============================================================================

@pytest.fixture
def market_hours_datetime():
    """Create a datetime during market hours (10:30 AM IST)."""
    from backend.core.utils.timezone import IST
    return datetime.now(IST).replace(hour=10, minute=30, second=0, microsecond=0)


@pytest.fixture
def before_market_datetime():
    """Create a datetime before market open (9:00 AM IST)."""
    from backend.core.utils.timezone import IST
    return datetime.now(IST).replace(hour=9, minute=0, second=0, microsecond=0)


@pytest.fixture
def after_market_datetime():
    """Create a datetime after market close (4:00 PM IST)."""
    from backend.core.utils.timezone import IST
    return datetime.now(IST).replace(hour=16, minute=0, second=0, microsecond=0)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

@pytest.fixture
def assert_signal_valid():
    """Helper to validate Signal objects."""
    def _assert(signal):
        from backend.models import Signal, SignalType
        
        assert signal is not None
        assert isinstance(signal, Signal)
        assert signal.symbol is not None
        assert signal.price > 0
        assert signal.stop_loss is not None
        assert signal.target is not None
        assert signal.stop_loss < signal.price < signal.target
        assert isinstance(signal.signal_type, SignalType)
    
    return _assert
