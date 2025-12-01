"""
Signal Executor Service

Decision engine for executing trading signals with all guardrails.
- Check market hours and time windows
- Check position/order conflicts
- Enforce capital and risk limits
- Execute orders via OrderManager
- Log all decisions to trade_logs
"""

from typing import Optional, Dict, Any
from datetime import datetime, time
from dataclasses import dataclass
from enum import Enum
import logging

from backend.models import Signal
from backend.core.services.order_manager import OrderManager
from backend.core.services.position_manager import PositionManager
from backend.core.services.capital_manager import CapitalManager
from backend.infrastructure.database.base import IDatabase

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """Execution status"""
    EXECUTED = "EXECUTED"
    IGNORED = "IGNORED"
    FAILED = "FAILED"


@dataclass
class ExecutionResult:
    """Result of signal execution"""
    status: ExecutionStatus
    decision: str  # EXECUTE, IGNORE, FAILED
    reason: str
    order_id: Optional[str] = None
    quantity: Optional[int] = None
    error: Optional[str] = None


@dataclass
class TradingHours:
    """Trading hours configuration"""
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    skip_first_minutes: int = 15  # Skip 9:15-9:30
    skip_last_minutes: int = 15   # Skip 3:15-3:30
    auto_exit_time: time = time(15, 20)  # Exit all at 3:20 PM


