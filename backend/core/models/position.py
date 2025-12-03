"""
Position Model

Active trading position tracking.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime

from .enums import PositionStatus


@dataclass
class Position:
    """
    Active trading position.
    
    Tracks an open position from entry to exit, including
    P&L calculations and exit condition monitoring.
    
    Attributes:
        symbol: Stock trading symbol
        instrument_token: Kite instrument token
        entry_price: Price at which position was opened
        quantity: Number of shares held
        stop_loss: Stop loss price
        target: Target price for profit booking
        entry_time: When position was opened
        current_price: Latest price (updated dynamically)
        pnl: Absolute P&L in rupees
        pnl_pct: P&L as percentage
        status: Current position status
        exit_price: Price at which position was closed
        exit_time: When position was closed
        exit_reason: Reason for closing position
    """
    symbol: str
    instrument_token: int
    entry_price: float
    quantity: int
    stop_loss: float
    target: float
    entry_time: datetime
    
    # Dynamic fields updated during position lifecycle
    current_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    
    def update_pnl(self, current_price: float) -> None:
        """
        Update P&L based on current price.
        
        Args:
            current_price: Current market price
        """
        self.current_price = current_price
        self.pnl = (current_price - self.entry_price) * self.quantity
        self.pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
    
    def check_exit(
        self,
        current_price: float,
        current_time: datetime,
        exit_time: datetime
    ) -> Optional[str]:
        """
        Check if position should be exited.
        
        Args:
            current_price: Current market price
            current_time: Current timestamp
            exit_time: Time-based exit threshold
            
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
    
    def close(
        self,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str
    ) -> None:
        """
        Close the position.
        
        Args:
            exit_price: Price at which position was closed
            exit_time: When position was closed
            exit_reason: Reason for closing (SL_HIT, TARGET_HIT, etc.)
        """
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = exit_reason
        self.status = PositionStatus[exit_reason]
        self.update_pnl(exit_price)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
