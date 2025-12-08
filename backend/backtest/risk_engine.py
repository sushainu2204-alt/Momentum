"""
Risk Engine Module

Capital allocation, position sizing, and risk checks.
Ensures all trades comply with risk management rules.

Features:
    - Dynamic position sizing
    - Capital allocation
    - Maximum position limits
    - Drawdown protection
    - Daily loss limits
    - Exposure management
"""

import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
import logging

from .config import BacktestConfig, RiskConfig
from .events import RiskCheckEvent, SignalEvent
from .signal_engine import BacktestSignal

logger = logging.getLogger(__name__)


@dataclass
class PortfolioState:
    """Current state of the portfolio."""
    
    # Capital
    total_capital: float
    available_capital: float
    invested_capital: float
    
    # Positions
    open_positions: int
    positions_by_strategy: Dict[str, int] = field(default_factory=dict)
    positions_by_symbol: Dict[str, int] = field(default_factory=dict)
    
    # P&L
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    
    # Daily tracking
    daily_trades: int = 0
    daily_pnl: float = 0.0
    daily_loss: float = 0.0
    
    # Drawdown
    peak_equity: float = 0.0
    current_drawdown: float = 0.0
    max_drawdown: float = 0.0
    
    def update_pnl(self, unrealized: float) -> None:
        """Update P&L values."""
        self.unrealized_pnl = unrealized
        self.total_pnl = self.realized_pnl + unrealized
        
        # Update equity
        current_equity = self.total_capital + self.total_pnl
        
        # Track peak and drawdown
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        
        if self.peak_equity > 0:
            self.current_drawdown = (
                (self.peak_equity - current_equity) / self.peak_equity
            ) * 100
            
            if self.current_drawdown > self.max_drawdown:
                self.max_drawdown = self.current_drawdown


@dataclass
class RiskCheckResult:
    """Result of a risk check."""
    passed: bool
    reason: str
    allowed_quantity: int = 0
    allocated_capital: float = 0.0
    position_value: float = 0.0
    stop_loss_risk: float = 0.0


