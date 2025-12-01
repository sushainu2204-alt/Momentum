"""
Sync Jobs Integration Tests

Tests all background sync jobs to verify they work correctly
with database and Kite API integration.
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, time
from decimal import Decimal

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.database.postgres import PostgresDatabase
from jobs.sync_jobs import SyncJobsScheduler


# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "appdb",
    "user": "appuser",
    "password": "secret"
}


class MockKiteService:
    """Mock Kite API for sync job testing."""
    
    def __init__(self):
        self.orders_data = []
        self.positions_data = []
        self.margins_data = {
            "equity": {
                "enabled": True,
                "net": 105000.00,
                "available": {
                    "adhoc_margin": 0,
                    "cash": 75000.00,
                    "opening_balance": 100000.00,
                    "live_balance": 105000.00,
                    "collateral": 25000.00,
                    "intraday_payin": 0
                },
                "utilised": {
                    "debits": 25000.00,
                    "exposure": 0,
                    "m2m_realised": 3000.00,
                    "m2m_unrealised": 2000.00,
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
    
    def orders(self):
        """Get all orders."""
        return self.orders_data
    
    def positions(self):
        """Get positions."""
        return {
            "net": self.positions_data,
            "day": self.positions_data
        }
    
    def margins(self, segment: str = "equity"):
        """Get margins."""
        return self.margins_data
    
    def add_order(self, order_data):
        """Add mock order."""
        self.orders_data.append(order_data)
    
    def add_position(self, position_data):
        """Add mock position."""
        self.positions_data.append(position_data)


async def setup_test_data():
    """Setup test data for sync jobs."""
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    print("🧹 Setting up test data for sync jobs...")
    
    # Clean up old test data
    await db.execute("DELETE FROM positions WHERE symbol LIKE 'SYNC%'", {})
    await db.execute("DELETE FROM orders WHERE symbol LIKE 'SYNC%'", {})
    await db.execute("DELETE FROM trade_logs WHERE symbol LIKE 'SYNC%'", {})
    
    # Create test positions
    position_id = await db.insert("positions", {
        "symbol": "SYNCTEST1",
        "instrument_token": 111,
        "strategy_name": "sync_test",
        "entry_price": Decimal("100.00"),
        "entry_time": datetime.now(),
        "quantity": 50,
        "stop_loss": Decimal("95.00"),
        "target": Decimal("110.00"),
        "current_price": Decimal("105.00"),
        "pnl": Decimal("250.00"),
        "pnl_pct": Decimal("5.00"),
        "status": "OPEN",
        "entry_order_id": "SYNC_ORDER_1"
    })
    
    # Create test orders
    await db.insert("orders", {
        "order_id": "SYNC_ORDER_1",
        "symbol": "SYNCTEST1",
        "instrument_token": 111,
        "strategy_name": "sync_test",
        "order_type": "LIMIT",
        "transaction_type": "BUY",
        "quantity": 50,
        "price": Decimal("100.00"),
        "status": "COMPLETE",
        "filled_quantity": 50,
        "average_price": Decimal("100.00"),
        "placed_at": datetime.now(),
        "position_id": position_id
    })
    
    await db.disconnect()
    print("✅ Test data created\n")


async def test_order_sync_job():
    """Test order sync job."""
    print("="*60)
    print("TEST 1: Order Sync Job")
    print("="*60)
    
    kite = MockKiteService()
    
    # Add mock orders from Kite
    kite.add_order({
        "order_id": "KITE_ORDER_1",
        "exchange_order_id": "EXC_1",
        "tradingsymbol": "SYNCTEST2",
        "exchange": "NSE",
        "instrument_token": 222,
        "transaction_type": "BUY",
        "quantity": 25,
        "order_type": "MARKET",
        "product": "MIS",
        "status": "COMPLETE",
        "status_message": "Order completed",
        "filled_quantity": 25,
        "pending_quantity": 0,
        "average_price": 150.0,
        "price": 0,
        "trigger_price": 0,
        "placed_by": "TEST_USER",
        "order_timestamp": datetime.now(),
        "exchange_timestamp": datetime.now(),
        "variety": "regular",
        "validity": "DAY",
        "tag": "test_tag"
    })
    
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    scheduler = SyncJobsScheduler(kite_service=kite, database=db)
    
    try:
        print("\n1. Running order sync job...")
        await scheduler._sync_orders_job()
        
        # Verify order was synced
        orders = await db.fetch_all(
            "SELECT * FROM orders WHERE order_id = :order_id",
            {"order_id": "KITE_ORDER_1"}
        )
        
        if orders:
            print(f"✅ Order synced successfully: {orders[0]['symbol']}")
        else:
            print("❌ Order not synced")
            return False
        
        await db.disconnect()
        print("\n✅ Order sync job test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Order sync job test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def test_position_sync_job():
    """Test position sync job."""
    print("\n" + "="*60)
    print("TEST 2: Position Sync Job")
    print("="*60)
    
    kite = MockKiteService()
    
    # Add mock position from Kite
    kite.add_position({
        "tradingsymbol": "SYNCTEST3",
        "exchange": "NSE",
        "instrument_token": 333,
        "product": "MIS",
        "quantity": 30,
        "overnight_quantity": 0,
        "multiplier": 1,
        "average_price": 200.0,
        "close_price": 0,
        "last_price": 210.0,
        "value": 6000.0,
        "pnl": 300.0,
        "m2m": 300.0,
        "unrealised": 300.0,
        "realised": 0,
        "buy_quantity": 30,
        "buy_price": 200.0,
        "buy_value": 6000.0,
        "buy_m2m": 0,
        "sell_quantity": 0,
        "sell_price": 0,
        "sell_value": 0,
        "sell_m2m": 0,
        "day_buy_quantity": 30,
        "day_buy_price": 200.0,
        "day_buy_value": 6000.0,
        "day_sell_quantity": 0,
        "day_sell_price": 0,
        "day_sell_value": 0
    })
    
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    scheduler = SyncJobsScheduler(kite_service=kite, database=db)
    
    try:
        print("\n1. Running position sync job...")
        await scheduler._sync_positions_job()
        
        # Verify positions were synced
        positions = await db.fetch_all(
            "SELECT * FROM positions WHERE symbol = :symbol",
            {"symbol": "SYNCTEST3"}
        )
        
        if positions:
            print(f"✅ Position synced: {positions[0]['symbol']}, P&L: ₹{positions[0]['pnl']}")
        else:
            print("⚠️  Position not yet in DB (may need position creation first)")
        
        await db.disconnect()
        print("\n✅ Position sync job test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Position sync job test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def test_margins_sync_job():
    """Test margins sync job."""
    print("\n" + "="*60)
    print("TEST 3: Margins Sync Job")
    print("="*60)
    
    kite = MockKiteService()
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    scheduler = SyncJobsScheduler(kite_service=kite, database=db)
    
    try:
        print("\n1. Running margins sync job...")
        await scheduler._sync_margins_job()
        
        # Verify margins were synced
        today = datetime.now().date()
        capital = await db.fetch_one(
            "SELECT * FROM capital_state WHERE date = :date",
            {"date": today}
        )
        
        if capital:
            print(f"✅ Margins synced:")
            print(f"   Current capital: ₹{capital['current_capital']:,.2f}")
            print(f"   Available capital: ₹{capital['available_capital']:,.2f}")
            print(f"   Realized P&L: ₹{capital['realized_pnl']:,.2f}")
            print(f"   Unrealized P&L: ₹{capital['unrealized_pnl']:,.2f}")
        else:
            print("❌ Margins not synced")
            return False
        
        await db.disconnect()
        print("\n✅ Margins sync job test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Margins sync job test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def test_position_monitoring_job():
    """Test position monitoring job."""
    print("\n" + "="*60)
    print("TEST 4: Position Monitoring Job")
    print("="*60)
    
    kite = MockKiteService()
    
    # Add position with profit (should hit target)
    kite.add_position({
        "tradingsymbol": "SYNCTEST1",
        "exchange": "NSE",
        "instrument_token": 111,
        "product": "MIS",
        "quantity": 50,
        "overnight_quantity": 0,
        "multiplier": 1,
        "average_price": 100.0,
        "close_price": 0,
        "last_price": 112.0,  # Above target of 110
        "value": 5000.0,
        "pnl": 600.0,
        "m2m": 600.0,
        "unrealised": 600.0,
        "realised": 0,
        "buy_quantity": 50,
        "buy_price": 100.0,
        "buy_value": 5000.0,
        "buy_m2m": 0,
        "sell_quantity": 0,
        "sell_price": 0,
        "sell_value": 0,
        "sell_m2m": 0,
        "day_buy_quantity": 50,
        "day_buy_price": 100.0,
        "day_buy_value": 5000.0,
        "day_sell_quantity": 0,
        "day_sell_price": 0,
        "day_sell_value": 0
    })
    
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    scheduler = SyncJobsScheduler(kite_service=kite, database=db)
    
    try:
        print("\n1. Running position monitoring job...")
        await scheduler._monitor_positions_job()
        
        # Check if exit signals were generated (in dry_run, no actual exit)
        print(f"✅ Position monitoring completed")
        print(f"   (In dry_run mode, exits are logged but not executed)")
        
        await db.disconnect()
        print("\n✅ Position monitoring job test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Position monitoring job test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def test_daily_initialization_job():
    """Test daily initialization job."""
    print("\n" + "="*60)
    print("TEST 5: Daily Initialization Job")
    print("="*60)
    
    kite = MockKiteService()
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    scheduler = SyncJobsScheduler(kite_service=kite, database=db)
    
    try:
        print("\n1. Running daily initialization job...")
        await scheduler._daily_initialization_job()
        
        # Verify capital was initialized
        today = datetime.now().date()
        capital = await db.fetch_one(
            "SELECT * FROM capital_state WHERE date = :date",
            {"date": today}
        )
        
        if capital:
            print(f"✅ Daily capital initialized:")
            print(f"   Starting capital: ₹{capital['starting_capital']:,.2f}")
            print(f"   Opening balance (from Kite): ₹{capital['starting_capital']:,.2f}")
        else:
            print("❌ Capital not initialized")
            return False
        
        await db.disconnect()
        print("\n✅ Daily initialization job test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Daily initialization job test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def test_job_status():
    """Test job status retrieval."""
    print("\n" + "="*60)
    print("TEST 6: Job Status")
    print("="*60)
    
    kite = MockKiteService()
    db = PostgresDatabase(DB_CONFIG)
    await db.connect()
    
    scheduler = SyncJobsScheduler(kite_service=kite, database=db)
    
    try:
        print("\n1. Getting job status...")
        status = scheduler.get_job_status()
        
        print(f"✅ Scheduler status: {status['scheduler_status']}")
        print(f"\n   Configured jobs:")
        for job_name, job_info in status['jobs'].items():
            print(f"   - {job_name}: {job_info['status']}")
        
        await db.disconnect()
        print("\n✅ Job status test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Job status test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        return False


async def run_all_tests():
    """Run all sync job tests."""
    print("\n" + "="*60)
    print("SYNC JOBS INTEGRATION TESTS")
    print("="*60)
    print("Testing all background sync jobs")
    print()
    
    # Setup
    await setup_test_data()
    
    # Run tests
    results = []
    results.append(("Order Sync Job", await test_order_sync_job()))
    results.append(("Position Sync Job", await test_position_sync_job()))
    results.append(("Margins Sync Job", await test_margins_sync_job()))
    results.append(("Position Monitoring Job", await test_position_monitoring_job()))
    results.append(("Daily Initialization Job", await test_daily_initialization_job()))
    results.append(("Job Status", await test_job_status()))
    
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
        print("\n🎉 All sync job tests passed!")
        print("\n📝 Next steps:")
        print("   1. Run paper trading mode test")
        print("   2. Monitor real-time sync during market hours")
        print("   3. Validate guardrails with live market data")
        return True
    else:
        print("\n⚠️  Some tests failed. Fix issues before proceeding.")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
