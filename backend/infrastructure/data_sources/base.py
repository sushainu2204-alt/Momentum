"""
Data Source Abstractions

Pluggable data source interfaces for market data.
Allows switching between Zerodha, NSE API, Yahoo Finance, etc.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime
import pandas as pd
from dataclasses import dataclass


@dataclass
class Quote:
    """Real-time quote data"""
    instrument_token: int
    symbol: str
    last_price: float
    volume: int
    change_pct: float
    timestamp: datetime
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None


@dataclass
class Instrument:
    """Instrument metadata"""
    instrument_token: int
    exchange_token: int
    tradingsymbol: str
    name: str
    exchange: str
    segment: str
    instrument_type: str
    lot_size: int


class IDataSource(ABC):
    """
    Interface for market data providers.
    
    Implementations:
    - ZerodhaDataSource: Kite Connect API
    - NSEDataSource: NSE official API
    - YahooFinanceDataSource: Yahoo Finance API
    """
    
    @abstractmethod
    def get_quote(self, instrument_token: int) -> Quote:
        """Get real-time quote for a single instrument"""
        pass
    
    @abstractmethod
    def get_quotes(self, instrument_tokens: List[int]) -> Dict[int, Quote]:
        """Get real-time quotes for multiple instruments"""
        pass
    
    @abstractmethod
    def get_historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str
    ) -> pd.DataFrame:
        """
        Get historical OHLCV data
        
        Args:
            instrument_token: Instrument identifier
            from_date: Start date
            to_date: End date
            interval: Candle interval (5minute, 15minute, day, etc.)
        
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        pass
    
    @abstractmethod
    def get_instruments(self, exchange: Optional[str] = None) -> List[Instrument]:
        """Get list of all tradable instruments"""
        pass
    
    @abstractmethod
    def search_instruments(self, query: str) -> List[Instrument]:
        """Search instruments by name or symbol"""
        pass


class IStockUniverse(ABC):
    """
    Interface for stock universe definition.
    
    Implementations:
    - FnOUniverse: F&O stocks (~200 stocks)
    - Nifty500Universe: Nifty 500 index constituents
    - Nifty200Universe: Nifty 200 index constituents
    - CustomUniverse: User-defined list
    """
    
    @abstractmethod
    def get_instruments(self, data_source: IDataSource) -> List[Instrument]:
        """
        Get list of instruments in this universe
        
        Args:
            data_source: Data source to fetch instrument metadata
        
        Returns:
            List of instruments in this universe
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Get universe name for logging"""
        pass


class IStockScreener(ABC):
    """
    Interface for stock screening logic.
    
    Separates screening logic from data fetching.
    """
    
    @abstractmethod
    def screen(
        self,
        universe: List[Instrument],
        data_source: IDataSource,
        **criteria
    ) -> List[Quote]:
        """
        Screen stocks based on criteria
        
        Args:
            universe: List of instruments to screen
            data_source: Data source for fetching quotes
            **criteria: Screening criteria (e.g., min_gain=2.0, max_gain=3.0)
        
        Returns:
            List of quotes that passed screening
        """
        pass
