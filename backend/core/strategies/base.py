"""
Base Strategy Interface

Defines the contract for all trading strategies.
Implements Strategy Pattern for pluggable trading algorithms.

Usage:
    class MyStrategy(BaseStrategy):
        def apply_filters(self, candidate, stock_df) -> bool:
            # Check if candidate passes strategy filters
            return True
        
        def should_enter(self, candidate, stock_df, current_time) -> Optional[Signal]:
            # Generate entry signal if conditions met
            return signal
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
import pandas as pd
import logging

from backend.config import BaseStrategyConfig

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    Implements Strategy Pattern for pluggable algorithms.
    Each strategy is responsible for:
    1. Filtering candidates (apply_filters)
    2. Generating entry signals (should_enter)
    3. Generating exit signals (should_exit)
    4. Calculating indicators (calculate_indicators)
    
    Strategies should be pure business logic - no I/O operations.
    """
    
    def __init__(self, config: BaseStrategyConfig):
        """
        Initialize strategy with configuration.
        
        Args:
            config: Strategy-specific configuration
        """
        self.config = config
        self.name = config.name
        self.description = config.description
    
    # ================================================================
    # REQUIRED METHODS (must implement in concrete strategies)
    # ================================================================
    
    @abstractmethod
    def apply_filters(
        self,
        candidate: Any,  # Candidate type from models
        stock_df: pd.DataFrame
    ) -> bool:
        """
        Apply strategy-specific filters to a candidate.
        
        This method should check all entry criteria and return
        True only if the candidate passes all filters.
        
        Args:
            candidate: Stock candidate from screener
            stock_df: Historical OHLCV data with indicators
        
        Returns:
            True if candidate passes all filters
        """
        pass
    
    @abstractmethod
    def should_enter(
        self,
        candidate: Any,  # Candidate type from models
        stock_df: pd.DataFrame,
        current_time: datetime
    ) -> Optional[Any]:  # Returns Signal or None
        """
        Generate BUY signal if entry conditions are met.
        
        Called only for candidates that passed apply_filters().
        
        Args:
            candidate: Stock candidate that passed filters
            stock_df: Historical OHLCV data with indicators
            current_time: Current timestamp
        
        Returns:
            Signal object if should enter, None otherwise
        """
        pass
    
    @property
    @abstractmethod
    def min_data_points(self) -> int:
        """
        Minimum number of data points required for strategy.
        
        Used to validate that enough historical data is available
        before applying filters or generating signals.
        """
        pass
    
    # ================================================================
    # OPTIONAL METHODS (override if needed)
    # ================================================================
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate strategy-specific indicators on DataFrame.
        
        Override this method to add indicator columns to the DataFrame.
        Default implementation returns DataFrame unchanged.
        
        Args:
            df: OHLCV DataFrame
        
        Returns:
            DataFrame with indicator columns added
        """
        return df
    
    def should_exit(
        self,
        position: Any,  # Position type from models
        current_price: float,
        current_time: datetime
    ) -> Optional[Any]:  # Returns Signal or None
        """
        Generate SELL signal if exit conditions are met.
        
        Override this method to implement custom exit logic.
        Default implementation checks standard SL/Target/Time exits.
        
        Args:
            position: Open position to evaluate
            current_price: Current market price
            current_time: Current timestamp
        
        Returns:
            Signal object if should exit, None otherwise
        """
        return None
    
    def calculate_position_size(
        self,
        capital: float,
        price: float
    ) -> int:
        """
        Calculate position size based on capital and price.
        
        Override to implement custom position sizing logic.
        Default uses position_size_pct from config.
        
        Args:
            capital: Available capital
            price: Current stock price
        
        Returns:
            Number of shares to buy
        """
        position_capital = capital * self.config.position_size_pct
        quantity = int(position_capital / price)
        return max(1, quantity)
    
    # ================================================================
    # BACKTESTING SUPPORT (optional)
    # ================================================================
    
    def calculate_signals_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate signals for entire DataFrame (for backtesting).
        
        Override to implement batch signal generation for backtesting.
        Default returns DataFrame unchanged.
        
        Args:
            df: DataFrame with OHLC data
        
        Returns:
            DataFrame with 'signal' column added (1=BUY, -1=SELL, 0=HOLD)
        """
        return df
    
    # ================================================================
    # LEGACY SUPPORT (for backward compatibility)
    # ================================================================
    
    def generate_signal(
        self,
        current_indicators: Tuple,
        previous_indicators: Tuple
    ) -> Optional[str]:
        """
        Generate trading signal based on indicator values.
        
        Legacy method for strategies using indicator-based signals.
        Prefer should_enter() and should_exit() for new strategies.
        
        Args:
            current_indicators: Current indicator values
            previous_indicators: Previous indicator values
        
        Returns:
            "BUY", "SELL", or None
        """
        return None
    
    # ================================================================
    # HELPER METHODS
    # ================================================================
    
    def _log_filter_result(
        self,
        symbol: str,
        filter_name: str,
        passed: bool,
        info: str
    ) -> None:
        """
        Log filter result with consistent formatting.
        
        Args:
            symbol: Stock symbol
            filter_name: Name of the filter
            passed: Whether filter passed
            info: Additional info about the result
        """
        status = "✅" if passed else "❌"
        logger.debug(f"{symbol}: {status} {filter_name} - {info}")
    
    def _is_entry_allowed(self, current_time: datetime) -> bool:
        """
        Check if entry is allowed at current time.
        
        Args:
            current_time: Current timestamp
        
        Returns:
            True if within trading window
        """
        # Create cutoff times - ensure same timezone as current_time
        entry_cutoff = datetime.combine(
            current_time.date(),
            self.config.no_entry_after
        )
        market_open = datetime.combine(
            current_time.date(),
            self.config.market_open_time
        )
        
        # Handle timezone-aware datetimes
        if current_time.tzinfo is not None:
            entry_cutoff = entry_cutoff.replace(tzinfo=current_time.tzinfo)
            market_open = market_open.replace(tzinfo=current_time.tzinfo)
        
        return market_open <= current_time <= entry_cutoff
