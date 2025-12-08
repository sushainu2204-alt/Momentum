"""
Backtest Configuration System

Centralized configuration for all backtest parameters.
Follows the existing pattern in backend/config/strategy_config.py
"""

from dataclasses import dataclass, field
from datetime import datetime, time, date
from typing import List, Optional, Dict, Any
from enum import Enum


class FillModelType(Enum):
    """Order fill model types."""
    NEXT_OPEN = "next_open"           # Fill at next candle open (realistic)
    SAME_CLOSE = "same_close"         # Fill at signal candle close
    VWAP_ESTIMATE = "vwap_estimate"   # Fill at estimated VWAP
    WORST_CASE = "worst_case"         # Fill at worst price in candle


class SlippageModel(Enum):
    """Slippage simulation models."""
    NONE = "none"
    FIXED = "fixed"               # Fixed percentage slippage
    VOLUME_BASED = "volume_based" # Higher slippage for low volume
    SPREAD_BASED = "spread_based" # Based on typical bid-ask spread


@dataclass
class ExecutionConfig:
    """
    Order execution and simulation configuration.
    """
    # Fill model
    fill_model: FillModelType = FillModelType.NEXT_OPEN
    
    # Slippage
    slippage_model: SlippageModel = SlippageModel.FIXED
    slippage_pct: float = 0.05           # 0.05% slippage
    slippage_ticks: int = 1              # Alternative: slippage in ticks
    
    # Spread simulation
    spread_pct: float = 0.02             # 0.02% spread
    
    # Commission/Brokerage
    commission_per_trade: float = 20.0   # Fixed commission per trade
    commission_pct: float = 0.0003       # 0.03% of trade value
    stt_pct: float = 0.001               # 0.1% STT on sell
    
    # Latency simulation
    latency_candles: int = 0             # Order delay in candles
    
    # Partial fills
    allow_partial_fills: bool = False
    min_fill_pct: float = 0.5            # Minimum 50% fill required


@dataclass
class RiskConfig:
    """
    Risk management configuration.
    """
    # Capital allocation
    initial_capital: float = 100000.0
    per_trade_capital_pct: float = 0.20  # 20% of capital per trade
    max_capital_per_trade: float = 50000.0  # Hard cap per trade
    
    # Position limits
    max_positions: int = 5               # Maximum concurrent positions
    max_positions_per_strategy: int = 2  # Max positions per strategy
    max_positions_per_symbol: int = 1    # Max positions per symbol
    
    # Daily limits
    max_daily_trades: int = 20           # Maximum trades per day
    max_daily_loss_pct: float = 3.0      # Stop trading if down 3%
    max_daily_loss_amount: float = 5000.0
    
    # Drawdown limits
    max_drawdown_pct: float = 10.0       # Stop if portfolio down 10%
    
    # Exposure limits
    max_sector_exposure_pct: float = 30.0  # Max 30% in one sector
    max_single_stock_pct: float = 25.0     # Max 25% in one stock


@dataclass
class TimeConfig:
    """
    Time-related configuration for intraday trading.
    """
    market_open: time = field(default_factory=lambda: time(9, 15))
    market_close: time = field(default_factory=lambda: time(15, 30))
    
    # Entry window
    entry_start_time: time = field(default_factory=lambda: time(9, 30))  # Start entering after 9:30
    entry_end_time: time = field(default_factory=lambda: time(15, 0))    # No entries after 3:00 PM
    
    # Auto square-off (MIS)
    auto_square_off_time: time = field(default_factory=lambda: time(15, 20))  # 3:20 PM
    
    # Avoid first/last N minutes
    skip_first_minutes: int = 15         # Skip first 15 minutes volatility
    skip_last_minutes: int = 10          # Skip last 10 minutes


