"""
Kite Connect API Service
Handles authentication, WebSocket streaming, and API calls.
"""
import json
from kiteconnect import KiteConnect, KiteTicker
from typing import List, Optional, Callable
from backend.config import settings
from backend.core.models import Tick
from backend.infrastructure.messaging import IMessageBrokerSync


class KiteService:
    """
    Service for Kite Connect API interactions.
    Implements Facade pattern to simplify Kite API usage.
    """
    
    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or settings.KITE_API_KEY
        self.api_secret = api_secret or settings.KITE_API_SECRET
        self.kite = KiteConnect(api_key=self.api_key)
        self.ticker: Optional[KiteTicker] = None
        
        # Set access token if available
        if settings.KITE_ACCESS_TOKEN:
            self.kite.set_access_token(settings.KITE_ACCESS_TOKEN)
    
    def get_login_url(self) -> str:
        """Get Zerodha login URL for OAuth flow"""
        return self.kite.login_url()
    
    def generate_session(self, request_token: str) -> dict:
        """
        Exchange request token for access token.
        
        Args:
            request_token: Token from OAuth callback
            
        Returns:
            Session data with access_token, user_id, etc.
        """
        session_data = self.kite.generate_session(
            request_token=request_token,
            api_secret=self.api_secret
        )
        
        # Update settings and .env
        settings.update_access_token(session_data["access_token"])
        
        # Set on current instance
        self.kite.set_access_token(session_data["access_token"])
        
        return session_data
    
    def set_access_token(self, token: str):
        """Set access token for API calls"""
        self.kite.set_access_token(token)
        settings.update_access_token(token)
    
    def margins(self):
        """Get margins from Kite API"""
        return self.kite.margins()
    
    def get_historical_data(
        self,
        instrument_token: int,
        from_date: str,
        to_date: str,
        interval: str = "5minute"
    ) -> List[dict]:
        """
        Fetch historical OHLC data.
        
        Args:
            instrument_token: Instrument token
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            interval: Candle interval (minute, 5minute, day, etc.)
            
        Returns:
            List of OHLC records
        """
        return self.kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
    
    def start_ticker(
        self,
        instruments: List[int],
        on_tick_callback: Callable[[List[Tick]], None],
        message_broker: IMessageBrokerSync = None
    ):
        """
        Start WebSocket ticker for live market data.
        
        Args:
            instruments: List of instrument tokens to subscribe
            on_tick_callback: Callback function for processing ticks
            message_broker: Message broker for publishing ticks (injected dependency)
        """
        access_token = settings.KITE_ACCESS_TOKEN
        if not access_token:
            raise ValueError("Access token not set. Authenticate first.")
        
        if message_broker is None:
            from backend.infrastructure.messaging import RedisMessageBrokerSync
            message_broker = RedisMessageBrokerSync(settings.REDIS_URL)
        
        # Create ticker instance
        self.ticker = KiteTicker(self.api_key, access_token)
        
        def on_connect(ws, response):
            """Subscribe to instruments on connection"""
            print(f"✓ WebSocket connected. Subscribing to {len(instruments)} instruments...")
            ws.subscribe(instruments)
            ws.set_mode(ws.MODE_LTP, instruments)
        
        def on_ticks(ws, ticks):
            """Handle incoming ticks"""
            if not ticks:
                return
            
            # Convert to Tick objects
            tick_objects = [Tick.from_kite_tick(t) for t in ticks]
            
            # Publish to message broker
            for tick_obj in tick_objects:
                channel = f"ticks:{tick_obj.instrument_token}"
                payload = {
                    "instrument_token": tick_obj.instrument_token,
                    "last_price": tick_obj.last_price,
                    "ltp": tick_obj.last_price,
                }
                message_broker.publish(channel, json.dumps(payload))
            
            # Call custom callback
            on_tick_callback(tick_objects)
        
        def on_error(ws, code, reason):
            """Handle errors"""
            print(f"⚠ WebSocket error [{code}]: {reason}")
        
        def on_close(ws, code, reason):
            """Handle close"""
            print(f"✗ WebSocket closed [{code}]: {reason}")
        
        # Assign callbacks
        self.ticker.on_connect = on_connect
        self.ticker.on_ticks = on_ticks
        self.ticker.on_error = on_error
        self.ticker.on_close = on_close
        
        # Connect in background thread
        self.ticker.connect(threaded=True)
        
        print(f"📡 Ticker started for {len(instruments)} instruments")
    
    def stop_ticker(self):
        """Stop WebSocket ticker"""
        if self.ticker:
            self.ticker.close()
            print("✗ Ticker stopped")
