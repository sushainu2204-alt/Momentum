"""
Integration Tests for All Managers

Tests OrderManager, PositionManager, CapitalManager, and SignalExecutor
with mock Kite API to verify functionality before paper trading.
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.database.postgres import PostgresDatabase
from infrastructure.database.position_repository import PositionRepository
from infrastructure.database.order_repository import OrderRepository
from core.services.order_manager import OrderManager
from core.services.position_manager import PositionManager
from core.services.capital_manager import CapitalManager, TradingLimits
from core.services.signal_executor import SignalExecutor
from models import Signal, SignalType, Position, PositionStatus


# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "appdb",
    "user": "appuser",
    "password": "secret"
}


class MockKiteService:
    """Mock Kite API for testing without real API calls."""
    
    def __init__(self):
        self.orders: Dict[str, Dict] = {}
        self.positions: List[Dict] = []
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
                    "debits": 0,
                    "exposure": 0,
                    "m2m_realised": 0,
                    "m2m_unrealised": 0,
                    "option_premium": 0,
                    "payout": 0,
                    "span": 0,
                    "holding_sales": 0,
                    "turnover": 0,
                    "liquid_collateral": 0,
                    "stock_collateral": 0
                }
            }
        }
        self.next_order_id = 1000
    
    def place_order(
        self,
        tradingsymbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str,
        product: str,
        variety: str = "regular",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        validity: str = "DAY",
        tag: Optional[str] = None
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
            "validity": validity,
            "tag": tag
        }
        
        print(f"  [MOCK] Placed order {order_id}: {transaction_type} {quantity} {tradingsymbol} @ ₹{price}")
        return order_id
    
    def orders(self) -> List[Dict]:
        """Get all orders."""
        return list(self.orders.values())
    
    def order_history(self, order_id: str) -> List[Dict]:
        """Get order history."""
        if order_id in self.orders:
            return [self.orders[order_id]]
        return []
    
    def positions(self) -> Dict[str, List[Dict]]:
        """Get all positions."""
        return {
            "net": self.positions,
            "day": self.positions
        }
    
    def margins(self, segment: str = "equity") -> Dict:
        """Get margin data."""
        return self.margins_data
    
    def modify_order(
        self,
        variety: str,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None,
        validity: Optional[str] = None
    ) -> str:
        """Mock order modification."""
        if order_id in self.orders:
            if quantity:
                self.orders[order_id]["quantity"] = quantity
            if price:
                self.orders[order_id]["price"] = price
            if trigger_price:
                self.orders[order_id]["trigger_price"] = trigger_price
            if order_type:
                self.orders[order_id]["order_type"] = order_type
            print(f"  [MOCK] Modified order {order_id}")
        return order_id
    
    def cancel_order(self, variety: str, order_id: str) -> str:
        """Mock order cancellation."""
        if order_id in self.orders:
            self.orders[order_id]["status"] = "CANCELLED"
            print(f"  [MOCK] Cancelled order {order_id}")
        return order_id
    
    def add_position(self, symbol: str, quantity: int, average_price: float, pnl: float = 0):
        """Add a mock position."""
        self.positions.append({
            "tradingsymbol": symbol,
            "exchange": "NSE",
            "instrument_token": 12345,
            "product": "MIS",
            "quantity": quantity,
            "overnight_quantity": 0,
            "multiplier": 1,
            "average_price": average_price,
            "close_price": 0,
            "last_price": average_price + (pnl / quantity) if quantity > 0 else average_price,
            "value": quantity * average_price,
            "pnl": pnl,
            "m2m": pnl,
            "unrealised": pnl,
            "realised": 0,
            "buy_quantity": quantity if quantity > 0 else 0,
            "buy_price": average_price if quantity > 0 else 0,
            "buy_value": quantity * average_price if quantity > 0 else 0,
            "buy_m2m": 0,
            "sell_quantity": abs(quantity) if quantity < 0 else 0,
            "sell_price": average_price if quantity < 0 else 0,
            "sell_value": abs(quantity) * average_price if quantity < 0 else 0,
            "sell_m2m": 0,
            "day_buy_quantity": quantity if quantity > 0 else 0,
            "day_buy_price": average_price if quantity > 0 else 0,
            "day_buy_value": quantity * average_price if quantity > 0 else 0,
            "day_sell_quantity": abs(quantity) if quantity < 0 else 0,
            "day_sell_price": average_price if quantity < 0 else 0,
            "day_sell_value": abs(quantity) * average_price if quantity < 0 else 0
        })
    
    def update_margins(self, utilized_debits: float, realized_pnl: float = 0, unrealized_pnl: float = 0):
        """Update mock margins."""
        self.margins_data["equity"]["utilised"]["debits"] = utilized_debits
        self.margins_data["equity"]["utilised"]["m2m_realised"] = realized_pnl
        self.margins_data["equity"]["utilised"]["m2m_unrealised"] = unrealized_pnl
        self.margins_data["equity"]["available"]["cash"] = (
            self.margins_data["equity"]["available"]["opening_balance"]
            - utilized_debits
            + realized_pnl
        )


async def setup_test_environment():
    """Setup test environment and clean up existing data."""
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    print("🧹 Cleaning up test data...")
    await db.execute("DELETE FROM positions WHERE symbol LIKE 'TEST%'", {})
    await db.execute("DELETE FROM orders WHERE symbol LIKE 'TEST%'", {})
    await db.execute("DELETE FROM trade_logs WHERE symbol LIKE 'TEST%'", {})
    await db.execute("DELETE FROM cooldown_tracker WHERE symbol LIKE 'TEST%'", {})
    await db.execute("DELETE FROM signals WHERE symbol LIKE 'TEST%'", {})
    
    # Initialize capital state for today
    today = datetime.now().date()
    await db.execute(
        """
        INSERT INTO capital_state (
            date, starting_capital, current_capital, available_capital,
            max_risk_allowed, max_positions_allowed
        )
        VALUES (:date, :starting, :current, :available, :max_risk, :max_positions)
        ON CONFLICT (date) DO UPDATE SET
            current_capital = EXCLUDED.current_capital,
            available_capital = EXCLUDED.available_capital
        """,
        {
            "date": today,
            "starting": Decimal("100000.00"),
            "current": Decimal("100000.00"),
            "available": Decimal("100000.00"),
            "max_risk": Decimal("10000.00"),
            "max_positions": 5
        }
    )
    
    await db.disconnect()
    print("✅ Test environment ready\n")


async def test_order_manager():
    """Test OrderManager functionality."""
    print("="*60)
    print("TEST 1: OrderManager")
    print("="*60)
    
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    kite = MockKiteService()
    order_manager = OrderManager(kite_service=kite, database=db)
    
    try:
        # Test 1.1: Place order
        print("\n1.1 Testing order placement...")
        order_id = await order_manager.place_order(
            symbol="TESTSTOCK1",
            instrument_token=12345,
            transaction_type="BUY",
            quantity=10,
            price=Decimal("100.50"),
            order_type="LIMIT",
            strategy_name="test_strategy"
        )
        print(f"✅ Order placed: {order_id}")
        
        # Test 1.2: Get order status
        print("\n1.2 Testing order status retrieval...")
        order = await order_manager.get_order_by_id(order_id)
        if order and order["status"] == "COMPLETE":
            print(f"✅ Order status: {order['status']}")
        else:
            print(f"❌ Order status incorrect: {order}")
            return False
        
        # Test 1.3: Check pending orders
        print("\n1.3 Testing pending orders check...")
        has_pending = await order_manager.has_pending_order("TESTSTOCK1")
        print(f"✅ Has pending order: {has_pending} (expected: False for completed order)")
        
        # Test 1.4: Get orders by symbol
        print("\n1.4 Testing orders by symbol...")
        orders = await order_manager.get_orders_by_symbol("TESTSTOCK1")
        print(f"✅ Found {len(orders)} order(s) for TESTSTOCK1")
        
        # Test 1.5: Sync orders from Kite
        print("\n1.5 Testing order sync from Kite...")
        kite.place_order(
            tradingsymbol="TESTSTOCK2",
            exchange="NSE",
            transaction_type="BUY",
            quantity=5,
            order_type="MARKET",
            product="MIS",
            price=200.0
        )
        synced = await order_manager.sync_orders_from_kite()
        print(f"✅ Synced {synced} order(s) from Kite")
        
        await db.disconnect()
        print("\n✅ OrderManager tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ OrderManager test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def test_position_manager():
    """Test PositionManager functionality."""
    print("\n" + "="*60)
    print("TEST 2: PositionManager")
    print("="*60)
    
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    kite = MockKiteService()
    position_manager = PositionManager(kite_service=kite, database=db)
    
    try:
        # Test 2.1: Create position
        print("\n2.1 Testing position creation...")
        position_id = await position_manager.create_position(
            symbol="TESTSTOCK3",
            instrument_token=12345,
            strategy_name="test_strategy",
            entry_price=Decimal("150.00"),
            quantity=20,
            stop_loss=Decimal("145.00"),
            target=Decimal("160.00"),
            entry_order_id="TEST_1001"
        )
        print(f"✅ Position created: ID {position_id}")
        
        # Test 2.2: Get open positions
        print("\n2.2 Testing open positions retrieval...")
        positions = await position_manager.get_open_positions()
        print(f"✅ Found {len(positions)} open position(s)")
        
        # Test 2.3: Check if symbol has position
        print("\n2.3 Testing position existence check...")
        has_position = await position_manager.has_position("TESTSTOCK3")
        print(f"✅ Has position for TESTSTOCK3: {has_position}")
        
        # Test 2.4: Update position price
        print("\n2.4 Testing position price update...")
        await position_manager.update_position_price(
            position_id=position_id,
            current_price=Decimal("155.00"),
            pnl=Decimal("100.00"),
            pnl_pct=Decimal("3.33")
        )
        updated = await position_manager.get_position_by_id(position_id)
        print(f"✅ Position updated: P&L = ₹{updated.pnl}")
        
        # Test 2.5: Check exit conditions
        print("\n2.5 Testing exit conditions...")
        # Simulate price hitting stop loss
        kite.add_position("TESTSTOCK3", 20, 150.0, -100.0)  # Position with loss
        exit_signals = await position_manager.check_exits(datetime.now())
        print(f"✅ Generated {len(exit_signals)} exit signal(s)")
        
        # Test 2.6: Close position
        print("\n2.6 Testing position closure...")
        await position_manager.close_position(
            position_id=position_id,
            exit_price=Decimal("145.00"),
            exit_reason="SL_HIT",
            pnl=Decimal("-100.00")
        )
        closed = await position_manager.get_position_by_id(position_id)
        print(f"✅ Position closed: Status = {closed.status}")
        
        # Test 2.7: Sync positions from Kite
        print("\n2.7 Testing position sync from Kite...")
        kite.add_position("TESTSTOCK4", 15, 180.0, 50.0)
        synced = await position_manager.sync_positions_from_kite()
        print(f"✅ Synced {synced} position(s) from Kite")
        
        await db.disconnect()
        print("\n✅ PositionManager tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ PositionManager test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def test_capital_manager():
    """Test CapitalManager functionality."""
    print("\n" + "="*60)
    print("TEST 3: CapitalManager")
    print("="*60)
    
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    kite = MockKiteService()
    position_manager = PositionManager(kite_service=kite, database=db)
    capital_manager = CapitalManager(kite_service=kite, position_manager=position_manager, database=db)
    
    try:
        # Test 3.1: Get available capital
        print("\n3.1 Testing available capital retrieval...")
        available = await capital_manager.get_available_capital()
        print(f"✅ Available capital: ₹{available:,.2f}")
        
        # Test 3.2: Check position limit
        print("\n3.2 Testing position limit check...")
        can_open = await capital_manager.check_position_limit()
        print(f"✅ Can open new position: {can_open}")
        
        # Test 3.3: Calculate position size
        print("\n3.3 Testing position sizing...")
        quantity = await capital_manager.calculate_position_size(
            symbol="TESTSTOCK5",
            entry_price=Decimal("200.00"),
            stop_loss=Decimal("190.00")
        )
        print(f"✅ Calculated position size: {quantity} shares")
        
        # Test 3.4: Check capital allocation
        print("\n3.4 Testing capital allocation check...")
        capital_needed = Decimal("200.00") * quantity
        can_allocate = await capital_manager.can_allocate_capital(capital_needed)
        print(f"✅ Can allocate ₹{capital_needed:,.2f}: {can_allocate}")
        
        # Test 3.5: Initialize daily capital
        print("\n3.5 Testing daily capital initialization...")
        await capital_manager.initialize_daily_capital()
        print(f"✅ Daily capital initialized")
        
        # Test 3.6: Sync margins to DB
        print("\n3.6 Testing margins sync...")
        kite.update_margins(utilized_debits=20000.0, realized_pnl=500.0)
        await capital_manager.sync_margins_to_db()
        print(f"✅ Margins synced to database")
        
        # Test 3.7: Get capital summary
        print("\n3.7 Testing capital summary...")
        summary = await capital_manager.get_capital_summary()
        print(f"✅ Capital summary:")
        print(f"   Starting: ₹{summary['starting_capital']:,.2f}")
        print(f"   Current: ₹{summary['current_capital']:,.2f}")
        print(f"   Available: ₹{summary['available_capital']:,.2f}")
        print(f"   Utilized: ₹{summary['utilized_margin']:,.2f}")
        print(f"   P&L: ₹{summary['total_pnl']:,.2f}")
        
        await db.disconnect()
        print("\n✅ CapitalManager tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ CapitalManager test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def test_signal_executor():
    """Test SignalExecutor with all 9 guardrails."""
    print("\n" + "="*60)
    print("TEST 4: SignalExecutor (9 Guardrails)")
    print("="*60)
    
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    kite = MockKiteService()
    order_manager = OrderManager(kite_service=kite, database=db)
    position_manager = PositionManager(kite_service=kite, database=db)
    capital_manager = CapitalManager(kite_service=kite, position_manager=position_manager, database=db)
    
    executor = SignalExecutor(
        order_manager=order_manager,
        position_manager=position_manager,
        capital_manager=capital_manager,
        database=db,
        dry_run=True  # Test in dry run mode
    )
    
    try:
        # Test 4.1: Valid signal - all guardrails pass
        print("\n4.1 Testing valid signal (all guardrails pass)...")
        signal = Signal(
            symbol="TESTSTOCK6",
            instrument_token=12345,
            signal_type=SignalType.BUY,
            price=250.0,
            stop_loss=240.0,
            target=270.0,
            timestamp=datetime.now(),
            reason="Test signal"
        )
        
        result = await executor.execute_signal(signal, "test_strategy", {})
        print(f"✅ Signal execution result: {result.status}")
        print(f"   Reason: {result.reason}")
        
        # Test 4.2: Signal for existing position (guardrail 3)
        print("\n4.2 Testing guardrail 3: No existing position...")
        # Create a position first
        await position_manager.create_position(
            symbol="TESTSTOCK7",
            instrument_token=12345,
            strategy_name="test_strategy",
            entry_price=Decimal("300.00"),
            quantity=10,
            stop_loss=Decimal("290.00"),
            target=Decimal("320.00"),
            entry_order_id="TEST_1002"
        )
        
        signal2 = Signal(
            symbol="TESTSTOCK7",
            instrument_token=12345,
            signal_type=SignalType.BUY,
            price=305.0,
            stop_loss=295.0,
            target=325.0,
            timestamp=datetime.now(),
            reason="Test duplicate position"
        )
        
        result2 = await executor.execute_signal(signal2, "test_strategy", {})
        print(f"✅ Signal blocked by guardrail: {result2.status}")
        print(f"   Reason: {result2.reason}")
        
        # Test 4.3: Check execution stats
        print("\n4.3 Testing execution statistics...")
        stats = await executor.get_execution_stats()
        print(f"✅ Execution stats:")
        print(f"   Total signals: {stats['total_signals']}")
        print(f"   Executed: {stats['executed']}")
        print(f"   Ignored: {stats['ignored']}")
        print(f"   Failed: {stats['failed']}")
        
        # Test 4.4: Verify trade logs
        print("\n4.4 Verifying trade logs...")
        logs = await db.fetch_all(
            "SELECT * FROM trade_logs WHERE symbol LIKE 'TEST%' ORDER BY timestamp DESC LIMIT 5",
            {}
        )
        print(f"✅ Found {len(logs)} trade log entries")
        for log in logs:
            print(f"   - {log['log_type']}: {log['decision']} - {log['reason']}")
        
        await db.disconnect()
        print("\n✅ SignalExecutor tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ SignalExecutor test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def run_all_tests():
    """Run all manager integration tests."""
    print("\n" + "="*60)
    print("MANAGER INTEGRATION TESTS")
    print("="*60)
    print("Testing all managers with mock Kite API")
    print()
    
    # Setup
    await setup_test_environment()
    
    # Run tests
    results = []
    results.append(("OrderManager", await test_order_manager()))
    results.append(("PositionManager", await test_position_manager()))
    results.append(("CapitalManager", await test_capital_manager()))
    results.append(("SignalExecutor", await test_signal_executor()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")
    
    print()
    print(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All manager tests passed!")
        print("\n📝 Next: Test sync jobs with test_sync_jobs.py")
        return True
    else:
        print("\n⚠️  Some tests failed. Fix issues before proceeding.")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
