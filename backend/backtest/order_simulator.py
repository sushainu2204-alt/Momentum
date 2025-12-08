"""
Order Simulator Module

Simulates order execution, fills, slippage, and position management.
Handles stop loss, trailing stop loss, and target exits.

Features:
    - Multiple fill models (next open, same close, VWAP)
    - Slippage simulation
    - Stop loss management
    - Trailing stop loss
    - Target profit booking
    - Time-based exits (MIS square-off)
    - Partial fills (optional)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, date, time
from typing import Dict, List, Optional, Tuple
from enum import Enum
import uuid
import logging

from .config import BacktestConfig, ExecutionConfig, StopLossConfig, FillModelType
from .events import OrderEvent, FillEvent, ExitSignalEvent
from .signal_engine import BacktestSignal

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PositionStatus(Enum):
    """Position status."""
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class Order:
    """Order representation."""
    order_id: str
    symbol: str
    instrument_token: int
    side: str  # BUY or SELL
    quantity: int
    order_type: str  # MARKET, LIMIT
    price: float  # For limit orders
    stop_loss: float
    target: float
    strategy_id: str
    signal_id: Optional[str] = None
    timestamp: datetime = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    filled_price: float = 0.0
    fill_timestamp: Optional[datetime] = None


@dataclass
class BacktestPosition:
    """
    Active position in backtest.
    
    Tracks position from entry to exit with all state.
    """
    position_id: str
    symbol: str
    instrument_token: int
    strategy_id: str
    
    # Entry
    entry_price: float
    entry_time: datetime
    quantity: int
    
    # Stop loss
    initial_sl: float
    current_sl: float
    
    # Target
    target: float
    
    # Trailing state (with defaults)
    sl_trail_count: int = 0
    
    # Current state
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    highest_price: float = 0.0  # For trailing SL
    status: PositionStatus = PositionStatus.OPEN
    
    # Exit
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    realized_pnl: float = 0.0
    
    def update_price(self, price: float) -> None:
        """Update current price and P&L."""
        self.current_price = price
        self.unrealized_pnl = (price - self.entry_price) * self.quantity
        self.unrealized_pnl_pct = ((price - self.entry_price) / self.entry_price) * 100
        
        # Track highest price for trailing SL
        if price > self.highest_price:
            self.highest_price = price
    
    def close(
        self,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str
    ) -> None:
        """Close the position."""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = exit_reason
        self.realized_pnl = (exit_price - self.entry_price) * self.quantity
        self.status = PositionStatus.CLOSED


class FillModel:
    """
    Fill model for simulating order execution.
    
    Different models have different assumptions about
    where orders get filled.
    """
    
    def __init__(self, config: ExecutionConfig):
        self.config = config
    
    def get_fill_price(
        self,
        order: Order,
        current_candle: pd.Series,
        next_candle: Optional[pd.Series] = None
    ) -> Tuple[float, float]:
        """
        Calculate fill price based on fill model.
        
        Args:
            order: Order to fill
            current_candle: Candle at order time
            next_candle: Next candle (for next_open model)
        
        Returns:
            Tuple of (fill_price, slippage)
        """
        base_price = self._get_base_price(order, current_candle, next_candle)
        slippage = self._calculate_slippage(order, base_price)
        
        # Apply slippage (adverse for buyer)
        if order.side == "BUY":
            fill_price = base_price + slippage
        else:
            fill_price = base_price - slippage
        
        return fill_price, slippage
    
    def _get_base_price(
        self,
        order: Order,
        current_candle: pd.Series,
        next_candle: Optional[pd.Series]
    ) -> float:
        """Get base price based on fill model type."""
        
        if self.config.fill_model == FillModelType.NEXT_OPEN:
            if next_candle is not None:
                return next_candle['open']
            return current_candle['close']
        
        elif self.config.fill_model == FillModelType.SAME_CLOSE:
            return current_candle['close']
        
        elif self.config.fill_model == FillModelType.VWAP_ESTIMATE:
            # Estimate VWAP as typical price
            return (
                current_candle['high'] + 
                current_candle['low'] + 
                current_candle['close']
            ) / 3
        
        elif self.config.fill_model == FillModelType.WORST_CASE:
            if order.side == "BUY":
                return current_candle['high']
            else:
                return current_candle['low']
        
        # Default: close price
        return current_candle['close']
    
    def _calculate_slippage(self, order: Order, price: float) -> float:
        """Calculate slippage amount."""
        
        if self.config.slippage_model.value == "none":
            return 0.0
        
        elif self.config.slippage_model.value == "fixed":
            return price * (self.config.slippage_pct / 100)
        
        elif self.config.slippage_model.value == "volume_based":
            # Higher slippage for larger orders (simplified)
            base_slippage = price * (self.config.slippage_pct / 100)
            # Could factor in volume here
            return base_slippage * 1.5
        
        return 0.0


class OrderSimulator:
    """
    Order execution simulator.
    
    Handles:
    - Order placement and execution
    - Fill simulation
    - Position management
    - Stop loss monitoring
    - Trailing stop loss
    - Target exits
    - Time-based exits
    
    Usage:
        simulator = OrderSimulator(config)
        
        # Submit order from signal
        order = simulator.submit_order(signal, quantity)
        
        # Process candle (check fills, SL, target)
        events = simulator.process_candle(timestamp, candle_data)
        
        # At day end, square off all positions
        events = simulator.square_off_all(timestamp, prices)
    """
    
    def __init__(self, config: BacktestConfig):
        """
        Initialize order simulator.
        
        Args:
            config: Backtest configuration
        """
        self.config = config
        self.exec_config = config.execution
        self.sl_config = config.stop_loss
        self.time_config = config.time
        
        # Fill model
        self.fill_model = FillModel(self.exec_config)
        
        # Orders
        self._pending_orders: Dict[str, Order] = {}
        self._completed_orders: List[Order] = []
        
        # Positions
        self._open_positions: Dict[str, BacktestPosition] = {}
        self._closed_positions: List[BacktestPosition] = []
        
        # For tracking next candle fills
        self._orders_waiting_fill: Dict[str, Order] = {}
    
    def submit_order(
        self,
        signal: BacktestSignal,
        quantity: int
    ) -> Order:
        """
        Submit order from signal.
        
        Args:
            signal: Trading signal
            quantity: Order quantity
        
        Returns:
            Created order
        """
        order_id = str(uuid.uuid4())[:8]
        
        order = Order(
            order_id=order_id,
            symbol=signal.symbol,
            instrument_token=signal.instrument_token,
            side="BUY" if signal.signal_type.value == "BUY" else "SELL",
            quantity=quantity,
            order_type="MARKET",
            price=signal.price,
            stop_loss=signal.stop_loss,
            target=signal.target,
            strategy_id=signal.strategy_id,
            timestamp=signal.timestamp,
            status=OrderStatus.PENDING
        )
        
        # For NEXT_OPEN fill model, queue order for next candle
        if self.exec_config.fill_model == FillModelType.NEXT_OPEN:
            self._orders_waiting_fill[order_id] = order
        else:
            self._pending_orders[order_id] = order
        
        logger.debug(f"Order submitted: {order_id} | {signal.symbol} | Qty: {quantity}")
        
        return order
    
    def process_candle(
        self,
        timestamp: datetime,
        market_data: Dict[str, pd.Series],
        features_data: Optional[Dict[str, pd.DataFrame]] = None
    ) -> List:
        """
        Process a candle tick for all positions and orders.
        
        Args:
            timestamp: Current timestamp
            market_data: Current candle for each symbol
            features_data: Historical data (for getting next candle)
        
        Returns:
            List of events (fills, exits)
        """
        events = []
        
        # 1. Process pending order fills (for same-candle fills)
        for order_id, order in list(self._pending_orders.items()):
            if order.symbol in market_data:
                candle = market_data[order.symbol]
                fill_event = self._fill_order(order, candle, None)
                if fill_event:
                    events.append(fill_event)
        
        # 2. Process orders waiting for next candle
        for order_id, order in list(self._orders_waiting_fill.items()):
            if order.symbol in market_data:
                candle = market_data[order.symbol]
                fill_event = self._fill_order(order, candle, candle)  # Use current as "next"
                if fill_event:
                    events.append(fill_event)
                    del self._orders_waiting_fill[order_id]
        
        # 3. Update open positions and check exits
        for position_id, position in list(self._open_positions.items()):
            if position.symbol not in market_data:
                continue
            
            candle = market_data[position.symbol]
            
            # Update position price
            position.update_price(candle['close'])
            
            # Check exit conditions
            exit_event = self._check_position_exit(position, candle, timestamp)
            if exit_event:
                events.append(exit_event)
        
        # 4. Check time-based exit (square-off)
        if timestamp.time() >= self.time_config.auto_square_off_time:
            square_off_events = self._square_off_all(timestamp, market_data)
            events.extend(square_off_events)
        
        return events
    
    def _fill_order(
        self,
        order: Order,
        current_candle: pd.Series,
        next_candle: Optional[pd.Series]
    ) -> Optional[FillEvent]:
        """Fill a pending order."""
        
        # Get fill price
        fill_price, slippage = self.fill_model.get_fill_price(
            order, current_candle, next_candle
        )
        
        # Calculate commission
        trade_value = fill_price * order.quantity
        commission = self._calculate_commission(trade_value, order.side)
        
        # Update order
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.filled_price = fill_price
        order.fill_timestamp = current_candle.get('timestamp', datetime.now())
        
        # Create position
        position = self._create_position_from_order(order, fill_price)
        
        # Remove from pending
        if order.order_id in self._pending_orders:
            del self._pending_orders[order.order_id]
        
        self._completed_orders.append(order)
        
        logger.debug(
            f"Order filled: {order.symbol} | Price: ₹{fill_price:.2f} | "
            f"Slippage: ₹{slippage:.2f}"
        )
        
        return FillEvent(
            timestamp=order.fill_timestamp,
            symbol=order.symbol,
            instrument_token=order.instrument_token,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission,
            slippage=slippage,
            strategy_id=order.strategy_id,
            order_id=order.order_id
        )
    
    def _calculate_commission(self, trade_value: float, side: str) -> float:
        """Calculate total commission including brokerage, STT, etc."""
        
        # Fixed commission
        commission = self.exec_config.commission_per_trade
        
        # Percentage commission
        commission += trade_value * self.exec_config.commission_pct
        
        # STT on sell (intraday)
        if side == "SELL":
            commission += trade_value * self.exec_config.stt_pct
        
        return commission
    
    def _create_position_from_order(
        self,
        order: Order,
        fill_price: float
    ) -> BacktestPosition:
        """Create position from filled order."""
        
        position_id = str(uuid.uuid4())[:8]
        
        # Calculate initial SL if not provided
        if order.stop_loss <= 0:
            sl_distance = fill_price * (self.sl_config.initial_sl_pct / 100)
            initial_sl = fill_price - sl_distance
        else:
            initial_sl = order.stop_loss
        
        # Calculate target if not provided
        if order.target <= 0:
            if self.sl_config.use_rr_ratio:
                sl_distance = fill_price - initial_sl
                target = fill_price + (sl_distance * self.sl_config.risk_reward_ratio)
            else:
                target = fill_price * (1 + self.sl_config.initial_target_pct / 100)
        else:
            target = order.target
        
        position = BacktestPosition(
            position_id=position_id,
            symbol=order.symbol,
            instrument_token=order.instrument_token,
            strategy_id=order.strategy_id,
            entry_price=fill_price,
            entry_time=order.fill_timestamp,
            quantity=order.quantity,
            initial_sl=initial_sl,
            current_sl=initial_sl,
            target=target,
            current_price=fill_price,
            highest_price=fill_price
        )
        
        self._open_positions[position_id] = position
        
        return position
    
    def _check_position_exit(
        self,
        position: BacktestPosition,
        candle: pd.Series,
        timestamp: datetime
    ) -> Optional[ExitSignalEvent]:
        """Check if position should be exited."""
        
        low = candle['low']
        high = candle['high']
        close = candle['close']
        
        exit_reason = None
        exit_price = None
        
        # Check stop loss (low breached SL)
        if low <= position.current_sl:
            exit_reason = "SL_HIT"
            exit_price = position.current_sl  # Assume SL order filled at SL price
        
        # Check target (high reached target)
        elif high >= position.target:
            exit_reason = "TARGET_HIT"
            exit_price = position.target
        
        # If no exit triggered, update trailing SL
        if exit_reason is None and self.sl_config.enable_trailing_sl:
            self._update_trailing_sl(position, high)
        
        # Execute exit if triggered
        if exit_reason:
            return self._exit_position(position, exit_price, timestamp, exit_reason)
        
        return None
    
    def _update_trailing_sl(
        self,
        position: BacktestPosition,
        current_high: float
    ) -> None:
        """Update trailing stop loss."""
        
        # Check if trailing should be activated
        profit_pct = ((position.highest_price - position.entry_price) / 
                     position.entry_price) * 100
        
        if profit_pct < self.sl_config.trailing_sl_activation_pct:
            return
        
        # Calculate new SL based on highest price
        trail_distance = position.highest_price * (self.sl_config.trailing_sl_distance_pct / 100)
        new_sl = position.highest_price - trail_distance
        
        # Only move SL up, never down
        if new_sl > position.current_sl:
            # Check if move is at least step size
            step_size = position.entry_price * (self.sl_config.trailing_sl_step_pct / 100)
            if new_sl - position.current_sl >= step_size:
                position.current_sl = new_sl
                position.sl_trail_count += 1
                
                logger.debug(
                    f"Trailing SL updated: {position.symbol} | "
                    f"New SL: ₹{new_sl:.2f} | Trail #{position.sl_trail_count}"
                )
    
    def _exit_position(
        self,
        position: BacktestPosition,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str
    ) -> ExitSignalEvent:
        """Exit a position."""
        
        # Apply slippage to exit
        slippage = exit_price * (self.exec_config.slippage_pct / 100)
        final_exit_price = exit_price - slippage  # Adverse for seller
        
        # Close position
        position.close(final_exit_price, exit_time, exit_reason)
        
        # Move to closed positions
        if position.position_id in self._open_positions:
            del self._open_positions[position.position_id]
        self._closed_positions.append(position)
        
        logger.debug(
            f"Position exited: {position.symbol} | Reason: {exit_reason} | "
            f"PnL: ₹{position.realized_pnl:.0f}"
        )
        
        return ExitSignalEvent(
            timestamp=exit_time,
            symbol=position.symbol,
            exit_reason=exit_reason,
            exit_price=final_exit_price,
            position_id=position.position_id
        )
    
    def _square_off_all(
        self,
        timestamp: datetime,
        market_data: Dict[str, pd.Series]
    ) -> List[ExitSignalEvent]:
        """Square off all open positions (MIS exit)."""
        
        events = []
        
        for position_id, position in list(self._open_positions.items()):
            if position.symbol in market_data:
                candle = market_data[position.symbol]
                exit_price = candle['close']
                
                event = self._exit_position(
                    position, exit_price, timestamp, "TIME_EXIT"
                )
                events.append(event)
        
        return events
    
    def square_off_position(
        self,
        symbol: str,
        timestamp: datetime,
        exit_price: float,
        reason: str = "MANUAL_EXIT"
    ) -> Optional[ExitSignalEvent]:
        """Manually square off a specific position."""
        
        for position_id, position in list(self._open_positions.items()):
            if position.symbol == symbol:
                return self._exit_position(position, exit_price, timestamp, reason)
        
        return None
    
    def get_open_positions(self) -> Dict[str, BacktestPosition]:
        """Get all open positions."""
        return self._open_positions
    
    def get_closed_positions(self) -> List[BacktestPosition]:
        """Get all closed positions."""
        return self._closed_positions
    
    def get_position_symbols(self) -> List[str]:
        """Get symbols with open positions."""
        return [p.symbol for p in self._open_positions.values()]
    
    def get_unrealized_pnl(self) -> float:
        """Get total unrealized P&L."""
        return sum(p.unrealized_pnl for p in self._open_positions.values())
    
    def get_realized_pnl(self) -> float:
        """Get total realized P&L."""
        return sum(p.realized_pnl for p in self._closed_positions)
    
    def reset(self) -> None:
        """Reset simulator state."""
        self._pending_orders.clear()
        self._completed_orders.clear()
        self._open_positions.clear()
        self._closed_positions.clear()
        self._orders_waiting_fill.clear()
