"""
Strategy Worker - Live Trading
Subscribes to market ticks and generates signals in real-time.
"""
import asyncio
import pandas as pd
from collections import deque, defaultdict
from backend.config import settings
from backend.core.strategies import EMACrossoverStrategy
from backend.core.services import SignalService
from backend.core.models import Tick
from backend.infrastructure.messaging import IMessageBroker


class StrategyWorker:
    """
    Worker that processes live market ticks and generates trading signals.
    Uses Strategy Pattern for pluggable strategies.
    """
    
    def __init__(
        self,
        strategy: EMACrossoverStrategy = None,
        message_broker: IMessageBroker = None,
        signal_service: SignalService = None,
        buffer_size: int = None
    ):
        self.strategy = strategy or EMACrossoverStrategy(
            fast_period=settings.DEFAULT_FAST_EMA,
            slow_period=settings.DEFAULT_SLOW_EMA
        )
        
        # Dependency injection
        if message_broker is None:
            from backend.infrastructure.messaging import RedisMessageBroker
            message_broker = RedisMessageBroker(settings.REDIS_URL)
        
        self.message_broker = message_broker
        self.buffer_size = buffer_size or settings.DEFAULT_BUFFER_SIZE
        self.signal_service = signal_service or SignalService(message_broker=message_broker)
        
        # Buffers: instrument_token -> deque of prices
        self.buffers = defaultdict(lambda: deque(maxlen=self.buffer_size))
        
        print(f"✓ Strategy Worker initialized")
        print(f"  Strategy: {self.strategy.name}")
        print(f"  Fast EMA: {self.strategy.fast_period}")
        print(f"  Slow EMA: {self.strategy.slow_period}")
        print(f"  Buffer Size: {self.buffer_size}")
    
    async def start(self):
        """Start the worker and subscribe to tick stream"""
        print(f"\n✓ Connecting to message broker...")
        print(f"✓ Subscribed to {settings.TICKS_CHANNEL_PATTERN}")
        print("  Waiting for market data...\n")
        
        message_count = 0
        
        async for message in self.message_broker.subscribe(settings.TICKS_CHANNEL_PATTERN):
            message_count += 1
            
            if message_count % 10 == 1:
                print(f"📥 Received {message_count} messages...")
            
            # Parse tick data
            try:
                tick_data = message.get("data")
                tick = Tick.from_json(tick_data)
            except Exception as e:
                print(f"⚠ Failed to parse tick: {e}")
                continue
            
            # Process tick
            await self._process_tick(tick)
    
    async def _process_tick(self, tick: Tick):
        """Process a single tick and check for signals"""
        token = str(tick.instrument_token)
        price = tick.last_price
        
        # Add to buffer
        buffer = self.buffers[token]
        buffer.append(price)
        
        # Log buffer status periodically
        if len(buffer) % 10 == 0:
            print(f"  Buffer [{token}]: {len(buffer)} prices, latest=₹{price:.2f}")
        
        # Check if we have enough data
        if len(buffer) < self.strategy.min_data_points:
            return
        
        # Calculate indicators
        prices_series = pd.Series(list(buffer))
        fast_ema_series, slow_ema_series = self.strategy.get_indicator_series(prices_series)
        
        if len(fast_ema_series) < 2:
            return
        
        # Current and previous indicators
        curr_fast = float(fast_ema_series.iloc[-1])
        curr_slow = float(slow_ema_series.iloc[-1])
        prev_fast = float(fast_ema_series.iloc[-2])
        prev_slow = float(slow_ema_series.iloc[-2])
        
        # Generate signal
        signal = self.strategy.generate_signal(
            current_indicators=(curr_fast, curr_slow),
            previous_indicators=(prev_fast, prev_slow)
        )
        
        # Publish signal if generated
        if signal:
            await self.signal_service.publish_signal(
                instrument_token=tick.instrument_token,
                signal_type=signal,
                price=price,
                strategy_name=self.strategy.name,
                metadata={
                    "ema_fast": curr_fast,
                    "ema_slow": curr_slow,
                    "fast_period": self.strategy.fast_period,
                    "slow_period": self.strategy.slow_period,
                }
            )


async def main():
    """Main entry point for strategy worker"""
    worker = StrategyWorker()
    try:
        await worker.start()
    except KeyboardInterrupt:
        print("\n✗ Worker stopped by user")
    except Exception as e:
        print(f"\n⚠ Worker error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
