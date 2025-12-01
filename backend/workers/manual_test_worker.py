"""
Manual Test Worker

Interactive worker for controlled end-to-end testing.
Runs through complete flow with manual symbol input.

Usage:
    python backend/workers/manual_test_worker.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import logging

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.strategies.manual_test_strategy import ManualTestStrategy, ManualTestConfig
from backend.core.services.kite_service import KiteService
from backend.core.services.signal_storage import SignalStorage
from backend.infrastructure.database.postgres import PostgresDatabase
from backend.infrastructure.database.position_repository import PositionRepository
from backend.infrastructure.database.order_repository import OrderRepository
from backend.core.services.order_manager import OrderManager
from backend.core.services.position_manager import PositionManager
from backend.core.services.capital_manager import CapitalManager, TradingLimits
from backend.core.services.signal_executor import SignalExecutor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database config
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "appdb",
    "user": "appuser",
    "password": "secret"
}


class ManualTestWorker:
    """Interactive worker for manual testing."""
    
    def __init__(self):
        self.kite = None
        self.db = None
        self.signal_executor = None
        self.strategy = None
        
    async def initialize(self):
        """Initialize all services."""
        logger.info("🔧 Initializing services...")
        
        # Kite service
        self.kite = KiteService()
        logger.info("✅ Kite service ready")
        
        # Database
        self.db = PostgresDatabase(DB_CONFIG)
        await self.db.connect()
        logger.info("✅ Database connected")
        
        # Repositories
        position_repo = PositionRepository(self.db)
        order_repo = OrderRepository(self.db)
        
        # Managers
        order_manager = OrderManager(self.kite, order_repo)
        position_manager = PositionManager(self.kite, position_repo)
        
        limits = TradingLimits(
            max_positions=5,
            position_size_pct=20,
            risk_per_trade_pct=2
        )
        capital_manager = CapitalManager(
            database=self.db,
            kite_service=self.kite,
            position_manager=position_manager,
            limits=limits
        )
        
        # Initialize daily capital
        await capital_manager.initialize_daily_capital()
        
        # Signal executor
        self.signal_executor = SignalExecutor(
            order_manager=order_manager,
            position_manager=position_manager,
            capital_manager=capital_manager,
            database=self.db,
            dry_run=True  # PAPER TRADING MODE
        )
        
        logger.info("✅ All services initialized")
        
    async def cleanup(self):
        """Cleanup resources."""
        if self.db:
            await self.db.disconnect()
            
    def get_user_input(self):
        """Get test parameters from user."""
        print("\n" + "="*70)
        print("  MANUAL TEST MODE - PAPER TRADING")
        print("="*70)
        print("\n✅ PAPER TRADING MODE - No real orders will be placed")
        print("💡 All guardrails will be validated without actual execution\n")
        
        # Get symbol
        symbol = input("Enter stock symbol (e.g., YESBANK): ").strip().upper()
        
        # Get current price
        try:
            ltp = self.kite.kite.ltp(f"NSE:{symbol}")
            current_price = ltp[f"NSE:{symbol}"]["last_price"]
            print(f"📊 Current price of {symbol}: ₹{current_price:.2f}")
        except Exception as e:
            print(f"❌ Could not fetch price for {symbol}: {e}")
            return None
        
        # Get entry price
        entry_str = input(f"Entry price [press Enter for current ₹{current_price:.2f}]: ").strip()
        entry_price = float(entry_str) if entry_str else current_price
        
        # Get SL %
        sl_str = input("Stop loss % [default 2%]: ").strip()
        stop_loss_pct = float(sl_str) if sl_str else 2.0
        
        # Get Target %
        target_str = input("Target % [default 3%]: ").strip()
        target_pct = float(target_str) if target_str else 3.0
        
        # Get quantity
        qty_str = input("Quantity [default 1]: ").strip()
        quantity = int(qty_str) if qty_str else 1
        
        # Calculate amounts
        stop_loss = entry_price * (1 - stop_loss_pct / 100)
        target = entry_price * (1 + target_pct / 100)
        required_capital = entry_price * quantity
        
        # Confirmation
        print("\n" + "="*70)
        print("  CONFIRM TEST PARAMETERS")
        print("="*70)
        print(f"\n📋 Symbol: {symbol}")
        print(f"💰 Entry: ₹{entry_price:.2f}")
        print(f"🛑 Stop Loss: ₹{stop_loss:.2f} ({stop_loss_pct}%)")
        print(f"🎯 Target: ₹{target:.2f} ({target_pct}%)")
        print(f"📦 Quantity: {quantity}")
        print(f"💵 Required Capital: ₹{required_capital:.2f}")
        print(f"\n⚠️  Risk per trade: ₹{(entry_price - stop_loss) * quantity:.2f}")
        print(f"💚 Potential profit: ₹{(target - entry_price) * quantity:.2f}")
        
        confirm = input("\n✅ Proceed with this test? (yes/no): ").strip().lower()
        
        if confirm != 'yes':
            print("❌ Test cancelled")
            return None
        
        return {
            "symbol": symbol,
            "entry_price": entry_price,
            "stop_loss_pct": stop_loss_pct,
            "target_pct": target_pct,
            "quantity": quantity
        }
    
    async def run_test(self):
        """Run manual test flow."""
        try:
            await self.initialize()
            
            # Get test parameters
            params = self.get_user_input()
            if not params:
                return
            
            # Create strategy config
            config = ManualTestConfig(**params)
            
            # Create strategy
            self.strategy = ManualTestStrategy(config)
            
            print("\n" + "="*70)
            print("  EXECUTING TEST FLOW")
            print("="*70)
            
            # Step 1: Get candidates
            print("\n📋 Step 1: Getting candidates...")
            candidates = self.strategy.get_candidates()
            print(f"✅ Found {len(candidates)} candidate(s)")
            
            if not candidates:
                print("❌ No candidates")
                return
            
            candidate = candidates[0]
            
            # Step 2: Fetch instrument token
            print(f"\n🔍 Step 2: Fetching instrument token for {candidate.symbol}...")
            try:
                instruments = self.kite.kite.instruments("NSE")
                matching = [i for i in instruments if i['tradingsymbol'] == candidate.symbol]
                if matching:
                    candidate.instrument_token = matching[0]['instrument_token']
                    print(f"✅ Instrument token: {candidate.instrument_token}")
                else:
                    print(f"❌ Instrument token not found")
                    return
            except Exception as e:
                print(f"❌ Error fetching instrument: {e}")
                return
            
            # Step 3: Generate signal
            print(f"\n🎯 Step 3: Generating signal...")
            signal = self.strategy.generate_entry_signal(candidate, None)
            
            if not signal:
                print("❌ No signal generated")
                return
            
            print(f"✅ Signal generated: {signal.symbol} @ ₹{signal.price:.2f}")
            
            # Step 4: Execute through guardrails
            print(f"\n🛡️  Step 4: Executing through 9 guardrails...")
            print("⏳ This will validate:")
            print("   1. Market hours")
            print("   2. Position limit")
            print("   3. Capital availability")
            print("   4. Existing position check")
            print("   5. Pending order check")
            print("   6. Cooldown period")
            print("   7. Duplicate signal check")
            print("   8. Price validation")
            print("   9. Risk validation")
            
            result = await self.signal_executor.execute_signal(
                signal=signal,
                strategy_name="manual_test"
            )
            
            print(f"\n📊 Execution Result:")
            print(f"   Decision: {result.decision}")
            print(f"   Reason: {result.reason or 'N/A'}")
            
            if result.decision == "EXECUTE":
                print(f"   Order ID: {result.order_id or 'PAPER_TRADING'}")
                print(f"   Quantity: {result.quantity}")
                print(f"\n✅ WOULD PLACE ORDER (PAPER TRADING MODE)")
                print(f"🎯 All guardrails passed - order would execute in live mode")
                print(f"\n💡 In live mode, bracket order would be created with automatic SL/Target")
            elif result.decision == "IGNORE":
                print(f"\n⚠️  Signal ignored by guardrail: {result.reason}")
            else:
                print(f"\n❌ Execution failed: {result.reason}")
            
            # Step 5: Show trade log
            print(f"\n📝 Step 5: Checking trade log...")
            logs = await self.db.fetch_all(
                "SELECT * FROM trade_logs WHERE symbol = $1 ORDER BY timestamp DESC LIMIT 1",
                {"1": signal.symbol}
            )
            
            if logs:
                log = logs[0]
                print(f"✅ Trade log entry created:")
                print(f"   Decision: {log['decision']}")
                print(f"   Log type: {log['log_type']}")
                print(f"   Strategy: {log['strategy_name']}")
                print(f"   Timestamp: {log['timestamp']}")
            
            # Step 6: Show capital state
            print(f"\n💰 Step 6: Capital state after execution...")
            summary = await self.signal_executor.capital_manager.get_capital_summary()
            print(f"   Available: ₹{summary.get('available_capital', 0):,.2f}")
            print(f"   In positions: ₹{summary.get('utilized_margin', 0):,.2f}")
            print(f"   Open positions: {summary.get('open_positions_count', 0)}")
            
            print("\n" + "="*70)
            print("  TEST COMPLETED")
            print("="*70)
            
        except Exception as e:
            logger.error(f"Test failed: {e}", exc_info=True)
        finally:
            await self.cleanup()


async def main():
    """Main entry point."""
    worker = ManualTestWorker()
    await worker.run_test()


if __name__ == "__main__":
    asyncio.run(main())
