"""
NSE Data Source

Fetches top gainers/losers from NSE India API.
Uses aiohttp for async HTTP calls to avoid blocking the event loop.
Implements async context manager for proper resource cleanup.
"""

from typing import List, Dict, Optional
from datetime import datetime
import aiohttp
import logging
from dataclasses import dataclass

from backend.core.utils.retry import retry_async, AIOHTTP_ERRORS

logger = logging.getLogger(__name__)


@dataclass
class NSETopGainer:
    """NSE Top Gainer data"""
    symbol: str
    open_price: float
    high_price: float
    low_price: float
    last_price: float
    previous_close: float
    change: float
    pct_change: float
    volume: int
    total_traded_value: float
    year_high: float
    year_low: float
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class NSEDataSource:
    """
    NSE India API data source for top gainers/losers.
    
    Implements async context manager for proper resource cleanup.
    
    Usage:
        # Using context manager (recommended)
        async with NSEDataSource() as nse:
            gainers = await nse.get_top_gainers()
        
        # Manual management
        nse = NSEDataSource()
        try:
            gainers = await nse.get_top_gainers()
        finally:
            await nse.close()
    """
    
    BASE_URL = "https://www.nseindia.com"
    
    # NSE requires these headers
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.nseindia.com/'
    }
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._cookies_initialized = False
    
    async def __aenter__(self) -> "NSEDataSource":
        """Enter async context manager."""
        await self._get_session()  # Ensure session is created
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager and cleanup resources."""
        await self.close()
        return None  # Don't suppress exceptions
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(
                headers=self.HEADERS,
                timeout=timeout
            )
        return self._session
    
    async def _init_cookies(self) -> None:
        """Initialize session by visiting homepage to get cookies."""
        if self._cookies_initialized:
            return
        
        try:
            session = await self._get_session()
            async with session.get(self.BASE_URL) as response:
                await response.read()  # Read response to complete request
                self._cookies_initialized = True
                logger.debug("NSE session cookies initialized")
        except Exception as e:
            logger.warning(f"Could not initialize NSE session: {e}")
    
    async def close(self) -> None:
        """Close the aiohttp session and cleanup resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self._cookies_initialized = False
            logger.debug("NSEDataSource session closed")
    
    async def _fetch_gainers_data(self, url: str) -> dict:
        """Internal method to fetch gainers data with retry support"""
        session = await self._get_session()
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()
    
    async def get_top_gainers(self, limit: Optional[int] = None, category: str = "allSec") -> List[NSETopGainer]:
        """
        Get top gainers from NSE.
        
        Args:
            limit: Optional limit on number of gainers to return
            category: Category to fetch - 'allSec' (All Securities - DEFAULT), 'FOSec' (F&O Securities), 
                     'NIFTY', 'BANKNIFTY', 'NIFTYNEXT50', 'SecGtr20' (Securities > Rs 20), 
                     'SecLwr20' (Securities < Rs 20)
        
        Returns:
            List of NSETopGainer objects
        """
        try:
            # Initialize session and cookies
            await self._init_cookies()
            
            # Fetch top gainers with retry
            url = f"{self.BASE_URL}/api/live-analysis-variations?index=gainers"
            data = await retry_async(
                self._fetch_gainers_data,
                url,
                max_retries=3,
                base_delay=1.0,
                retryable_exceptions=AIOHTTP_ERRORS
            )
            
            gainers = []
            
            # NSE API returns nested structure with different categories
            logger.debug(f"Available categories: {list(data.keys())}")
            for cat in data.keys():
                if cat != 'legends' and isinstance(data.get(cat), dict):
                    cat_data = data.get(cat, {}).get('data', [])
                    logger.debug(f"   {cat}: {len(cat_data)} stocks")
            
            if category not in data:
                logger.warning(f"Category '{category}' not found in NSE response.")
                return []
            
            # Get data for specified category
            category_data = data.get(category, {})
            stocks = category_data.get('data', [])
            
            logger.info(f"Found {len(stocks)} stocks in '{category}' category")
            
            # Parse each stock
            for stock in stocks:
                try:
                    gainer = NSETopGainer(
                        symbol=stock.get('symbol', ''),
                        open_price=float(stock.get('open_price', 0)),
                        high_price=float(stock.get('high_price', 0)),
                        low_price=float(stock.get('low_price', 0)),
                        last_price=float(stock.get('ltp', 0)),
                        previous_close=float(stock.get('prev_price', 0)),
                        change=float(stock.get('net_price', 0)),
                        pct_change=float(stock.get('perChange', 0)),
                        volume=int(stock.get('trade_quantity', 0)),
                        total_traded_value=float(stock.get('turnover', 0)),
                        year_high=0.0,  # Not available in this API response
                        year_low=0.0    # Not available in this API response
                    )
                    gainers.append(gainer)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing stock data: {e}")
                    continue
            
            logger.info(f"Fetched {len(gainers)} top gainers from NSE ({category})")
            
            # Log gainers at debug level
            for i, gainer in enumerate(gainers, 1):
                logger.debug(f"{i:2}. {gainer.symbol:15} {gainer.last_price:10.2f} {gainer.pct_change:8.2f}% {gainer.volume:15,}")
            
            # Apply limit if specified
            if limit:
                gainers = gainers[:limit]
            
            return gainers
            
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching NSE top gainers: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching top gainers: {e}", exc_info=True)
            return []
    
    async def get_top_losers(self, limit: Optional[int] = None) -> List[NSETopGainer]:
        """
        Get top losers from NSE.
        
        Args:
            limit: Optional limit on number of losers to return
        
        Returns:
            List of NSETopGainer objects (with negative changes)
        """
        try:
            # Initialize session and cookies
            await self._init_cookies()
            session = await self._get_session()
            
            # Fetch top losers
            url = f"{self.BASE_URL}/api/live-analysis-variations?index=loosers"  # Note: NSE API uses "loosers"
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
            
            losers = []
            
            if 'data' in data:
                stocks = data['data']
                
                for stock in stocks:
                    try:
                        loser = NSETopGainer(
                            symbol=stock.get('symbol', ''),
                            open_price=float(stock.get('open', 0)),
                            high_price=float(stock.get('dayHigh', 0)),
                            low_price=float(stock.get('dayLow', 0)),
                            last_price=float(stock.get('lastPrice', 0)),
                            previous_close=float(stock.get('previousClose', 0)),
                            change=float(stock.get('change', 0)),
                            pct_change=float(stock.get('pChange', 0)),
                            volume=int(stock.get('totalTradedVolume', 0)),
                            total_traded_value=float(stock.get('totalTradedValue', 0)),
                            year_high=float(stock.get('yearHigh', 0)),
                            year_low=float(stock.get('yearLow', 0))
                        )
                        losers.append(loser)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error parsing stock data: {e}")
                        continue
            
            # Apply limit if specified
            if limit:
                losers = losers[:limit]
            
            logger.info(f"Fetched {len(losers)} top losers from NSE")
            
            return losers
            
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching NSE top losers: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching top losers: {e}", exc_info=True)
            return []
    
    def map_to_candidate(self, gainer: NSETopGainer, instrument_token: int = 0) -> Dict:
        """
        Map NSETopGainer to Candidate-compatible dict.
        
        Args:
            gainer: NSE top gainer object
            instrument_token: Optional instrument token from Kite
        
        Returns:
            Dict with candidate fields
        """
        return {
            'symbol': gainer.symbol,
            'instrument_token': instrument_token,
            'current_price': gainer.last_price,
            'gain_pct': gainer.pct_change,
            'volume': gainer.volume,
            'avg_volume': gainer.volume,  # Will be enriched later
            'timestamp': gainer.timestamp,
            'open_price': gainer.open_price,
            'high_price': gainer.high_price,
            'low_price': gainer.low_price
        }
