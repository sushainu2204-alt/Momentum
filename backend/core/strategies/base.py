"""Base strategy interface"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import pandas as pd


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    Implements Strategy Pattern for pluggable algorithms.
    """
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def calculate_indicators(self, prices: pd.Series) -> Tuple:
        """
        Calculate strategy indicators from price series.
        
        Args:
            prices: Series of prices
            
        Returns:
            Tuple of indicator values
        """
        pass
    
    @abstractmethod
    def generate_signal(self, current_indicators: Tuple, previous_indicators: Tuple) -> Optional[str]:
        """
        Generate trading signal based on indicator values.
        
        Args:
            current_indicators: Current indicator values
            previous_indicators: Previous indicator values
            
        Returns:
            "BUY", "SELL", or None
        """
        pass
    
    @abstractmethod
    def calculate_signals_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate signals for entire DataFrame (backtesting).
        
        Args:
            df: DataFrame with OHLC data
            
        Returns:
            DataFrame with added indicator and signal columns
        """
        pass
    
    @property
    @abstractmethod
    def min_data_points(self) -> int:
        """Minimum number of data points required for calculation"""
        pass
