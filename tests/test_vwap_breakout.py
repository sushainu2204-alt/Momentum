"""
Test VWAP Breakout Strategy

Validates:
1. VWAP calculation and breakout detection
2. Volume surge confirmation
3. Entry/exit signal generation
4. Position sizing
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime, time

from backend.core.strategies import VWAPBreakoutStrategy
from backend.core.config import VWAPBreakoutConfig
from backend.models import Candidate, Position


def create_sample_data(num_candles=100):
    """Create sample OHLCV data for testing"""
    dates = pd.date_range(end=datetime.now(), periods=num_candles, freq='5T')
    
    # Create realistic price movement
    base_price = 100
    prices = base_price + np.cumsum(np.random.randn(num_candles) * 0.5)
    prices = np.maximum(prices, base_price * 0.9)  # Floor at 90% of base
    
    df = pd.DataFrame({
        'date': dates,
        'open': prices + np.random.rand(num_candles) * 0.5,
        'high': prices + np.random.rand(num_candles) * 1.0,
        'low': prices - np.random.rand(num_candles) * 0.5,
        'close': prices,
        'volume': np.random.randint(100000, 500000, num_candles)
    })
    
    # Add a volume spike at the end
    df.loc[df.index[-1], 'volume'] = df['volume'].mean() * 2.5
    
    # Price should be above VWAP in last candle
    df.loc[df.index[-1], 'close'] = df['close'].mean() * 1.01
    
    return df


def test_vwap_breakout_strategy():
    """Test VWAP breakout strategy logic"""
    
    print("=" * 70)
    print("TESTING VWAP BREAKOUT STRATEGY")
    print("=" * 70)
    
    # Create config
    config = VWAPBreakoutConfig(
        volume_multiplier=1.5,
        vwap_breakout_pct=0.2,
        stop_loss_pct=0.7,
        target_pct=1.5
    )
    
    print(f"\n📊 Configuration:")
    print(f"   Volume Multiplier: {config.volume_multiplier}x")
    print(f"   VWAP Breakout: {config.vwap_breakout_pct}%")
    print(f"   Stop Loss: {config.stop_loss_pct}%")
    print(f"   Target: {config.target_pct}%")
    print(f"   Risk:Reward: 1:{config.target_pct/config.stop_loss_pct:.2f}")
    
    # Create strategy
    strategy = VWAPBreakoutStrategy(config)
    
    # Create sample data
    df = create_sample_data(100)
    current_price = df['close'].iloc[-1]
    
    print(f"\n📈 Sample Data:")
    print(f"   Candles: {len(df)}")
    print(f"   Current Price: ₹{current_price:.2f}")
    print(f"   Avg Volume: {df['volume'].mean():,.0f}")
    print(f"   Current Volume: {df['volume'].iloc[-1]:,.0f}")
    
    # Create candidate
    candidate = Candidate(
        symbol="TEST",
        instrument_token=12345,
        current_price=current_price,
        open_price=df['open'].iloc[-1],
        high_price=df['high'].iloc[-1],
        low_price=df['low'].iloc[-1],
        volume=int(df['volume'].iloc[-1]),
        gain_pct=2.5,
        avg_volume=int(df['volume'].mean()),
        timestamp=datetime.now()
    )
    
    print(f"\n🎯 Candidate:")
    print(f"   Symbol: {candidate.symbol}")
    print(f"   Price: ₹{candidate.current_price:.2f}")
    print(f"   Volume: {candidate.volume:,}")
    print(f"   Avg Volume: {candidate.avg_volume:,}")
    print(f"   Volume Ratio: {candidate.volume/candidate.avg_volume:.2f}x")
    
    # Test filters
    print(f"\n🔍 Testing Filters:")
    
    # Filter 1: VWAP Breakout
    vwap_pass = strategy._check_vwap_breakout(candidate, df)
    print(f"   ✓ VWAP Breakout: {'PASS' if vwap_pass else 'FAIL'}")
    
    # Filter 2: Volume Surge
    volume_pass = strategy._check_volume_surge(df)
    print(f"   ✓ Volume Surge: {'PASS' if volume_pass else 'FAIL'}")
    
    # Combined filters
    all_pass = strategy.apply_filters(candidate, df)
    print(f"\n   {'✅ All filters PASSED' if all_pass else '❌ Some filters FAILED'}")
    
    # Test entry signal
    print(f"\n📍 Testing Entry Signal:")
    current_time = datetime.now().replace(hour=10, minute=30)
    
    if all_pass:
        signal = strategy.should_enter(candidate, df, current_time)
        
        if signal:
            print(f"   ✅ BUY Signal Generated")
            print(f"      Symbol: {signal.symbol}")
            print(f"      Entry Price: ₹{signal.price:.2f}")
            print(f"      Stop Loss: ₹{signal.stop_loss:.2f} ({config.stop_loss_pct}%)")
            print(f"      Target: ₹{signal.target:.2f} ({config.target_pct}%)")
            print(f"      Reason: {signal.reason}")
        else:
            print(f"   ❌ No entry signal (outside trading hours?)")
    else:
        print(f"   ⚠️  Skipped (filters failed)")
    
    # Test position sizing
    print(f"\n💰 Testing Position Sizing:")
    capital = 100000
    quantity = strategy.calculate_position_size(capital, current_price)
    position_value = quantity * current_price
    
    print(f"   Capital: ₹{capital:,.2f}")
    print(f"   Position Size: {config.position_size_pct*100}%")
    print(f"   Quantity: {quantity} shares")
    print(f"   Position Value: ₹{position_value:,.2f}")
    print(f"   Actual %: {position_value/capital*100:.1f}%")
    
    # Test exit conditions
    if all_pass and signal:
        print(f"\n🚪 Testing Exit Conditions:")
        
        # Create position
        position = Position(
            symbol=signal.symbol,
            instrument_token=signal.instrument_token,
            entry_price=signal.price,
            quantity=quantity,
            stop_loss=signal.stop_loss,
            target=signal.target,
            entry_time=current_time
        )
        
        # Test target hit
        target_price = signal.target
        exit_signal = strategy.should_exit(position, target_price, current_time)
        print(f"   Target Hit: {'✅ EXIT' if exit_signal else '❌'}")
        
        # Test stop loss hit
        sl_price = signal.stop_loss
        position.current_price = sl_price  # Reset
        exit_signal = strategy.should_exit(position, sl_price, current_time)
        print(f"   Stop Loss Hit: {'✅ EXIT' if exit_signal else '❌'}")
        
        # Test time exit
        exit_time = datetime.now().replace(hour=15, minute=20)
        exit_signal = strategy.should_exit(position, signal.price, exit_time)
        print(f"   Time Exit (3:20 PM): {'✅ EXIT' if exit_signal else '❌'}")
    
    print(f"\n" + "=" * 70)
    print("✅ VWAP BREAKOUT STRATEGY TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    test_vwap_breakout_strategy()
