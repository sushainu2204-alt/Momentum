"""
Test Bullish Flag Strategy

Validates:
1. Flag pattern detection (pole + pullback)
2. Breakout confirmation
3. Volume surge validation
4. Entry/exit signal generation
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime

from backend.core.strategies import BullishFlagStrategy
from backend.core.config import BullishFlagConfig
from backend.models import Candidate, Position


def create_flag_pattern_data():
    """Create sample data with bullish flag pattern"""
    np.random.seed(42)  # Consistent random data
    
    # Create 20 candles with flag pattern
    dates = pd.date_range(end=datetime.now(), periods=20, freq='5min')
    
    # Candles 0-4: Sideways (before pole)
    prices1 = [100, 100.2, 100.1, 100.3, 100.2]
    
    # Candles 5-8: Strong upward move (+2.5% - flag pole)
    prices2 = [100.5, 101.2, 101.8, 102.5]
    
    # Candles 9-12: Pullback (-0.7% from high - flag consolidation)
    prices3 = [102.2, 102.0, 101.9, 101.8]
    
    # Candles 13-15: Sideways consolidation
    prices4 = [101.9, 101.8, 101.9]
    
    # Candles 16-19: Breakout above flag
    prices5 = [102.2, 102.6, 102.9, 103.2]
    
    all_prices = prices1 + prices2 + prices3 + prices4 + prices5
    
    df = pd.DataFrame({
        'date': dates,
        'open': all_prices,
        'high': [p + np.random.rand() * 0.3 for p in all_prices],
        'low': [p - np.random.rand() * 0.3 for p in all_prices],
        'close': all_prices,
        'volume': np.random.randint(100000, 300000, 20)
    })
    
    # Add volume spike on breakout
    df.loc[df.index[-1], 'volume'] = int(df['volume'].mean() * 1.5)
    
    return df


def test_bullish_flag_strategy():
    """Test bullish flag strategy logic"""
    
    print("=" * 70)
    print("TESTING BULLISH FLAG STRATEGY")
    print("=" * 70)
    
    # Create config
    config = BullishFlagConfig(
        min_initial_move_pct=2.0,
        pullback_pct_min=0.3,
        pullback_pct_max=1.5,  # Allow up to 1.5% pullback
        pullback_candles_min=2,
        pullback_candles_max=5,
        breakout_threshold_pct=0.1,
        volume_multiplier=1.3,
        stop_loss_pct=0.8,
        target_pct=1.8
    )
    
    print(f"\n📊 Configuration:")
    print(f"   Min Initial Move: {config.min_initial_move_pct}%")
    print(f"   Pullback Range: {config.pullback_pct_min}% - {config.pullback_pct_max}%")
    print(f"   Pullback Candles: {config.pullback_candles_min} - {config.pullback_candles_max}")
    print(f"   Breakout Threshold: {config.breakout_threshold_pct}%")
    print(f"   Volume Multiplier: {config.volume_multiplier}x")
    print(f"   Stop Loss: {config.stop_loss_pct}%")
    print(f"   Target: {config.target_pct}%")
    print(f"   Risk:Reward: 1:{config.target_pct/config.stop_loss_pct:.2f}")
    
    # Create strategy
    strategy = BullishFlagStrategy(config)
    
    # Create sample data with flag pattern
    df = create_flag_pattern_data()
    current_price = df['close'].iloc[-1]
    
    print(f"\n📈 Sample Data (Bullish Flag Pattern):")
    print(f"   Candles: {len(df)}")
    print(f"   Price Range: ₹{df['low'].min():.2f} - ₹{df['high'].max():.2f}")
    print(f"   Current Price: ₹{current_price:.2f}")
    print(f"   Total Move: {((current_price - df['close'].iloc[0]) / df['close'].iloc[0]) * 100:.2f}%")
    
    print(f"\n   Price Evolution:")
    print(f"   Candles 0-4:  Sideways ~100")
    print(f"   Candles 5-8:  Pole +2.5% → 102.5 (FLAG POLE)")
    print(f"   Candles 9-12: Pullback → 101.8 (FLAG)")
    print(f"   Candles 13-15: Consolidation")
    print(f"   Candles 16-19: Breakout → {current_price:.2f} (BREAKOUT)")
    
    # Create candidate
    candidate = Candidate(
        symbol="TEST",
        instrument_token=12345,
        current_price=current_price,
        open_price=df['open'].iloc[-1],
        high_price=df['high'].iloc[-1],
        low_price=df['low'].iloc[-1],
        volume=int(df['volume'].iloc[-1]),
        gain_pct=3.2,
        avg_volume=int(df['volume'].mean()),
        timestamp=datetime.now()
    )
    
    print(f"\n🎯 Candidate:")
    print(f"   Symbol: {candidate.symbol}")
    print(f"   Price: ₹{candidate.current_price:.2f}")
    print(f"   Volume: {candidate.volume:,}")
    print(f"   Avg Volume: {candidate.avg_volume:,}")
    
    # Test flag pattern detection
    print(f"\n🚩 Testing Flag Pattern Detection:")
    pattern_found, flag_high, flag_low = strategy.detect_flag_pattern(df)
    
    if pattern_found:
        print(f"   ✅ Flag Pattern Detected!")
        print(f"      Flag High: ₹{flag_high:.2f}")
        print(f"      Flag Low: ₹{flag_low:.2f}")
        print(f"      Pullback: {((flag_high - flag_low) / flag_high) * 100:.2f}%")
    else:
        print(f"   ❌ No flag pattern detected")
    
    # Test filters
    print(f"\n🔍 Testing Filters:")
    all_pass = strategy.apply_filters(candidate, df)
    print(f"   {'✅ All filters PASSED' if all_pass else '❌ Some filters FAILED'}")
    
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
            
            # Test position sizing
            print(f"\n💰 Position Sizing:")
            capital = 100000
            quantity = strategy.calculate_position_size(capital, current_price)
            position_value = quantity * current_price
            
            print(f"   Capital: ₹{capital:,.2f}")
            print(f"   Position Size: {config.position_size_pct*100}%")
            print(f"   Quantity: {quantity} shares")
            print(f"   Position Value: ₹{position_value:,.2f}")
            
            # Test exit conditions
            print(f"\n🚪 Testing Exit Conditions:")
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
            exit_signal = strategy.should_exit(position, sl_price, current_time)
            print(f"   Stop Loss Hit: {'✅ EXIT' if exit_signal else '❌'}")
            
            # Test time exit
            exit_time = datetime.now().replace(hour=15, minute=20)
            exit_signal = strategy.should_exit(position, signal.price, exit_time)
            print(f"   Time Exit (3:20 PM): {'✅ EXIT' if exit_signal else '❌'}")
        else:
            print(f"   ❌ No entry signal (outside trading hours?)")
    else:
        print(f"   ⚠️  Skipped (filters failed)")
    
    print(f"\n" + "=" * 70)
    print("✅ BULLISH FLAG STRATEGY TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    test_bullish_flag_strategy()
