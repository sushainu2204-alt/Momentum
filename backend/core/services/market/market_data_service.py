"""
Market Data Service
Handles historical data fetching with caching.
"""
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

from backend.config import settings
from backend.core.services.market.kite_service import KiteService
from backend.infrastructure.cache import ICache

logger = logging.getLogger(__name__)


class MarketDataService:
    """
    Service for fetching and caching market data.
    Implements Repository pattern for data access.
    
    Usage:
        # With dependency injection (preferred)
        kite = KiteService()
        cache = RedisCache(redis_url)
        service = MarketDataService(kite_service=kite, cache=cache)
        
        # With defaults
        service = MarketDataService()
        
        # Fetch historical data
        df = service.fetch_historical_data(
            instrument_token=738561,
            from_date=datetime(2024, 1, 1),
            to_date=datetime.now()
        )
    """
    
    def __init__(
        self,
        kite_service: Optional[KiteService] = None,
        cache: Optional[ICache] = None
    ):
        """
        Initialize MarketDataService.
        
        Args:
            kite_service: KiteService instance for API calls.
                         If None, creates a new KiteService.
            cache: Cache implementation for storing historical data.
                  If None, creates a RedisCache.
        """
        self.kite_service = kite_service or KiteService()
        
        if cache is None:
            from backend.infrastructure.cache import RedisCache
            cache = RedisCache(settings.REDIS_URL)
            logger.debug("Initialized with default RedisCache")
        
        self.cache = cache
        self.cache_ttl = 86400  # 24 hours
    
    def fetch_historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "5minute",
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Fetch historical OHLC data with Redis caching.
        
        Args:
            instrument_token: Kite instrument token
            from_date: Start date for data
            to_date: End date for data
            interval: Candle interval (minute, 5minute, 15minute, day, etc.)
            use_cache: Whether to use cache (default: True)
            
        Returns:
            DataFrame with OHLC data (columns: date, open, high, low, close, volume)
        """
        cache_key = f"historical:{instrument_token}:{from_date.date()}:{to_date.date()}:{interval}"
        
        # Try cache first
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                logger.debug(f"Cache hit for {cache_key}")
                data = json.loads(cached)
                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'])
                return df
        
        # Fetch from API
        logger.debug(f"Fetching historical data from Kite API for token {instrument_token}")
        records = self.kite_service.get_historical_data(
            instrument_token=instrument_token,
            from_date=from_date.strftime("%Y-%m-%d"),
            to_date=to_date.strftime("%Y-%m-%d"),
            interval=interval
        )
        
        if not records:
            logger.warning(f"No data returned for instrument {instrument_token}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(records)
        
        # Cache the data
        if use_cache:
            cache_data = df.copy()
            cache_data['date'] = cache_data['date'].astype(str)
            self.cache.set(
                cache_key,
                json.dumps(cache_data.to_dict(orient='records')),
                ttl=self.cache_ttl
            )
            logger.debug(f"Cached {len(df)} records for token {instrument_token}")
        
        return df
    
    def fetch_intraday_data(
        self,
        instrument_token: int,
        days: int = 30,
        interval: str = "5minute",
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Fetch intraday data for recent days.
        
        Args:
            instrument_token: Kite instrument token
            days: Number of days to fetch (default: 30)
            interval: Candle interval (default: 5minute)
            use_cache: Whether to use cache (default: True)
            
        Returns:
            DataFrame with OHLC data
        """
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)
        
        return self.fetch_historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval,
            use_cache=use_cache
        )
    
    def clear_cache(self, pattern: str = "historical:*") -> int:
        """
        Clear cached historical data.
        
        Args:
            pattern: Key pattern to match (default: historical:*)
            
        Returns:
            Number of cache entries cleared
        """
        keys = self.cache.keys(pattern)
        if keys:
            for key in keys:
                self.cache.delete(key)
            logger.info(f"Cleared {len(keys)} cache entries matching '{pattern}'")
            return len(keys)
        return 0
