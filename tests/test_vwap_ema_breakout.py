"""
Test VWAP EMA Breakout Strategy

Validates:
1. Price range filter (2-4% gain)
2. VWAP filter (price > VWAP)
3. EMA filter (price > 20 EMA)
4. Volume surge (> 1.5x average)
5. Previous candle high breakout
6. Entry/exit signal generation
7. Signal storage to file
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import asyncio
import json
from datetime import datetime

from backend.core.strategies import VWAPEMABreakoutStrategy
from backend.core.config import VWAPEMABreakoutConfig
from backend.models import Candidate, Position
from backend.core.services.signal_storage import SignalStorage


def create_test_data():
    """Create sample data with uptrend and breakout"""
    np.random.seed(42)
    
    # Create 30 candles with uptrend
    dates = pd.date_range(end=datetime.now(), periods=30, freq='5min')
    
    # Gradual uptrend from 100 to 103 (+3%)
    base_prices = np.linspace(100, 103, 30)
    
    # Add some noise
    noise = np.random.randn(30) * 0.2
    closes = base_prices + noise
    
    df = pd.DataFrame({
        'date': dates,
        'open': closes - 0.1,
        'high': closes + 0.2,
        'low': closes - 0.2,
        'close': closes,
        'volume': np.random.randint(150000, 250000, 30)
    })
    
    # Add volume spike on last candle
    df.loc[df.index[-1], 'volume'] = int(df['volume'].mean() * 1.6)
    
    # Ensure last candle breaks previous high
    df.loc[df.index[-1], 'close'] = df['high'].iloc[-2] + 0.15
    df.loc[df.index[-1], 'high'] = df['close'].iloc[-1] + 0.1
    
    return df


async def test_vwap_ema_breakout_strategy():
    """Test VWAP EMA Breakout strategy logic and signal storage"""
    
    print("=" * 70)
    print("TESTING VWAP EMA BREAKOUT STRATEGY")
    print("=" * 70)
    
    # Create config
    config = VWAPEMABreakoutConfig(
        min_gain_pct=2.0,
        max_gain_pct=4.0,
        ema_period=20,
        vwap_enabled=True,
        volume_multiplier=1.5,
        volume_lookback=20,
        breakout_previous_high=True,
        stop_loss_pct=0.7,
        target_pct=1.5
    )
    
    print(f"\n📊 Configuration:")
    print(f"   Gain Range: {config.min_gain_pct}% - {config.max_gain_pct}%")
    print(f"   EMA Period: {config.ema_period}")
    print(f"   VWAP Enabled: {config.vwap_enabled}")
    print(f"   Volume Multiplier: {config.volume_multiplier}x")
    print(f"   Breakout Previous High: {config.breakout_previous_high}")
    print(f"   Stop Loss: {config.stop_loss_pct}%")
    print(f"   Target: {config.target_pct}%")
    print(f"   Risk:Reward: 1:{config.target_pct/config.stop_loss_pct:.2f}")
    
    # Create strategy
    strategy = VWAPEMABreakoutStrategy(config)
    
    # Create sample data
    df = create_test_data()
    current_price = df['close'].iloc[-1]
    prev_high = df['high'].iloc[-2]
    
    print(f"\n📈 Sample Data:")
    print(f"   Candles: {len(df)}")
    print(f"   Price Range: ₹{df['low'].min():.2f} - ₹{df['high'].max():.2f}")
    print(f"   Current Price: ₹{current_price:.2f}")
    print(f"   Previous High: ₹{prev_high:.2f}")
    print(f"   Total Move: {((current_price - df['close'].iloc[0]) / df['close'].iloc[0]) * 100:.2f}%")
    print(f"   Breakout: {'✅ Yes' if current_price > prev_high else '❌ No'} ({current_price:.2f} > {prev_high:.2f})")
    
    # Calculate indicators
    df_with_indicators = strategy.calculate_indicators(df)
    
    vwap = df_with_indicators['vwap'].iloc[-1]
    ema = df_with_indicators['ema_20'].iloc[-1]
    
    print(f"\n📉 Technical Indicators:")
    print(f"   VWAP: ₹{vwap:.2f}")
    print(f"   EMA(20): ₹{ema:.2f}")
    print(f"   Price > VWAP: {'✅' if current_price > vwap else '❌'} ({current_price:.2f} > {vwap:.2f})")
    print(f"   Price > EMA: {'✅' if current_price > ema else '❌'} ({current_price:.2f} > {ema:.2f})")
    
    # Create candidate with 3% gain (within 2-4% range)
    candidate = Candidate(
        symbol="TEST",
        instrument_token=12345,
        current_price=current_price,
        open_price=df['open'].iloc[-1],
        high_price=df['high'].iloc[-1],
        low_price=df['low'].iloc[-1],
        volume=int(df['volume'].iloc[-1]),
        gain_pct=3.0,  # Within range
        avg_volume=int(df['volume'].mean()),
        timestamp=datetime.now()
    )
    
    print(f"\n🎯 Candidate:")
    print(f"   Symbol: {candidate.symbol}")
    print(f"   Price: ₹{candidate.current_price:.2f}")
    print(f"   Gain: {candidate.gain_pct:.1f}% {'✅' if config.min_gain_pct <= candidate.gain_pct <= config.max_gain_pct else '❌'}")
    print(f"   Volume: {candidate.volume:,}")
    print(f"   Avg Volume: {candidate.avg_volume:,}")
    print(f"   Volume Ratio: {candidate.volume/candidate.avg_volume:.2f}x {'✅' if candidate.volume/candidate.avg_volume >= config.volume_multiplier else '❌'}")
    
    # Test filters
    print(f"\n🔍 Testing Filters:")
    
    # Test individual filters
    print(f"   1. Price Range (2-4%): {'✅ PASS' if strategy._check_price_range(candidate) else '❌ FAIL'}")
    print(f"   2. VWAP Filter: {'✅ PASS' if strategy._check_vwap_filter(df_with_indicators) else '❌ FAIL'}")
    print(f"   3. EMA Filter: {'✅ PASS' if strategy._check_ema_filter(df_with_indicators) else '❌ FAIL'}")
    print(f"   4. Volume Surge: {'✅ PASS' if strategy._check_volume_surge(df_with_indicators) else '❌ FAIL'}")
    print(f"   5. Previous High Breakout: {'✅ PASS' if strategy._check_breakout_previous_high(df_with_indicators) else '❌ FAIL'}")
    
    # Test all filters together
    all_pass = strategy.apply_filters(candidate, df_with_indicators)
    print(f"\n   {'✅ All filters PASSED' if all_pass else '❌ Some filters FAILED'}")
    
    # Test entry signal
    print(f"\n📍 Testing Entry Signal:")
    current_time = datetime.now().replace(hour=10, minute=30)
    
    if all_pass:
        signal = strategy.should_enter(candidate, df_with_indicators, current_time)
        
        if signal:
            print(f"   ✅ BUY Signal Generated")
            print(f"      Symbol: {signal.symbol}")
            print(f"      Entry Price: ₹{signal.price:.2f}")
            print(f"      Stop Loss: ₹{signal.stop_loss:.2f} ({config.stop_loss_pct}%)")
            print(f"      Target: ₹{signal.target:.2f} ({config.target_pct}%)")
            print(f"      SL Distance: ₹{signal.price - signal.stop_loss:.2f}")
            print(f"      Target Distance: ₹{signal.target - signal.price:.2f}")
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
            print(f"   Risk per trade: ₹{quantity * (signal.price - signal.stop_loss):.2f}")
            
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
            
            # Test signal storage
            print(f"\n💾 Testing Signal Storage:")
            test_signals_path = "./test_signals"
            storage = SignalStorage(storage_type="file", base_path=test_signals_path)
            
            # Prepare metadata
            metadata = {
                "gain_pct": candidate.gain_pct,
                "volume": candidate.volume,
                "avg_volume": candidate.avg_volume,
                "volume_ratio": candidate.volume / candidate.avg_volume,
                "vwap": vwap,
                "ema_20": ema,
                "prev_high": prev_high,
                "breakout_amount": current_price - prev_high
            }
            
            # Save signal
            await storage.save_signal(signal, "vwap_ema_breakout", metadata)
            
            # Check if file was created
            date_str = signal.timestamp.strftime("%Y-%m-%d")
            signal_file = Path(test_signals_path) / date_str / "vwap_ema_breakout_signals.json"
            
            if signal_file.exists():
                print(f"   ✅ Signal file created: {signal_file}")
                
                # Read and verify
                with open(signal_file, 'r') as f:
                    saved_signals = json.load(f)
                
                print(f"   ✅ Signals saved: {len(saved_signals)}")
                
                # Display saved signal
                if saved_signals:
                    saved = saved_signals[-1]
                    print(f"\n   📄 Saved Signal Details:")
                    print(f"      Symbol: {saved['symbol']}")
                    print(f"      Price: ₹{saved['price']:.2f}")
                    print(f"      Stop Loss: ₹{saved['stop_loss']:.2f}")
                    print(f"      Target: ₹{saved['target']:.2f}")
                    print(f"      Quantity: {saved['quantity']}")
                    print(f"      Metadata: {json.dumps(saved['metadata'], indent=8)}")
                
                print(f"\n   💡 Signal file saved at: {signal_file.absolute()}")
                print(f"      (File kept for inspection - delete test_signals/ manually when done)")
            else:
                print(f"   ❌ Signal file NOT created: {signal_file}")
        else:
            print(f"   ❌ No entry signal (outside trading hours?)")
    else:
        print(f"   ⚠️  Skipped (filters failed)")
    
    print(f"\n" + "=" * 70)
    print("✅ VWAP EMA BREAKOUT STRATEGY TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_vwap_ema_breakout_strategy())
