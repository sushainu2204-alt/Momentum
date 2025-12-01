# backend/models.py
from pydantic import BaseModel
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AccessData(BaseModel):
    access_token: str
    public_token: Optional[str]
    user_id: Optional[str]


class SignalType(str, Enum):
    """Signal types for trading"""
    BUY = "BUY"
    SELL = "SELL"


class PositionStatus(str, Enum):
    """Position status"""
    OPEN = "OPEN"
    TARGET_HIT = "TARGET_HIT"
    SL_HIT = "SL_HIT"
    TIME_EXIT = "TIME_EXIT"
    MANUAL_EXIT = "MANUAL_EXIT"


@dataclass
class Signal:
    """Trading signal"""
    symbol: str
    instrument_token: int
    signal_type: SignalType
    price: float
    timestamp: datetime
    reason: Optional[str] = None
    quantity: Optional[int] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None


@dataclass
class Candidate:
    """Stock that passed initial screening"""
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


@dataclass
class Position:
    """Active trading position"""
    symbol: str
    instrument_token: int
    entry_price: float
    quantity: int
    stop_loss: float
    target: float
    entry_time: datetime
    
    # Dynamic fields
    current_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    
    def update_pnl(self, current_price: float):
        """Update P&L based on current price"""
        self.current_price = current_price
        self.pnl = (current_price - self.entry_price) * self.quantity
        self.pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
    
    def check_exit(self, current_price: float, current_time: datetime, exit_time: datetime) -> Optional[str]:
        """
        Check if position should be exited.
        
        Returns:
            Exit reason if should exit, None otherwise
        """
        # Check stop loss
        if current_price <= self.stop_loss:
            return "SL_HIT"
        
        # Check target
        if current_price >= self.target:
            return "TARGET_HIT"
        
        # Check time-based exit
        if current_time >= exit_time:
            return "TIME_EXIT"
        
        return None
    
    def close(self, exit_price: float, exit_time: datetime, exit_reason: str):
        """Close the position"""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = exit_reason
        self.status = PositionStatus[exit_reason]
        self.update_pnl(exit_price)
