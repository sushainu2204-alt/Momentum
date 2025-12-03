"""
Pytest Configuration and Shared Fixtures

This module provides:
1. Async event loop configuration
2. Mock factories for external dependencies (Kite, Database, Redis, Broker)
3. Mock implementations of interfaces (IDatabase, IDataSource, IBroker, ICache)
4. Sample data factories for OHLCV, Signals, Candidates, Positions
5. Utility fixtures for common test scenarios
"""

import asyncio
from datetime import datetime, time, timedelta
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

# Import interfaces for type checking
from backend.infrastructure.database.base import IDatabase
from backend.infrastructure.data_sources.base import IDataSource, Quote, Instrument
from backend.infrastructure.brokers.base import (
    IBroker, OrderResponse, OrderStatus, Position as BrokerPosition, MarginInfo, OrderBook
)


# ============================================================================
# ASYNC EVENT LOOP
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# MOCK FACTORIES
# ============================================================================

class MockKiteClient:
    """
    Mock Kite Connect client for testing.
    
    Provides realistic mock responses for all Kite API methods.
    """
    
    def __init__(self):
        self._orders: Dict[str, Dict] = {}
        self._positions: List[Dict] = []
        self._order_id_counter = 1000
    
    def place_order(
        self,
        tradingsymbol: str,
        exchange: str = "NSE",
        transaction_type: str = "BUY",
        quantity: int = 1,
        order_type: str = "MARKET",
        product: str = "MIS",
        price: Optional[float] = None,
        **kwargs
    ) -> str:
        """Mock order placement."""
        order_id = f"TEST_{self._order_id_counter}"
        self._order_id_counter += 1
        
        self._orders[order_id] = {
            "order_id": order_id,
            "tradingsymbol": tradingsymbol,
            "exchange": exchange,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": order_type,
            "product": product,
            "status": "COMPLETE",
            "average_price": price or 100.0,
            "filled_quantity": quantity,
        }
        return order_id
    
    def orders(self) -> List[Dict]:
        """Get all orders."""
        return list(self._orders.values())
    
    def positions(self) -> Dict[str, List[Dict]]:
        """Get positions."""
        return {"net": self._positions, "day": self._positions}
    
    def margins(self, segment: str = "equity") -> Dict:
        """Get margins."""
        return {
            "equity": {
                "net": 100000.0,
                "available": {"cash": 80000.0},
                "utilised": {"debits": 20000.0},
            }
        }
    
    def ltp(self, instruments: List[str]) -> Dict:
        """Get last traded price."""
        return {inst: {"last_price": 2450.0} for inst in instruments}
    
    def quote(self, instruments: List[str]) -> Dict:
        """Get quotes."""
        return {
            inst: {
                "last_price": 2450.0,
                "volume": 1000000,
                "ohlc": {"open": 2400.0, "high": 2460.0, "low": 2390.0, "close": 2445.0},
            }
            for inst in instruments
        }
    
    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "5minute",
        **kwargs
    ) -> List[Dict]:
        """Generate mock historical data."""
        num_candles = 50
        dates = pd.date_range(end=to_date, periods=num_candles, freq="5min")
        base_price = 100.0
        
        return [
            {
                "date": date,
                "open": base_price + i * 0.1 - 0.3,
                "high": base_price + i * 0.1 + 0.5,
                "low": base_price + i * 0.1 - 0.5,
                "close": base_price + i * 0.1,
                "volume": 100000 + i * 1000,
            }
            for i, date in enumerate(dates)
        ]


@pytest.fixture
def mock_kite() -> MockKiteClient:
    """Provide mock Kite client."""
    return MockKiteClient()


