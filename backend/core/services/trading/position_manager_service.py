"""
Position Manager Service

Manages multiple open positions for a strategy.
Tracks P&L, handles exits, enforces risk limits.
"""

from typing import List, Dict, Optional
from datetime import datetime
import logging

from backend.core.models import Position, Signal, SignalType, PositionStatus
from backend.config import BaseStrategyConfig

logger = logging.getLogger(__name__)

# TODO : Is this really needed? I can check the positions on Kite for now. if its is very much needed,This should be generalized for other strategies as well
class PositionManagerService:
    """
    Manages multiple positions for any trading strategy.
    
    Features:
    - Track open positions
    - Update P&L in real-time
    - Check for exits (SL/Target/Time)
    - Enforce max concurrent positions
    - Calculate total capital at risk
    - Report daily P&L
    
    Usage:
        manager = PositionManagerService(config)
        
        # Add position
        manager.add_position(signal)
        
        # Update all positions
        exit_signals = manager.update_positions(quotes, current_time)
        
        # Get stats
        stats = manager.get_stats()
    """
    
    def __init__(self, config: BaseStrategyConfig):
        """
        Initialize position manager.
        
        Args:
            config: Any strategy configuration that extends BaseStrategyConfig
        """
        self.config = config
        self.positions: Dict[str, Position] = {}  # symbol -> Position
        self.closed_positions: List[Position] = []
    
    # ================================================================
    # POSITION MANAGEMENT
    # ================================================================
    
    def add_position(self, signal: Signal) -> bool:
        """
        Add new position from BUY signal.
        
        Args:
            signal: BUY signal with entry details
        
        Returns:
            True if position added, False if rejected
        """
        # Check if symbol already has open position
        if signal.symbol in self.positions:
            logger.warning(f"Position already exists for {signal.symbol}")
            return False
        
        # Check max concurrent positions
        if len(self.positions) >= self.config.max_positions:
            logger.warning(
                f"Max concurrent positions reached: {self.config.max_positions}"
            )
            return False
        
        # Check capital at risk
        if not self._check_risk_limits(signal):
            logger.warning(f"Risk limits exceeded for {signal.symbol}")
            return False
        
        # Create position
        position = Position(
            symbol=signal.symbol,
            instrument_token=signal.instrument_token,
            entry_price=signal.price,
            quantity=signal.quantity,
            stop_loss=signal.stop_loss,
            target=signal.target,
            entry_time=signal.timestamp
        )
        
        self.positions[signal.symbol] = position
        logger.info(
            f"Position opened: {signal.symbol} @ {signal.price:.2f}, "
            f"qty={signal.quantity}, SL={signal.stop_loss:.2f}, "
            f"Target={signal.target:.2f}"
        )
        
        return True
    
    def close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str
    ) -> Optional[Position]:
        """
        Close position and move to closed positions.
        
        Args:
            symbol: Stock symbol
            exit_price: Exit price
            exit_time: Exit time
            exit_reason: Reason for exit
        
        Returns:
            Closed position or None
        """
        if symbol not in self.positions:
            logger.warning(f"Position not found: {symbol}")
            return None
        
        position = self.positions[symbol]
        position.close(exit_price, exit_time, exit_reason)
        
        # Move to closed positions
        self.closed_positions.append(position)
        del self.positions[symbol]
        
        logger.info(
            f"Position closed: {symbol} @ {exit_price:.2f}, "
            f"P&L: {position.pnl:.2f} ({position.pnl_pct:.2f}%), "
            f"Reason: {exit_reason}"
        )
        
        return position
    
    # ================================================================
    # UPDATE & MONITORING
    # ================================================================
    
    def update_positions(
        self,
        quotes: Dict[str, float],  # symbol -> current_price
        current_time: datetime
    ) -> List[Signal]:
        """
        Update all positions with current prices and check for exits.
        
        Args:
            quotes: Dict of symbol -> current_price
            current_time: Current time
        
        Returns:
            List of SELL signals for positions to exit
        """
        exit_signals = []
        exit_time = datetime.combine(current_time.date(), self.config.exit_time)
        if current_time.tzinfo is not None:
            exit_time = exit_time.replace(tzinfo=current_time.tzinfo)
        
        for symbol, position in list(self.positions.items()):
            # Get current price
            if symbol not in quotes:
                logger.warning(f"No quote for {symbol}, skipping")
                continue
            
            current_price = quotes[symbol]
            
            # Update P&L
            position.update_pnl(current_price)
            
            # Check exit conditions
            exit_reason = position.check_exit(current_price, current_time, exit_time)
            
            if exit_reason:
                # Generate exit signal
                signal = Signal(
                    symbol=symbol,
                    instrument_token=position.instrument_token,
                    signal_type=SignalType.SELL,
                    price=current_price,
                    timestamp=current_time,
                    reason=exit_reason,
                    quantity=position.quantity
                )
                exit_signals.append(signal)
                
                # Close position
                self.close_position(symbol, current_price, current_time, exit_reason)
        
        return exit_signals
    
    def update_position_price(self, symbol: str, current_price: float):
        """
        Update single position price (for real-time updates).
        
        Args:
            symbol: Stock symbol
            current_price: Current price
        """
        if symbol in self.positions:
            self.positions[symbol].update_pnl(current_price)
    
    # ================================================================
    # RISK MANAGEMENT
    # ================================================================
    
    def _check_risk_limits(self, signal: Signal) -> bool:
        """
        Check if adding position would exceed risk limits.
        
        Args:
            signal: BUY signal
        
        Returns:
            True if within risk limits
        """
        # Calculate position risk (SL distance * quantity)
        position_risk = abs(signal.price - signal.stop_loss) * signal.quantity
        
        # Calculate total capital at risk
        total_risk = position_risk
        for position in self.positions.values():
            pos_risk = abs(position.entry_price - position.stop_loss) * position.quantity
            total_risk += pos_risk
        
        # Check against max capital at risk
        max_risk = self.config.get_max_capital_at_risk()
        
        if total_risk > max_risk:
            logger.warning(
                f"Risk limit exceeded: {total_risk:.2f} > {max_risk:.2f}"
            )
            return False
        
        return True
    
    def get_total_capital_at_risk(self) -> float:
        """
        Calculate total capital at risk across all positions.
        
        Returns:
            Total capital at risk
        """
        total_risk = 0.0
        for position in self.positions.values():
            pos_risk = abs(position.entry_price - position.stop_loss) * position.quantity
            total_risk += pos_risk
        
        return total_risk
    
    # ================================================================
    # QUERIES & STATS
    # ================================================================
    
    def get_open_positions(self) -> List[Position]:
        """Get list of open positions"""
        return list(self.positions.values())
    
    def get_closed_positions(self) -> List[Position]:
        """Get list of closed positions"""
        return self.closed_positions
    
    def has_position(self, symbol: str) -> bool:
        """Check if position exists for symbol"""
        return symbol in self.positions
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position by symbol"""
        return self.positions.get(symbol)
    
    def get_position_count(self) -> int:
        """Get count of open positions"""
        return len(self.positions)
    
    def get_stats(self) -> Dict:
        """
        Get comprehensive stats.
        
        Returns:
            Dict with open positions, closed positions, P&L, win rate, etc.
        """
        # Open positions stats
        open_count = len(self.positions)
        open_pnl = sum(p.pnl for p in self.positions.values())
        
        # Closed positions stats
        closed_count = len(self.closed_positions)
        
        if closed_count > 0:
            closed_pnl = sum(p.pnl for p in self.closed_positions)
            winners = [p for p in self.closed_positions if p.pnl > 0]
            losers = [p for p in self.closed_positions if p.pnl < 0]
            
            win_rate = len(winners) / closed_count * 100
            avg_win = sum(p.pnl for p in winners) / len(winners) if winners else 0
            avg_loss = sum(p.pnl for p in losers) / len(losers) if losers else 0
            
            # Profit factor
            total_wins = sum(p.pnl for p in winners)
            total_losses = abs(sum(p.pnl for p in losers))
            profit_factor = total_wins / total_losses if total_losses > 0 else 0
            
        else:
            closed_pnl = 0
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            profit_factor = 0
        
        # Total stats
        total_pnl = open_pnl + closed_pnl
        capital_at_risk = self.get_total_capital_at_risk()
        
        return {
            "open_positions": open_count,
            "closed_positions": closed_count,
            "open_pnl": open_pnl,
            "closed_pnl": closed_pnl,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "capital_at_risk": capital_at_risk,
            "max_concurrent_positions": self.config.max_positions
        }
    
    def reset(self):
        """Reset manager (clear all positions)"""
        self.positions.clear()
        self.closed_positions.clear()
        logger.info("Position manager reset")
    
    def __str__(self) -> str:
        """String representation"""
        stats = self.get_stats()
        return (
            f"PositionManager("
            f"open={stats['open_positions']}, "
            f"closed={stats['closed_positions']}, "
            f"pnl={stats['total_pnl']:.2f})"
        )
