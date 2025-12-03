"""
Quick test script to validate new architecture.
Run this to ensure everything works!

Usage:
    python non-prod/scripts/validation/validate_architecture.py
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

print("="*60)
print("VALIDATING NEW ARCHITECTURE")
print("="*60)

errors = []

# Test 1: Import config
print("\n1. Testing config module...")
try:
    from backend.config import settings
    print(f"   ✓ Config loaded")
    print(f"   ✓ Redis URL: {settings.REDIS_URL}")
    print(f"   ✓ Default EMAs: {settings.DEFAULT_FAST_EMA}/{settings.DEFAULT_SLOW_EMA}")
except Exception as e:
    errors.append(f"Config import failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 2: Import models
print("\n2. Testing models...")
try:
    from backend.core.models import Signal, Trade
    print(f"   ✓ Signal model imported")
    print(f"   ✓ Trade model imported")
except Exception as e:
    errors.append(f"Models import failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 3: Import strategies
print("\n3. Testing strategies...")
try:
    from backend.core.strategies import BaseStrategy, EMACrossoverStrategy
    print(f"   ✓ BaseStrategy imported")
    print(f"   ✓ EMACrossoverStrategy imported")
    
    # Test strategy creation
    strategy = EMACrossoverStrategy(fast_period=9, slow_period=21)
    print(f"   ✓ Created strategy: {strategy.name}")
    print(f"   ✓ Min data points: {strategy.min_data_points}")
except Exception as e:
    errors.append(f"Strategies import failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 4: Import services
print("\n4. Testing services...")
try:
    from backend.core.services import KiteService, MarketDataService, SignalService
    print(f"   ✓ KiteService imported")
    print(f"   ✓ MarketDataService imported")
    print(f"   ✓ SignalService imported")
except Exception as e:
    errors.append(f"Services import failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 5: Import workers
print("\n5. Testing workers...")
try:
    from backend.workers.vwap_breakout_worker import VWAPBreakoutWorker
    print(f"   ✓ VWAPBreakoutWorker imported")
except Exception as e:
    errors.append(f"Workers import failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 6: Import backtesting
print("\n6. Testing backtesting...")
try:
    from backend.backtesting.engine import BacktestEngine
    print(f"   ✓ BacktestEngine imported")
    
    # Test engine creation
    engine = BacktestEngine(initial_capital=100000)
    print(f"   ✓ Created engine with capital: ₹{engine.initial_capital:,.2f}")
except Exception as e:
    errors.append(f"Backtesting import failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 7: Import API
print("\n7. Testing API...")
try:
    from backend.api.routes import router
    print(f"   ✓ API routes imported")
except Exception as e:
    errors.append(f"API import failed: {e}")
    print(f"   ✗ Failed: {e}")

# Test 8: Test strategy with sample data
print("\n8. Testing strategy with sample data...")
try:
    import pandas as pd
    from backend.core.strategies import EMACrossoverStrategy
    
    # Create sample price data
    prices = pd.Series([100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
                       110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
                       120, 121, 122])
    
    strategy = EMACrossoverStrategy(fast_period=5, slow_period=10)
    fast_ema, slow_ema = strategy.calculate_indicators(prices)
    
    print(f"   ✓ Calculated EMAs on {len(prices)} prices")
    print(f"   ✓ Fast EMA: {fast_ema:.2f}")
    print(f"   ✓ Slow EMA: {slow_ema:.2f}")
except Exception as e:
    errors.append(f"Strategy calculation failed: {e}")
    print(f"   ✗ Failed: {e}")

# Summary
print("\n" + "="*60)
if not errors:
    print("✅ ALL TESTS PASSED!")
    print("   New architecture is working correctly.")
    print("\n   Next steps:")
    print("   1. Start backend: uvicorn backend.main:app --reload")
    print("   2. Run worker: python backend/workers/run_strategy.py")
    print("   3. Run backtest: python non-prod/tools/backtesting/runner.py --days 7")
else:
    print("❌ SOME TESTS FAILED:")
    for error in errors:
        print(f"   - {error}")
    sys.exit(1)

print("="*60 + "\n")
