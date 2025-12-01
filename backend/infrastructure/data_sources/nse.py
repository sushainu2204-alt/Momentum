"""
NSE Data Source

Fetches top gainers/losers from NSE India API.
"""

from typing import List, Dict, Optional
from datetime import datetime
import requests
from dataclasses import dataclass


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
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class NSEDataSource:
    """
    NSE India API data source for top gainers/losers.
    
    Usage:
        nse = NSEDataSource()
        gainers = nse.get_top_gainers()
    """
    
    BASE_URL = "https://www.nseindia.com"
    
    def __init__(self):
        self.session = requests.Session()
        # NSE requires these headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.nseindia.com/'
        })
        
    def _init_session(self):
        """Initialize session by visiting homepage to get cookies"""
        try:
            self.session.get(self.BASE_URL, timeout=10)
        except Exception as e:
            print(f"⚠️  Warning: Could not initialize NSE session: {e}")
    
    def get_top_gainers(self, limit: Optional[int] = None, category: str = "allSec") -> List[NSETopGainer]:
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
            # Initialize session if needed
            self._init_session()
            
            # Fetch top gainers
            url = f"{self.BASE_URL}/api/live-analysis-variations?index=gainers"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            gainers = []
            
            # NSE API returns nested structure with different categories
            # Print all available categories
            print(f"📋 Available categories: {list(data.keys())}")
            for cat in data.keys():
                if cat != 'legends' and isinstance(data.get(cat), dict):
                    cat_data = data.get(cat, {}).get('data', [])
                    print(f"   {cat}: {len(cat_data)} stocks")
            
            if category not in data:
                print(f"⚠️  Category '{category}' not found in NSE response.")
                return []
            
            # Get data for specified category
            category_data = data.get(category, {})
            stocks = category_data.get('data', [])
            
            print(f"📊 Found {len(stocks)} stocks in '{category}' category")
            
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
                    print(f"⚠️  Error parsing stock data: {e}")
                    continue
            
            print(f"✓ Fetched {len(gainers)} top gainers from NSE ({category})")
            
            # Print all gainers
            print(f"\n📊 All {len(gainers)} gainers:")
            for i, gainer in enumerate(gainers, 1):
                print(f"{i:2}. {gainer.symbol:15} {gainer.last_price:10.2f} {gainer.pct_change:8.2f}% {gainer.volume:15,}")
            
            # Apply limit if specified
            if limit:
                gainers = gainers[:limit]
            
            return gainers
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching NSE top gainers: {e}")
            print(f"❌ Response status: {response.status_code if 'response' in locals() else 'N/A'}")
            if 'response' in locals():
                print(f"❌ Response text: {response.text[:500]}")
            return []
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_top_losers(self, limit: Optional[int] = None) -> List[NSETopGainer]:
        """
        Get top losers from NSE.
        
        Args:
            limit: Optional limit on number of losers to return
        
        Returns:
            List of NSETopGainer objects (with negative changes)
        """
        try:
            # Initialize session if needed
            self._init_session()
            
            # Fetch top losers
            url = f"{self.BASE_URL}/api/live-analysis-variations?index=loosers"  # Note: NSE API uses "loosers"
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
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
                        print(f"⚠️  Error parsing stock data: {e}")
                        continue
            
            # Apply limit if specified
            if limit:
                losers = losers[:limit]
            
            print(f"✓ Fetched {len(losers)} top losers from NSE")
            
            return losers
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching NSE top losers: {e}")
            return []
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
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