@dataclass
class StopLossConfig:
    """
    Stop loss and target configuration.
    """
    # Initial stop loss
    initial_sl_pct: float = 1.0          # 1% initial SL
    use_atr_sl: bool = False             # Use ATR-based SL
    atr_sl_multiplier: float = 1.5       # SL = Entry - 1.5 * ATR
    
    # Trailing stop loss
    enable_trailing_sl: bool = True
    trailing_sl_activation_pct: float = 0.5  # Activate after 0.5% profit
    trailing_sl_distance_pct: float = 0.3    # Trail by 0.3%
    trailing_sl_step_pct: float = 0.1        # Move SL in 0.1% steps
    
    # Target
    initial_target_pct: float = 2.0      # 2% target
    use_rr_ratio: bool = True            # Use Risk:Reward ratio
    risk_reward_ratio: float = 2.0       # 1:2 RR ratio
    
    # Partial profit booking
    enable_partial_exit: bool = False
    partial_exit_pct: float = 50.0       # Exit 50% at first target
    first_target_pct: float = 1.0        # First target at 1%


@dataclass
class StrategyBacktestConfig:
    """
    Per-strategy backtest configuration.
    """
    strategy_id: str
    enabled: bool = True
    weight: float = 1.0                  # Weight for signal priority
    
    # Override global settings for this strategy
    sl_override: Optional[float] = None
    target_override: Optional[float] = None
    max_positions_override: Optional[int] = None


@dataclass
class BacktestConfig:
    """
    Master configuration for backtest run.
    
    Usage:
        config = BacktestConfig(
            initial_capital=100000,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            strategies=['vwap_breakout', 'bullish_flag']
        )
    """
    # Date range
    start_date: date = field(default_factory=lambda: date(2024, 1, 1))
    end_date: date = field(default_factory=lambda: date(2024, 12, 31))
    
    # Capital
    initial_capital: float = 100000.0
    
    # Strategies to run
    strategies: List[str] = field(default_factory=lambda: ['vwap_breakout'])
    strategy_configs: Dict[str, StrategyBacktestConfig] = field(default_factory=dict)
    
    # Universe
    universe_file: str = "data/universes/nifty500_stocks.csv"
    symbols: Optional[List[str]] = None  # Override universe with specific symbols
    
    # Data settings
    data_path: str = "data/historical"
    data_frequency: str = "1min"         # 1min, 5min, 15min
    
    # Sub-configs
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    time: TimeConfig = field(default_factory=TimeConfig)
    stop_loss: StopLossConfig = field(default_factory=StopLossConfig)
    
    # Logging & Output
    log_level: str = "INFO"
    save_trades: bool = True
    save_equity_curve: bool = True
    output_path: str = "backtest_results"
    
    # Advanced
    enable_shorting: bool = False        # Only long positions
    warmup_candles: int = 50             # Candles needed for indicators
    
    def __post_init__(self):
        """Validate and setup after initialization."""
        # Sync initial capital
        self.risk.initial_capital = self.initial_capital
        
        # Create strategy configs if not provided
        for strategy_id in self.strategies:
            if strategy_id not in self.strategy_configs:
                self.strategy_configs[strategy_id] = StrategyBacktestConfig(
                    strategy_id=strategy_id
                )
    
    def validate(self) -> bool:
        """Validate configuration."""
        errors = []
        
        if self.start_date >= self.end_date:
            errors.append("start_date must be before end_date")
        
        if self.initial_capital <= 0:
            errors.append("initial_capital must be positive")
        
        if not self.strategies:
            errors.append("At least one strategy must be specified")
        
        if self.risk.max_positions < 1:
            errors.append("max_positions must be at least 1")
        
        if self.risk.per_trade_capital_pct <= 0 or self.risk.per_trade_capital_pct > 1:
            errors.append("per_trade_capital_pct must be between 0 and 1")
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'initial_capital': self.initial_capital,
            'strategies': self.strategies,
            'data_frequency': self.data_frequency,
            'universe_file': self.universe_file,
            'max_positions': self.risk.max_positions,
            'per_trade_capital_pct': self.risk.per_trade_capital_pct,
            'fill_model': self.execution.fill_model.value,
            'slippage_pct': self.execution.slippage_pct,
        }