class MockDatabase:
    """
    Mock async database for testing.
    
    Stores data in memory and provides async interface matching IDatabase.
    """
    
    def __init__(self):
        self.tables: Dict[str, List[Dict]] = {
            "signals": [],
            "positions": [],
            "orders": [],
            "trades": [],
        }
        self._id_counters: Dict[str, int] = {table: 1 for table in self.tables}
        self._connected = False
    
    async def connect(self) -> None:
        """Connect to database."""
        self._connected = True
    
    async def disconnect(self) -> None:
        """Disconnect from database."""
        self._connected = False
    
    async def insert(self, table: str, data: Dict) -> int:
        """Insert record and return ID."""
        if table not in self.tables:
            self.tables[table] = []
            self._id_counters[table] = 1
        
        record_id = self._id_counters[table]
        self._id_counters[table] += 1
        
        data = data.copy()
        data["id"] = record_id
        data["created_at"] = datetime.now()
        self.tables[table].append(data)
        
        return record_id
    
    async def update(self, table: str, data: Dict, where: Dict) -> int:
        """Update records matching where clause."""
        updated = 0
        for record in self.tables.get(table, []):
            if all(record.get(k) == v for k, v in where.items()):
                record.update(data)
                updated += 1
        return updated
    
    async def delete(self, table: str, where: Dict) -> int:
        """Delete records matching where clause."""
        if table not in self.tables:
            return 0
        
        original_len = len(self.tables[table])
        self.tables[table] = [
            r for r in self.tables[table]
            if not all(r.get(k) == v for k, v in where.items())
        ]
        return original_len - len(self.tables[table])
    
    async def fetch_one(self, query: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Fetch single record."""
        results = await self.fetch_all(query, params)
        return results[0] if results else None
    
    async def fetch_all(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Fetch all matching records."""
        query_lower = query.lower()
        for table_name, records in self.tables.items():
            if table_name in query_lower:
                return records
        return []
    
    async def execute(self, query: str, params: Optional[Dict] = None) -> int:
        """Execute query."""
        return 1
    
    def seed(self, table: str, records: List[Dict]) -> None:
        """Seed test data."""
        if table not in self.tables:
            self.tables[table] = []
        for record in records:
            record_id = self._id_counters.get(table, 1)
            self._id_counters[table] = record_id + 1
            record["id"] = record_id
            self.tables[table].append(record)


@pytest.fixture
def mock_db() -> MockDatabase:
    """Provide mock database."""
    return MockDatabase()


@pytest.fixture
def mock_database() -> MagicMock:
    """Provide mock database with AsyncMock methods for unit tests."""
    db = MagicMock()
    db.connect = AsyncMock()
    db.disconnect = AsyncMock()
    db.insert = AsyncMock(return_value=1)
    db.update = AsyncMock(return_value=1)
    db.delete = AsyncMock(return_value=1)
    db.fetch_one = AsyncMock(return_value=None)
    db.fetch_all = AsyncMock(return_value=[])
    db.execute = AsyncMock(return_value=1)
    return db


@pytest.fixture
def mock_redis() -> MagicMock:
    """Provide mock Redis client."""
    redis = MagicMock()
    redis.publish = AsyncMock()
    redis.subscribe = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    redis.lpush = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    return redis


# ============================================================================
# MOCK DATA SOURCE (implements IDataSource)
# ============================================================================

class MockDataSource(IDataSource):
    """
    Mock data source implementing IDataSource interface.
    
    Provides deterministic test data for market data operations.
    """
    
    def __init__(self):
        self._instruments: List[Instrument] = self._create_default_instruments()
        self._quotes: Dict[int, Quote] = {}
        self._historical_data: Dict[int, pd.DataFrame] = {}
    
    def _create_default_instruments(self) -> List[Instrument]:
        """Create default test instruments."""
        return [
            Instrument(
                instrument_token=738561,
                exchange_token=2885,
                tradingsymbol="RELIANCE",
                name="Reliance Industries",
                exchange="NSE",
                segment="NSE",
                instrument_type="EQ",
                lot_size=1
            ),
            Instrument(
                instrument_token=340481,
                exchange_token=1330,
                tradingsymbol="INFY",
                name="Infosys Limited",
                exchange="NSE",
                segment="NSE",
                instrument_type="EQ",
                lot_size=1
            ),
            Instrument(
                instrument_token=2953217,
                exchange_token=11536,
                tradingsymbol="TCS",
                name="Tata Consultancy Services",
                exchange="NSE",
                segment="NSE",
                instrument_type="EQ",
                lot_size=1
            ),
            Instrument(
                instrument_token=779521,
                exchange_token=3045,
                tradingsymbol="SBIN",
                name="State Bank of India",
                exchange="NSE",
                segment="NSE",
                instrument_type="EQ",
                lot_size=1
            ),
            Instrument(
                instrument_token=408065,
                exchange_token=1594,
                tradingsymbol="ICICIBANK",
                name="ICICI Bank",
                exchange="NSE",
                segment="NSE",
                instrument_type="EQ",
                lot_size=1
            ),
        ]
    
    def get_quote(self, instrument_token: int) -> Quote:
        """Get quote for instrument."""
        quotes = self.get_quotes([instrument_token])
        return quotes.get(instrument_token)
    
    def get_quotes(self, instrument_tokens: List[int]) -> Dict[int, Quote]:
        """Get quotes for multiple instruments."""
        result = {}
        for token in instrument_tokens:
            # Return cached or generate default
            if token in self._quotes:
                result[token] = self._quotes[token]
            else:
                # Find instrument
                instrument = next(
                    (i for i in self._instruments if i.instrument_token == token),
                    None
                )
                symbol = instrument.tradingsymbol if instrument else f"UNKNOWN_{token}"
                
                result[token] = Quote(
                    instrument_token=token,
                    symbol=symbol,
                    last_price=2450.0,
                    volume=500000,
                    change_pct=2.5,
                    timestamp=datetime.now(),
                    open_price=2400.0,
                    high_price=2470.0,
                    low_price=2390.0,
                    close_price=2395.0
                )
        return result
    
    def get_historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str
    ) -> pd.DataFrame:
        """Get historical OHLCV data."""
        if instrument_token in self._historical_data:
            return self._historical_data[instrument_token]
        
        # Generate default historical data
        num_candles = 50
        dates = pd.date_range(end=to_date, periods=num_candles, freq="5min")
        base_price = 100.0
        
        df = pd.DataFrame({
            "date": dates,
            "open": [base_price + i * 0.1 - 0.3 for i in range(num_candles)],
            "high": [base_price + i * 0.1 + 0.5 for i in range(num_candles)],
            "low": [base_price + i * 0.1 - 0.5 for i in range(num_candles)],
            "close": [base_price + i * 0.1 for i in range(num_candles)],
            "volume": [100000 + i * 1000 for i in range(num_candles)],
        })
        df = df.set_index("date")
        return df
    
    def get_instruments(self, exchange: Optional[str] = None) -> List[Instrument]:
        """Get all instruments."""
        if exchange:
            return [i for i in self._instruments if i.exchange == exchange]
        return self._instruments
    
    def search_instruments(self, query: str) -> List[Instrument]:
        """Search instruments by symbol or name."""
        query_lower = query.lower()
        return [
            i for i in self._instruments
            if query_lower in i.tradingsymbol.lower() or query_lower in i.name.lower()
        ]
    
    def set_quote(self, instrument_token: int, quote: Quote) -> None:
        """Set a specific quote for testing."""
        self._quotes[instrument_token] = quote
    
    def set_historical_data(self, instrument_token: int, df: pd.DataFrame) -> None:
        """Set historical data for testing."""
        self._historical_data[instrument_token] = df
    
    def add_instrument(self, instrument: Instrument) -> None:
        """Add an instrument for testing."""
        self._instruments.append(instrument)


