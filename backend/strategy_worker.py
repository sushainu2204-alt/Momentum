# backend/strategy_worker.py
"""
Simple strategy worker:
- Subscribes to redis channel patterns "ticks:*"
- Aggregates recent last-price into a small buffer
- Computes EMA9 and EMA21 using pandas and issues signals when EMA9 crosses EMA21
- Publishes signals to redis channel "signals"
"""

import asyncio
import os
import json
import pandas as pd
import redis.asyncio as aioredis
from collections import deque

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
# window size for EMA calculation (keep modest)
MAX_POINTS = 200

class InstrumentBuffer:
    def __init__(self):
        self.prices = deque(maxlen=MAX_POINTS)

    def add_price(self, p):
        self.prices.append(float(p))

    def compute_emas(self):
        if len(self.prices) < 21:
            return None, None
        s = pd.Series(list(self.prices))
        ema9 = float(s.ewm(span=9, adjust=False).mean().iloc[-1])
        ema21 = float(s.ewm(span=21, adjust=False).mean().iloc[-1])
        return ema9, ema21

async def worker():
    print(f"Connecting to Redis at {REDIS_URL}...")
    redis = aioredis.from_url(REDIS_URL)
    pubsub = redis.pubsub()
    # subscribe to wildcard? redis-py does not support patterns with subscribe; use psubscribe
    await pubsub.psubscribe("ticks:*")
    print("✓ Strategy worker subscribed to ticks:*")
    print("  Waiting for market data...")
    buffers = {}  # instrument_token -> InstrumentBuffer
    message_count = 0
    async for message in pubsub.listen():
        message_count += 1
        if message_count % 10 == 1:
            print(f"  📥 Received {message_count} messages from Redis...")
        # message is dict with fields: type, pattern, channel, data
        if message is None:
            continue
        if message.get("type") not in ("pmessage",):
            continue
        data = message.get("data")
        if not data:
            continue
        try:
            tick = json.loads(data)
        except Exception:
            # sometimes data is bytes; try decode
            try:
                tick = json.loads(data.decode())
            except Exception:
                continue
        token = str(tick.get("instrument_token"))
        ltp = None
        # tick payload can differ depending on mode; try typical fields
        if "last_price" in tick:
            ltp = tick["last_price"]
        elif "ltp" in tick:
            ltp = tick["ltp"]
        if ltp is None:
            continue

        if token not in buffers:
            buffers[token] = InstrumentBuffer()
            print(f"  📊 Started tracking instrument {token}")
        buf = buffers[token]
        buf.add_price(ltp)
        
        # Print buffer status every 5 ticks
        if len(buf.prices) % 5 == 0:
            print(f"  Buffer for {token}: {len(buf.prices)} prices, latest={ltp}")
        
        emas = buf.compute_emas()
        if emas is None:
            continue
        ema9, ema21 = emas
        # simple crossover logic: check last two points with EMAs to detect cross
        # We'll compute previous ema by running on all but last point
        if len(buf.prices) < 22:
            # Not enough history to compute a previous ema reliably
            continue
        s = pd.Series(list(buf.prices))
        ema9_series = s.ewm(span=9, adjust=False).mean()
        ema21_series = s.ewm(span=21, adjust=False).mean()
        prev_ema9 = float(ema9_series.iloc[-2])
        prev_ema21 = float(ema21_series.iloc[-2])
        curr_ema9 = float(ema9_series.iloc[-1])
        curr_ema21 = float(ema21_series.iloc[-1])

        signal = None
        if prev_ema9 <= prev_ema21 and curr_ema9 > curr_ema21:
            signal = "BUY"
        elif prev_ema9 >= prev_ema21 and curr_ema9 < curr_ema21:
            signal = "SELL"

        if signal:
            payload = {
                "instrument_token": token,
                "signal": signal,
                "ema9": curr_ema9,
                "ema21": curr_ema21,
                "price": ltp,
                "timestamp": pd.Timestamp.utcnow().isoformat(),
            }
            # publish signal
            await redis.publish("signals", json.dumps(payload))
            print("Published signal:", payload)

if __name__ == "__main__":
    asyncio.run(worker())
