"""Trading signal model"""
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Literal
import json


@dataclass
class Signal:
    """Represents a trading signal"""
    instrument_token: int
    signal_type: Literal["BUY", "SELL"]
    price: float
    timestamp: datetime
    strategy_name: str = "EMA_CROSSOVER"
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_json(self) -> str:
        """Convert to JSON string for Redis publishing"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Signal":
        """Create Signal from JSON string"""
        data = json.loads(json_str)
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)
