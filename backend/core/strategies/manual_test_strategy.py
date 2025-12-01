"""
Manual Test Strategy

Simple strategy for controlled end-to-end testing.
Allows manual input of symbol, price, SL, target for validating full flow.

NOT FOR PRODUCTION - TESTING ONLY
"""

from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import logging

from backend.core.strategies.base import BaseStrategy
from backend.core.config.strategy_config import BaseStrategyConfig
from backend.models import Candidate, Signal, SignalType

logger = logging.getLogger(__name__)


class ManualTestConfig(BaseStrategyConfig):
    """Configuration for manual test strategy."""
    
    def __init__(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_pct: float = 2.0,
        target_pct: float = 3.0,
        quantity: int = 1,
        **kwargs
    ):
        """
        Initialize manual test config.
        
        Args:
            symbol: Stock symbol to test (e.g., "YESBANK")
            entry_price: Desired entry price
            stop_loss_pct: SL % below entry (default 2%)
            target_pct: Target % above entry (default 3%)
            quantity: Number of shares (default 1)
        """
        super().__init__(
            name="Manual Test",
            description=f"Manual test for {symbol.upper()}",
            **kwargs
        )
        self.symbol = symbol.upper()
        self.entry_price = entry_price
        self.stop_loss_pct = stop_loss_pct
        self.target_pct = target_pct
        self.quantity = quantity
        
    def validate(self) -> bool:
        """Validate configuration (required by base class)."""
        if self.entry_price <= 0:
            return False
        if self.stop_loss_pct <= 0 or self.stop_loss_pct >= 100:
            return False
        if self.target_pct <= 0 or self.target_pct >= 100:
            return False
        if self.quantity <= 0:
            return False
        return True
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        base_dict = super().to_dict()
        base_dict.update({
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "stop_loss_pct": self.stop_loss_pct,
            "target_pct": self.target_pct,
            "quantity": self.quantity
        })
        return base_dict


class ManualTestStrategy(BaseStrategy):
    """
    Manual test strategy for controlled testing.
    
    Flow:
    1. Gets manual symbol input
    2. Generates test signal with specified SL/Target
    3. Validates through all 9 guardrails
    4. Tests bracket order placement
    
    Use this to test system with minimal capital.
    """
    
    def __init__(self, config: ManualTestConfig):
        super().__init__(name=config.name)
        self.config: ManualTestConfig = config
    
    @property
    def min_data_points(self) -> int:
        """No data points needed for manual test."""
        return 0
    
    def calculate_indicators(self, prices) -> Tuple:
        """Not used in manual test."""
        return ()
    
    def generate_signal(self, current_indicators, previous_indicators) -> Optional[str]:
        """Not used in manual test."""
        return None
    
    def calculate_signals_dataframe(self, df) -> Any:
        """Not used in manual test."""
        return df
        
    def get_candidates(self) -> List[Candidate]:
        """
        Return single candidate from config.
        
        Returns:
            List with single manually specified candidate
        """
        logger.info(f"📋 Manual test candidate: {self.config.symbol}")
        
        candidate = Candidate(
            symbol=self.config.symbol,
            instrument_token=0,  # Will be fetched by worker
            current_price=self.config.entry_price,
            gain_pct=0.0,  # Not relevant for manual test
            volume=0,  # Not relevant for manual test
            avg_volume=0.0,
            timestamp=datetime.now()
        )
        
        return [candidate]
    
    def apply_filters(self, candidate: Candidate, df: Any) -> bool:
        """
        Always pass filters for manual test.
        
        Args:
            candidate: Test candidate
            df: Market data (not used)
        
        Returns:
            True (no filters in test mode)
        """
        logger.info(f"✅ Manual test - skipping filters for {candidate.symbol}")
        return True
    
    def generate_entry_signal(
        self,
        candidate: Candidate,
        df: Any
    ) -> Optional[Signal]:
        """
        Generate test signal with manual parameters.
        
        Args:
            candidate: Test candidate
            df: Market data (not used for manual test)
        
        Returns:
            Test signal with specified entry/SL/target
        """
        try:
            # Calculate SL and Target from percentages
            stop_loss = self.config.entry_price * (1 - self.config.stop_loss_pct / 100)
            target = self.config.entry_price * (1 + self.config.target_pct / 100)
            
            signal = Signal(
                timestamp=datetime.now(),
                symbol=self.config.symbol,
                instrument_token=candidate.instrument_token,
                signal_type=SignalType.BUY,
                price=self.config.entry_price,
                stop_loss=stop_loss,
                target=target,
                quantity=self.config.quantity,
                reason=f"Manual test entry (SL: {self.config.stop_loss_pct}%, Target: {self.config.target_pct}%)"
            )
            
            logger.info(
                f"🎯 Test signal generated:\n"
                f"   Symbol: {signal.symbol}\n"
                f"   Entry: ₹{signal.price:.2f}\n"
                f"   SL: ₹{signal.stop_loss:.2f} ({self.config.stop_loss_pct}%)\n"
                f"   Target: ₹{signal.target:.2f} ({self.config.target_pct}%)\n"
                f"   Quantity: {self.config.quantity}"
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"Error generating test signal: {e}")
            return None
