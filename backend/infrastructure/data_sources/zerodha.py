"""
Zerodha Data Source Implementation

Implements IDataSource using Kite Connect API.
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
import pandas as pd
from kiteconnect import KiteConnect

from .base import IDataSource, Quote, Instrument
from backend.core.utils.retry import retry_sync, KITE_API_ERRORS


class ZerodhaDataSource(IDataSource):
    """
    Kite Connect API implementation of IDataSource.
    
    Usage:
        kite = KiteConnect(api_key=settings.KITE_API_KEY)
        kite.set_access_token(settings.KITE_ACCESS_TOKEN)
        data_source = ZerodhaDataSource(kite)
    """
    
    def __init__(self, kite: KiteConnect):
        self.kite = kite
        self._instruments_cache: Optional[List[Instrument]] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(hours=24)
    
    def get_quote(self, instrument_token: int) -> Quote:
        """Get real-time quote for single instrument"""
        quotes = self.get_quotes([instrument_token])
        return quotes[instrument_token]
    
    def get_quotes(self, instrument_tokens: List[int]) -> Dict[int, Quote]:
        """
        Get real-time quotes for multiple instruments.
        
        Returns:
            Dict mapping instrument_token -> Quote
        """
        # Kite quote API accepts instrument tokens directly in format: "NSE:256265"
        # Build proper identifiers
        identifiers = []
        for token in instrument_tokens:
            # Try to find instrument to get proper exchange
            instruments = self.get_instruments()
            matching = [i for i in instruments if i.instrument_token == token]
            
            if matching:
                inst = matching[0]
                identifiers.append(f"{inst.exchange}:{inst.tradingsymbol}")
            else:
                # Default to NSE
                identifiers.append(f"NSE:{token}")
        
        # Fetch quotes from Kite with retry
        raw_quotes = retry_sync(
            lambda: self.kite.quote(identifiers),
            retryable_exceptions=KITE_API_ERRORS,
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0
        )
        
        quotes = {}
        for key, data in raw_quotes.items():
            instrument_token = data['instrument_token']
            
            # Calculate % change
            ohlc = data.get('ohlc', {})
            open_price = ohlc.get('open', 0)
            last_price = data.get('last_price', 0)
            
            if open_price > 0:
                change_pct = ((last_price - open_price) / open_price) * 100
            else:
                change_pct = 0.0
            
            quote = Quote(
                instrument_token=instrument_token,
                symbol=data.get('tradingsymbol', ''),
                last_price=last_price,
                volume=data.get('volume', 0),
                change_pct=change_pct,
                timestamp=data.get('timestamp', datetime.now()),
                open_price=open_price,
                high_price=ohlc.get('high'),
                low_price=ohlc.get('low'),
                close_price=ohlc.get('close')
            )
            
            quotes[instrument_token] = quote
        
        return quotes
    
    def get_historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str
    ) -> pd.DataFrame:
        """
        Get historical OHLCV data from Kite.
        
        Args:
            instrument_token: Instrument token
            from_date: Start date
            to_date: End date
            interval: Kite interval string (5minute, 15minute, day, etc.)
        
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        # Wrap with retry for rate limiting
        data = retry_sync(
            lambda: self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval
            ),
            retryable_exceptions=KITE_API_ERRORS,
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0
        )
        
        df = pd.DataFrame(data)
        
        if not df.empty:
            df = df.rename(columns={'datetime': 'date'})
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
        
        return df
    
    def get_instruments(self, exchange: Optional[str] = None) -> List[Instrument]:
        """
        Get all instruments with caching.
        
        Args:
            exchange: Filter by exchange (NSE, BSE, NFO, etc.)
        
        Returns:
            List of instruments
        """
        # Check cache
        if self._instruments_cache and self._cache_time:
            if datetime.now() - self._cache_time < self._cache_ttl:
                instruments = self._instruments_cache
                if exchange:
                    instruments = [i for i in instruments if i.exchange == exchange]
                return instruments
        
        # Fetch from API with retry
        raw_instruments = retry_sync(
            lambda: self.kite.instruments(exchange=exchange),
            retryable_exceptions=KITE_API_ERRORS,
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0
        )
        
        instruments = []
        for data in raw_instruments:
            instrument = Instrument(
                instrument_token=data['instrument_token'],
                exchange_token=data['exchange_token'],
                tradingsymbol=data['tradingsymbol'],
                name=data.get('name', data['tradingsymbol']),
                exchange=data['exchange'],
                segment=data['segment'],
                instrument_type=data['instrument_type'],
                lot_size=data.get('lot_size', 1)
            )
            instruments.append(instrument)
        
        # Update cache
        if not exchange:  # Only cache full list
            self._instruments_cache = instruments
            self._cache_time = datetime.now()
        
        return instruments
    
    def search_instruments(self, query: str) -> List[Instrument]:
        """
        Search instruments by symbol or name.
        
        Args:
            query: Search query (symbol or name)
        
        Returns:
            Matching instruments
        """
        all_instruments = self.get_instruments()
        
        query_lower = query.lower()
        matches = [
            inst for inst in all_instruments
            if query_lower in inst.tradingsymbol.lower() 
            or query_lower in inst.name.lower()
        ]
        
        return matches