class RiskEngine:
    """
    Risk management engine.
    
    Performs all risk checks before allowing a trade:
    - Capital availability
    - Position limits
    - Daily loss limits
    - Drawdown limits
    - Position sizing
    
    Usage:
        engine = RiskEngine(config)
        
        # Check if signal can be traded
        result = engine.check_signal(signal, portfolio_state)
        
        if result.passed:
            quantity = result.allowed_quantity
            execute_trade(signal, quantity)
    """
    
    def __init__(self, config: BacktestConfig):
        """
        Initialize risk engine.
        
        Args:
            config: Backtest configuration
        """
        self.config = config
        self.risk_config = config.risk
        
        # Initialize portfolio state
        self.portfolio = PortfolioState(
            total_capital=config.initial_capital,
            available_capital=config.initial_capital,
            invested_capital=0.0,
            open_positions=0,
            peak_equity=config.initial_capital
        )
        
        # Track daily resets
        self._current_date: Optional[date] = None
    
    def check_signal(
        self,
        signal: BacktestSignal,
        current_time: datetime
    ) -> RiskCheckResult:
        """
        Perform all risk checks for a signal.
        
        Args:
            signal: Trading signal
            current_time: Current timestamp
        
        Returns:
            RiskCheckResult with pass/fail and details
        """
        # Check for new day (reset daily counters)
        self._check_day_reset(current_time.date())
        
        # Run all checks
        checks = [
            self._check_capital_available(signal),
            self._check_position_limits(signal),
            self._check_daily_limits(),
            self._check_drawdown_limits(),
        ]
        
        for result in checks:
            if not result.passed:
                return result
        
        # All checks passed - calculate position size
        return self._calculate_position_size(signal)
    
    def _check_day_reset(self, current_date: date) -> None:
        """Reset daily counters on new day."""
        if self._current_date != current_date:
            self.portfolio.daily_trades = 0
            self.portfolio.daily_pnl = 0.0
            self.portfolio.daily_loss = 0.0
            self._current_date = current_date
    
    def _check_capital_available(
        self,
        signal: BacktestSignal
    ) -> RiskCheckResult:
        """Check if sufficient capital is available."""
        
        # Calculate minimum required capital
        min_quantity = 1
        min_capital = signal.price * min_quantity
        
        if self.portfolio.available_capital < min_capital:
            return RiskCheckResult(
                passed=False,
                reason=f"Insufficient capital. Available: ₹{self.portfolio.available_capital:.0f}, "
                       f"Required: ₹{min_capital:.0f}"
            )
        
        return RiskCheckResult(passed=True, reason="Capital check passed")
    
    def _check_position_limits(
        self,
        signal: BacktestSignal
    ) -> RiskCheckResult:
        """Check position limits."""
        
        # Check overall position limit
        if self.portfolio.open_positions >= self.risk_config.max_positions:
            return RiskCheckResult(
                passed=False,
                reason=f"Max positions reached ({self.risk_config.max_positions})"
            )
        
        # Check per-strategy limit
        strategy_positions = self.portfolio.positions_by_strategy.get(
            signal.strategy_id, 0
        )
        if strategy_positions >= self.risk_config.max_positions_per_strategy:
            return RiskCheckResult(
                passed=False,
                reason=f"Max positions for {signal.strategy_id} reached "
                       f"({self.risk_config.max_positions_per_strategy})"
            )
        
        # Check per-symbol limit
        symbol_positions = self.portfolio.positions_by_symbol.get(
            signal.symbol, 0
        )
        if symbol_positions >= self.risk_config.max_positions_per_symbol:
            return RiskCheckResult(
                passed=False,
                reason=f"Already have position in {signal.symbol}"
            )
        
        return RiskCheckResult(passed=True, reason="Position limits check passed")
    
    def _check_daily_limits(self) -> RiskCheckResult:
        """Check daily trading limits."""
        
        # Check max daily trades
        if self.portfolio.daily_trades >= self.risk_config.max_daily_trades:
            return RiskCheckResult(
                passed=False,
                reason=f"Max daily trades reached ({self.risk_config.max_daily_trades})"
            )
        
        # Check daily loss limit (percentage)
        daily_loss_pct = abs(self.portfolio.daily_loss / self.portfolio.total_capital) * 100
        if daily_loss_pct >= self.risk_config.max_daily_loss_pct:
            return RiskCheckResult(
                passed=False,
                reason=f"Daily loss limit reached ({daily_loss_pct:.1f}%)"
            )
        
        # Check daily loss limit (absolute)
        if abs(self.portfolio.daily_loss) >= self.risk_config.max_daily_loss_amount:
            return RiskCheckResult(
                passed=False,
                reason=f"Daily loss amount limit reached (₹{abs(self.portfolio.daily_loss):.0f})"
            )
        
        return RiskCheckResult(passed=True, reason="Daily limits check passed")
    
    def _check_drawdown_limits(self) -> RiskCheckResult:
        """Check drawdown limits."""
        
        if self.portfolio.current_drawdown >= self.risk_config.max_drawdown_pct:
            return RiskCheckResult(
                passed=False,
                reason=f"Max drawdown reached ({self.portfolio.current_drawdown:.1f}%)"
            )
        
        return RiskCheckResult(passed=True, reason="Drawdown check passed")
    
    def _calculate_position_size(
        self,
        signal: BacktestSignal
    ) -> RiskCheckResult:
        """
        Calculate position size based on risk parameters.
        
        Uses Kelly-like sizing based on:
        - Available capital
        - Per-trade capital limit
        - Stop loss risk
        """
        # Method 1: Fixed percentage of capital
        capital_per_trade = min(
            self.portfolio.available_capital * self.risk_config.per_trade_capital_pct,
            self.risk_config.max_capital_per_trade
        )
        
        # Calculate quantity from capital
        quantity_from_capital = int(capital_per_trade / signal.price)
        
        # Method 2: Risk-based sizing (optional)
        # Risk per trade = SL distance * quantity
        # Max risk = 1% of capital
        if signal.stop_loss > 0:
            sl_distance = abs(signal.price - signal.stop_loss)
            sl_distance_pct = (sl_distance / signal.price) * 100
            
            max_risk = self.portfolio.total_capital * 0.01  # 1% risk
            quantity_from_risk = int(max_risk / sl_distance) if sl_distance > 0 else 0
            
            # Use minimum of both methods
            quantity = min(quantity_from_capital, quantity_from_risk) if quantity_from_risk > 0 else quantity_from_capital
        else:
            quantity = quantity_from_capital
        
        # Ensure minimum quantity
        quantity = max(1, quantity)
        
        # Final position value
        position_value = quantity * signal.price
        
        # Calculate risk amount
        stop_loss_risk = 0.0
        if signal.stop_loss > 0:
            stop_loss_risk = quantity * abs(signal.price - signal.stop_loss)
        
        return RiskCheckResult(
            passed=True,
            reason="All risk checks passed",
            allowed_quantity=quantity,
            allocated_capital=position_value,
            position_value=position_value,
            stop_loss_risk=stop_loss_risk
        )
    
    def on_position_opened(
        self,
        symbol: str,
        strategy_id: str,
        quantity: int,
        entry_price: float
    ) -> None:
        """
        Update portfolio state when position is opened.
        
        Args:
            symbol: Stock symbol
            strategy_id: Strategy that generated signal
            quantity: Position quantity
            entry_price: Entry price
        """
        position_value = quantity * entry_price
        
        self.portfolio.open_positions += 1
        self.portfolio.invested_capital += position_value
        self.portfolio.available_capital -= position_value
        self.portfolio.daily_trades += 1
        
        # Update strategy positions
        self.portfolio.positions_by_strategy[strategy_id] = (
            self.portfolio.positions_by_strategy.get(strategy_id, 0) + 1
        )
        
        # Update symbol positions
        self.portfolio.positions_by_symbol[symbol] = (
            self.portfolio.positions_by_symbol.get(symbol, 0) + 1
        )
        
        logger.debug(
            f"Position opened: {symbol} | Qty: {quantity} | "
            f"Value: ₹{position_value:.0f} | Open: {self.portfolio.open_positions}"
        )
    
    def on_position_closed(
        self,
        symbol: str,
        strategy_id: str,
        quantity: int,
        entry_price: float,
        exit_price: float,
        pnl: float
    ) -> None:
        """
        Update portfolio state when position is closed.
        
        Args:
            symbol: Stock symbol
            strategy_id: Strategy that generated signal
            quantity: Position quantity
            entry_price: Entry price
            exit_price: Exit price
            pnl: Realized P&L
        """
        position_value = quantity * entry_price
        
        self.portfolio.open_positions -= 1
        self.portfolio.invested_capital -= position_value
        self.portfolio.available_capital += (position_value + pnl)
        self.portfolio.realized_pnl += pnl
        
        # Update daily P&L
        self.portfolio.daily_pnl += pnl
        if pnl < 0:
            self.portfolio.daily_loss += abs(pnl)
        
        # Update strategy positions
        self.portfolio.positions_by_strategy[strategy_id] = max(
            0, self.portfolio.positions_by_strategy.get(strategy_id, 0) - 1
        )
        
        # Update symbol positions
        self.portfolio.positions_by_symbol[symbol] = max(
            0, self.portfolio.positions_by_symbol.get(symbol, 0) - 1
        )
        
        # Update portfolio state
        self.portfolio.update_pnl(0)  # Will be updated with unrealized PnL
        
        logger.debug(
            f"Position closed: {symbol} | PnL: ₹{pnl:.0f} | "
            f"Total PnL: ₹{self.portfolio.realized_pnl:.0f}"
        )
    
    def update_unrealized_pnl(self, unrealized_pnl: float) -> None:
        """Update unrealized P&L from open positions."""
        self.portfolio.update_pnl(unrealized_pnl)
    
    def get_portfolio_state(self) -> PortfolioState:
        """Get current portfolio state."""
        return self.portfolio
    
    def get_current_equity(self) -> float:
        """Get current total equity."""
        return self.portfolio.total_capital + self.portfolio.total_pnl
    
    def get_available_capital(self) -> float:
        """Get available capital for new trades."""
        return self.portfolio.available_capital
    
    def reset(self) -> None:
        """Reset risk engine to initial state."""
        self.portfolio = PortfolioState(
            total_capital=self.config.initial_capital,
            available_capital=self.config.initial_capital,
            invested_capital=0.0,
            open_positions=0,
            peak_equity=self.config.initial_capital
        )
        self._current_date = None
    
    def to_risk_check_event(
        self,
        signal: BacktestSignal,
        result: RiskCheckResult
    ) -> RiskCheckEvent:
        """Convert result to event."""
        return RiskCheckEvent(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            passed=result.passed,
            reason=result.reason,
            allowed_quantity=result.allowed_quantity,
            allocated_capital=result.allocated_capital
        )