@pytest.fixture
def mock_data_source() -> MockDataSource:
    """Provide mock data source implementing IDataSource."""
    return MockDataSource()


# ============================================================================
# MOCK BROKER (implements IBroker)
# ============================================================================

class MockBroker(IBroker):
    """
    Mock broker implementing IBroker interface.
    
    Provides deterministic test responses for broker operations.
    """
    
    def __init__(self):
        self._orders: Dict[str, OrderBook] = {}
        self._positions: List[BrokerPosition] = []
        self._order_id_counter = 1000
        self._connected = True
        self._available_margin = 100000.0
        self._used_margin = 0.0
    
    async def place_order(
        self,
        symbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        product: str = "MIS",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        tag: Optional[str] = None
    ) -> OrderResponse:
        """Place a mock order."""
        order_id = f"MOCK_{self._order_id_counter}"
        self._order_id_counter += 1
        
        # Create order book entry
        order_book = OrderBook(
            order_id=order_id,
            exchange_order_id=f"EX_{order_id}",
            status=OrderStatus.COMPLETE,
            symbol=symbol,
            exchange=exchange,
            transaction_type=transaction_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            average_price=price or 2450.0,
            filled_quantity=quantity,
            pending_quantity=0,
            order_type=order_type,
            product=product,
            placed_by="TEST_USER",
            order_timestamp=datetime.now(),
            exchange_timestamp=datetime.now(),
            variety="regular",
            validity="DAY",
            tag=tag
        )
        self._orders[order_id] = order_book
        
        # Update margin
        order_value = quantity * (price or 2450.0)
        if product == "MIS":
            self._used_margin += order_value * 0.20  # 20% margin for intraday
        else:
            self._used_margin += order_value
        
        return OrderResponse(
            order_id=order_id,
            status=OrderStatus.COMPLETE,
            symbol=symbol,
            exchange=exchange,
            transaction_type=transaction_type,
            quantity=quantity,
            price=price,
            average_price=price or 2450.0,
            filled_quantity=quantity,
            order_type=order_type,
            product=product,
            timestamp=datetime.now()
        )
    
    async def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None
    ) -> OrderResponse:
        """Modify an existing order."""
        if order_id not in self._orders:
            raise ValueError(f"Order {order_id} not found")
        
        order = self._orders[order_id]
        if quantity:
            order.quantity = quantity
        if price:
            order.price = price
        if trigger_price:
            order.trigger_price = trigger_price
        if order_type:
            order.order_type = order_type
        
        return OrderResponse(
            order_id=order_id,
            status=order.status,
            symbol=order.symbol,
            exchange=order.exchange,
            transaction_type=order.transaction_type,
            quantity=order.quantity,
            price=order.price,
            average_price=order.average_price,
            filled_quantity=order.filled_quantity,
            order_type=order.order_type,
            product=order.product,
            timestamp=datetime.now()
        )
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if order_id in self._orders:
            self._orders[order_id].status = OrderStatus.CANCELLED
            return True
        return False
    
    async def get_order(self, order_id: str) -> Optional[OrderBook]:
        """Get order by ID."""
        return self._orders.get(order_id)
    
    async def get_orders(self) -> List[OrderBook]:
        """Get all orders."""
        return list(self._orders.values())
    
    async def get_positions(self) -> List[BrokerPosition]:
        """Get all positions."""
        return self._positions
    
    async def get_position(self, symbol: str, exchange: str = "NSE") -> Optional[BrokerPosition]:
        """Get position for symbol."""
        for pos in self._positions:
            if pos.symbol == symbol and pos.exchange == exchange:
                return pos
        return None
    
    async def get_margins(self) -> MarginInfo:
        """Get margin information."""
        return MarginInfo(
            available_cash=self._available_margin - self._used_margin,
            available_margin=self._available_margin - self._used_margin,
            used_margin=self._used_margin,
            total_balance=self._available_margin,
            collateral=0.0
        )
    
    async def is_connected(self) -> bool:
        """Check connection status."""
        return self._connected
    
    def get_broker_name(self) -> str:
        """Get broker name."""
        return "MockBroker"
    
    def add_position(self, position: BrokerPosition) -> None:
        """Add a position for testing."""
        self._positions.append(position)
    
    def set_margin(self, available: float, used: float = 0.0) -> None:
        """Set margin for testing."""
        self._available_margin = available
        self._used_margin = used
    
    def set_connected(self, connected: bool) -> None:
        """Set connection status for testing."""
        self._connected = connected
    
    def clear_orders(self) -> None:
        """Clear all orders."""
        self._orders.clear()
    
    def clear_positions(self) -> None:
        """Clear all positions."""
        self._positions.clear()