class SignalExecutor:
    """
    Execute trading signals with comprehensive guardrails.
    
    Decision Flow:
    1. Check market hours (9:15 AM - 3:30 PM)
    2. Check time window (skip first/last 15 mins)
    3. Check no existing position
    4. Check no pending order
    5. Check cooldown (no re-entry same day)
    6. Check max positions limit
    7. Calculate position size
    8. Check available capital
    9. Place order if all pass
    
    All decisions logged to trade_logs table.
    """
    
    def __init__(
        self,
        database: IDatabase,
        order_manager: OrderManager,
        position_manager: PositionManager,
        capital_manager: CapitalManager,
        hours: Optional[TradingHours] = None,
        dry_run: bool = False
    ):
        self.db = database
        self.order_manager = order_manager
        self.position_manager = position_manager
        self.capital_manager = capital_manager
        self.hours = hours or TradingHours()
        self.dry_run = dry_run  # Paper trading mode
    
    # ================================================================
    # MAIN EXECUTION
    # ================================================================
    
    async def execute_signal(
        self,
        signal: Signal,
        strategy_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        Execute trading signal with all guardrails.
        
        Args:
            signal: Trading signal
            strategy_name: Name of strategy that generated signal
            metadata: Additional metadata
        
        Returns:
            ExecutionResult with status and details
        """
        try:
            current_time = datetime.now()
            
            # ============================================================
            # GUARDRAIL 1: Check market hours
            # ============================================================
            if not self._is_market_open(current_time):
                result = ExecutionResult(
                    status=ExecutionStatus.IGNORED,
                    decision="IGNORE",
                    reason="Market closed"
                )
                await self._log_decision(signal, strategy_name, result, metadata)
                return result
            
            # ============================================================
            # GUARDRAIL 2: Check time window
            # ============================================================
            if not self._is_valid_time_window(current_time):
                result = ExecutionResult(
                    status=ExecutionStatus.IGNORED,
                    decision="IGNORE",
                    reason="Outside trading window (skip first/last 15 mins)"
                )
                await self._log_decision(signal, strategy_name, result, metadata)
                return result
            
            # ============================================================
            # GUARDRAIL 3: Check existing position (for BUY signals)
            # ============================================================
            if signal.signal_type == "BUY":
                has_position = await self.position_manager.has_position(signal.symbol)
                if has_position:
                    result = ExecutionResult(
                        status=ExecutionStatus.IGNORED,
                    decision="IGNORE",
                        reason=f"Already have position in {signal.symbol}"
                    )
                    await self._log_decision(signal, strategy_name, result, metadata)
                    return result
            
            # ============================================================
            # GUARDRAIL 4: Check pending order
            # ============================================================
            transaction_type = "BUY" if signal.signal_type == "BUY" else "SELL"
            has_pending = await self.order_manager.has_pending_order(
                signal.symbol,
                transaction_type
            )
            if has_pending:
                result = ExecutionResult(
                    status=ExecutionStatus.IGNORED,
                    decision="IGNORE",
                    reason=f"Pending {transaction_type} order exists for {signal.symbol}"
                )
                await self._log_decision(signal, strategy_name, result, metadata)
                return result
            
            # ============================================================
            # GUARDRAIL 5: Check cooldown (for BUY signals)
            # ============================================================
            if signal.signal_type == "BUY":
                in_cooldown = await self._check_cooldown(signal.symbol, strategy_name)
                if in_cooldown:
                    result = ExecutionResult(
                        status=ExecutionStatus.IGNORED,
                    decision="IGNORE",
                        reason=f"{signal.symbol} in cooldown (no re-entry same day)"
                    )
                    await self._log_decision(signal, strategy_name, result, metadata)
                    return result
            
            # ============================================================
            # GUARDRAIL 6: Check max positions limit (for BUY signals)
            # ============================================================
            if signal.signal_type == "BUY":
                can_open = await self.capital_manager.check_position_limit()
                if not can_open:
                    result = ExecutionResult(
                        status=ExecutionStatus.IGNORED,
                    decision="IGNORE",
                        reason="Max positions limit reached"
                    )
                    await self._log_decision(signal, strategy_name, result, metadata)
                    return result
            
            # ============================================================
            # GUARDRAIL 7: Calculate position size
            # ============================================================
            if signal.signal_type == "BUY":
                quantity = await self.capital_manager.calculate_position_size(
                    entry_price=signal.price,
                    stop_loss=signal.stop_loss
                )
            else:
                # For SELL signals, get quantity from existing position
                position = await self.position_manager.get_position(signal.symbol)
                if not position:
                    result = ExecutionResult(
                        status=ExecutionStatus.IGNORED,
                    decision="IGNORE",
                        reason=f"No position found to exit for {signal.symbol}"
                    )
                    await self._log_decision(signal, strategy_name, result, metadata)
                    return result
                quantity = position['quantity']
            
            # ============================================================
            # GUARDRAIL 8: Check available capital (for BUY signals)
            # ============================================================
            if signal.signal_type == "BUY":
                required_capital = signal.price * quantity
                can_allocate = await self.capital_manager.can_allocate(required_capital)
                if not can_allocate:
                    result = ExecutionResult(
                        status=ExecutionStatus.IGNORED,
                    decision="IGNORE",
                        reason="Insufficient capital"
                    )
                    await self._log_decision(signal, strategy_name, result, metadata)
                    return result
                
                # Check risk limit
                risk = abs(signal.price - signal.stop_loss) * quantity
                within_risk = await self.capital_manager.check_risk_limit(risk)
                if not within_risk:
                    result = ExecutionResult(
                        status=ExecutionStatus.IGNORED,
                    decision="IGNORE",
                        reason="Risk limit exceeded"
                    )
                    await self._log_decision(signal, strategy_name, result, metadata)
                    return result
            
            # ============================================================
            # GUARDRAIL 9: Place order
            # ============================================================
            if self.dry_run:
                logger.info(
                    f"[DRY RUN] Would place {signal.signal_type} order: "
                    f"{signal.symbol} x{quantity} @ ₹{signal.price:.2f}"
                )
                result = ExecutionResult(
                    status=ExecutionStatus.EXECUTED,
                    decision="EXECUTE",
                    reason="Order placed (DRY RUN)",
                    quantity=quantity
                )
            else:
                # Place actual order
                order_id = await self.order_manager.place_order(
                    signal=signal,
                    quantity=quantity,
                    strategy_name=strategy_name,
                    order_type="MARKET",  # Use MARKET for simplicity
                    product="MIS"  # Intraday
                )
                
                if order_id:
                    result = ExecutionResult(
                        status=ExecutionStatus.EXECUTED,
                    decision="EXECUTE",
                        reason="Order placed successfully",
                        order_id=order_id,
                        quantity=quantity
                    )
                    
                    # Add cooldown for BUY orders
                    if signal.signal_type == "BUY":
                        await self._add_cooldown(signal.symbol, strategy_name)
                else:
                    result = ExecutionResult(
                        status=ExecutionStatus.FAILED,
                    decision="FAILED",
                        reason="Order placement failed",
                        error="No order_id returned"
                    )
            
            # Log decision
            await self._log_decision(signal, strategy_name, result, metadata)
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing signal: {e}", exc_info=True)
            result = ExecutionResult(
                status=ExecutionStatus.FAILED,
                    decision="FAILED",
                reason="Execution error",
                error=str(e)
            )
            await self._log_decision(signal, strategy_name, result, metadata)
            return result
    
    # ================================================================
    # TIME CHECKS
    # ================================================================
    
    def _is_market_open(self, current_time: datetime) -> bool:
        """Check if market is currently open"""
        current_time_only = current_time.time()
        
        # Check if within market hours
        if (current_time_only < self.hours.market_open or 
            current_time_only > self.hours.market_close):
            return False
        
        # Check if weekday (Monday=0, Sunday=6)
        if current_time.weekday() >= 5:  # Saturday or Sunday
            return False
        
        return True
    
    def _is_valid_time_window(self, current_time: datetime) -> bool:
        """
        Check if current time is in valid trading window.
        Skip first 15 and last 15 minutes.
        """
        current_time_only = current_time.time()
        
        # Calculate skip windows
        skip_until = time(
            self.hours.market_open.hour,
            self.hours.market_open.minute + self.hours.skip_first_minutes
        )
        
        skip_from = time(
            self.hours.market_close.hour,
            self.hours.market_close.minute - self.hours.skip_last_minutes
        )
        
        # Check if in skip windows
        if current_time_only < skip_until:
            return False
        
        if current_time_only > skip_from:
            return False
        
        return True
    
    def should_exit_all_positions(self, current_time: datetime) -> bool:
        """Check if it's time to exit all positions (3:20 PM)"""
        return current_time.time() >= self.hours.auto_exit_time
    
    # ================================================================
    # COOLDOWN MANAGEMENT
    # ================================================================
    
    async def _check_cooldown(self, symbol: str, strategy_name: str) -> bool:
        """
        Check if symbol is in cooldown for strategy.
        
        Returns:
            True if in cooldown
        """
        try:
            result = await self.db.fetch_one(
                """
                SELECT * FROM cooldown_tracker
                WHERE symbol = $1
                AND strategy_name = $2
                AND cooldown_until > $3
                """,
                {
                    "1": signal.symbol,
                    "2": strategy_name,
                    "3": datetime.now()
                }
            )
            
            return result is not None
            
        except Exception as e:
            logger.error(f"Error checking cooldown: {e}")
            return False
    
    async def _add_cooldown(
        self,
        symbol: str,
        strategy_name: str,
        hours: int = 24
    ):
        """
        Add cooldown for symbol.
        
        Args:
            symbol: Stock symbol
            strategy_name: Strategy name
            hours: Cooldown hours (default: 24 - no re-entry same day)
        """
        try:
            from datetime import timedelta
            
            cooldown_until = datetime.now() + timedelta(hours=hours)
            
            await self.db.insert("cooldown_tracker", {
                "symbol": symbol,
                "strategy_name": strategy_name,
                "reason": "Position opened",
                "cooldown_until": cooldown_until
            })
            
            logger.debug(f"Cooldown added: {symbol} ({strategy_name}) until {cooldown_until}")
            
        except Exception as e:
            logger.error(f"Error adding cooldown: {e}")
    
    # ================================================================
    # DECISION LOGGING
    # ================================================================
    
    async def _log_decision(
        self,
        signal: Signal,
        strategy_name: str,
        result: ExecutionResult,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log execution decision to trade_logs.
        
        Args:
            signal: Trading signal
            strategy_name: Strategy name
            result: Execution result
            metadata: Additional metadata
        """
        try:
            # Determine action based on result
            if result.status == ExecutionStatus.EXECUTED:
                action = "ORDER_PLACED"
            elif result.status == ExecutionStatus.IGNORED:
                action = "SIGNAL_IGNORED"
            else:
                action = "EXECUTION_FAILED"
            
            # Build log entry
            log_data = {
                "timestamp": datetime.now(),
                "log_type": action,
                "symbol": signal.symbol,
                "strategy_name": strategy_name,
                "decision": result.status.value if result.status else "UNKNOWN",
                "reason": result.reason,
                "signal_id": None,
                "order_id": result.order_id,
                "position_id": None,
                "data": {
                    "signal": {
                        "price": signal.price,
                        "signal_type": signal.signal_type,
                        "stop_loss": signal.stop_loss,
                        "target": signal.target,
                        "reason": signal.reason
                    },
                    "strategy_metadata": metadata,
                    "error": result.error
                }
            }
            
            await self.db.insert("trade_logs", log_data)
            
            logger.info(
                f"Decision logged: {action} - {signal.symbol} "
                f"({signal.signal_type}) - {result.reason}"
            )
            
        except Exception as e:
            logger.error(f"Error logging decision: {e}")
    
    # ================================================================
    # BATCH OPERATIONS
    # ================================================================
    
    async def execute_exit_signals(
        self,
        exit_signals: list,
        strategy_name: str = "AUTO_EXIT"
    ) -> list:
        """
        Execute multiple exit signals (e.g., from position monitoring).
        
        Args:
            exit_signals: List of exit signals
            strategy_name: Strategy name for logging
        
        Returns:
            List of ExecutionResult
        """
        results = []
        
        for signal in exit_signals:
            result = await self.execute_signal(
                signal=signal,
                strategy_name=strategy_name,
                metadata={"auto_exit": True}
            )
            results.append(result)
        
        return results
    
    async def get_execution_stats(self) -> dict:
        """
        Get execution statistics for today.
        
        Returns:
            Statistics dictionary
        """
        try:
            from datetime import date
            
            result = await self.db.fetch_one(
                """
                SELECT 
                    COUNT(*) as total_signals,
                    SUM(CASE WHEN log_type = 'ORDER_PLACED' THEN 1 ELSE 0 END) as executed,
                    SUM(CASE WHEN log_type = 'SIGNAL_IGNORED' THEN 1 ELSE 0 END) as ignored,
                    SUM(CASE WHEN log_type = 'EXECUTION_FAILED' THEN 1 ELSE 0 END) as failed
                FROM trade_logs
                WHERE DATE(timestamp) = $1
                """,
                {"1": date.today()}
            )
            
            return result or {
                "total_signals": 0,
                "executed": 0,
                "ignored": 0,
                "failed": 0
            }
            
        except Exception as e:
            logger.error(f"Error getting execution stats: {e}")
            return {}
