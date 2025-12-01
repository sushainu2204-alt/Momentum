"""Tick data model"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Tick:
    """Represents a market tick"""
    instrument_token: int
    last_price: float
    timestamp: Optional[datetime] = None
    volume: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    
    @classmethod
    def from_kite_tick(cls, tick: dict) -> "Tick":
        """Create Tick from Kite Connect tick data"""
        return cls(
            instrument_token=tick.get("instrument_token"),
            last_price=tick.get("last_price") or tick.get("ltp"),
            timestamp=tick.get("timestamp"),
            volume=tick.get("volume"),
            bid=tick.get("bid"),
            ask=tick.get("ask"),
        )
    
    @classmethod
    def from_json(cls, data: dict) -> "Tick":
        """Create Tick from JSON/Redis data"""
        return cls(
            instrument_token=data.get("instrument_token"),
            last_price=data.get("last_price") or data.get("ltp"),
            timestamp=data.get("timestamp"),
            volume=data.get("volume"),
            bid=data.get("bid"),
            ask=data.get("ask"),
        )
