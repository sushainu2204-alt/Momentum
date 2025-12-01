"""
Test script to verify database setup and repositories.

Run this after applying schema.sql to ensure everything works.
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.database.postgres import PostgresDatabase
from infrastructure.database.position_repository import PositionRepository
from infrastructure.database.order_repository import OrderRepository
from models import Position, PositionStatus


# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "appdb",
    "user": "appuser",
    "password": "secret"
}


async def test_database_connection():
    """Test basic database connectivity."""
    print("\n" + "="*60)
    print("TEST 1: Database Connection")
    print("="*60)
    
    db = PostgresDatabase(DB_CONFIG)
    try:
        await db.connect()
        print("✅ Database connection successful!")
        
        # Test simple query
        result = await db.fetch_all(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
            {}
        )
        print(f"✅ Found {len(result)} tables in database:")
        for row in result:
            print(f"   - {row['tablename']}")
        
        await db.disconnect()
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


async def test_position_repository():
    """Test PositionRepository CRUD operations."""
    print("\n" + "="*60)
    print("TEST 2: Position Repository")
    print("="*60)
    
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    repo = PositionRepository(db)
    
    try:
        # Create test position
        position = Position(
            symbol="TESTSTOCK",
            instrument_token=123456,
            strategy_name="test_strategy",
            entry_price=Decimal("100.50"),
            entry_time=datetime.now(),
            quantity=10,
            stop_loss=Decimal("95.00"),
            target=Decimal("110.00"),
            status="OPEN"
        )
        
        print("\n1. Creating position...")
        position_id = await repo.create_position(position)
        print(f"✅ Position created with ID: {position_id}")
        
        # Get position
        print("\n2. Retrieving position...")
        retrieved = await repo.get_position_by_id(position_id)
        if retrieved:
            print(f"✅ Position retrieved: {retrieved.symbol} @ ₹{retrieved.entry_price}")
        else:
            print("❌ Failed to retrieve position")
            return False
        
        # Get open positions
        print("\n3. Getting open positions...")
        open_positions = await repo.get_open_positions()
        print(f"✅ Found {len(open_positions)} open position(s)")
        
        # Update position
        print("\n4. Updating position...")
        await repo.update_position_price(
            position_id=position_id,
            current_price=Decimal("105.00"),
            pnl=Decimal("45.00"),
            pnl_pct=Decimal("4.48")
        )
        updated = await repo.get_position_by_id(position_id)
        print(f"✅ Position updated: P&L = ₹{updated.pnl} ({updated.pnl_pct}%)")
        
        # Close position
        print("\n5. Closing position...")
        await repo.close_position(
            position_id=position_id,
            exit_price=Decimal("108.00"),
            exit_time=datetime.now(),
            exit_reason="TARGET_HIT",
            pnl=Decimal("75.00"),
            pnl_pct=Decimal("7.46")
        )
        closed = await repo.get_position_by_id(position_id)
        print(f"✅ Position closed: Status = {closed.status}, Exit = ₹{closed.exit_price}")
        
        # Cleanup
        print("\n6. Cleaning up test data...")
        await db.execute(
            "DELETE FROM positions WHERE id = :id",
            {"id": position_id}
        )
        print("✅ Test data cleaned up")
        
        await db.disconnect()
        return True
        
    except Exception as e:
        print(f"❌ Position repository test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def test_order_repository():
    """Test OrderRepository CRUD operations."""
    print("\n" + "="*60)
    print("TEST 3: Order Repository")
    print("="*60)
    
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    repo = OrderRepository(db)
    
    try:
        # Create test order using raw data
        order_data = {
            "order_id": "TEST_ORDER_123",
            "symbol": "TESTSTOCK",
            "instrument_token": 123456,
            "strategy_name": "test_strategy",
            "order_type": "MARKET",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": Decimal("100.50"),
            "status": "PENDING",
            "placed_at": datetime.now()
        }
        
        print("\n1. Creating order...")
        order_id = await db.insert("orders", order_data)
        print(f"✅ Order created with ID: {order_id}")
        
        # Get order
        print("\n2. Retrieving order...")
        retrieved = await repo.get_order_by_kite_order_id("TEST_ORDER_123")
        if retrieved:
            print(f"✅ Order retrieved: {retrieved.symbol} {retrieved.transaction_type} x{retrieved.quantity}")
        else:
            print("❌ Failed to retrieve order")
            return False
        
        # Get pending orders
        print("\n3. Getting pending orders...")
        pending = await repo.get_pending_orders()
        print(f"✅ Found {len(pending)} pending order(s)")
        
        # Update order status
        print("\n4. Updating order status to COMPLETE...")
        await repo.update_order_status(
            order_id="TEST_ORDER_123",
            status="COMPLETE",
            filled_quantity=10,
            average_price=Decimal("100.25")
        )
        updated = await repo.get_order_by_kite_order_id("TEST_ORDER_123")
        print(f"✅ Order updated: Status = {updated.status}, Avg Price = ₹{updated.average_price}")
        
        # Cleanup
        print("\n5. Cleaning up test data...")
        await db.execute(
            "DELETE FROM orders WHERE order_id = :order_id",
            {"order_id": "TEST_ORDER_123"}
        )
        print("✅ Test data cleaned up")
        
        await db.disconnect()
        return True
        
    except Exception as e:
        print(f"❌ Order repository test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def test_capital_state():
    """Test capital_state table operations."""
    print("\n" + "="*60)
    print("TEST 4: Capital State")
    print("="*60)
    
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    try:
        # Initialize capital for today
        print("\n1. Initializing capital state...")
        today = datetime.now().date()
        
        await db.execute(
            """
            INSERT INTO capital_state (
                date, starting_capital, current_capital, available_capital,
                max_risk_allowed, max_positions_allowed
            )
            VALUES (
                :date, :starting_capital, :current_capital, :available_capital,
                :max_risk_allowed, :max_positions_allowed
            )
            ON CONFLICT (date) DO UPDATE SET
                current_capital = EXCLUDED.current_capital,
                available_capital = EXCLUDED.available_capital
            """,
            {
                "date": today,
                "starting_capital": Decimal("100000.00"),
                "current_capital": Decimal("100000.00"),
                "available_capital": Decimal("100000.00"),
                "max_risk_allowed": Decimal("10000.00"),
                "max_positions_allowed": 5
            }
        )
        print("✅ Capital state initialized")
        
        # Retrieve capital state
        print("\n2. Retrieving capital state...")
        result = await db.fetch_one(
            "SELECT * FROM capital_state WHERE date = :date",
            {"date": today}
        )
        if result:
            print(f"✅ Capital state retrieved:")
            print(f"   Starting Capital: ₹{result['starting_capital']:,.2f}")
            print(f"   Available Capital: ₹{result['available_capital']:,.2f}")
            print(f"   Max Positions: {result['max_positions_allowed']}")
        else:
            print("❌ Failed to retrieve capital state")
            return False
        
        # Update capital state
        print("\n3. Updating capital state...")
        await db.execute(
            """
            UPDATE capital_state
            SET current_capital = :current_capital,
                available_capital = :available_capital,
                realized_pnl = :realized_pnl
            WHERE date = :date
            """,
            {
                "date": today,
                "current_capital": Decimal("101500.00"),
                "available_capital": Decimal("80000.00"),
                "realized_pnl": Decimal("1500.00")
            }
        )
        
        updated = await db.fetch_one(
            "SELECT * FROM capital_state WHERE date = :date",
            {"date": today}
        )
        print(f"✅ Capital state updated:")
        print(f"   Current Capital: ₹{updated['current_capital']:,.2f}")
        print(f"   Available Capital: ₹{updated['available_capital']:,.2f}")
        print(f"   Realized P&L: ₹{updated['realized_pnl']:,.2f}")
        
        await db.disconnect()
        return True
        
    except Exception as e:
        print(f"❌ Capital state test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def test_trade_logs():
    """Test trade_logs table operations."""
    print("\n" + "="*60)
    print("TEST 5: Trade Logs")
    print("="*60)
    
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    try:
        # Insert test log entry
        print("\n1. Creating trade log entry...")
        log_id = await db.insert(
            "trade_logs",
            {
                "timestamp": datetime.now(),
                "log_type": "SIGNAL_GENERATED",
                "symbol": "TESTSTOCK",
                "strategy_name": "test_strategy",
                "decision": "EXECUTE",
                "reason": "All guardrails passed",
                "data": {"price": 100.50, "quantity": 10}
            }
        )
        print(f"✅ Trade log created with ID: {log_id}")
        
        # Retrieve logs
        print("\n2. Retrieving trade logs...")
        logs = await db.fetch_all(
            """
            SELECT * FROM trade_logs 
            WHERE symbol = :symbol 
            ORDER BY timestamp DESC 
            LIMIT 5
            """,
            {"symbol": "TESTSTOCK"}
        )
        print(f"✅ Found {len(logs)} log entr{'y' if len(logs) == 1 else 'ies'}")
        for log in logs:
            print(f"   - {log['log_type']}: {log['decision']} - {log['reason']}")
        
        # Cleanup
        print("\n3. Cleaning up test data...")
        await db.execute(
            "DELETE FROM trade_logs WHERE id = :id",
            {"id": log_id}
        )
        print("✅ Test data cleaned up")
        
        await db.disconnect()
        return True
        
    except Exception as e:
        print(f"❌ Trade logs test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def run_all_tests():
    """Run all database tests."""
    print("\n" + "="*60)
    print("DATABASE SETUP VERIFICATION")
    print("="*60)
    print("This script tests the database setup and all repositories.")
    print()
    
    results = []
    
    # Test 1: Database connection
    results.append(("Database Connection", await test_database_connection()))
    
    # Test 2: Position repository
    results.append(("Position Repository", await test_position_repository()))
    
    # Test 3: Order repository
    results.append(("Order Repository", await test_order_repository()))
    
    # Test 4: Capital state
    results.append(("Capital State", await test_capital_state()))
    
    # Test 5: Trade logs
    results.append(("Trade Logs", await test_trade_logs()))
    
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
        print("\n🎉 All tests passed! Database setup is complete and working.")
        print("\n📝 Next steps:")
        print("   1. Initialize capital state for the trading day")
        print("   2. Test paper trading mode (dry_run=True)")
        print("   3. Run workers in execution mode")
    else:
        print("\n⚠️  Some tests failed. Please fix issues before proceeding.")
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
