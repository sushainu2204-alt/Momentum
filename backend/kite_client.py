# backend/kite_client.py
import os
import time
import json
from kiteconnect import KiteConnect, KiteTicker
import redis.asyncio as aioredis
import asyncio

class KiteClient:
    def __init__(self, api_key, api_secret, redirect_url, redis_url="redis://localhost:6379/0"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.redirect_url = redirect_url
        self.kite = KiteConnect(api_key=api_key)
        self.redis_url = redis_url
        self.redis = None

    def get_login_url(self):
        # returns login url to redirect user to
        return self.kite.login_url()

    def generate_session(self, request_token):
        # exchange the request token + api secret for the access token
        data = self.kite.generate_session(request_token, api_secret=self.api_secret)
        # data contains access_token, public_token, user_id etc.
        return data

    def start_ticker(self, access_token, user_id, instrument_tokens=None):
        """
        Starts a blocking KiteTicker client that publishes ticks to Redis.
        Runs in the calling thread — recommended to run in background thread/process.
        """
        if instrument_tokens is None:
            # Demo tokens: NIFTY 50 index, RELIANCE, TCS
            # You can find more tokens at: https://api.kite.trade/instruments
            instrument_tokens = [256265]  # NIFTY 50 index - always has data during market hours

        print(f"Will subscribe to instruments: {instrument_tokens}")
        print(f"API Key: {self.api_key}")
        print(f"Access Token: {access_token[:20]}...{access_token[-10:] if len(access_token) > 30 else ''}")
        
        # create non-async redis client for sync context
        import redis
        redis_sync = redis.Redis.from_url(self.redis_url)
        print(f"Redis client connected to: {self.redis_url}")

        # Small delay to ensure token is propagated
        time.sleep(1)
        
        kws = {
            "api_key": self.api_key,
            "access_token": access_token
        }
        print(f"Creating KiteTicker with credentials...")
        kite_ticker = KiteTicker(**kws)

        def on_connect(ws, response):
            print(f"✓ Ticker WebSocket connected successfully!")
            print(f"  Response: {response}")
            if instrument_tokens:
                print(f"  Subscribing to {len(instrument_tokens)} instruments: {instrument_tokens}")
                kite_ticker.subscribe(instrument_tokens)
                # set mode (full, ltp, quote) — choose ltp for minimal payload
                kite_ticker.set_mode(kite_ticker.MODE_LTP, instrument_tokens)
                print(f"  ✓ Subscribed to instruments in LTP mode")
            else:
                print("  ⚠ No instruments to subscribe to")

        def on_ticks(ws, ticks):
            # ticks is a list of tick dicts for instruments
            # publish each tick to redis channel ticks:<instrument_token>
            print(f"📊 Received {len(ticks)} tick(s)")
            for t in ticks:
                token = str(t.get("instrument_token"))
                ch = f"ticks:{token}"
                try:
                    redis_sync.publish(ch, json.dumps(t))
                    print(f"  ✓ Published to {ch}: LTP={t.get('last_price', t.get('ltp', 'N/A'))}")
                except Exception as e:
                    print(f"  ✗ Redis publish error: {e}")

        def on_close(ws, code, reason):
            print("Ticker closed", code, reason)

        def on_error(ws, code, reason):
            print(f"Ticker error: {code} - {reason}")
            if code == 403:
                print("❌ 403 Forbidden - Access token might be invalid or expired")
                print("   Check that:")
                print("   1. API key and secret are correct")
                print("   2. The app is properly configured on Kite Connect dashboard")
                print("   3. You completed a fresh login (tokens expire daily)")

        kite_ticker.on_connect = on_connect
        kite_ticker.on_ticks = on_ticks
        kite_ticker.on_close = on_close
        kite_ticker.on_error = on_error
        
        # Disable auto-reconnect for now to avoid spam
        kite_ticker.reconnect_max_tries = 3
        kite_ticker.reconnect_max_delay = 10

        try:
            print(f"Starting KiteTicker for user {user_id}...")
            print(f"Connecting to WebSocket...")
            # Use threaded=True to avoid Twisted signal handler issues in background thread
            kite_ticker.connect(threaded=True)
        except Exception as e:
            print(f"Ticker failed: {e}")
            import traceback
            traceback.print_exc()
