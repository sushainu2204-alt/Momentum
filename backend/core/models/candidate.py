"""
Candidate Model

Stock candidate that passed initial screening criteria.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Candidate:
    """
    Stock that passed initial screening criteria.
    
    Represents a potential trading opportunity identified
    by the stock screener before strategy filters are applied.
    
    Attributes:
        symbol: Stock trading symbol
        instrument_token: Kite instrument token
        current_price: Current/last traded price
        gain_pct: Percentage gain for the day
        volume: Trading volume
        avg_volume: Average volume for comparison
        timestamp: When candidate was identified
        open_price: Day's opening price
        high_price: Day's high price
        low_price: Day's low price
    """
    symbol: str
    instrument_token: int
    current_price: float
    gain_pct: float
    volume: int
    avg_volume: float
    timestamp: datetime
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
