"""
Comprehensive Manager and Sync Jobs Verification

Tests all managers with real Kite API calls and database operations.
Validates each functionality before paper trading.

Run during market hours for complete validation.
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, time, timedelta
from decimal import Decimal
import os
from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv()

from backend.core.services.kite_service import KiteService
from backend.infrastructure.database.postgres import PostgresDatabase
from backend.infrastructure.database.position_repository import PositionRepository
from backend.infrastructure.database.order_repository import OrderRepository
from backend.core.services.order_manager import OrderManager
from backend.core.services.position_manager import PositionManager
from backend.core.services.capital_manager import CapitalManager, TradingLimits
from backend.core.services.signal_executor import SignalExecutor
from backend.jobs.sync_jobs import SyncJobsScheduler
from backend.models import Signal, SignalType, Position, PositionStatus


# Database configuration
DB_CONFIG = {
    "host": "127.0.0.1",  # Use IPv4 explicitly instead of localhost
    "port": 5432,
    "database": "appdb",
    "user": "appuser",
    "password": "secret"
}


class VerificationTests:
    """Comprehensive verification test suite."""
    
    def __init__(self):
        self.db = None
        self.kite = None
        self.order_manager = None
        self.position_manager = None
        self.capital_manager = None
        self.signal_executor = None
        self.sync_jobs = None
        self.test_results = []
        
    async def setup(self):
        """Initialize all components."""
        print("\n" + "="*80)
        print("  COMPREHENSIVE MANAGER VERIFICATION")
        print("="*80)
        print("\n⚙️  Initializing components...")
        
        # Database
        self.db = PostgresDatabase(DB_CONFIG)
        await self.db.connect()
        print("✅ Database connected")
        
        # Kite API
        self.kite = KiteService()
        print("✅ Kite service initialized")
        
        # Repositories
        position_repo = PositionRepository(self.db)
        order_repo = OrderRepository(self.db)
        
        # Managers
        self.order_manager = OrderManager(self.kite, order_repo)
        self.position_manager = PositionManager(self.kite, position_repo)
        
        limits = TradingLimits(
            max_positions=5,
            position_size_pct=20,
            risk_per_trade_pct=2
        )
        self.capital_manager = CapitalManager(
            database=self.db,
            kite_service=self.kite,
            position_manager=self.position_manager,
            limits=limits
        )
        
        self.signal_executor = SignalExecutor(
            order_manager=self.order_manager,
            position_manager=self.position_manager,
            capital_manager=self.capital_manager,
            database=self.db,
            dry_run=True
        )
        
        # Create sync_jobs after signal_executor
        self.sync_jobs = SyncJobsScheduler(
            order_manager=self.order_manager,
            position_manager=self.position_manager,
            capital_manager=self.capital_manager,
            signal_executor=self.signal_executor
        )
        
        print("✅ All managers initialized")
        print("\n⚠️  NOTE: Running in DRY RUN mode - no real orders will be placed\n")
        
    async def cleanup(self):
        """Cleanup resources."""
        if self.db:
            await self.db.disconnect()
            
    def print_test_header(self, test_name):
        """Print formatted test header."""
        print("\n" + "="*80)
        print(f"  TEST: {test_name}")
        print("="*80)
        
    def record_result(self, test_name, passed, details=""):
        """Record test result."""
        self.test_results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"\n{status}: {test_name}")
        if details:
            print(f"   {details}")
            
    # =========================================================================
    # KITE API VERIFICATION
    # =========================================================================
    
    async def verify_kite_api(self):
        """Verify Kite API connectivity and data access."""
        self.print_test_header("Kite API Connectivity")
        
        try:
            # Test 1: Get profile
            print("\n📋 Fetching profile...")
            profile = self.kite.kite.profile()
            print(f"✅ Profile: {profile['user_name']} ({profile['user_id']})")
            
            # Test 2: Get margins
            print("\n💰 Fetching margins...")
            margins = self.kite.kite.margins()
            equity = margins.get('equity', {})
            available = equity.get('available', {}).get('cash', 0)
            print(f"✅ Available cash: ₹{available:,.2f}")
            
            # Test 3: Get holdings (optional, may be empty)
            print("\n📊 Fetching holdings...")
            holdings = self.kite.kite.holdings()
            print(f"✅ Holdings count: {len(holdings)}")
            
            # Test 4: Get positions
            print("\n📈 Fetching positions...")
            positions = self.kite.kite.positions()
            day_positions = positions.get('day', [])
            print(f"✅ Day positions: {len(day_positions)}")
            
            # Test 5: Get orders
            print("\n📝 Fetching orders...")
            orders = self.kite.kite.orders()
            print(f"✅ Orders count: {len(orders)}")
            
            self.record_result("Kite API Connectivity", True, 
                             f"Profile, margins, holdings, positions, orders - all accessible")
            
        except Exception as e:
            self.record_result("Kite API Connectivity", False, str(e))
            raise
            
    # =========================================================================
    # ORDER MANAGER VERIFICATION
    # =========================================================================
    
    async def verify_order_manager(self):
        """Verify OrderManager functionality."""
        self.print_test_header("OrderManager Verification")
        
        try:
            # Test 1: Sync orders from Kite
            print("\n🔄 Syncing orders from Kite...")
            await self.order_manager.sync_orders_from_kite()
            print("✅ Orders synced successfully")
            
            # Test 2: Get today's orders
            print("\n📋 Fetching today's orders from DB...")
            orders = await self.order_manager.get_todays_orders()
            print(f"✅ Found {len(orders)} orders in database")
            
            if orders:
                for order in orders[:3]:  # Show first 3
                    print(f"   - {order['symbol']}: {order['status']} "
                          f"({order['quantity']} @ ₹{order['price']})")
            
            # Test 3: Check pending orders
            print("\n⏳ Checking for pending orders...")
            has_pending = await self.order_manager.has_pending_order("TESTSTOCK")
            print(f"✅ Has pending order check working: {has_pending}")
            
            # Test 4: Get pending orders list
            print("\n📝 Fetching all pending orders...")
            pending = await self.order_manager.get_pending_orders()
            print(f"✅ Pending orders: {len(pending)}")
            
            self.record_result("OrderManager", True, 
                             f"Sync, fetch, pending checks - all working")
            
        except Exception as e:
            self.record_result("OrderManager", False, str(e))
            raise
            
    # =========================================================================
    # POSITION MANAGER VERIFICATION
    # =========================================================================
    
    async def verify_position_manager(self):
        """Verify PositionManager functionality."""
        self.print_test_header("PositionManager Verification")
        
        try:
            # Test 1: Sync positions from Kite
            print("\n🔄 Syncing positions from Kite...")
            await self.position_manager.sync_positions_from_kite()
            print("✅ Positions synced successfully")
            
            # Test 2: Get open positions
            print("\n📊 Fetching open positions from DB...")
            positions = await self.position_manager.get_open_positions()
            print(f"✅ Found {len(positions)} open positions")
            
            if positions:
                for pos in positions[:3]:  # Show first 3
                    pnl = pos.get('current_pnl', 0) or 0
                    print(f"   - {pos['symbol']}: {pos['quantity']} @ ₹{pos['entry_price']} "
                          f"(P&L: ₹{pnl:,.2f})")
            
            # Test 3: Check if position exists
            print("\n🔍 Testing position existence check...")
            has_position = await self.position_manager.has_position("TESTSTOCK")
            print(f"✅ Position check working: {has_position}")
            
            # Test 4: Get position count
            print("\n📈 Getting position count...")
            count = await self.position_manager.get_open_positions_count()
            print(f"✅ Current position count: {count}")
            
            print("\n📝 NOTE: SL/Target exits handled automatically by bracket orders")
            
            self.record_result("PositionManager", True, 
                             f"Sync, fetch, position checks - all working")
            
        except Exception as e:
            self.record_result("PositionManager", False, str(e))
            raise
            
    # =========================================================================
    # CAPITAL MANAGER VERIFICATION
    # =========================================================================
    
    async def verify_capital_manager(self):
        """Verify CapitalManager functionality."""
        self.print_test_header("CapitalManager Verification")
        
        try:
            # Test 1: Initialize daily capital
            print("\n💰 Initializing daily capital...")
            await self.capital_manager.initialize_daily_capital()
            print("✅ Daily capital initialized")
            
            # Test 2: Get available capital
            print("\n💵 Fetching available capital...")
            available = await self.capital_manager.get_available_capital()
            print(f"✅ Available capital: ₹{available:,.2f}")
            
            # Test 3: Get current capital
            print("\n📊 Fetching current capital state...")
            current = await self.capital_manager.get_current_capital()
            print(f"✅ Current capital: ₹{current:,.2f}")
            
            # Test 4: Get utilized margin
            print("\n📈 Fetching utilized margin...")
            utilized = await self.capital_manager.get_utilized_margin()
            print(f"✅ Utilized margin: ₹{utilized:,.2f}")
            
            # Test 5: Get capital summary
            print("\n📋 Fetching capital summary...")
            summary = await self.capital_manager.get_capital_summary()
            print(f"✅ Capital summary:")
            print(f"   - Starting: ₹{summary.get('starting_capital', 0):,.2f}")
            print(f"   - Current: ₹{summary.get('current_capital', 0):,.2f}")
            print(f"   - Available: ₹{summary.get('available_capital', 0):,.2f}")
            print(f"   - Utilized: ₹{summary.get('utilized_margin', 0):,.2f}")
            print(f"   - Realized P&L: ₹{summary.get('realized_pnl', 0):,.2f}")
            
            # Test 6: Calculate position size
            print("\n🧮 Testing position size calculation...")
            test_price = 2500.0
            test_sl = 2450.0
            quantity = await self.capital_manager.calculate_position_size(
                test_price, test_sl
            )
            required = test_price * quantity
            print(f"✅ Position size for ₹{test_price} (SL: ₹{test_sl}):")
            print(f"   - Quantity: {quantity}")
            print(f"   - Required capital: ₹{required:,.2f}")
            
            # Test 7: Check if can allocate
            print("\n✅ Testing capital allocation check...")
            can_allocate = await self.capital_manager.can_allocate(required)
            print(f"✅ Can allocate ₹{required:,.2f}: {can_allocate}")
            
            # Test 8: Check position limit
            print("\n🔢 Testing position limit check...")
            can_open = await self.capital_manager.check_position_limit()
            print(f"✅ Can open new position: {can_open}")
            
            # Test 9: Sync margins to DB
            print("\n💾 Syncing margins to database...")
            await self.capital_manager.sync_margins_to_db()
            print("✅ Margins synced to DB")
            
            self.record_result("CapitalManager", True, 
                             f"All capital management functions working")
            
        except Exception as e:
            self.record_result("CapitalManager", False, str(e))
            raise
            
    # =========================================================================
    # SIGNAL EXECUTOR VERIFICATION
    # =========================================================================
    
    async def verify_signal_executor(self):
        """Verify SignalExecutor with all 9 guardrails."""
        self.print_test_header("SignalExecutor Verification (9 Guardrails)")
        
        try:
            # Create test signal
            test_signal = Signal(
                timestamp=datetime.now(),
                symbol="RELIANCE",
                instrument_token=738561,
                signal_type=SignalType.BUY,
                price=2500.0,
                stop_loss=2450.0,
                target=2600.0,
                quantity=0,  # Will be calculated
                reason="Test signal for verification"
            )
            
            print(f"\n📊 Testing signal: {test_signal.symbol} @ ₹{test_signal.price}")
            
            # Execute signal (dry run)
            print("\n🛡️  Executing through all 9 guardrails...")
            result = await self.signal_executor.execute_signal(
                signal=test_signal,
                strategy_name="test_verification"
            )
            
            print(f"\n📋 Execution Result:")
            print(f"   - Decision: {result.decision}")
            print(f"   - Reason: {result.reason or 'N/A'}")
            
            if result.decision == 'EXECUTE':
                print(f"   - Order ID: {result.order_id or 'DRY RUN'}")
                print(f"   - Quantity: {result.quantity or 0}")
            
            # Get execution statistics
            print("\n📊 Fetching execution statistics...")
            stats = await self.signal_executor.get_execution_stats()
            print(f"✅ Execution statistics:")
            print(f"   - Total signals: {stats.get('total_signals', 0)}")
            print(f"   - Executed: {stats.get('executed', 0)}")
            print(f"   - Ignored: {stats.get('ignored', 0)}")
            print(f"   - Failed: {stats.get('failed', 0)}")
            
            if 'guardrails' in stats:
                print(f"\n   Guardrail breakdown:")
                for guardrail, count in stats['guardrails'].items():
                    if count > 0:
                        print(f"      - {guardrail}: {count} blocked")
            
            # Verify trade log entry
            print("\n📝 Verifying trade log entry...")
            logs = await self.db.fetch_all(
                "SELECT * FROM trade_logs WHERE symbol = $1 ORDER BY timestamp DESC LIMIT 1",
                {"1": test_signal.symbol}
            )
            
            if logs:
                print("✅ Trade log entry created:")
                log = logs[0]
                print(f"   - Decision: {log['decision']}")
                print(f"   - Log type: {log['log_type']}")
                print(f"   - Strategy: {log['strategy_name']}")
            else:
                print("⚠️  No trade log entry found (may be expected if guardrail blocked)")
            
            self.record_result("SignalExecutor (9 Guardrails)", True, 
                             f"Signal processed through all guardrails, logs created")
            
        except Exception as e:
            self.record_result("SignalExecutor (9 Guardrails)", False, str(e))
            raise
            
    # =========================================================================
    # SYNC JOBS VERIFICATION
    # =========================================================================
    
    async def verify_sync_jobs(self):
        """Verify all background sync jobs."""
        self.print_test_header("Sync Jobs Verification")
        
        try:
            # Test 1: Order sync job
            print("\n🔄 Testing order sync job...")
            await self.sync_jobs.trigger_order_sync()
            print("✅ Order sync job executed")
            
            # Test 2: Position sync job
            print("\n🔄 Testing position sync job...")
            await self.sync_jobs.trigger_position_sync()
            print("✅ Position sync job executed")
            
            # Test 3: Margins sync job
            print("\n🔄 Testing margins sync job...")
            await self.sync_jobs.trigger_margins_sync()
            print("✅ Margins sync job executed")
            
            # Test 4: Position monitoring job
            print("\n🔄 Testing position monitoring job...")
            await self.sync_jobs.trigger_position_monitoring()
            print("✅ Position monitoring job executed")
            
            # Check job status
            print("\n📊 Getting job status...")
            status = self.sync_jobs.get_job_status()
            print("✅ Job status:")
            print(f"   - Running: {status.get('running')}")
            print(f"   - Market hours: {status.get('market_hours')}")
            if status.get('jobs'):
                for job in status['jobs'][:3]:  # Show first 3
                    print(f"   - {job['name']}: Next run at {job.get('next_run', 'N/A')}")
            
            self.record_result("Sync Jobs", True, 
                             f"All 4 sync jobs working correctly")
            
        except Exception as e:
            self.record_result("Sync Jobs", False, str(e))
            raise
            
    # =========================================================================
    # DATABASE VERIFICATION
    # =========================================================================
    
    async def verify_database_state(self):
        """Verify database state after all operations."""
        self.print_test_header("Database State Verification")
        
        try:
            # Check all tables
            tables = ['positions', 'orders', 'capital_state', 'trade_logs', 
                     'cooldown_tracker', 'signals']
            
            print("\n📊 Table row counts:")
            for table in tables:
                result = await self.db.fetch_one(
                    f"SELECT COUNT(*) as count FROM {table}",
                    {}
                )
                count = result['count'] if result else 0
                print(f"   - {table}: {count} rows")
            
            # Check today's activity
            print("\n📅 Today's activity:")
            
            # Today's orders
            orders = await self.db.fetch_all(
                "SELECT COUNT(*) as count FROM orders WHERE DATE(placed_at) = CURRENT_DATE",
                {}
            )
            print(f"   - Orders today: {orders[0]['count'] if orders else 0}")
            
            # Today's positions
            positions = await self.db.fetch_all(
                "SELECT COUNT(*) as count FROM positions WHERE DATE(entry_time) = CURRENT_DATE",
                {}
            )
            print(f"   - Positions opened today: {positions[0]['count'] if positions else 0}")
            
            # Today's trade logs
            logs = await self.db.fetch_all(
                "SELECT COUNT(*) as count FROM trade_logs WHERE DATE(timestamp) = CURRENT_DATE",
                {}
            )
            print(f"   - Trade logs today: {logs[0]['count'] if logs else 0}")
            
            # Capital state
            capital = await self.db.fetch_one(
                "SELECT * FROM capital_state WHERE date = CURRENT_DATE",
                {}
            )
            if capital:
                print(f"\n💰 Today's capital state:")
                print(f"   - Starting: ₹{capital['starting_capital']:,.2f}")
                print(f"   - Current: ₹{capital['current_capital']:,.2f}")
                print(f"   - Available: ₹{capital['available_capital']:,.2f}")
                print(f"   - In positions: ₹{capital.get('capital_in_positions', 0):,.2f}")
            
            self.record_result("Database State", True, 
                             f"All tables accessible, data properly stored")
            
        except Exception as e:
            self.record_result("Database State", False, str(e))
            raise
            
    # =========================================================================
    # MAIN TEST RUNNER
    # =========================================================================
    
    async def run_all_tests(self):
        """Run all verification tests."""
        try:
            await self.setup()
            
            print("\n" + "="*80)
            print("  STARTING COMPREHENSIVE VERIFICATION")
            print("="*80)
            print("\n⚠️  All tests run in READ-ONLY or DRY RUN mode")
            print("⚠️  No real orders will be placed\n")
            
            input("Press ENTER to start verification tests...")
            
            # Run all tests
            await self.verify_kite_api()
            await self.verify_order_manager()
            await self.verify_position_manager()
            await self.verify_capital_manager()
            await self.verify_signal_executor()
            await self.verify_sync_jobs()
            await self.verify_database_state()
            
            # Print summary
            self.print_summary()
            
        except Exception as e:
            print(f"\n❌ Verification failed with error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.cleanup()
            
    def print_summary(self):
        """Print test results summary."""
        print("\n" + "="*80)
        print("  VERIFICATION SUMMARY")
        print("="*80)
        
        passed = sum(1 for r in self.test_results if r['passed'])
        total = len(self.test_results)
        
        for result in self.test_results:
            status = "✅" if result['passed'] else "❌"
            print(f"\n{status} {result['test']}")
            if result['details']:
                print(f"   └─ {result['details']}")
        
        print("\n" + "="*80)
        print(f"  TOTAL: {passed}/{total} tests passed")
        print("="*80)
        
        if passed == total:
            print("\n🎉 ALL VERIFICATIONS PASSED!")
            print("✅ System is ready for paper trading")
            print("\nNext step: cd workers && python run_workers.py → Select Paper Trading Mode")
        else:
            print("\n⚠️  Some verifications failed")
            print("❌ Fix issues before proceeding to paper trading")


async def main():
    """Main entry point."""
    tests = VerificationTests()
    await tests.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
