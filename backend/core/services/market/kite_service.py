"""
Kite Connect API Service
Handles authentication and API calls.
"""
import logging
from kiteconnect import KiteConnect
from typing import List, Optional

from backend.config import settings

logger = logging.getLogger(__name__)


class KiteService:
    """
    Service for Kite Connect API interactions.
    Implements Facade pattern to simplify Kite API usage.
    
    Usage:
        # Initialize with default settings
        kite = KiteService()
        
        # Or with custom credentials
        kite = KiteService(api_key="your_key", api_secret="your_secret")
        
        # Get historical data
        data = kite.get_historical_data(
            instrument_token=738561,
            from_date="2024-01-01",
            to_date="2024-01-31"
        )
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ):
        """
        Initialize KiteService.
        
        Args:
            api_key: Kite Connect API key (default: from settings)
            api_secret: Kite Connect API secret (default: from settings)
        """
        self.api_key = api_key or settings.KITE_API_KEY
        self.api_secret = api_secret or settings.KITE_API_SECRET
        self.kite = KiteConnect(api_key=self.api_key)
        
        # Set access token if available
        if settings.KITE_ACCESS_TOKEN:
            self.kite.set_access_token(settings.KITE_ACCESS_TOKEN)
            logger.debug("KiteService initialized with existing access token")
    
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
        
        logger.info(f"Session generated for user: {session_data.get('user_id')}")
        
        return session_data
    
    def set_access_token(self, token: str) -> None:
        """Set access token for API calls"""
        self.kite.set_access_token(token)
        settings.update_access_token(token)
        logger.debug("Access token updated")
    
    def margins(self) -> dict:
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
            instrument_token: Kite instrument token
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            interval: Candle interval (minute, 5minute, 15minute, day, etc.)
            
        Returns:
            List of OHLC records with keys: date, open, high, low, close, volume
        """
        return self.kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
