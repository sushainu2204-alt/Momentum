"""
Stock Screener Service

Screens stocks based on configurable criteria.
Follows Dependency Inversion Principle with injected dependencies.
"""

from typing import List
from datetime import datetime, timedelta

from backend.infrastructure.data_sources import (
    IDataSource,
    IStockUniverse,
    Quote,
    Instrument,
    FnOUniverse,
    Nifty500Universe,
    Nifty200Universe,
    CustomUniverse,
    NSEDataSource
)
from backend.core.config import TopGainersMomentumConfig
from backend.models import Candidate


class StockScreenerService:
    """
    Stock screening service with pluggable data sources and universes.
    
    Usage:
        data_source = ZerodhaDataSource(kite)
        universe = FnOUniverse()
        config = TopGainersMomentumConfig()
        
        screener = StockScreenerService(data_source, universe, config)
        candidates = screener.screen_top_gainers()
    """
    
    def __init__(
        self,
        data_source: IDataSource,
        universe: IStockUniverse,
        config: TopGainersMomentumConfig,
        use_nse_api: bool = True
    ):
        """
        Initialize screener with dependencies.
        
        Args:
            data_source: Data source for quotes and historical data
            universe: Stock universe to screen
            config: Strategy configuration
            use_nse_api: Use NSE API for top gainers (faster) vs scanning all stocks
        """
        self.data_source = data_source
        self.universe = universe
        self.config = config
        self.use_nse_api = use_nse_api
        
        # Initialize NSE data source if enabled
        self.nse_source = NSEDataSource() if use_nse_api else None
        
        # Cache instruments
        self._instruments: List[Instrument] = []
        self._instruments_loaded = False
    
    def _load_instruments(self) -> List[Instrument]:
        """Load instruments from universe (cached)"""
        if not self._instruments_loaded:
            print(f"📋 Loading {self.universe.get_name()}...")
            self._instruments = self.universe.get_instruments(self.data_source)
            self._instruments_loaded = True
            print(f"✓ Loaded {len(self._instruments)} instruments")
        
        return self._instruments
    

    def screen_top_gainers(self) -> List[Candidate]:
        """
        Screen for top gainer stocks based on % gain criteria.
        Uses NSE API if enabled, otherwise scans all stocks in universe.
        
        Returns:
            List of Candidate objects that meet gain criteria
        """
        if self.use_nse_api and self.nse_source:
            return self._screen_top_gainers_nse()
        else:
            return self._screen_top_gainers_universe()
    
    def _screen_top_gainers_nse(self) -> List[Candidate]:
        """
        Screen top gainers using NSE API (faster).
        
        Returns:
            List of Candidate objects filtered by universe and gain criteria
        """
        print("🔍 Fetching top gainers from NSE API...")
        
        # Get top gainers from NSE
        nse_gainers = self.nse_source.get_top_gainers()
        
        if not nse_gainers:
            print("⚠️  No gainers found from NSE API")
            return []
        
        # Load universe instruments for filtering
        universe_instruments = self._load_instruments()
        universe_symbols = {inst.tradingsymbol for inst in universe_instruments}
        
        # Build instrument token lookup
        symbol_to_token = {inst.tradingsymbol: inst.instrument_token 
                          for inst in universe_instruments}
        
        candidates = []
        
        for gainer in nse_gainers:
            # Filter by universe
            if gainer.symbol not in universe_symbols:
                continue
            
            # Filter by gain range
            if not (self.config.min_gain_pct <= gainer.pct_change <= self.config.max_gain_pct):
                continue
            
            # Get instrument token
            instrument_token = symbol_to_token.get(gainer.symbol, 0)
            
            # Create candidate
            candidate = Candidate(
                symbol=gainer.symbol,
                instrument_token=instrument_token,
                current_price=gainer.last_price,
                gain_pct=gainer.pct_change,
                volume=gainer.volume,
                avg_volume=gainer.volume,  # Will be enriched later
                timestamp=gainer.timestamp,
                open_price=gainer.open_price,
                high_price=gainer.high_price,
                low_price=gainer.low_price
            )
            candidates.append(candidate)
        
        # Sort by % gain (descending)
        candidates.sort(key=lambda c: c.gain_pct, reverse=True)
        
        print(f"✓ Found {len(candidates)} candidates with {self.config.min_gain_pct}%-{self.config.max_gain_pct}% gain")
        
        return candidates
    
    def _screen_top_gainers_universe(self) -> List[Candidate]:
        """
        Screen top gainers by scanning all stocks in universe (slower).
        
        Returns:
            List of Candidate objects that meet gain criteria
        """
        instruments = self._load_instruments()
        
        if not instruments:
            print("⚠️  No instruments found in universe")
            return []
        
        # Get instrument tokens
        instrument_tokens = [inst.instrument_token for inst in instruments]
        
        print(f"🔍 Fetching quotes for {len(instrument_tokens)} stocks...")
        
        # Fetch quotes (may need to batch if > 500)
        batch_size = 500
        all_quotes = {}
        
        for i in range(0, len(instrument_tokens), batch_size):
            batch = instrument_tokens[i:i + batch_size]
            try:
                quotes = self.data_source.get_quotes(batch)
                all_quotes.update(quotes)
            except Exception as e:
                print(f"⚠️  Error fetching batch {i//batch_size + 1}: {e}")
                continue
        
        # Filter by gain criteria and convert to Candidates
        candidates = []
        
        for token, quote in all_quotes.items():
            # Check gain range
            if self.config.min_gain_pct <= quote.change_pct <= self.config.max_gain_pct:
                # Convert Quote to Candidate
                candidate = Candidate(
                    symbol=quote.symbol,
                    instrument_token=quote.instrument_token,
                    current_price=quote.last_price,
                    gain_pct=quote.change_pct,
                    volume=quote.volume,
                    avg_volume=quote.volume,  # We'll calculate this later with historical data
                    timestamp=quote.timestamp,
                    open_price=quote.open_price,
                    high_price=quote.high_price,
                    low_price=quote.low_price
                )
                candidates.append(candidate)
        
        # Sort by % gain (descending)
        candidates.sort(key=lambda c: c.gain_pct, reverse=True)
        
        print(f"✓ Found {len(candidates)} candidates with {self.config.min_gain_pct}%-{self.config.max_gain_pct}% gain")
        
        return candidates
    
    def screen_with_filters(self, candidates: List[Candidate]) -> List[Candidate]:
        """
        Apply additional filters (volume, momentum, etc.)
        
        This is called after screen_top_gainers() to further filter.
        Actual filter logic is in TopGainersMomentumStrategy.
        
        Args:
            candidates: Initial candidate list
        
        Returns:
            Filtered candidates
        """
        # This will be implemented by the strategy
        # Screener just does initial % gain filtering
        return candidates
    
    def get_universe_size(self) -> int:
        """Get number of instruments in universe"""
        instruments = self._load_instruments()
        return len(instruments)
    
    def search_stock(self, query: str) -> List[Instrument]:
        """
        Search for stock in universe.
        
        Args:
            query: Symbol or name to search
        
        Returns:
            Matching instruments
        """
        instruments = self._load_instruments()
        
        query_lower = query.lower()
        matches = [
            inst for inst in instruments
            if query_lower in inst.tradingsymbol.lower()
            or query_lower in inst.name.lower()
        ]
        
        return matches
    
    def enrich_candidate_with_volume(self, candidate: Candidate, lookback_days: int = 10) -> Candidate:
        """
        Enrich candidate with average volume calculation.
        
        Args:
            candidate: Candidate to enrich
            lookback_days: Days to calculate average volume
        
        Returns:
            Enriched candidate with avg_volume
        """
        try:
            from_date = datetime.now() - timedelta(days=lookback_days * 2)  # Extra buffer for holidays
            to_date = datetime.now()
            
            # Fetch daily data
            df = self.data_source.get_historical_data(
                candidate.instrument_token,
                from_date,
                to_date,
                interval='day'
            )
            
            if df is not None and not df.empty and 'volume' in df.columns:
                # Calculate average volume
                avg_volume = df['volume'].tail(lookback_days).mean()
                candidate.avg_volume = avg_volume
            
        except Exception as e:
            print(f"⚠️  Could not enrich {candidate.symbol} with volume: {e}")
        
        return candidate


class UniverseFactory:
    """
    Factory for creating stock universes.
    
    Usage:
        universe = UniverseFactory.create('fno')
        universe = UniverseFactory.create('custom', symbols=['RELIANCE', 'TCS'])
    """
    
    @staticmethod
    def create(universe_type: str, **kwargs) -> IStockUniverse:
        """
        Create stock universe.
        
        Args:
            universe_type: 'fno', 'nifty500', 'nifty200', 'custom'
            **kwargs: Additional parameters (e.g., symbols for custom)
        
        Returns:
            Stock universe instance
        """
        if universe_type == 'fno':
            return FnOUniverse()
        
        elif universe_type == 'nifty500':
            return Nifty500Universe()
        
        elif universe_type == 'nifty200':
            return Nifty200Universe()
        
        elif universe_type == 'custom':
            symbols = kwargs.get('symbols')
            if not symbols:
                raise ValueError("Custom universe requires 'symbols' parameter")
            return CustomUniverse(symbols)
        
        else:
            raise ValueError(f"Unknown universe type: {universe_type}")