@pytest.fixture
def mock_broker() -> MockBroker:
    """Provide mock broker implementing IBroker."""
    return MockBroker()


# ============================================================================
# MOCK CACHE (implements ICache pattern)
# ============================================================================

class MockCache:
    """
    Mock cache for testing.
    
    Provides in-memory cache implementation.
    """
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._expiry: Dict[str, datetime] = {}
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if key in self._expiry:
            if datetime.now() > self._expiry[key]:
                del self._cache[key]
                del self._expiry[key]
                return None
        return self._cache.get(key)
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """Set value in cache."""
        self._cache[key] = value
        if ttl_seconds:
            self._expiry[key] = datetime.now() + timedelta(seconds=ttl_seconds)
        return True
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if key in self._cache:
            del self._cache[key]
            if key in self._expiry:
                del self._expiry[key]
            return True
        return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        result = await self.get(key)
        return result is not None
    
    async def clear(self) -> None:
        """Clear all cache."""
        self._cache.clear()
        self._expiry.clear()
    
    async def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern."""
        if pattern == "*":
            return list(self._cache.keys())
        # Simple pattern matching
        import fnmatch
        return [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]


@pytest.fixture
def mock_cache() -> MockCache:
    """Provide mock cache."""
    return MockCache()


# ============================================================================
# DATA FACTORIES
# ============================================================================

@pytest.fixture
def ohlcv_factory() -> Callable[..., pd.DataFrame]:
    """
    Factory for generating OHLCV test data.
    
    Usage:
        df = ohlcv_factory(num_candles=100, trend="up", base_price=100.0)
    """
    def _create(
        num_candles: int = 100,
        base_price: float = 100.0,
        trend: str = "up",
        volatility: float = 0.01,
        seed: int = 42,
    ) -> pd.DataFrame:
        np.random.seed(seed)
        
        dates = pd.date_range(end=datetime.now(), periods=num_candles, freq="5min")
        
        # Generate price movement based on trend
        if trend == "up":
            drift = 0.001
        elif trend == "down":
            drift = -0.001
        else:  # sideways
            drift = 0
        
        returns = np.random.randn(num_candles) * volatility + drift
        prices = base_price * (1 + np.cumsum(returns))
        prices = np.maximum(prices, base_price * 0.5)
        
        df = pd.DataFrame({
            "date": dates,
            "open": prices * (1 - np.random.rand(num_candles) * 0.005),
            "high": prices * (1 + np.random.rand(num_candles) * 0.01),
            "low": prices * (1 - np.random.rand(num_candles) * 0.01),
            "close": prices,
            "volume": np.random.randint(100000, 500000, num_candles),
        })
        
        # Ensure OHLC consistency
        df["high"] = df[["open", "high", "close"]].max(axis=1)
        df["low"] = df[["open", "low", "close"]].min(axis=1)
        
        return df
    
    return _create


@pytest.fixture
def signal_factory() -> Callable[..., Any]:
    """
    Factory for creating Signal test objects.
    
    Usage:
        signal = signal_factory(symbol="RELIANCE", price=2450.0)
    """
    from backend.core.models import Signal, SignalType
    
    def _create(
        symbol: str = "RELIANCE",
        instrument_token: int = 738561,
        signal_type: SignalType = SignalType.BUY,
        price: float = 2450.0,
        stop_loss: float = 2420.0,
        target: float = 2510.0,
        quantity: int = 10,
        reason: str = "Test signal",
        timestamp: Optional[datetime] = None,
    ) -> Signal:
        return Signal(
            symbol=symbol,
            instrument_token=instrument_token,
            signal_type=signal_type,
            price=price,
            stop_loss=stop_loss,
            target=target,
            quantity=quantity,
            reason=reason,
            timestamp=timestamp or datetime.now(),
        )
    
    return _create


@pytest.fixture
def candidate_factory() -> Callable[..., Any]:
    """
    Factory for creating Candidate test objects.
    
    Usage:
        candidate = candidate_factory(symbol="TCS", gain_pct=3.5)
    """
    from backend.core.models import Candidate
    
    def _create(
        symbol: str = "RELIANCE",
        instrument_token: int = 738561,
        current_price: float = 2450.0,
        gain_pct: float = 2.5,
        volume: int = 500000,
        avg_volume: float = 300000,
        open_price: Optional[float] = None,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> Candidate:
        return Candidate(
            symbol=symbol,
            instrument_token=instrument_token,
            current_price=current_price,
            gain_pct=gain_pct,
            volume=volume,
            avg_volume=avg_volume,
            open_price=open_price or current_price - 50,
            high_price=high_price or current_price + 10,
            low_price=low_price or current_price - 60,
            timestamp=timestamp or datetime.now(),
        )
    
    return _create


@pytest.fixture
def position_factory() -> Callable[..., Any]:
    """
    Factory for creating Position test objects.
    
    Usage:
        position = position_factory(symbol="INFY", entry_price=1650.0)
    """
    from backend.core.models import Position, PositionStatus
    
    def _create(
        symbol: str = "RELIANCE",
        instrument_token: int = 738561,
        entry_price: float = 2450.0,
        quantity: int = 10,
        stop_loss: float = 2420.0,
        target: float = 2510.0,
        entry_time: Optional[datetime] = None,
        current_price: Optional[float] = None,
        status: Any = None,
    ) -> Position:
        return Position(
            symbol=symbol,
            instrument_token=instrument_token,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            target=target,
            entry_time=entry_time or datetime.now(),
            current_price=current_price or entry_price,
            status=status or PositionStatus.OPEN,
        )
    
    return _create


# ============================================================================
# TIME FIXTURES
# ============================================================================

@pytest.fixture
def market_hours_time() -> datetime:
    """Return datetime during market hours (10:30 AM)."""
    return datetime.now().replace(hour=10, minute=30, second=0, microsecond=0)


@pytest.fixture
def before_market_time() -> datetime:
    """Return datetime before market open (9:00 AM)."""
    return datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)


@pytest.fixture
def after_market_time() -> datetime:
    """Return datetime after market close (4:00 PM)."""
    return datetime.now().replace(hour=16, minute=0, second=0, microsecond=0)


@pytest.fixture
def exit_time() -> datetime:
    """Return datetime at auto-exit time (3:20 PM)."""
    return datetime.now().replace(hour=15, minute=20, second=0, microsecond=0)


# ============================================================================
# STRATEGY CONFIG FIXTURES
# ============================================================================

@pytest.fixture
def vwap_breakout_config():
    """Create VWAP Breakout strategy config."""
    from backend.config import VWAPBreakoutConfig
    
    return VWAPBreakoutConfig(
        volume_multiplier=1.5,
        vwap_breakout_pct=0.2,
        stop_loss_pct=0.7,
        target_pct=1.5,
        position_size_pct=0.10,
    )


@pytest.fixture
def vwap_ema_config():
    """Create VWAP EMA Breakout strategy config."""
    from backend.config import VWAPEMABreakoutConfig
    
    return VWAPEMABreakoutConfig(
        min_gain_pct=2.0,
        max_gain_pct=4.0,
        ema_period=20,
        vwap_enabled=True,
        volume_multiplier=1.5,
        stop_loss_pct=0.7,
        target_pct=1.5,
    )


@pytest.fixture
def bullish_flag_config():
    """Create Bullish Flag strategy config."""
    from backend.config import BullishFlagConfig
    
    return BullishFlagConfig(
        min_initial_move_pct=2.0,
        pullback_pct_min=0.3,
        pullback_pct_max=1.5,
        stop_loss_pct=0.8,
        target_pct=1.8,
    )


@pytest.fixture
def ema_crossover_config():
    """Create EMA Crossover strategy config."""
    from backend.config import EMACrossoverConfig
    
    return EMACrossoverConfig(
        fast_period=9,
        slow_period=21,
    )


# ============================================================================
# ASSERTION HELPERS
# ============================================================================

@pytest.fixture
def assert_signal_valid() -> Callable[[Any], None]:
    """Helper to validate Signal objects."""
    from backend.core.models import Signal, SignalType
    
    def _assert(signal: Signal) -> None:
        assert signal is not None, "Signal should not be None"
        assert isinstance(signal, Signal), f"Expected Signal, got {type(signal)}"
        assert signal.symbol, "Signal must have symbol"
        assert signal.price > 0, "Signal price must be positive"
        assert signal.stop_loss is not None, "Signal must have stop_loss"
        assert signal.target is not None, "Signal must have target"
        assert signal.stop_loss < signal.price, "Stop loss must be below entry price"
        assert signal.target > signal.price, "Target must be above entry price"
        assert isinstance(signal.signal_type, SignalType), "Invalid signal_type"
    
    return _assert


@pytest.fixture
def assert_dataframe_valid() -> Callable[[pd.DataFrame], None]:
    """Helper to validate OHLCV DataFrames."""
    def _assert(df: pd.DataFrame) -> None:
        required_cols = ["open", "high", "low", "close", "volume"]
        for col in required_cols:
            assert col in df.columns, f"Missing required column: {col}"
        
        assert len(df) > 0, "DataFrame should not be empty"
        assert (df["high"] >= df["low"]).all(), "High must be >= Low"
        assert (df["high"] >= df["open"]).all(), "High must be >= Open"
        assert (df["high"] >= df["close"]).all(), "High must be >= Close"
        assert (df["low"] <= df["open"]).all(), "Low must be <= Open"
        assert (df["low"] <= df["close"]).all(), "Low must be <= Close"
        assert (df["volume"] >= 0).all(), "Volume must be non-negative"
    
    return _assert
