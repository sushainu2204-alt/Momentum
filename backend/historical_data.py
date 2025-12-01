# backend/historical_data.py
"""
Fetch and cache historical OHLC data from Kite API
"""
import os
from datetime import datetime, timedelta
from typing import List, Optional
import pandas as pd
from kiteconnect import KiteConnect
import redis
import json
from dotenv import load_dotenv

load_dotenv()

class HistoricalDataFetcher:
    def __init__(self, api_key: str, access_token: str, redis_url: str = "redis://localhost:6379/0"):
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)
        self.redis_client = redis.Redis.from_url(redis_url)
        
    def fetch_historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str = "minute",
        continuous: bool = False,
        oi: bool = False
    ) -> pd.DataFrame:
        """
        Fetch historical OHLC data from Kite API.
        
        Args:
            instrument_token: Instrument token (e.g., 256265 for NIFTY 50)
            from_date: Start date
            to_date: End date
            interval: Candle interval - "minute", "day", "3minute", "5minute", "10minute", 
                     "15minute", "30minute", "60minute"
            continuous: Get continuous data (for futures)
            oi: Include Open Interest data
            
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        cache_key = f"historical:{instrument_token}:{interval}:{from_date.date()}:{to_date.date()}"
        
        # Check cache first
        cached = self.redis_client.get(cache_key)
        if cached:
            print(f"✓ Using cached data for {instrument_token}")
            df = pd.read_json(cached)
            df['date'] = pd.to_datetime(df['date'])
            return df
        
        print(f"Fetching historical data for {instrument_token} from Kite API...")
        
        try:
            # Fetch from Kite API
            records = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval,
                continuous=continuous,
                oi=oi
            )
            
            if not records:
                print(f"⚠ No data returned for {instrument_token}")
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(records)
            
            # Cache for 24 hours
            self.redis_client.setex(
                cache_key,
                86400,  # 24 hours
                df.to_json(date_format='iso')
            )
            
            print(f"✓ Fetched {len(df)} candles for {instrument_token}")
            return df
            
        except Exception as e:
            print(f"Error fetching historical data: {e}")
            return pd.DataFrame()
    
    def fetch_intraday_data(
        self,
        instrument_token: int,
        interval: str = "5minute",
        days_back: int = 7
    ) -> pd.DataFrame:
        """
        Convenience method to fetch recent intraday data.
        
        Args:
            instrument_token: Instrument token
            interval: Candle interval (minute, 3minute, 5minute, etc.)
            days_back: Number of days to fetch
            
        Returns:
            DataFrame with OHLC data
        """
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days_back)
        
        return self.fetch_historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
    
    def get_instrument_info(self, instrument_token: int) -> dict:
        """Get instrument details from Kite API."""
        try:
            instruments = self.kite.instruments()
            for inst in instruments:
                if inst['instrument_token'] == instrument_token:
                    return inst
            return {}
        except Exception as e:
            print(f"Error fetching instrument info: {e}")
            return {}


if __name__ == "__main__":
    # Demo usage
    API_KEY = os.environ.get("KITE_API_KEY")
    ACCESS_TOKEN = os.environ.get("KITE_ACCESS_TOKEN")  # You need to set this after auth
    
    if not ACCESS_TOKEN:
        print("⚠ Set KITE_ACCESS_TOKEN in .env file after authenticating")
        print("  Run: export KITE_ACCESS_TOKEN='your_token_here'")
        exit(1)
    
    fetcher = HistoricalDataFetcher(API_KEY, ACCESS_TOKEN)
    
    # Fetch last 7 days of 5-minute candles for NIFTY 50
    df = fetcher.fetch_intraday_data(
        instrument_token=256265,  # NIFTY 50
        interval="5minute",
        days_back=7
    )
    
    print("\nSample data:")
    print(df.head(10))
    print(f"\nTotal candles: {len(df)}")
