"""
Strategy Configuration System

Per-strategy configuration with validation and defaults.
Follows Strategy Pattern with configurable parameters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import time


@dataclass
class BaseStrategyConfig(ABC):
    """
    Base class for all strategy configurations.
    
    Each strategy should extend this with its own parameters.
    """
    
    # Common parameters across all strategies
    name: str
    description: str
    enabled: bool = True
    
    @abstractmethod
    def validate(self) -> bool:
        """Validate configuration parameters"""
        pass


@dataclass
class EMACrossoverConfig(BaseStrategyConfig):
    """
    Configuration for EMA Crossover Strategy.
    
    Used by existing strategy_worker.py
    """
    
    name: str = "EMA Crossover"
    description: str = "Fast EMA crossing above/below Slow EMA"
    
    # EMA parameters
    fast_period: int = 9
    slow_period: int = 21
    
    # Buffer settings
    buffer_size: int = 200
    
    # Trading parameters
    position_size_pct: float = 0.95  # 95% of capital per trade
    
    def validate(self) -> bool:
        """Validate EMA config"""
        if self.fast_period >= self.slow_period:
            raise ValueError("Fast EMA period must be less than Slow EMA period")
        
        if self.buffer_size < max(self.fast_period, self.slow_period):
            raise ValueError(f"Buffer size must be >= {max(self.fast_period, self.slow_period)}")
        
        if not 0 < self.position_size_pct <= 1.0:
            raise ValueError("Position size must be between 0 and 1.0")
        
        return True


@dataclass
class TopGainersMomentumConfig(BaseStrategyConfig):
    """
    Configuration for Top Gainers Momentum Strategy.
    
    All parameters are configurable per the user's requirements.
    """
    
    name: str = "Top Gainers Momentum"
    description: str = "Buy 2-3% gainers with volume surge and trend filters"
    
    # ============================================================
    # SCREENING CRITERIA
    # ============================================================
    
    # % Gain filters
    min_gain_pct: float = 2.0        # Minimum % gain to consider
    max_gain_pct: float = 3.0        # Maximum % gain to consider
    max_open_gain_pct: float = 6.0   # Don't buy if already gained > this
    
    # ============================================================
    # VOLUME FILTERS
    # ============================================================
    
    # Daily volume surge
    volume_surge_multiplier: float = 2.0  # Current vol > 2x avg volume
    volume_lookback_days: int = 10        # Compare to 10-day avg
    
    # Candle volume surge
    candle_volume_lookback: int = 10      # Compare to last 10 candles
    
    # ============================================================
    # INDEX TREND FILTERS (NIFTY/BANK NIFTY)
    # ============================================================
    
    index_instrument_token: int = 256265  # NIFTY 50 by default
    index_ema_period: int = 50            # Index must be above 50 EMA
    index_rsi_period: int = 14            # RSI calculation period
    index_rsi_min: float = 55.0           # Index RSI must be > 55
    
    # ============================================================
    # STOCK MOMENTUM FILTERS
    # ============================================================
    
    stock_ema_period: int = 20            # Stock must be above 20 EMA
    check_vwap: bool = True               # Stock must be above VWAP
    check_candle_break: bool = True       # Current candle breaks previous high
    
    # ============================================================
    # RISK MANAGEMENT
    # ============================================================
    
    stop_loss_pct: float = 1.0            # 1% stop loss
    target_pct: float = 2.0               # 2% target
    trailing_stop: bool = False           # Enable trailing stop loss
    trailing_stop_pct: float = 0.5        # Trail by 0.5%
    
    # ============================================================
    # POSITION SIZING
    # ============================================================
    
    position_size_pct: float = 0.10       # 10% of capital per trade
    max_positions: int = 5                # Maximum concurrent positions
    
    # ============================================================
    # TIME FILTERS
    # ============================================================
    
    market_open_time: time = field(default_factory=lambda: time(9, 15))   # 9:15 AM
    market_close_time: time = field(default_factory=lambda: time(15, 30)) # 3:30 PM
    exit_time: time = field(default_factory=lambda: time(15, 20))         # 3:20 PM auto-exit
    
    # Don't enter trades after this time
    no_entry_after: time = field(default_factory=lambda: time(15, 00))    # 3:00 PM
    
    # ============================================================
    # SCANNING SETTINGS
    # ============================================================
    
    scan_interval_seconds: int = 60       # Scan every 1 minute
    universe_type: str = "fno"            # 'fno', 'nifty500', 'nifty200', 'custom'
    custom_symbols: Optional[List[str]] = None  # For universe_type='custom'
    
    # ============================================================
    # DATA SETTINGS
    # ============================================================
    
    timeframe: str = "5minute"            # 5-minute candles
    lookback_candles: int = 100           # Fetch last 100 candles for indicators
    
    def validate(self) -> bool:
        """Validate all configuration parameters"""
        
        # Gain filters
        if self.min_gain_pct >= self.max_gain_pct:
            raise ValueError("min_gain_pct must be < max_gain_pct")
        
        if self.max_open_gain_pct <= self.max_gain_pct:
            raise ValueError("max_open_gain_pct should be > max_gain_pct")
        
        # Volume filters
        if self.volume_surge_multiplier < 1.0:
            raise ValueError("volume_surge_multiplier must be >= 1.0")
        
        if self.volume_lookback_days < 1:
            raise ValueError("volume_lookback_days must be >= 1")
        
        # RSI filters
        if not 0 <= self.index_rsi_min <= 100:
            raise ValueError("index_rsi_min must be between 0 and 100")
        
        # Risk management
        if self.stop_loss_pct <= 0:
            raise ValueError("stop_loss_pct must be > 0")
        
        if self.target_pct <= 0:
            raise ValueError("target_pct must be > 0")
        
        if self.target_pct <= self.stop_loss_pct:
            print(f"⚠️  Warning: Target ({self.target_pct}%) <= Stop Loss ({self.stop_loss_pct}%). Risk:Reward < 1:1")
        
        # Position sizing
        if not 0 < self.position_size_pct <= 1.0:
            raise ValueError("position_size_pct must be between 0 and 1.0")
        
        if self.max_positions < 1:
            raise ValueError("max_positions must be >= 1")
        
        # Time filters
        if self.exit_time >= self.market_close_time:
            raise ValueError("exit_time must be before market_close_time")
        
        if self.no_entry_after >= self.exit_time:
            raise ValueError("no_entry_after must be before exit_time")
        
        # Universe
        if self.universe_type == "custom" and not self.custom_symbols:
            raise ValueError("custom_symbols required when universe_type='custom'")
        
        if self.universe_type not in ["fno", "nifty500", "nifty200", "custom"]:
            raise ValueError("universe_type must be one of: fno, nifty500, nifty200, custom")
        
        return True
    
    def get_risk_reward_ratio(self) -> float:
        """Calculate risk:reward ratio"""
        return self.target_pct / self.stop_loss_pct
    
    def get_max_capital_at_risk(self) -> float:
        """Calculate maximum capital at risk with all positions"""
        return self.position_size_pct * self.max_positions * self.stop_loss_pct
    
    def __str__(self) -> str:
        """Pretty print configuration"""
        return f"""
        ============================================================
        {self.name} Configuration
        ============================================================
        
        📊 Screening Criteria:
          • Gain Range: {self.min_gain_pct}% - {self.max_gain_pct}%
          • Max Open Gain: {self.max_open_gain_pct}%
          • Volume Surge: {self.volume_surge_multiplier}x ({self.volume_lookback_days} days)
        
        📈 Index Filters:
          • EMA Period: {self.index_ema_period}
          • RSI Period: {self.index_rsi_period}, Min: {self.index_rsi_min}
        
        📉 Stock Filters:
          • EMA Period: {self.stock_ema_period}
          • Check VWAP: {self.check_vwap}
          • Check Candle Break: {self.check_candle_break}
        
        ⚡ Risk Management:
          • Stop Loss: {self.stop_loss_pct}%
          • Target: {self.target_pct}%
          • Risk:Reward: 1:{self.get_risk_reward_ratio():.2f}
          • Trailing Stop: {self.trailing_stop}
        
        💰 Position Sizing:
          • Size per Trade: {self.position_size_pct * 100}%
          • Max Positions: {self.max_positions}
          • Max Capital at Risk: {self.get_max_capital_at_risk() * 100:.1f}%
        
        ⏰ Time Settings:
          • Market: {self.market_open_time} - {self.market_close_time}
          • Auto-Exit: {self.exit_time}
          • No Entry After: {self.no_entry_after}
        
        🔍 Scanning:
          • Universe: {self.universe_type.upper()}
          • Interval: {self.scan_interval_seconds}s
          • Timeframe: {self.timeframe}
        
        ============================================================
        """


@dataclass
class BullishFlagConfig(BaseStrategyConfig):
    """
    Configuration for Bullish Flag Momentum Strategy.
    
    Entry: After +2% move, wait for pullback, enter on breakout above flag
    """
    
    name: str = "Bullish Flag Momentum"
    description: str = "Enter on breakout after pullback following +2% move"
    
    # Flag pattern detection
    min_initial_move_pct: float = 2.0      # Minimum % move to form flag pole
    pullback_pct_min: float = 0.3          # Minimum pullback from high
    pullback_pct_max: float = 1.0          # Maximum pullback (>1% invalidates pattern)
    pullback_candles_min: int = 2          # Minimum candles in pullback
    pullback_candles_max: int = 5          # Maximum candles in pullback
    
    # Breakout confirmation
    breakout_threshold_pct: float = 0.1    # Break above flag high + 0.1%
    volume_multiplier: float = 1.3         # Volume on breakout > 1.3x average
    
    # Risk management
    stop_loss_pct: float = 0.8             # 0.8% stop loss
    target_pct: float = 1.8                # 1.8% target
    
    # Position sizing
    position_size_pct: float = 0.10
    max_positions: int = 5
    
    # Time filters
    market_open_time: time = field(default_factory=lambda: time(9, 15))
    market_close_time: time = field(default_factory=lambda: time(15, 30))
    exit_time: time = field(default_factory=lambda: time(15, 20))
    no_entry_after: time = field(default_factory=lambda: time(14, 30))
    
    # Data settings
    timeframe: str = "5minute"
    lookback_candles: int = 100
    
    def validate(self) -> bool:
        """Validate configuration"""
        if self.min_initial_move_pct <= 0:
            raise ValueError("min_initial_move_pct must be > 0")
        
        if self.pullback_pct_min >= self.pullback_pct_max:
            raise ValueError("pullback_pct_min must be < pullback_pct_max")
        
        if self.pullback_candles_min > self.pullback_candles_max:
            raise ValueError("pullback_candles_min must be <= pullback_candles_max")
        
        if self.stop_loss_pct <= 0 or self.target_pct <= 0:
            raise ValueError("stop_loss_pct and target_pct must be > 0")
        
        if not 0 < self.position_size_pct <= 1.0:
            raise ValueError("position_size_pct must be between 0 and 1.0")
        
        return True


@dataclass
class VWAPEMABreakoutConfig(BaseStrategyConfig):
    """
    Configuration for VWAP EMA Breakout Strategy.
    
    Entry: Price > VWAP & 20 EMA, 2-4% gain, breakout of previous candle high
    Exit: +1.5% target, -0.7% SL, 3:20 PM auto-exit
    """
    
    name: str = "VWAP EMA Breakout"
    description: str = "Breakout above previous candle high with VWAP & EMA confirmation"
    
    # Price change filters (from top gainers)
    min_gain_pct: float = 2.0              # Minimum gain %
    max_gain_pct: float = 4.0              # Maximum gain %
    
    # Technical indicators
    ema_period: int = 20                   # EMA period
    vwap_enabled: bool = True              # Require price > VWAP
    
    # Volume confirmation
    volume_multiplier: float = 1.5         # Volume > 1.5x average
    volume_lookback: int = 20              # Candles for avg volume
    
    # Breakout confirmation
    breakout_previous_high: bool = True    # Must break previous candle high
    
    # Risk management
    stop_loss_pct: float = 0.7             # 0.7% stop loss
    target_pct: float = 1.5                # 1.5% target
    
    # Position sizing
    position_size_pct: float = 0.10
    max_positions: int = 5
    
    # Time filters
    market_open_time: time = field(default_factory=lambda: time(9, 15))
    market_close_time: time = field(default_factory=lambda: time(15, 30))
    exit_time: time = field(default_factory=lambda: time(15, 20))
    no_entry_after: time = field(default_factory=lambda: time(14, 30))
    
    # Data settings
    timeframe: str = "5minute"
    lookback_candles: int = 100
    
    def validate(self) -> bool:
        """Validate configuration"""
        if self.min_gain_pct >= self.max_gain_pct:
            raise ValueError("min_gain_pct must be < max_gain_pct")
        
        if self.ema_period <= 0:
            raise ValueError("ema_period must be > 0")
        
        if self.volume_multiplier < 1.0:
            raise ValueError("volume_multiplier must be >= 1.0")
        
        if self.stop_loss_pct <= 0 or self.target_pct <= 0:
            raise ValueError("stop_loss_pct and target_pct must be > 0")
        
        if not 0 < self.position_size_pct <= 1.0:
            raise ValueError("position_size_pct must be between 0 and 1.0")
        
        return True


@dataclass
class VWAPBreakoutConfig(BaseStrategyConfig):
    """
    Configuration for VWAP Breakout Strategy.
    
    Entry: Stock breaks above VWAP with volume confirmation
    """
    
    name: str = "VWAP Breakout"
    description: str = "Enter when price breaks VWAP with high volume"
    
    # Volume confirmation
    volume_multiplier: float = 1.5         # Volume must be > 1.5x average
    volume_lookback_candles: int = 20      # Compare to last 20 candles
    
    # VWAP parameters
    vwap_breakout_pct: float = 0.2         # Price must be > VWAP + 0.2%
    
    # Risk management
    stop_loss_pct: float = 0.7             # 0.7% stop loss
    target_pct: float = 1.5                # 1.5% target
    
    # Position sizing
    position_size_pct: float = 0.10        # 10% of capital per trade
    max_positions: int = 5
    
    # Time filters
    market_open_time: time = field(default_factory=lambda: time(9, 15))
    market_close_time: time = field(default_factory=lambda: time(15, 30))
    exit_time: time = field(default_factory=lambda: time(15, 20))
    no_entry_after: time = field(default_factory=lambda: time(14, 30))
    
    # Data settings
    timeframe: str = "5minute"
    lookback_candles: int = 100
    
    def validate(self) -> bool:
        """Validate configuration"""
        if self.volume_multiplier < 1.0:
            raise ValueError("volume_multiplier must be >= 1.0")
        
        if self.stop_loss_pct <= 0 or self.target_pct <= 0:
            raise ValueError("stop_loss_pct and target_pct must be > 0")
        
        if self.target_pct <= self.stop_loss_pct:
            print(f"⚠️  Warning: Target ({self.target_pct}%) <= Stop Loss ({self.stop_loss_pct}%). Risk:Reward < 1:1")
        
        if not 0 < self.position_size_pct <= 1.0:
            raise ValueError("position_size_pct must be between 0 and 1.0")
        
        return True


# ============================================================
# STRATEGY CONFIG FACTORY
# ============================================================

class StrategyConfigFactory:
    """
    Factory for creating strategy configurations.
    
    Usage:
        config = StrategyConfigFactory.create('top_gainers_momentum')
        config = StrategyConfigFactory.create('ema_crossover', fast_period=5)
    """
    
    _strategies = {
        'ema_crossover': EMACrossoverConfig,
        'top_gainers_momentum': TopGainersMomentumConfig,
        'vwap_breakout': VWAPBreakoutConfig,
        'bullish_flag': BullishFlagConfig,
        'vwap_ema_breakout': VWAPEMABreakoutConfig,
    }
    
    @classmethod
    def create(cls, strategy_name: str, **kwargs) -> BaseStrategyConfig:
        """
        Create strategy configuration with optional overrides.
        
        Args:
            strategy_name: Strategy identifier
            **kwargs: Override default parameters
        
        Returns:
            Strategy configuration instance
        
        Example:
            config = StrategyConfigFactory.create(
                'top_gainers_momentum',
                min_gain_pct=1.5,
                max_gain_pct=2.5,
                stop_loss_pct=0.5
            )
        """
        if strategy_name not in cls._strategies:
            raise ValueError(f"Unknown strategy: {strategy_name}. Available: {list(cls._strategies.keys())}")
        
        config_class = cls._strategies[strategy_name]
        config = config_class(**kwargs)
        config.validate()
        
        return config
    
    @classmethod
    def register(cls, strategy_name: str, config_class: type):
        """Register new strategy configuration"""
        cls._strategies[strategy_name] = config_class
    
    @classmethod
    def list_strategies(cls) -> List[str]:
        """Get list of available strategies"""
        return list(cls._strategies.keys())
