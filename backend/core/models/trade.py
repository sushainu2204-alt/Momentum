"""Trade model for backtesting"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal


@dataclass
class Trade:
    """Represents a single trade"""
    entry_time: datetime
    entry_price: float
    signal: Literal["BUY", "SELL"]
    quantity: int
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    pnl_percent: float = 0.0
    
    def close_trade(self, exit_time: datetime, exit_price: float):
        """Close the trade and calculate P&L"""
        self.exit_time = exit_time
        self.exit_price = exit_price
        
        if self.signal == "BUY":
            self.pnl = (exit_price - self.entry_price) * self.quantity
        else:  # SELL/SHORT
            self.pnl = (self.entry_price - exit_price) * self.quantity
            
        self.pnl_percent = (self.pnl / (self.entry_price * self.quantity)) * 100
    
    def is_open(self) -> bool:
        """Check if trade is still open"""
        return self.exit_time is None
