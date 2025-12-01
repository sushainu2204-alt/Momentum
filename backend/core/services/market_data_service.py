"""
Market Data Service
Handles historical data fetching with caching.
"""
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from backend.config import settings
from backend.core.services.kite_service import KiteService
from backend.infrastructure.cache import ICache


class MarketDataService:
    """
    Service for fetching and caching market data.
    Implements Repository pattern for data access.
    """
    
    def __init__(self, kite_service: KiteService = None, cache: ICache = None):
        self.kite_service = kite_service or KiteService()
        
        # Dependency injection - use provided cache or default to Redis
        if cache is None:
            from backend.infrastructure.cache import RedisCache
            cache = RedisCache(settings.REDIS_URL)
        
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
            instrument_token: Instrument token
            from_date: Start date
            to_date: End date
            interval: Candle interval
            use_cache: Whether to use cache
            
        Returns:
            DataFrame with OHLC data
        """
        cache_key = f"historical:{instrument_token}:{from_date.date()}:{to_date.date()}:{interval}"
        
        # Try cache first
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                print(f"✓ Cache hit for {cache_key}")
                data = json.loads(cached)
                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'])
                return df
        
        # Fetch from API
        print(f"Fetching historical data from Kite API...")
        records = self.kite_service.get_historical_data(
            instrument_token=instrument_token,
            from_date=from_date.strftime("%Y-%m-%d"),
            to_date=to_date.strftime("%Y-%m-%d"),
            interval=interval
        )
        
        if not records:
            print(f"⚠ No data returned for instrument {instrument_token}")
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
            print(f"✓ Cached {len(df)} records")
        
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
            instrument_token: Instrument token
            days: Number of days to fetch
            interval: Candle interval
            use_cache: Whether to use cache
            
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
    
    def clear_cache(self, pattern: str = "historical:*"):
        """Clear cached historical data"""
        keys = self.cache.keys(pattern)
        if keys:
            for key in keys:
                self.cache.delete(key)
            print(f"✓ Cleared {len(keys)} cache entries")
