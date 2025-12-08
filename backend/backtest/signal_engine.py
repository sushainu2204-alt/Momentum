"""
Signal Engine Module

Evaluates strategy rules at each timestamp and generates trading signals.
This is the brain that connects strategies to the backtest loop.

Features:
    - Strategy plugin architecture
    - Multi-strategy evaluation
    - Signal prioritization
    - Collision handling (multiple signals same timestamp)
    - Signal filtering and validation
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, date, time
from typing import Dict, List, Optional, Type, Any, Callable
import logging
from abc import ABC, abstractmethod

from backend.core.models import Signal, SignalType, Candidate
from backend.core.strategies.base import BaseStrategy
from backend.core.strategies.vwap_breakout import VWAPBreakoutStrategy
from backend.core.strategies.bullish_flag import BullishFlagStrategy
from backend.core.strategies.top_gainers_momentum import TopGainersMomentumStrategy
from backend.config import (
    VWAPBreakoutConfig,
    BullishFlagConfig, 
    TopGainersMomentumConfig
)

from .events import SignalEvent
from .config import BacktestConfig, TimeConfig

logger = logging.getLogger(__name__)


@dataclass
class BacktestSignal:
    """
    Extended signal for backtesting with additional metadata.
    """
    symbol: str
    instrument_token: int
    signal_type: SignalType
    price: float
    timestamp: datetime
    strategy_id: str
    strategy_name: str
    
    # Entry levels
    stop_loss: float
    target: float
    quantity: Optional[int] = None
    
    # Signal metadata
    reason: str = ""
    confidence: float = 1.0
    priority: int = 0
    
    # Features at signal time
    features: Dict[str, float] = field(default_factory=dict)
    
    def to_signal_event(self) -> SignalEvent:
        """Convert to SignalEvent."""
        return SignalEvent(
            timestamp=self.timestamp,
            symbol=self.symbol,
            instrument_token=self.instrument_token,
            signal_type=self.signal_type.value,
            strategy_id=self.strategy_id,
            price=self.price,
            stop_loss=self.stop_loss,
            target=self.target,
            quantity=self.quantity,
            reason=self.reason,
            confidence=self.confidence,
            features=self.features
        )


class BacktestStrategyAdapter(ABC):
    """
    Adapter to make existing strategies work with backtester.
    
    Bridges the gap between live strategy interface and 
    backtest requirements.
    """
    
    def __init__(self, strategy_id: str, strategy_name: str):
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
    
    @abstractmethod
    def evaluate(
        self,
        symbol: str,
        instrument_token: int,
        current_candle: pd.Series,
        historical_df: pd.DataFrame,
        current_time: datetime
    ) -> Optional[BacktestSignal]:
        """
        Evaluate strategy rules for a symbol.
        
        Args:
            symbol: Stock symbol
            instrument_token: Instrument token
            current_candle: Current candle data
            historical_df: Historical data with features
            current_time: Current timestamp
        
        Returns:
            BacktestSignal if conditions met, None otherwise
        """
        pass
    
    def get_config(self) -> Any:
        """Get strategy configuration."""
        return None


class VWAPBreakoutAdapter(BacktestStrategyAdapter):
    """Adapter for VWAP Breakout Strategy."""
    
    def __init__(self, config: Optional[VWAPBreakoutConfig] = None):
        super().__init__("vwap_breakout", "VWAP Breakout")
        self.config = config or VWAPBreakoutConfig()
        self.strategy = VWAPBreakoutStrategy(self.config)
    
    def evaluate(
        self,
        symbol: str,
        instrument_token: int,
        current_candle: pd.Series,
        historical_df: pd.DataFrame,
        current_time: datetime
    ) -> Optional[BacktestSignal]:
        """Evaluate VWAP breakout conditions."""
        
        if historical_df.empty or len(historical_df) < 20:
            return None
        
        # Create candidate from current candle
        candidate = Candidate(
            symbol=symbol,
            instrument_token=instrument_token,
            current_price=current_candle['close'],
            gain_pct=current_candle.get('intraday_return', 0.0),
            volume=int(current_candle['volume']),
            avg_volume=historical_df['volume'].mean(),
            timestamp=current_time,
            open_price=current_candle['open'],
            high_price=current_candle['high'],
            low_price=current_candle['low']
        )
        
        # Check strategy filters
        try:
            if not self.strategy.apply_filters(candidate, historical_df):
                return None
            
            # Generate signal
            signal = self.strategy.should_enter(candidate, historical_df, current_time)
            
            if signal:
                return BacktestSignal(
                    symbol=symbol,
                    instrument_token=instrument_token,
                    signal_type=signal.signal_type,
                    price=signal.price,
                    timestamp=current_time,
                    strategy_id=self.strategy_id,
                    strategy_name=self.strategy_name,
                    stop_loss=signal.stop_loss or self._calculate_sl(signal.price),
                    target=signal.target or self._calculate_target(signal.price),
                    reason=signal.reason or "VWAP breakout with volume confirmation",
                    features=self._extract_features(current_candle, historical_df)
                )
        except Exception as e:
            logger.debug(f"VWAP strategy error for {symbol}: {e}")
        
        return None
    
    def _calculate_sl(self, price: float) -> float:
        """Calculate stop loss."""
        return price * (1 - self.config.stop_loss_pct / 100)
    
    def _calculate_target(self, price: float) -> float:
        """Calculate target."""
        return price * (1 + self.config.target_pct / 100)
    
    def _extract_features(
        self,
        candle: pd.Series,
        df: pd.DataFrame
    ) -> Dict[str, float]:
        """Extract relevant features."""
        features = {}
        
        for col in ['vwap', 'ema_20', 'ema_50', 'volume_ratio', 'rsi']:
            if col in candle:
                features[col] = float(candle[col])
        
        return features
    
    def get_config(self) -> VWAPBreakoutConfig:
        return self.config


class BullishFlagAdapter(BacktestStrategyAdapter):
    """Adapter for Bullish Flag Strategy."""
    
    def __init__(self, config: Optional[BullishFlagConfig] = None):
        super().__init__("bullish_flag", "Bullish Flag")
        self.config = config or BullishFlagConfig()
        self.strategy = BullishFlagStrategy(self.config)
    
    def evaluate(
        self,
        symbol: str,
        instrument_token: int,
        current_candle: pd.Series,
        historical_df: pd.DataFrame,
        current_time: datetime
    ) -> Optional[BacktestSignal]:
        """Evaluate bullish flag conditions."""
        
        if historical_df.empty or len(historical_df) < 15:
            return None
        
        candidate = Candidate(
            symbol=symbol,
            instrument_token=instrument_token,
            current_price=current_candle['close'],
            gain_pct=current_candle.get('intraday_return', 0.0),
            volume=int(current_candle['volume']),
            avg_volume=historical_df['volume'].mean(),
            timestamp=current_time,
            open_price=current_candle['open'],
            high_price=current_candle['high'],
            low_price=current_candle['low']
        )
        
        try:
            if not self.strategy.apply_filters(candidate, historical_df):
                return None
            
            signal = self.strategy.should_enter(candidate, historical_df, current_time)
            
            if signal:
                return BacktestSignal(
                    symbol=symbol,
                    instrument_token=instrument_token,
                    signal_type=signal.signal_type,
                    price=signal.price,
                    timestamp=current_time,
                    strategy_id=self.strategy_id,
                    strategy_name=self.strategy_name,
                    stop_loss=signal.stop_loss or self._calculate_sl(signal.price),
                    target=signal.target or self._calculate_target(signal.price),
                    reason=signal.reason or "Bullish flag breakout",
                    features=self._extract_features(current_candle, historical_df)
                )
        except Exception as e:
            logger.debug(f"Bullish flag strategy error for {symbol}: {e}")
        
        return None
    
    def _calculate_sl(self, price: float) -> float:
        return price * (1 - self.config.stop_loss_pct / 100)
    
    def _calculate_target(self, price: float) -> float:
        return price * (1 + self.config.target_pct / 100)
    
    def _extract_features(
        self,
        candle: pd.Series,
        df: pd.DataFrame
    ) -> Dict[str, float]:
        features = {}
        for col in ['max_gain_5', 'pullback_pct', 'volume_ratio']:
            if col in candle:
                features[col] = float(candle[col])
        return features
    
    def get_config(self) -> BullishFlagConfig:
        return self.config


class TopGainersMomentumAdapter(BacktestStrategyAdapter):
    """Adapter for Top Gainers Momentum Strategy."""
    
    def __init__(self, config: Optional[TopGainersMomentumConfig] = None):
        super().__init__("top_gainers", "Top Gainers Momentum")
        self.config = config or TopGainersMomentumConfig()
        self.strategy = TopGainersMomentumStrategy(self.config)
        
        # Index data for trend check (will be set externally)
        self._index_df: Optional[pd.DataFrame] = None
    
    def set_index_data(self, index_df: pd.DataFrame) -> None:
        """Set index data for trend filtering."""
        self._index_df = index_df
    
    def evaluate(
        self,
        symbol: str,
        instrument_token: int,
        current_candle: pd.Series,
        historical_df: pd.DataFrame,
        current_time: datetime
    ) -> Optional[BacktestSignal]:
        """Evaluate top gainers momentum conditions."""
        
        if historical_df.empty or len(historical_df) < 20:
            return None
        
        # Check gain range
        intraday_return = current_candle.get('intraday_return', 0.0)
        if not (self.config.min_gain_pct <= intraday_return <= self.config.max_gain_pct):
            return None
        
        # Avoid upper circuit
        if intraday_return >= self.config.max_open_gain_pct:
            return None
        
        candidate = Candidate(
            symbol=symbol,
            instrument_token=instrument_token,
            current_price=current_candle['close'],
            gain_pct=intraday_return,
            volume=int(current_candle['volume']),
            avg_volume=historical_df['volume'].mean(),
            timestamp=current_time,
            open_price=current_candle['open'],
            high_price=current_candle['high'],
            low_price=current_candle['low']
        )
        
        try:
            # Use simplified filter check for backtest
            # (Index filter skipped if no index data)
            if not self._check_filters(candidate, historical_df):
                return None
            
            return BacktestSignal(
                symbol=symbol,
                instrument_token=instrument_token,
                signal_type=SignalType.BUY,
                price=current_candle['close'],
                timestamp=current_time,
                strategy_id=self.strategy_id,
                strategy_name=self.strategy_name,
                stop_loss=self._calculate_sl(current_candle['close']),
                target=self._calculate_target(current_candle['close']),
                reason=f"Top gainer +{intraday_return:.1f}% with momentum",
                features=self._extract_features(current_candle, historical_df)
            )
        except Exception as e:
            logger.debug(f"Top gainers strategy error for {symbol}: {e}")
        
        return None
    
    def _check_filters(
        self,
        candidate: Candidate,
        df: pd.DataFrame
    ) -> bool:
        """Check momentum filters."""
        
        # Volume surge
        if candidate.avg_volume > 0:
            volume_ratio = candidate.volume / candidate.avg_volume
            if volume_ratio < self.config.volume_surge_multiplier:
                return False
        
        # Price above EMA
        if 'ema_20' in df.columns:
            current_ema = df['ema_20'].iloc[-1]
            if candidate.current_price <= current_ema:
                return False
        
        # Price above VWAP
        if self.config.check_vwap and 'vwap' in df.columns:
            current_vwap = df['vwap'].iloc[-1]
            if candidate.current_price <= current_vwap:
                return False
        
        return True
    
    def _calculate_sl(self, price: float) -> float:
        return price * (1 - self.config.stop_loss_pct / 100)
    
    def _calculate_target(self, price: float) -> float:
        return price * (1 + self.config.target_pct / 100)
    
    def _extract_features(
        self,
        candle: pd.Series,
        df: pd.DataFrame
    ) -> Dict[str, float]:
        features = {
            'gain_pct': candle.get('intraday_return', 0.0)
        }
        for col in ['vwap', 'ema_20', 'volume_ratio']:
            if col in candle:
                features[col] = float(candle[col])
        return features
    
    def get_config(self) -> TopGainersMomentumConfig:
        return self.config


class SignalEngine:
    """
    Signal generation engine.
    
    Coordinates strategy evaluation and signal generation
    across all symbols at each timestamp.
    
    Usage:
        engine = SignalEngine(config)
        engine.register_strategy('vwap_breakout', VWAPBreakoutAdapter())
        
        signals = engine.scan(timestamp, market_data, features_data)
    """
    
    # Strategy registry
    STRATEGY_REGISTRY: Dict[str, Type[BacktestStrategyAdapter]] = {
        'vwap_breakout': VWAPBreakoutAdapter,
        'bullish_flag': BullishFlagAdapter,
        'top_gainers': TopGainersMomentumAdapter,
    }
    
    def __init__(self, config: BacktestConfig):
        """
        Initialize signal engine.
        
        Args:
            config: Backtest configuration
        """
        self.config = config
        self.time_config = config.time
        
        # Active strategies
        self._strategies: Dict[str, BacktestStrategyAdapter] = {}
        
        # Signal history for analysis
        self._signal_history: List[BacktestSignal] = []
        
        # Initialize configured strategies
        self._initialize_strategies()
    
    def _initialize_strategies(self) -> None:
        """Initialize strategies from config."""
        for strategy_id in self.config.strategies:
            if strategy_id in self.STRATEGY_REGISTRY:
                adapter_class = self.STRATEGY_REGISTRY[strategy_id]
                self._strategies[strategy_id] = adapter_class()
                logger.info(f"Initialized strategy: {strategy_id}")
            else:
                logger.warning(f"Unknown strategy: {strategy_id}")
    
    def register_strategy(
        self,
        strategy_id: str,
        adapter: BacktestStrategyAdapter
    ) -> None:
        """
        Register a strategy adapter.
        
        Args:
            strategy_id: Unique strategy identifier
            adapter: Strategy adapter instance
        """
        self._strategies[strategy_id] = adapter
        logger.info(f"Registered strategy: {strategy_id}")
    
    def unregister_strategy(self, strategy_id: str) -> None:
        """Remove a strategy."""
        if strategy_id in self._strategies:
            del self._strategies[strategy_id]
    
    def scan(
        self,
        timestamp: datetime,
        market_data: Dict[str, pd.Series],
        features_data: Dict[str, pd.DataFrame],
        existing_positions: List[str] = None
    ) -> List[BacktestSignal]:
        """
        Scan all symbols for signals at current timestamp.
        
        Args:
            timestamp: Current timestamp
            market_data: Current candle for each symbol
            features_data: Historical data with features for each symbol
            existing_positions: Symbols with open positions (to skip)
        
        Returns:
            List of signals generated
        """
        existing_positions = existing_positions or []
        signals: List[BacktestSignal] = []
        
        # Check time constraints
        if not self._is_valid_entry_time(timestamp):
            return signals
        
        # Evaluate each symbol with each strategy
        for symbol, current_candle in market_data.items():
            # Skip if already have position
            if symbol in existing_positions:
                continue
            
            # Get historical data for this symbol
            historical_df = features_data.get(symbol)
            if historical_df is None or historical_df.empty:
                continue
            
            # Get instrument token (could be from mapping)
            instrument_token = self._get_instrument_token(symbol)
            
            # Evaluate each strategy
            for strategy_id, adapter in self._strategies.items():
                # Check if strategy is enabled
                strategy_config = self.config.strategy_configs.get(strategy_id)
                if strategy_config and not strategy_config.enabled:
                    continue
                
                try:
                    signal = adapter.evaluate(
                        symbol=symbol,
                        instrument_token=instrument_token,
                        current_candle=current_candle,
                        historical_df=historical_df,
                        current_time=timestamp
                    )
                    
                    if signal:
                        signals.append(signal)
                        self._signal_history.append(signal)
                        
                        logger.debug(
                            f"Signal: {signal.strategy_name} | {symbol} | "
                            f"₹{signal.price:.2f} | {signal.reason}"
                        )
                
                except Exception as e:
                    logger.error(f"Error evaluating {strategy_id} for {symbol}: {e}")
        
        # Sort signals by priority
        signals = self._prioritize_signals(signals)
        
        return signals
    
    def _is_valid_entry_time(self, timestamp: datetime) -> bool:
        """Check if timestamp is within valid entry window."""
        current_time = timestamp.time()
        
        return (
            self.time_config.entry_start_time <= current_time <= 
            self.time_config.entry_end_time
        )
    
    def _get_instrument_token(self, symbol: str) -> int:
        """Get instrument token for symbol."""
        # In backtest, we use a hash of symbol as token
        # In production, this would come from broker API
        return hash(symbol) % 10000000
    
    def _prioritize_signals(
        self,
        signals: List[BacktestSignal]
    ) -> List[BacktestSignal]:
        """
        Sort signals by priority.
        
        Priority factors:
        1. Strategy weight
        2. Signal confidence
        3. Volume
        """
        def priority_score(signal: BacktestSignal) -> float:
            strategy_config = self.config.strategy_configs.get(signal.strategy_id)
            weight = strategy_config.weight if strategy_config else 1.0
            
            volume_factor = signal.features.get('volume_ratio', 1.0)
            
            return weight * signal.confidence * min(volume_factor, 3.0)
        
        return sorted(signals, key=priority_score, reverse=True)
    
    def get_signal_history(self) -> List[BacktestSignal]:
        """Get all signals generated."""
        return self._signal_history
    
    def get_signals_by_strategy(
        self,
        strategy_id: str
    ) -> List[BacktestSignal]:
        """Get signals for a specific strategy."""
        return [
            s for s in self._signal_history
            if s.strategy_id == strategy_id
        ]
    
    def get_signals_by_symbol(
        self,
        symbol: str
    ) -> List[BacktestSignal]:
        """Get signals for a specific symbol."""
        return [
            s for s in self._signal_history
            if s.symbol == symbol
        ]
    
    def clear_history(self) -> None:
        """Clear signal history."""
        self._signal_history.clear()
    
    def get_strategy_stats(self) -> Dict[str, Dict[str, int]]:
        """Get signal statistics by strategy."""
        stats = {}
        
        for strategy_id in self._strategies:
            strategy_signals = self.get_signals_by_strategy(strategy_id)
            stats[strategy_id] = {
                'total_signals': len(strategy_signals),
                'unique_symbols': len(set(s.symbol for s in strategy_signals))
            }
        
        return stats
